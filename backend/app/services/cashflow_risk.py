"""Upcoming financial commitments & cash-flow warning. Deterministic, read-only, grounded in the ledger.

    balance now + expected income - upcoming recurring payments  ->  simple timeline  ->  one risk level

Inputs (all already stored by FinPilot; nothing is invented):
  * current balance                       accounts.current_balance
  * upcoming payments                     recurring_payments (detected from real history), due within the horizon
  * expected income                       the next salary, expected one average cycle length after the current
                                          cycle's salary (only when the cycle was started by a salary)
  * savings target / spending so far      the active cycle and the user's savings target
  * remaining budget                      planned spend limit (income - target), else the sum of category budgets
  * safety buffer                         settings.safety_buffer (a floor the user wants to stay above)

Risk levels, worst first:
  SHORTFALL  the balance would go below zero at some point before the last upcoming payment
  AT_RISK    covered, but the payments would push the savings target or the planned spending limit out of reach
  WATCH      covered, but the balance would drop below the safety buffer
  SAFE       covered and above the buffer

FinPilot only reports. It never pays, cancels, transfers or edits anything.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

import psycopg

from app.config import get_settings
from app.ledger import money
from app.services import queries
from app.services.budgets import INTERVAL_DAYS, STALE_AFTER_DAYS, expected_cycle_end
from app.services.cycle_state import as_of, savings_progress_for
from app.services.recurring import list_recurring
from app.services.savings import inr

ZERO = Decimal("0.00")
DEFAULT_HORIZON_DAYS = 30
TIGHT_SAVINGS_MARGIN = Decimal("0.10")  # savings left within 10% of the target after the payments = "difficult to reach"
TIGHT_SPEND_RATIO = Decimal("0.90")  # spending + payments above 90% of the planned limit = "close to exceeding it"

HIGH_PRIORITY = ("housing", "rent", "utilit", "insurance", "loan", "emi", "health", "education", "electric", "mobile")
LOW_PRIORITY = ("subscription", "entertainment", "shopping", "dining", "streaming")


def priority_for(category: Optional[str]) -> str:
    c = (category or "").lower()
    if any(k in c for k in HIGH_PRIORITY):
        return "high"
    if any(k in c for k in LOW_PRIORITY):
        return "low"
    return "medium"


def _day(dt: datetime, tz: ZoneInfo) -> str:
    local = dt.astimezone(tz)
    return f"{local:%b} {local.day}"


def _days_until(due: datetime, now: datetime, tz: ZoneInfo) -> int:
    return (due.astimezone(tz).date() - now.astimezone(tz).date()).days


def _in_days(n: int) -> str:
    return "today" if n <= 0 else "tomorrow" if n == 1 else f"in {n} days"


# --------------------------------------------------------------------- inputs

def upcoming_payments(conn: psycopg.Connection, user_id: str, now: datetime, horizon_days: int, tz: ZoneInfo) -> list[dict]:
    """Every expected recurring payment due within the horizon (a weekly payment can appear several times)."""
    horizon = now + timedelta(days=horizon_days)
    out: list[dict] = []
    for r in list_recurring(conn, user_id):
        step = INTERVAL_DAYS.get(r["frequency"])
        due = r["next_expected_payment"]
        if not step or due < now - timedelta(days=STALE_AFTER_DAYS):
            continue  # not a known cadence, or so overdue it is probably no longer happening
        while due <= horizon:
            out.append({
                "merchant": r["merchant"], "category": r["category"], "amount": money(r["average_amount"]),
                "due_at": due, "due_label": _day(due, tz), "days_remaining": max(0, _days_until(due, now, tz)),
                "priority": priority_for(r["category"]), "frequency": r["frequency"],
            })
            due = due + timedelta(days=step)
    return sorted(out, key=lambda p: p["due_at"])


def expected_income(conn: psycopg.Connection, user_id: str, cycle: Optional[dict], now: datetime, horizon_days: int, tz: ZoneInfo) -> list[dict]:
    """The next salary: one average cycle length after the current cycle began, for the amount that started it."""
    if cycle is None or cycle["salary_transaction_id"] is None:
        return []
    salary = conn.execute(
        "select amount from transactions where id = %s and user_id = %s", (cycle["salary_transaction_id"], user_id)
    ).fetchone()
    when = expected_cycle_end(conn, user_id, cycle)
    if salary is None or not (now - timedelta(days=STALE_AFTER_DAYS) <= when <= now + timedelta(days=horizon_days)):
        return []
    return [{"label": "Salary", "amount": money(salary["amount"]), "date": when, "date_label": _day(when, tz),
             "days_remaining": max(0, _days_until(when, now, tz))}]


# ------------------------------------------------------------------ the check

def assess(
    *,
    now: datetime,
    balance: Decimal,
    payments: list[dict],
    incomes: list[dict],
    buffer: Decimal,
    savings: Optional[dict],
    spending: Optional[dict],
    cycle_end: Optional[datetime],
    tz: ZoneInfo,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
) -> dict:
    """Pure: everything is passed in, so the same inputs always give the same warning."""
    if not payments:
        return _result(
            risk_level="SAFE", balance=balance, upcoming_total=ZERO, income_total=ZERO, projected=balance, lowest=balance,
            shortfall=ZERO, buffer=buffer, payments=[], incomes=[], timeline=[], now=now, horizon_days=horizon_days,
            savings_impact=_savings_none(), budget_impact=_budget_none(),
            headline="Nothing due soon",
            warning_message=f"No recurring payments are expected in the next {horizon_days} days.",
            suggested_action=None, covered_by_income=False,
        )

    upcoming_total = sum((p["amount"] for p in payments), ZERO)
    # Income counts only up to the last payment: money that arrives afterwards cannot cover it.
    last_due = payments[-1]["due_at"]
    incomes = [i for i in incomes if i["date"] <= last_due]
    income_total = sum((i["amount"] for i in incomes), ZERO)

    # Walk the timeline in date order (income first on the same day) and track the running balance.
    events = [("income", i["date"], i["amount"], i["label"], i) for i in incomes] + \
             [("payment", p["due_at"], -p["amount"], p["merchant"], p) for p in payments]
    events.sort(key=lambda e: (e[1], 0 if e[0] == "income" else 1))
    running, lowest = balance, balance
    timeline = [{"kind": "start", "date": now, "date_label": "Today", "label": "Balance now", "amount": None,
                 "balance_after": balance, "shortfall": False}]
    first_short: Optional[dict] = None
    for kind, when, delta, label, src in events:
        running += delta
        lowest = min(lowest, running)
        short = kind == "payment" and running < 0
        if kind == "payment":
            src["balance_after"] = running
            src["shortfall"] = short
            if short and first_short is None:
                first_short = {**src, "balance_before": running - delta}
        timeline.append({"kind": kind, "date": when, "date_label": _day(when, tz), "label": label, "amount": delta,
                         "balance_after": running, "shortfall": short})
    shortfall = -lowest if lowest < 0 else ZERO

    # Income is what makes the payments affordable when the balance alone would not cover them.
    covered_by_income = bool(incomes) and balance - upcoming_total < 0 and lowest >= 0

    in_cycle = sum((p["amount"] for p in payments if cycle_end is None or p["due_at"] <= cycle_end), ZERO)
    savings_impact = _savings_impact(savings, in_cycle)
    budget_impact = _budget_impact(spending, in_cycle, cycle_end, now)

    if lowest < 0:
        level = "SHORTFALL"
    elif savings_impact["at_risk"] or budget_impact["at_risk"]:
        level = "AT_RISK"
    elif lowest < buffer:
        level = "WATCH"
    else:
        level = "SAFE"

    headline, message, action = _explain(
        level, now=now, balance=balance, payments=payments, incomes=incomes, first_short=first_short, shortfall=shortfall,
        lowest=lowest, buffer=buffer, covered_by_income=covered_by_income, savings_impact=savings_impact,
        budget_impact=budget_impact, upcoming_total=upcoming_total,
    )
    return _result(
        risk_level=level, balance=balance, upcoming_total=upcoming_total, income_total=income_total, projected=running,
        lowest=lowest, shortfall=shortfall, buffer=buffer, payments=payments, incomes=incomes, timeline=timeline, now=now,
        horizon_days=horizon_days, savings_impact=savings_impact, budget_impact=budget_impact, headline=headline,
        warning_message=message, suggested_action=action, covered_by_income=covered_by_income,
    )


def _savings_none() -> dict:
    return {"status": "NO_TARGET", "at_risk": False, "target": None, "message": "No savings target is set for this cycle."}


def _savings_impact(savings: Optional[dict], due_this_cycle: Decimal) -> dict:
    if not savings or savings.get("target") is None or not savings.get("income"):
        return _savings_none()
    target, now_savings = savings["target"], savings["estimated_savings"]
    after = now_savings - due_this_cycle
    margin = after - target
    base = {"target": target, "savings_now": now_savings, "savings_after": after, "upcoming": due_this_cycle}
    if due_this_cycle <= 0:
        return {**base, "status": "UNAFFECTED", "at_risk": False,
                "message": "No upcoming payment falls inside this cycle, so your savings target is unaffected."}
    if margin < 0:
        return {**base, "status": "OFF_TARGET", "at_risk": True,
                "message": f"These upcoming payments ({inr(due_this_cycle)}) would leave about {inr(after)} of this cycle's "
                           f"income, {inr(-margin)} short of your {inr(target)} savings target."}
    if margin < target * TIGHT_SAVINGS_MARGIN:
        return {**base, "status": "TIGHT", "at_risk": True,
                "message": f"This upcoming {inr(due_this_cycle)} may reduce the amount available toward your {inr(target)} "
                           f"savings target. Only {inr(margin)} of room would remain."}
    return {**base, "status": "OK", "at_risk": False,
            "message": f"Your {inr(target)} savings target still looks reachable after these payments ({inr(margin)} of room)."}


def _budget_none() -> dict:
    return {"status": "NO_LIMIT", "at_risk": False, "message": "No planned spending limit is set (no savings target or category budgets)."}


def _budget_impact(spending: Optional[dict], due_this_cycle: Decimal, cycle_end: Optional[datetime], now: datetime) -> dict:
    if not spending or not spending.get("limit"):
        return _budget_none()
    limit, spent = spending["limit"], spending["spent"]
    after = spent + due_this_cycle
    days_left = max(0, int((cycle_end - now).total_seconds() // 86400)) if cycle_end else None
    base = {"planned_spend": limit, "spent": spent, "upcoming": due_this_cycle, "after_upcoming": after,
            "remaining": limit - after, "days_left": days_left, "basis": spending["basis"]}
    left = f", with about {days_left} days left in the cycle" if days_left is not None else ""
    if due_this_cycle <= 0:
        return {**base, "status": "UNAFFECTED", "at_risk": False, "message": "No upcoming payment falls inside this cycle."}
    if after > limit:
        return {**base, "status": "OVER", "at_risk": True,
                "message": f"You have spent {inr(spent)} of your {inr(limit)} planned spending. With {inr(due_this_cycle)} "
                           f"still due, you would exceed it by {inr(after - limit)}{left}."}
    if after > limit * TIGHT_SPEND_RATIO:
        return {**base, "status": "TIGHT", "at_risk": True,
                "message": f"You have spent {inr(spent)} of your {inr(limit)} planned spending. With {inr(due_this_cycle)} "
                           f"still due, only {inr(limit - after)} would be left{left}."}
    return {**base, "status": "OK", "at_risk": False,
            "message": f"Spending plus upcoming payments ({inr(after)}) stays within your {inr(limit)} plan."}


def _explain(level, *, now, balance, payments, incomes, first_short, shortfall, lowest, buffer, covered_by_income,
             savings_impact, budget_impact, upcoming_total):
    if level == "SHORTFALL":
        p = first_short
        earlier = "" if p["balance_before"] == balance else " (after earlier income and payments)"
        no_income = "" if incomes else " No income is expected before then."
        msg = (f"Your {inr(p['amount'])} {p['merchant']} payment is due on {p['due_label']} ({_in_days(p['days_remaining'])}), "
               f"but your available balance would be {inr(p['balance_before'])}{earlier}. "
               f"Potential shortfall: {inr(shortfall)}.{no_income}")
        action = ("Consider adding funds before the due date or reviewing the subscription." if p["priority"] == "low"
                  else "Consider adding funds before the due date.")
        return "Upcoming payment may exceed your available balance", msg, action
    if level == "AT_RISK":
        parts = [i["message"] for i in (savings_impact, budget_impact) if i["at_risk"]]
        headline = "Savings goal at risk" if savings_impact["at_risk"] else "Planned spending at risk"
        return headline, " ".join(parts), "Consider which of these payments could wait, or whether your target still fits."
    if level == "WATCH":
        if covered_by_income:
            msg = (f"Your expected income should cover the payments, but your balance would drop to {inr(lowest)}, "
                   f"below your {inr(buffer)} safety buffer.")
        else:
            msg = (f"The payments appear affordable, but they would leave your projected balance at {inr(lowest)}, "
                   f"below your {inr(buffer)} safety buffer.")
        return "Low balance buffer", msg, None
    if covered_by_income:
        inc = incomes[0]
        return "Upcoming payment covered", (
            f"Your expected income on {inc['date_label']} should cover the {inr(upcoming_total)} "
            f"due by {payments[-1]['due_label']}."), None
    return "Upcoming payments covered", (
        f"You have {inr(balance)} available and {inr(upcoming_total)} due by {payments[-1]['due_label']}. "
        f"You stay above your {inr(buffer)} safety buffer."), None


def _result(*, risk_level, balance, upcoming_total, income_total, projected, lowest, shortfall, buffer, payments, incomes,
            timeline, now, horizon_days, savings_impact, budget_impact, headline, warning_message, suggested_action,
            covered_by_income) -> dict:
    keys = ("merchant", "category", "amount", "due_at", "due_label", "days_remaining", "priority", "frequency")
    return {
        "risk_level": risk_level,
        "headline": headline,
        "warning_message": warning_message,
        "suggested_action": suggested_action,
        "current_balance": balance,
        "upcoming_amount": upcoming_total,
        "expected_income": income_total,
        "projected_balance": projected,
        "lowest_balance": lowest,
        "shortfall_amount": shortfall,
        "safety_buffer": buffer,
        "covered_by_income": covered_by_income,
        "savings_impact": savings_impact,
        "budget_impact": budget_impact,
        "upcoming_payments": [
            {**{k: p[k] for k in keys}, "balance_after": p.get("balance_after"), "shortfall": p.get("shortfall", False)}
            for p in payments
        ],
        "expected_income_items": incomes,
        "timeline": timeline,
        "horizon_days": horizon_days,
        "as_of": now,
        "note": "Read-only warning. FinPilot never makes payments, cancels subscriptions or moves money.",
    }


# ------------------------------------------------------------------ DB wrapper

def check_upcoming_financial_risk(
    conn: psycopg.Connection, user_id: str, account_id: str,
    horizon_days: int = DEFAULT_HORIZON_DAYS, safety_buffer: Optional[Decimal] = None,
    extra_payments: Optional[list[dict]] = None,
) -> dict:
    """`extra_payments` are hypothetical one-off payments (What-if). They are never stored."""
    settings = get_settings()
    tz = ZoneInfo(settings.app_timezone)
    account = queries.get_account(conn, user_id, account_id)
    now = as_of(conn, user_id, account_id)
    buffer = money(safety_buffer if safety_buffer is not None else Decimal(str(settings.safety_buffer)))
    cycle = queries.active_cycle(conn, user_id, account_id)

    savings = spending = cycle_end = None
    if cycle is not None:
        cycle_end = expected_cycle_end(conn, user_id, cycle)
        progress = savings_progress_for(conn, user_id, cycle)
        savings = {"target": progress.target, "income": progress.income, "estimated_savings": progress.estimated_savings}
        if progress.planned_spend_limit is not None:
            spending = {"limit": progress.planned_spend_limit, "spent": progress.net_spend, "basis": "income minus savings target"}
        else:
            total = sum((b["amount"] for b in queries.budgets_for(conn, user_id)), ZERO)
            if total > 0:
                spending = {"limit": total, "spent": progress.net_spend, "basis": "sum of category budgets"}

    return assess(
        now=now, balance=account["current_balance"],
        payments=sorted(upcoming_payments(conn, user_id, now, horizon_days, tz) + [dict(x) for x in extra_payments or []],
                        key=lambda x: x["due_at"]),
        incomes=expected_income(conn, user_id, cycle, now, horizon_days, tz),
        buffer=buffer, savings=savings, spending=spending, cycle_end=cycle_end, tz=tz, horizon_days=horizon_days,
    )
