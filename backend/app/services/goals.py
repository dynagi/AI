"""Financial goals: purchase, emergency fund, travel, education, custom.

Everything here is cash-flow arithmetic over the user's own ledger. There are no return assumptions and no
investment advice.

Pace
----
The monthly amount the user can realistically put towards goals is their recent *savings pace*:

  history_avg       = average (income - net spend) of their last <= 3 closed cycles
  current_projected = projected savings of the cycle in progress (so a spending spike THIS cycle lowers it)
  effective pace    = the lower of the two (whichever exist)

Goals compete for that pace. Active goals are funded in order of priority (HIGH first), then earliest target
date; a goal's *allocation* is what is left of the pace when its turn comes, capped at what it needs.

Status of an active goal:
  COMPLETED  current >= target
  ON_TRACK   allocation covers the required monthly amount
  AT_RISK    allocation covers at least 70% of it
  BEHIND     less than 70%, or the target date has passed
  None       there is no closed cycle yet to base a pace on (reason: insufficient_history)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional
from zoneinfo import ZoneInfo

import psycopg

from app.config import get_settings
from app.ledger import money
from app.services import queries
from app.services.cycle_state import as_of, savings_progress_for
from app.services.savings import inr, inr0

GOAL_TYPES = ("PURCHASE", "EMERGENCY_FUND", "TRAVEL", "EDUCATION", "CUSTOM")
PRIORITIES = ("LOW", "MEDIUM", "HIGH")
DAYS_PER_MONTH = Decimal("30.4375")
ZERO = Decimal("0.00")
_PRIORITY_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


class GoalNotFound(Exception):
    pass


class GoalError(ValueError):
    pass


# --------------------------------------------------------------------------- pace


@dataclass
class Pace:
    history_average: Optional[Decimal]  # None when there is no closed cycle with income yet
    history_cycles: int
    current_projected: Optional[Decimal]  # None when the active cycle has no income yet
    effective: Optional[Decimal]
    basis: str  # "history_and_current_cycle" | "history" | "current_cycle" | "none"

    def as_dict(self) -> dict:
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in self.__dict__.items()}


def combine_pace(history_savings: list[Decimal], current_projected: Optional[Decimal]) -> Pace:
    hist = sum(history_savings, ZERO) / len(history_savings) if history_savings else None
    hist = money(hist) if hist is not None else None
    if hist is not None and current_projected is not None:
        return Pace(hist, len(history_savings), current_projected, min(hist, current_projected), "history_and_current_cycle")
    if hist is not None:
        return Pace(hist, len(history_savings), None, hist, "history")
    if current_projected is not None:
        return Pace(None, 0, current_projected, current_projected, "current_cycle")
    return Pace(None, 0, None, None, "none")


def savings_pace(conn: psycopg.Connection, user_id: str, account_id: str) -> Pace:
    cycle = queries.active_cycle(conn, user_id, account_id)
    history: list[Decimal] = []
    current: Optional[Decimal] = None
    if cycle is not None:
        for h in queries.closed_cycles_before(conn, user_id, cycle, limit=3):
            if h["income_total"] > 0:
                history.append(h["income_total"] - (h["expense_total"] - h["refund_total"]))
        if cycle["income_total"] > 0:
            current = savings_progress_for(conn, user_id, cycle).projected_savings
    return combine_pace(history, current)


# ----------------------------------------------------------------------- analysis


def _months_between(days: int) -> Decimal:
    return Decimal(days) / DAYS_PER_MONTH


def analyze_goals(goals: list[dict], pace: Pace, today: date) -> dict:
    """Pure function: goal rows + pace + today -> analysis for each goal and for all goals together."""
    active = [g for g in goals if g["status"] == "ACTIVE"]
    order = sorted(
        (g for g in active if g["current_amount"] < g["target_amount"]),
        key=lambda g: (_PRIORITY_RANK[g["priority"]], g["target_date"], str(g["created_at"])),
    )

    def required_monthly(g: dict) -> Decimal:
        remaining = max(ZERO, g["target_amount"] - g["current_amount"])
        days = (g["target_date"] - today).days
        if days <= 0:
            return remaining
        months = _months_between(days)
        return money(remaining / months) if months > 0 else remaining

    available = pace.effective if (pace.effective is not None and pace.effective > 0) else ZERO
    left = available
    allocations: dict[str, Decimal] = {}
    taken_before: dict[str, Decimal] = {}  # what higher-priority goals already claimed
    for g in order:
        need = required_monthly(g)
        got = min(need, left)
        taken_before[str(g["id"])] = money(available - left)
        allocations[str(g["id"])] = money(got)
        left -= got

    total_required = sum((required_monthly(g) for g in order), ZERO)

    out = []
    for g in goals:
        gid = str(g["id"])
        target, current = g["target_amount"], g["current_amount"]
        remaining = max(ZERO, target - current)
        progress = float((current / target * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)) if target else 0.0
        days_left = (g["target_date"] - today).days
        req = required_monthly(g)
        a: dict[str, Any] = {
            "id": gid, "name": g["name"], "goal_type": g["goal_type"], "priority": g["priority"], "lifecycle": g["status"],
            "target_amount": target, "current_amount": current, "remaining_amount": remaining,
            "progress_percent": min(progress, 100.0), "target_date": g["target_date"], "days_remaining": days_left,
            "required_monthly_contribution": req if remaining > 0 else ZERO,
            "allocated_monthly_savings": allocations.get(gid),
            "available_monthly_savings": money(max(ZERO, available - taken_before.get(gid, ZERO))) if gid in allocations else None,
            "status": None, "reason": None,
            "projected_completion_date": None, "message": "",
        }
        if current >= target:
            a.update(status="COMPLETED", message=f"{g['name']} is fully funded ({inr(current)} of {inr(target)}).")
        elif g["status"] == "PAUSED":
            a.update(status="PAUSED", message=f"{g['name']} is paused, so it is not part of your savings-pace analysis.")
        elif g["status"] == "COMPLETED":
            a.update(status="COMPLETED", message=f"{g['name']} was marked complete.")
        elif pace.effective is None:
            a.update(reason="insufficient_history", message=(
                f"There is not enough cycle history yet to estimate your monthly savings, so progress towards "
                f"{g['name']} cannot be projected. It needs about {inr0(req)} per month."))
        else:
            alloc = allocations.get(gid, ZERO)
            if days_left <= 0:
                status = "BEHIND"
            elif alloc >= req:
                status = "ON_TRACK"
            elif req > 0 and alloc >= req * Decimal("0.7"):
                status = "AT_RISK"
            else:
                status = "BEHIND"
            a["status"] = status
            avail_to = a["available_monthly_savings"] or ZERO
            if avail_to > 0:  # project from the savings actually available to this goal, not the capped requirement
                months = remaining / avail_to
                a["projected_completion_date"] = today + timedelta(days=int(months * DAYS_PER_MONTH) + 1)
            note = " after your higher-priority goals" if (status != "ON_TRACK" and taken_before.get(gid, ZERO) > 0) else ""
            if pace.effective <= 0:
                a["message"] = (
                    f"Based on your recent spending, this cycle is on course to save nothing (projected "
                    f"{inr0(pace.effective)}), so no monthly savings are available for {g['name']}, which needs about "
                    f"{inr0(req)} per month. At the current pace, the goal may not be reached by {g['target_date']:%d %b %Y}."
                )
            elif status == "ON_TRACK":
                when = a["projected_completion_date"]
                a["message"] = (
                    f"Based on your transaction history, you are saving about {inr0(pace.effective)} per month and "
                    f"{g['name']} needs about {inr0(req)} per month, so it is on track"
                    + (f" (projected completion around {when:%d %b %Y})." if when else "."))
            else:
                a["message"] = (
                    f"Based on your recent spending you are saving approximately {inr0(pace.effective)} per month, and "
                    f"{inr0(avail_to)} of that is available for {g['name']}{note}, while the goal requires approximately "
                    f"{inr0(req)} per month. At the current pace, the goal may not be reached by "
                    f"{g['target_date']:%d %b %Y}.")
        out.append(a)

    return {
        "goals": out,
        "combined": {
            "active_goals": len(order),
            "total_required_monthly": money(total_required),
            "savings_pace_monthly": pace.effective,
            "unallocated_monthly_savings": money(left) if pace.effective is not None else None,
            "pace": pace.as_dict(),
        },
    }


# ---------------------------------------------------------------------------- CRUD


def _today(conn: psycopg.Connection, user_id: str, account_id: Optional[str]) -> date:
    tz = ZoneInfo(get_settings().app_timezone)
    if account_id:
        return as_of(conn, user_id, account_id).astimezone(tz).date()
    return datetime.now(tz).date()


def list_goals(conn: psycopg.Connection, user_id: str) -> list[dict]:
    return conn.execute(
        "select * from financial_goals where user_id = %s order by (status = 'COMPLETED'), created_at", (user_id,)
    ).fetchall()


def get_goal(conn: psycopg.Connection, user_id: str, goal_id: str) -> dict:
    try:
        row = conn.execute("select * from financial_goals where id = %s and user_id = %s", (goal_id, user_id)).fetchone()
    except psycopg.errors.InvalidTextRepresentation:
        conn.rollback()
        row = None
    if row is None:
        raise GoalNotFound(goal_id)
    return row


def create_goal(
    conn: psycopg.Connection, user_id: str, *, name: str, goal_type: str, target_amount: Decimal,
    current_amount: Decimal, target_date: date, priority: str = "MEDIUM",
) -> dict:
    if goal_type not in GOAL_TYPES:
        raise GoalError(f"goal_type must be one of {list(GOAL_TYPES)}")
    if priority not in PRIORITIES:
        raise GoalError(f"priority must be one of {list(PRIORITIES)}")
    if current_amount < 0 or target_amount <= 0:
        raise GoalError("target must be positive and the current amount cannot be negative")
    status = "COMPLETED" if current_amount >= target_amount else "ACTIVE"
    return conn.execute(
        """
        insert into financial_goals (user_id, name, goal_type, target_amount, current_amount, target_date, priority, status, completed_at)
        values (%s, %s, %s, %s, %s, %s, %s, %s, case when %s = 'COMPLETED' then now() end) returning *
        """,
        (user_id, name.strip(), goal_type, target_amount, current_amount, target_date, priority, status, status),
    ).fetchone()


def update_goal(conn: psycopg.Connection, user_id: str, goal_id: str, changes: dict) -> dict:
    goal = get_goal(conn, user_id, goal_id)
    allowed = {"name", "goal_type", "target_amount", "target_date", "priority", "status"}
    fields = {k: v for k, v in changes.items() if k in allowed and v is not None}
    if "goal_type" in fields and fields["goal_type"] not in GOAL_TYPES:
        raise GoalError(f"goal_type must be one of {list(GOAL_TYPES)}")
    if "priority" in fields and fields["priority"] not in PRIORITIES:
        raise GoalError(f"priority must be one of {list(PRIORITIES)}")
    if "status" in fields and fields["status"] not in ("ACTIVE", "PAUSED", "COMPLETED"):
        raise GoalError("status must be ACTIVE, PAUSED or COMPLETED")
    if "target_amount" in fields and fields["target_amount"] <= 0:
        raise GoalError("target must be positive")
    if "name" in fields:
        fields["name"] = fields["name"].strip()
        if not fields["name"]:
            raise GoalError("name cannot be empty")
    if not fields:
        return goal
    sets = ", ".join(f"{k} = %s" for k in fields)
    params = list(fields.values())
    extra = ""
    if fields.get("status") == "COMPLETED":
        extra = ", completed_at = now()"
    elif fields.get("status") in ("ACTIVE", "PAUSED"):
        extra = ", completed_at = null"
    return conn.execute(
        f"update financial_goals set {sets}{extra} where id = %s and user_id = %s returning *", (*params, goal_id, user_id)
    ).fetchone()


def add_contribution(
    conn: psycopg.Connection, user_id: str, goal_id: str, amount: Decimal, notes: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> tuple[dict, dict]:
    """Add money to a goal. Raises the goal's current_amount; never touches the ledger or expense totals."""
    if amount <= 0:
        raise GoalError("A contribution must be greater than zero.")
    goal = conn.execute(
        "select * from financial_goals where id = %s and user_id = %s for update", (goal_id, user_id)
    ).fetchone()
    if goal is None:
        raise GoalNotFound(goal_id)
    contribution = conn.execute(
        """insert into goal_contributions (goal_id, user_id, amount, "timestamp", source, notes)
           values (%s, %s, %s, coalesce(%s, now()), 'manual', %s) returning *""",
        (goal_id, user_id, amount, timestamp, notes),
    ).fetchone()
    new_current = goal["current_amount"] + amount
    completed = new_current >= goal["target_amount"]
    updated = conn.execute(
        """update financial_goals set current_amount = %s,
             status = case when %s then 'COMPLETED' else status end,
             completed_at = case when %s and completed_at is null then now() else completed_at end
           where id = %s and user_id = %s returning *""",
        (new_current, completed, completed, goal_id, user_id),
    ).fetchone()
    return contribution, updated


def contributions_for(conn: psycopg.Connection, user_id: str, goal_id: str, limit: int = 50) -> list[dict]:
    return conn.execute(
        """select id, amount, "timestamp", source, notes from goal_contributions
           where goal_id = %s and user_id = %s order by "timestamp" desc limit %s""",
        (goal_id, user_id, limit),
    ).fetchall()


def goals_overview(conn: psycopg.Connection, user_id: str, account_id: Optional[str]) -> dict:
    goals = list_goals(conn, user_id)
    if account_id:
        pace = savings_pace(conn, user_id, account_id)
    else:
        pace = Pace(None, 0, None, None, "none")
    return analyze_goals(goals, pace, _today(conn, user_id, account_id))
