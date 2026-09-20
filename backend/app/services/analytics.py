"""Trend, daily-spending and unusual-activity analytics (deterministic, over the ledger)."""

from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

import psycopg

from app.config import get_settings
from app.services import queries
from app.services.alerts import (
    HIGH_SPEND_FLOOR, HIGH_SPEND_MULTIPLE, LARGE_TXN_FLOOR, LARGE_TXN_MULTIPLE, average_daily_spend,
)
from app.services.cycle_state import as_of
from app.services.savings import inr, inr0

ZERO = Decimal("0.00")


def _tz() -> ZoneInfo:
    return ZoneInfo(get_settings().app_timezone)


def monthly_trends(conn: psycopg.Connection, user_id: str, account_id: str, limit: int = 6) -> list[dict]:
    """Per-cycle totals, oldest first, ending with the active cycle."""
    from app.services.comparison import cycle_summary  # local import: comparison imports cycle_state

    rows = list(reversed(queries.list_cycles(conn, user_id, account_id)[:limit]))
    out = []
    prev_expenses: Optional[Decimal] = None
    for c in rows:
        s = cycle_summary(conn, user_id, c)
        out.append({
            "cycle_id": s["id"], "label": s["label"], "status": s["status"], "income": s["income"], "expenses": s["expenses"],
            "savings": s["savings"], "savings_rate": s["savings_rate"],
            "top_category": s["top_categories"][0]["category"] if s["top_categories"] else None,
            "change_vs_previous": (s["expenses"] - prev_expenses) if prev_expenses is not None else None,
            "change_percent": (round(float((s["expenses"] - prev_expenses) / prev_expenses * 100), 1)
                               if prev_expenses else None),
        })
        prev_expenses = s["expenses"]
    return out


def daily_spending(conn: psycopg.Connection, user_id: str, account_id: str, days: int = 14) -> dict:
    """Expense totals per calendar day (India time) for the last N days up to 'now', zero-filled."""
    tz = _tz()
    now = as_of(conn, user_id, account_id).astimezone(tz)
    today = now.date()
    start = datetime(today.year, today.month, today.day, tzinfo=tz) - timedelta(days=days - 1)
    rows = conn.execute(
        """
        select (("timestamp" at time zone %s)::date) as day, sum(amount) as total, count(*) as count
        from transactions
        where user_id = %s and account_id = %s and transaction_type = 'EXPENSE' and "timestamp" >= %s
        group by 1 order by 1
        """,
        (get_settings().app_timezone, user_id, account_id, start),
    ).fetchall()
    by_day = {r["day"]: r for r in rows}
    series = []
    for i in range(days):
        d = (start + timedelta(days=i)).date()
        r = by_day.get(d)
        series.append({"date": d, "total": r["total"] if r else ZERO, "transactions": r["count"] if r else 0})
    yesterday = today - timedelta(days=1)
    lookup = {s["date"]: s for s in series}
    return {
        "as_of": now, "today": lookup.get(today), "yesterday": lookup.get(yesterday), "days": series,
        "average_daily_spend": (sum((s["total"] for s in series), ZERO) / days).quantize(Decimal("0.01")),
    }


def unusual_for_cycle(conn: psycopg.Connection, user_id: str, cycle: dict, account_id: Optional[str] = None) -> list[dict]:
    """Category spikes vs the user's own recent cycles, unusually large transactions, and high-spend days."""
    tz = _tz()
    aid = account_id or str(cycle["account_id"])
    cid = str(cycle["id"])
    out: list[dict] = []

    history_ids = [str(h["id"]) for h in queries.closed_cycles_before(conn, user_id, cycle, limit=3)]
    if len(history_ids) >= 2:
        for cat in queries.category_breakdown(conn, user_id, cid):
            past = queries.category_history(conn, user_id, cat["category"], history_ids)
            if sum(1 for p in past if p > 0) < 2:
                continue
            avg = sum(past, ZERO) / len(past)
            if avg > 0 and cat["total"] >= Decimal("1.5") * avg and cat["total"] - avg >= 1000:
                pct = int(((cat["total"] - avg) / avg * 100).to_integral_value())
                ids = [str(r["id"]) for r in conn.execute(
                    """select id from transactions where user_id = %s and financial_cycle_id = %s and category = %s
                       and transaction_type = 'EXPENSE' order by amount desc limit 3""", (user_id, cid, cat["category"])).fetchall()]
                out.append({
                    "type": "CATEGORY_SPIKE", "category": cat["category"],
                    "message": f"{cat['category']} spending is {pct}% higher than your recent average "
                               f"({inr(cat['total'])} vs {inr0(avg)} over your last {len(past)} cycles).",
                    "evidence": {"current": cat["total"], "average": avg, "history": past, "transaction_ids": ids},
                })

    amounts = [r["amount"] for r in conn.execute(
        "select amount from transactions where user_id = %s and account_id = %s and transaction_type = 'EXPENSE'", (user_id, aid)).fetchall()]
    if len(amounts) >= 10:
        median = Decimal(str(statistics.median(float(a) for a in amounts)))
        threshold = max(LARGE_TXN_FLOOR, LARGE_TXN_MULTIPLE * median)
        for t in conn.execute(
            """select id, "timestamp", merchant, description, amount from transactions
               where user_id = %s and financial_cycle_id = %s and transaction_type = 'EXPENSE' and not is_recurring and amount >= %s
               order by amount desc limit 3""", (user_id, cid, threshold)).fetchall():
            out.append({
                "type": "LARGE_TRANSACTION", "category": None,
                "message": f"A transaction of {inr(t['amount'])} at {t['merchant'] or t['description']} is much larger than "
                           f"your typical transaction (median {inr0(median)}).",
                "evidence": {"transaction_ids": [str(t["id"])], "amount": t["amount"], "median": median},
            })

    days = conn.execute(
        """select (("timestamp" at time zone %s)::date) as day, sum(amount) as total, array_agg(id::text) as ids
           from transactions where user_id = %s and financial_cycle_id = %s and transaction_type = 'EXPENSE' and not is_recurring
           group by 1 having sum(amount) >= %s order by 2 desc limit 3""",
        (get_settings().app_timezone, user_id, cid, HIGH_SPEND_FLOOR),
    ).fetchall()
    for d in days:
        day_start = datetime(d["day"].year, d["day"].month, d["day"].day, tzinfo=tz)
        avg = average_daily_spend(conn, user_id, aid, day_start)
        if avg and avg > 0 and d["total"] >= HIGH_SPEND_MULTIPLE * avg:
            out.append({
                "type": "HIGH_SPENDING_DAY", "category": None,
                "message": f"{d['day']:%d %b}: {inr(d['total'])} spent in one day, significantly above your recent daily "
                           f"average of {inr0(avg)}.",
                "evidence": {"day": d["day"], "total": d["total"], "average": avg, "transaction_ids": d["ids"]},
            })
    return out
