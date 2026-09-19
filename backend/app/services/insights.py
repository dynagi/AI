"""Dashboard insights. Each one is derived from actual rows and stores its evidence.

If there is no supporting data there is no insight: a category with no
transactions can never appear here, and nothing is generated from assumptions.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import psycopg

from app.config import get_settings
from app.services import queries
from app.services.cycle_state import as_of
from app.services.recurring import list_recurring
from app.services.savings import inr, inr0


def _upsert(conn, user_id, cycle_id, key, itype, severity, title, message, evidence):
    conn.execute(
        """
        insert into financial_insights (user_id, financial_cycle_id, insight_type, severity, title, message, evidence, dedupe_key)
        values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
        on conflict (user_id, dedupe_key) do update set
          severity = excluded.severity, title = excluded.title, message = excluded.message,
          evidence = excluded.evidence, financial_cycle_id = excluded.financial_cycle_id
        """,
        (user_id, cycle_id, itype, severity, title, message, json.dumps(evidence, default=str), key),
    )


def refresh_insights(conn: psycopg.Connection, user_id: str, account_id: str) -> int:
    tz = ZoneInfo(get_settings().app_timezone)
    cycle = queries.active_cycle(conn, user_id, account_id)
    if cycle is None:
        return 0
    cid = str(cycle["id"])
    produced: list[str] = []

    def emit(kind, itype, severity, title, message, evidence):
        key = f"{kind}:{cid}"
        produced.append(key)
        _upsert(conn, user_id, cid, key, itype, severity, title, message, evidence)

    breakdown = queries.category_breakdown(conn, user_id, cid)
    total = cycle["expense_total"]
    prev = queries.previous_cycle(conn, user_id, cycle)

    if breakdown and total > 0:
        top = breakdown[0]
        share = int((top["total"] / total * 100).to_integral_value())
        emit("top_category", "spending", "info", f"{top['category']} is your biggest category",
             f"{top['category']} accounts for {inr(top['total'])} ({share}%) of this cycle's {inr(total)} in expenses.",
             {"category": top["category"], "total": str(top["total"]), "share_percent": share, "cycle_expenses": str(total)})

    # Categories above the user's own recent average.
    history_ids = [str(h["id"]) for h in queries.closed_cycles_before(conn, user_id, cycle, limit=3)]
    if len(history_ids) >= 2:
        spikes = []
        for cat in breakdown:
            past = queries.category_history(conn, user_id, cat["category"], history_ids)
            if sum(1 for p in past if p > 0) < 2:
                continue
            avg = sum(past, Decimal("0")) / len(past)
            if avg > 0 and cat["total"] >= Decimal("1.3") * avg and cat["total"] - avg >= 500:
                spikes.append((cat, avg, past))
        for cat, avg, past in sorted(spikes, key=lambda s: s[0]["total"] - s[1], reverse=True)[:2]:
            ids = [str(r["id"]) for r in conn.execute(
                "select id from transactions where user_id = %s and financial_cycle_id = %s and category = %s and transaction_type = 'EXPENSE' order by amount desc limit 3",
                (user_id, cid, cat["category"])).fetchall()]
            emit(f"category_vs_avg:{cat['category']}", "category_spike", "warning",
                 f"{cat['category']} spending is significantly higher than your recent average",
                 f"{cat['category']}: {inr(cat['total'])} this cycle vs {inr0(avg)} average over your last {len(past)} cycles.",
                 {"category": cat["category"], "current": str(cat["total"]), "average": str(avg),
                  "history": [str(p) for p in past], "top_transaction_ids": ids})

    # Recurring commitments (only when real recurring payments exist).
    recurring = list_recurring(conn, user_id)
    if recurring:
        monthly = [r for r in recurring if r["frequency"] == "monthly"]
        monthly_total = sum((r["average_amount"] for r in monthly), Decimal("0"))
        emit("recurring", "recurring", "info", "Recurring commitments",
             f"You have {len(recurring)} recurring payment{'s' if len(recurring) != 1 else ''}"
             + (f" totaling approximately {inr(monthly_total)}/month." if monthly else "."),
             {"count": len(recurring), "monthly_total": str(monthly_total), "merchants": [r["merchant"] for r in recurring]})
        now = as_of(conn, user_id, account_id)
        upcoming = sorted((r for r in recurring if r["next_expected_payment"] >= now), key=lambda r: r["next_expected_payment"])
        if upcoming:
            n = upcoming[0]
            emit("next_recurring", "recurring", "info", "Next expected recurring payment",
                 f"Your next expected recurring payment is approximately {inr(n['average_amount'])} ({n['merchant']}) "
                 f"around {n['next_expected_payment'].astimezone(tz):%d %b}.",
                 {"merchant": n["merchant"], "amount": str(n["average_amount"]), "expected": n["next_expected_payment"].isoformat()})

    if prev and prev["expense_total"] > 0 and total > 0:
        pct = int((total / prev["expense_total"] * 100).to_integral_value())
        emit("vs_previous", "comparison", "info", "Compared with your previous cycle",
             f"You have spent {inr(total)} this cycle, {pct}% of the {inr(prev['expense_total'])} you spent in the previous cycle.",
             {"current": str(total), "previous": str(prev["expense_total"]), "previous_cycle_id": str(prev["id"])})

    big = queries.largest_expenses(conn, user_id, cid, limit=1)
    if big and total > 0:
        b = big[0]
        emit("largest", "spending", "info", "Largest expense this cycle",
             f"Your largest expense this cycle was {inr(b['amount'])} at {b['merchant'] or b['description']} on "
             f"{b['timestamp'].astimezone(tz):%d %b}.",
             {"transaction_id": str(b["id"]), "amount": str(b["amount"])})

    # Retire insights for this cycle that no longer apply.
    conn.execute(
        "delete from financial_insights where user_id = %s and financial_cycle_id = %s and not (dedupe_key = any(%s))",
        (user_id, cid, produced),
    )
    return len(produced)


def list_insights(conn: psycopg.Connection, user_id: str, limit: int = 20) -> list[dict]:
    return conn.execute(
        """
        select fi.* from financial_insights fi
        join financial_cycles fc on fc.id = fi.financial_cycle_id and fc.status = 'ACTIVE'
        where fi.user_id = %s and not fi.dismissed
        order by (fi.severity = 'warning') desc, fi.created_at desc limit %s
        """,
        (user_id, limit),
    ).fetchall()
