"""Proactive alerts, raised while the cycle is running (never only at month end).

Every alert is computed from ledger data and carries the numbers and transaction
ids it was computed from in `evidence`. Language is descriptive, never a moral
judgement ("significantly above your recent average", not "you shouldn't").
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

import psycopg

from app.config import get_settings
from app.services import queries
from app.services.budgets import budget_status
from app.services.cycle_state import as_of, cycle_label, savings_progress_for
from app.services.goals import goals_overview
from app.services.ledger_service import InsertedTxn
from app.services.savings import inr, inr0

INTERACTIVE_MAX_ROWS = 25  # bulk imports (CSV / demo bank connect) do not replay "new event" alerts
HIGH_SPEND_MULTIPLE = Decimal("3")
HIGH_SPEND_FLOOR = Decimal("2000")
HISTORY_DAYS = 30
MIN_HISTORY_DAYS = 14
LARGE_TXN_FLOOR = Decimal("5000")
LARGE_TXN_MULTIPLE = Decimal("8")


def upsert_alert(
    conn: psycopg.Connection, user_id: str, *, alert_type: str, severity: str, title: str, message: str,
    dedupe_key: str, evidence: dict, cycle_id: Optional[str] = None, transaction_id: Optional[str] = None,
) -> dict:
    return conn.execute(
        """
        insert into agent_alerts
          (user_id, financial_cycle_id, transaction_id, alert_type, severity, title, message, evidence, dedupe_key)
        values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
        on conflict (user_id, dedupe_key) do update set
          severity = excluded.severity, title = excluded.title, message = excluded.message,
          evidence = excluded.evidence, transaction_id = coalesce(excluded.transaction_id, agent_alerts.transaction_id)
        returning *
        """,
        (user_id, cycle_id, transaction_id, alert_type, severity, title, message, json.dumps(evidence, default=str), dedupe_key),
    ).fetchone()


def _local_day_bounds(ts: datetime, tz: ZoneInfo) -> tuple[datetime, datetime]:
    local = ts.astimezone(tz)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def average_daily_spend(conn: psycopg.Connection, user_id: str, account_id: str, day_start: datetime) -> Optional[Decimal]:
    """Average EXPENSE per calendar day over the 30 days before `day_start`. None if there is too little history."""
    first = conn.execute(
        'select min("timestamp") as ts from transactions where user_id = %s and account_id = %s', (user_id, account_id)
    ).fetchone()["ts"]
    if first is None or first > day_start - timedelta(days=MIN_HISTORY_DAYS):
        return None
    total = conn.execute(
        """
        select coalesce(sum(amount), 0) as total from transactions
        where user_id = %s and account_id = %s and transaction_type = 'EXPENSE'
          and "timestamp" >= %s and "timestamp" < %s
        """,
        (user_id, account_id, day_start - timedelta(days=HISTORY_DAYS), day_start),
    ).fetchone()["total"]
    return (total / HISTORY_DAYS).quantize(Decimal("0.01"))


def evaluate_alerts(
    conn: psycopg.Connection, user_id: str, account_id: str, *, inserted: list[InsertedTxn], new_cycle_ids: list[str]
) -> list[dict]:
    settings = get_settings()
    tz = ZoneInfo(settings.app_timezone)
    cycle = queries.active_cycle(conn, user_id, account_id)
    if cycle is None:
        return []
    cycle_id = str(cycle["id"])
    interactive = len(inserted) <= INTERACTIVE_MAX_ROWS
    now = as_of(conn, user_id, account_id)
    raised: list[dict] = []

    def raise_(**kw):
        raised.append(upsert_alert(conn, user_id, cycle_id=cycle_id, **kw))

    prev = queries.previous_cycle(conn, user_id, cycle)

    # --- New financial cycle (a SALARY arrived and opened the active cycle)
    if interactive and cycle_id in new_cycle_ids and cycle["salary_transaction_id"]:
        salary_txn = next((t for t in inserted if str(t.id) == str(cycle["salary_transaction_id"])), None)
        if salary_txn:
            local = salary_txn.timestamp.astimezone(tz)
            prev_text = (
                f" The previous cycle ({cycle_label(prev, tz)}, {inr(prev['expense_total'])} spent) is closed and kept in your history."
                if prev else ""
            )
            raise_(
                alert_type="NEW_CYCLE", severity="info", title="New financial cycle started",
                message=f"Your salary of {inr(salary_txn.amount)} arrived at {local:%I:%M %p} on {local:%d %b %Y}. "
                        f"A new cycle has begun and its expense counter is back to zero.{prev_text}",
                dedupe_key=f"new_cycle:{cycle_id}", transaction_id=str(salary_txn.id),
                evidence={"salary_transaction_id": str(salary_txn.id), "salary": str(salary_txn.amount),
                          "opening_balance": str(cycle["opening_balance"]),
                          "carried_over_balance": str(cycle["carried_over_balance"])},
            )
            raise_(
                alert_type="SAVINGS_TARGET_NEEDED", severity="info", title="Set your savings target for this cycle",
                message="How much do you want to save this cycle? FinPilot will track your spending against it.",
                dedupe_key=f"set_target:{cycle_id}", evidence={"cycle_id": cycle_id},
            )

    # --- Event alerts for the transactions that just arrived
    in_cycle_ids = []
    if inserted:
        in_cycle_ids = [
            str(r["id"]) for r in conn.execute(
                "select id from transactions where user_id = %s and financial_cycle_id = %s and id = any(%s::uuid[]) and transaction_type = 'EXPENSE'",
                (user_id, cycle_id, [t.id for t in inserted]),
            ).fetchall()
        ]
    triggers = [t for t in inserted if str(t.id) in in_cycle_ids]

    if triggers:
        # High single-day spending, judged for the most recent day among the triggers.
        latest = max(triggers, key=lambda t: t.timestamp)
        day_start, day_end = _local_day_bounds(latest.timestamp, tz)
        avg = average_daily_spend(conn, user_id, account_id, day_start)
        day_rows = conn.execute(
            """
            select id, amount, merchant, description from transactions
            where user_id = %s and account_id = %s and transaction_type = 'EXPENSE' and not is_recurring
              and "timestamp" >= %s and "timestamp" < %s
            """,
            (user_id, account_id, day_start, day_end),
        ).fetchall()
        day_total = sum((r["amount"] for r in day_rows), Decimal("0"))
        if avg is not None and avg > 0 and day_total >= HIGH_SPEND_MULTIPLE * avg and day_total >= HIGH_SPEND_FLOOR:
            local_day = day_start.date()
            when = "today" if local_day == now.astimezone(tz).date() else f"on {local_day:%d %b}"
            raise_(
                alert_type="HIGH_SPENDING", severity="warning", title="⚠️ High spending detected",
                message=f"You spent {inr(day_total)} {when}, which is significantly above your recent daily spending "
                        f"average of {inr0(avg)}.",
                dedupe_key=f"high_spend:{account_id}:{local_day.isoformat()}", transaction_id=str(latest.id),
                evidence={"day": local_day.isoformat(), "day_total": str(day_total), "average_daily_spend": str(avg),
                          "window_days": HISTORY_DAYS, "transaction_ids": [str(r["id"]) for r in day_rows]},
            )

        # Unusually large single transactions.
        amounts = [r["amount"] for r in conn.execute(
            "select amount from transactions where user_id = %s and account_id = %s and transaction_type = 'EXPENSE'",
            (user_id, account_id)).fetchall()]
        if len(amounts) >= 10:
            median = Decimal(str(statistics.median(float(a) for a in amounts)))
            threshold = max(LARGE_TXN_FLOOR, LARGE_TXN_MULTIPLE * median)
            for t in sorted(triggers, key=lambda x: -x.amount)[:3]:
                if t.amount >= threshold:
                    row = conn.execute("select merchant, description from transactions where id = %s and user_id = %s", (t.id, user_id)).fetchone()
                    who = row["merchant"] or row["description"]
                    raise_(
                        alert_type="LARGE_TRANSACTION", severity="warning", title="Large transaction detected",
                        message=f"A transaction of {inr(t.amount)} at {who} is much larger than your typical transaction "
                                f"(median {inr0(median)}).",
                        dedupe_key=f"large_txn:{t.id}", transaction_id=str(t.id),
                        evidence={"transaction_id": str(t.id), "amount": str(t.amount), "median_expense": str(median), "threshold": str(threshold)},
                    )

    # --- State alerts (cheap, de-duplicated)
    progress = savings_progress_for(conn, user_id, cycle)
    if progress.status == "AT_RISK":
        raise_(
            alert_type="SAVINGS_AT_RISK",
            severity="critical" if progress.reason == "limit_exceeded" else "warning",
            title="⚠️ Savings goal at risk", message=progress.message,
            dedupe_key=f"savings_risk:{cycle_id}",
            evidence={k: (str(v) if isinstance(v, Decimal) else v) for k, v in progress.__dict__.items() if k != "message"},
        )

    if prev and prev["expense_total"] > 0:
        ratio = cycle["expense_total"] / prev["expense_total"]
        if ratio >= 1:
            over = cycle["expense_total"] - prev["expense_total"]
            raise_(
                alert_type="PREVIOUS_CYCLE_THRESHOLD", severity="warning", title="Spending passed last cycle's total",
                message=f"You have exceeded last cycle's total by {inr(over)}.",
                dedupe_key=f"prev_cycle:{cycle_id}:100",
                evidence={"current_expenses": str(cycle["expense_total"]), "previous_expenses": str(prev["expense_total"]), "previous_cycle_id": str(prev["id"])},
            )
        elif ratio >= Decimal("0.8"):
            raise_(
                alert_type="PREVIOUS_CYCLE_THRESHOLD", severity="info", title="Approaching last cycle's total",
                message=f"You have reached {int(ratio * 100)}% of last cycle's total expenses "
                        f"({inr(cycle['expense_total'])} of {inr(prev['expense_total'])}).",
                dedupe_key=f"prev_cycle:{cycle_id}:80",
                evidence={"current_expenses": str(cycle["expense_total"]), "previous_expenses": str(prev["expense_total"]), "previous_cycle_id": str(prev["id"])},
            )

    history = queries.closed_cycles_before(conn, user_id, cycle, limit=3)
    history_ids = [str(h["id"]) for h in history]
    if len(history_ids) >= 2:
        for cat in queries.category_breakdown(conn, user_id, cycle_id):
            past = queries.category_history(conn, user_id, cat["category"], history_ids)
            if sum(1 for p in past if p > 0) < 2:
                continue
            avg_cat = sum(past, Decimal("0")) / len(past)
            if avg_cat > 0 and cat["total"] >= Decimal("1.5") * avg_cat and cat["total"] - avg_cat >= 1000:
                pct = int(((cat["total"] - avg_cat) / avg_cat * 100).to_integral_value())
                ids = [str(r["id"]) for r in conn.execute(
                    "select id from transactions where user_id = %s and financial_cycle_id = %s and category = %s and transaction_type = 'EXPENSE' order by amount desc limit 3",
                    (user_id, cycle_id, cat["category"])).fetchall()]
                raise_(
                    alert_type="CATEGORY_SPIKE", severity="warning", title=f"{cat['category']} spending is above average",
                    message=f"{cat['category']} spending is {pct}% higher than your recent average "
                            f"({inr(cat['total'])} this cycle vs {inr0(avg_cat)} average over your last {len(past)} cycles).",
                    dedupe_key=f"category_spike:{cycle_id}:{cat['category']}",
                    evidence={"category": cat["category"], "current": str(cat["total"]), "average": str(avg_cat),
                              "history": [str(p) for p in past], "top_transaction_ids": ids},
                )

    for b in budget_status(conn, user_id, account_id):
        if b["percent_used"] >= 80:
            level = 100 if b["percent_used"] >= 100 else 80
            raise_(
                alert_type="BUDGET_THRESHOLD", severity="warning" if level == 100 else "info",
                title=f"{b['category']} budget",
                message=f"{b['category']} spending has reached {int(b['percent_used'])}% of the {inr(b['amount'])} budget "
                        f"for this cycle.",
                dedupe_key=f"budget:{cycle_id}:{b['category']}:{level}",
                evidence={"category": b["category"], "spent": str(b["spent"]), "budget": str(b["amount"])},
            )

    # --- Goals that the current savings pace no longer supports
    for g in goals_overview(conn, user_id, account_id)["goals"]:
        if g["lifecycle"] == "ACTIVE" and g["status"] in ("AT_RISK", "BEHIND"):
            raise_(
                alert_type="GOAL_AT_RISK", severity="critical" if g["status"] == "BEHIND" else "warning",
                title=f"⚠️ {g['name']} goal {'is behind' if g['status'] == 'BEHIND' else 'at risk'}", message=g["message"],
                dedupe_key=f"goal_risk:{g['id']}:{cycle_id}",
                evidence={"goal_id": g["id"], "required_monthly": str(g["required_monthly_contribution"]),
                          "allocated_monthly": str(g["allocated_monthly_savings"]), "status": g["status"]},
            )

    return raised


def list_alerts(conn: psycopg.Connection, user_id: str, limit: int = 30, unread_only: bool = False) -> list[dict]:
    extra = "and not is_read" if unread_only else ""
    return conn.execute(
        f"select * from agent_alerts where user_id = %s {extra} order by created_at desc limit %s", (user_id, limit)
    ).fetchall()
