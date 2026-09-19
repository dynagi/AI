"""Recurring payment detection from real history only.

A merchant is only called recurring when there is real evidence: at least three
payments, evenly spaced (weekly / monthly / quarterly / yearly), with similar amounts.
"""

from __future__ import annotations

import statistics
from datetime import timedelta
from decimal import Decimal
from typing import Optional

import psycopg

from app.services.categorization import merchant_key

MIN_OCCURRENCES = 3
MAX_AMOUNT_VARIATION = 0.25  # stdev/mean


def _frequency(avg_days: float) -> Optional[tuple[str, float]]:
    """(name, max allowed stdev of the interval in days)"""
    if 6 <= avg_days <= 9:
        return "weekly", 2.0
    if 27 <= avg_days <= 33:
        return "monthly", 5.0
    if 85 <= avg_days <= 97:
        return "quarterly", 10.0
    if 350 <= avg_days <= 380:
        return "yearly", 20.0
    return None


def detect_recurring(conn: psycopg.Connection, user_id: str, account_id: Optional[str] = None) -> list[dict]:
    where, params = "user_id = %s and transaction_type = 'EXPENSE'", [user_id]
    if account_id:
        where += " and account_id = %s"
        params.append(account_id)
    txns = conn.execute(
        f'select id, "timestamp", description, merchant, amount, category from transactions where {where} order by "timestamp"',
        params,
    ).fetchall()
    return detect_from_rows(txns)


def detect_from_rows(txns: list[dict]) -> list[dict]:
    """Pure detection over EXPENSE rows (id, timestamp, description, merchant, amount, category), oldest first."""
    groups: dict[str, list[dict]] = {}
    for t in txns:
        groups.setdefault(merchant_key(t["merchant"] or t["description"]), []).append(t)

    found: list[dict] = []
    for key, members in groups.items():
        if len(members) < MIN_OCCURRENCES or not key:
            continue
        gaps = [(members[i]["timestamp"] - members[i - 1]["timestamp"]).total_seconds() / 86400 for i in range(1, len(members))]
        avg_gap = statistics.fmean(gaps)
        freq = _frequency(avg_gap)
        if not freq:
            continue
        frequency, tolerance = freq
        gap_sd = statistics.pstdev(gaps)
        if gap_sd > tolerance:
            continue
        amounts = [float(m["amount"]) for m in members]
        avg_amt = statistics.fmean(amounts)
        variation = statistics.pstdev(amounts) / avg_amt if avg_amt else 1.0
        if variation > MAX_AMOUNT_VARIATION:
            continue

        interval_score = max(0.0, 1 - gap_sd / avg_gap)
        amount_score = max(0.0, 1 - variation)
        confidence = min(0.98, 0.45 * interval_score + 0.45 * amount_score + 0.02 * len(members))
        last = members[-1]
        found.append(
            {
                "recurring_group_id": key,
                "merchant": last["merchant"] or last["description"],
                "category": last["category"],
                "average_amount": Decimal(str(round(avg_amt, 2))),
                "frequency": frequency,
                "last_payment": last["timestamp"],
                "next_expected_payment": last["timestamp"] + timedelta(days=avg_gap),
                "confidence": Decimal(str(round(confidence, 2))),
                "occurrences": len(members),
                "member_ids": [str(m["id"]) for m in members],
            }
        )
    return found


def refresh_recurring(conn: psycopg.Connection, user_id: str, account_id: Optional[str] = None) -> list[dict]:
    """Detect and persist recurring payments, flag their transactions, retire stale ones."""
    found = detect_recurring(conn, user_id, account_id)

    seen = []
    for r in found:
        seen.append(r["recurring_group_id"])
        conn.execute(
            """
            insert into recurring_payments
              (user_id, recurring_group_id, merchant, category, average_amount, frequency,
               last_payment, next_expected_payment, confidence, occurrences, active)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true)
            on conflict (user_id, recurring_group_id) do update set
              merchant = excluded.merchant, category = excluded.category, average_amount = excluded.average_amount,
              frequency = excluded.frequency, last_payment = excluded.last_payment,
              next_expected_payment = excluded.next_expected_payment, confidence = excluded.confidence,
              occurrences = excluded.occurrences, active = true
            """,
            (
                user_id, r["recurring_group_id"], r["merchant"], r["category"], r["average_amount"], r["frequency"],
                r["last_payment"], r["next_expected_payment"], r["confidence"], r["occurrences"],
            ),
        )
        conn.execute(
            "update transactions set is_recurring = true, recurring_group_id = %s where user_id = %s and id = any(%s::uuid[])",
            (r["recurring_group_id"], user_id, r["member_ids"]),
        )

    conn.execute(
        "update recurring_payments set active = false where user_id = %s and active and not (recurring_group_id = any(%s))",
        (user_id, seen),
    )
    conn.execute(
        """
        update transactions set is_recurring = false, recurring_group_id = null
        where user_id = %s and is_recurring and not (recurring_group_id = any(%s))
        """,
        (user_id, seen),
    )
    return found


def list_recurring(conn: psycopg.Connection, user_id: str) -> list[dict]:
    return conn.execute(
        "select * from recurring_payments where user_id = %s and active order by average_amount desc", (user_id,)
    ).fetchall()
