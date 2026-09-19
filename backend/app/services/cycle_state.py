"""Cycle-level state used by the dashboard, alerts and the agent tools."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import psycopg

from app.services import queries
from app.services.savings import SavingsProgress, compute_savings_progress, elapsed_days

Row = dict


def as_of(conn: psycopg.Connection, user_id: str, account_id: str) -> datetime:
    """'Now' for cycle maths: the wall clock, or the latest ledger entry if that is later.

    The Demo Bank Simulator can post transactions dated after the wall clock (the demo story is set on
    30 Sep 2026); using the later of the two keeps elapsed-time maths sensible in both worlds.
    """
    now = datetime.now(timezone.utc)
    row = conn.execute(
        'select max("timestamp") as ts from transactions where user_id = %s and account_id = %s',
        (user_id, account_id),
    ).fetchone()
    latest = row["ts"] if row else None
    return max(now, latest) if latest else now


def get_target(conn: psycopg.Connection, user_id: str, cycle_id: str) -> Optional[Decimal]:
    row = conn.execute(
        "select target_amount from monthly_savings_targets where user_id = %s and financial_cycle_id = %s",
        (user_id, cycle_id),
    ).fetchone()
    return row["target_amount"] if row else None


def set_target(conn: psycopg.Connection, user_id: str, cycle_id: str, amount: Decimal) -> Row:
    row = conn.execute(
        """
        insert into monthly_savings_targets (user_id, financial_cycle_id, target_amount)
        values (%s, %s, %s)
        on conflict (financial_cycle_id) do update set target_amount = excluded.target_amount
        returning *
        """,
        (user_id, cycle_id, amount),
    ).fetchone()
    conn.execute(
        "update financial_cycles set savings_target = %s where id = %s and user_id = %s",
        (amount, cycle_id, user_id),
    )
    return row


def savings_progress_for(conn: psycopg.Connection, user_id: str, cycle: Row) -> SavingsProgress:
    cycle_id = str(cycle["id"])
    ref = (cycle["end_at"] or as_of(conn, user_id, str(cycle["account_id"])))
    history = queries.closed_cycles_before(conn, user_id, cycle, limit=3)
    return compute_savings_progress(
        income=cycle["income_total"],
        other_inflows=cycle["other_inflow_total"],
        expenses=cycle["expense_total"],
        refunds=cycle["refund_total"],
        target=get_target(conn, user_id, cycle_id),
        elapsed_days=elapsed_days(cycle["start_at"], ref),
        recent_net_spends=[h["expense_total"] - h["refund_total"] for h in history],
        recent_cycle_days=[(h["end_at"] - h["start_at"]).total_seconds() / 86400 for h in history if h["end_at"]],
    )


def cycle_label(cycle: Row, tz) -> str:
    start = cycle["start_at"].astimezone(tz)
    if cycle["end_at"]:
        end = cycle["end_at"].astimezone(tz)
        return f"{start:%d %b} – {end:%d %b %Y}"
    return f"{start:%d %b %Y} – now"
