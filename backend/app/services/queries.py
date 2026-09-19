"""Read-side queries. Every function takes user_id and scopes by it.

These are the single source of every financial number the dashboard, the
comparison page and the AI agent show: nothing is computed in the frontend and
nothing is remembered by the LLM.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

import psycopg

Row = dict[str, Any]


# ---------------------------------------------------------------- accounts

def list_accounts(conn: psycopg.Connection, user_id: str) -> list[Row]:
    return conn.execute(
        "select * from financial_accounts where user_id = %s order by created_at", (user_id,)
    ).fetchall()


def get_account(conn: psycopg.Connection, user_id: str, account_id: str) -> Optional[Row]:
    return conn.execute(
        "select * from financial_accounts where id = %s and user_id = %s", (account_id, user_id)
    ).fetchone()


def primary_account(conn: psycopg.Connection, user_id: str, account_id: Optional[str] = None) -> Optional[Row]:
    """The account the dashboard/agent reads: the requested one, else the first ACTIVE bank/demo account,
    else any ACTIVE account, else (so data stays visible after a disconnect) the earliest remaining account."""
    if account_id:
        return get_account(conn, user_id, account_id)
    return conn.execute(
        """
        select * from financial_accounts
        where user_id = %s
        order by (status = 'ACTIVE') desc, (source in ('demo', 'bank')) desc, created_at
        limit 1
        """,
        (user_id,),
    ).fetchone()


def writable_account(conn: psycopg.Connection, user_id: str, account_id: Optional[str] = None) -> Optional[Row]:
    """The ACTIVE account new manual/CSV data should go to (None if the user has no active account)."""
    if account_id:
        return get_account(conn, user_id, account_id)
    return conn.execute(
        """
        select * from financial_accounts where user_id = %s and status = 'ACTIVE'
        order by (source in ('demo', 'bank')) desc, created_at limit 1
        """,
        (user_id,),
    ).fetchone()


# ------------------------------------------------------------------ cycles

def get_cycle(conn: psycopg.Connection, user_id: str, cycle_id: str) -> Optional[Row]:
    return conn.execute(
        "select * from financial_cycles where id = %s and user_id = %s", (cycle_id, user_id)
    ).fetchone()


def active_cycle(conn: psycopg.Connection, user_id: str, account_id: str) -> Optional[Row]:
    return conn.execute(
        "select * from financial_cycles where user_id = %s and account_id = %s and status = 'ACTIVE'",
        (user_id, account_id),
    ).fetchone()


def previous_cycle(conn: psycopg.Connection, user_id: str, cycle: Row) -> Optional[Row]:
    return conn.execute(
        """
        select * from financial_cycles
        where user_id = %s and account_id = %s and start_at < %s
        order by start_at desc limit 1
        """,
        (user_id, cycle["account_id"], cycle["start_at"]),
    ).fetchone()


def closed_cycles_before(conn: psycopg.Connection, user_id: str, cycle: Row, limit: int = 3) -> list[Row]:
    return conn.execute(
        """
        select * from financial_cycles
        where user_id = %s and account_id = %s and start_at < %s and status = 'CLOSED'
        order by start_at desc limit %s
        """,
        (user_id, cycle["account_id"], cycle["start_at"], limit),
    ).fetchall()


def list_cycles(conn: psycopg.Connection, user_id: str, account_id: Optional[str] = None) -> list[Row]:
    if account_id:
        return conn.execute(
            "select * from financial_cycles where user_id = %s and account_id = %s order by start_at desc",
            (user_id, account_id),
        ).fetchall()
    return conn.execute(
        "select * from financial_cycles where user_id = %s order by start_at desc", (user_id,)
    ).fetchall()


# ---------------------------------------------------------- cycle aggregates

def category_breakdown(conn: psycopg.Connection, user_id: str, cycle_id: str) -> list[Row]:
    """Spending per category for one cycle. Only categories that actually have EXPENSE rows appear."""
    return conn.execute(
        """
        select category, sum(amount) as total, count(*) as count
        from transactions
        where user_id = %s and financial_cycle_id = %s and transaction_type = 'EXPENSE'
        group by category order by total desc
        """,
        (user_id, cycle_id),
    ).fetchall()


def largest_expenses(conn: psycopg.Connection, user_id: str, cycle_id: str, limit: int = 5) -> list[Row]:
    return conn.execute(
        """
        select id, "timestamp", description, merchant, amount, category
        from transactions
        where user_id = %s and financial_cycle_id = %s and transaction_type = 'EXPENSE'
        order by amount desc, "timestamp" limit %s
        """,
        (user_id, cycle_id, limit),
    ).fetchall()


def recurring_spend_in_cycle(conn: psycopg.Connection, user_id: str, cycle_id: str) -> Row:
    return conn.execute(
        """
        select coalesce(sum(amount), 0) as total, count(*) as count
        from transactions
        where user_id = %s and financial_cycle_id = %s and transaction_type = 'EXPENSE' and is_recurring
        """,
        (user_id, cycle_id),
    ).fetchone()


def category_history(
    conn: psycopg.Connection, user_id: str, category: str, cycle_ids: list[str]
) -> list[Decimal]:
    """The user's spending in one category in each of the given cycles (zeros included)."""
    if not cycle_ids:
        return []
    rows = conn.execute(
        """
        select financial_cycle_id, sum(amount) as total
        from transactions
        where user_id = %s and category = %s and transaction_type = 'EXPENSE' and financial_cycle_id = any(%s::uuid[])
        group by financial_cycle_id
        """,
        (user_id, category, cycle_ids),
    ).fetchall()
    by = {str(r["financial_cycle_id"]): r["total"] for r in rows}
    return [by.get(cid, Decimal("0")) for cid in cycle_ids]


# ----------------------------------------------------------- transactions

def list_transactions(
    conn: psycopg.Connection,
    user_id: str,
    account_id: Optional[str] = None,
    cycle_id: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    category: Optional[str] = None,
    query: Optional[str] = None,
    min_amount: Optional[Decimal] = None,
    transaction_types: Optional[list[str]] = None,
    limit: int = 100,
    offset: int = 0,
    newest_first: bool = True,
) -> list[Row]:
    where = ["t.user_id = %(user_id)s"]
    p: dict[str, Any] = {"user_id": user_id, "limit": min(max(limit, 1), 500), "offset": max(offset, 0)}
    if account_id:
        where.append("t.account_id = %(account_id)s"); p["account_id"] = account_id
    if cycle_id:
        where.append("t.financial_cycle_id = %(cycle_id)s"); p["cycle_id"] = cycle_id
    if start:
        where.append('t."timestamp" >= %(start)s'); p["start"] = start
    if end:
        where.append('t."timestamp" < %(end)s'); p["end"] = end
    if category:
        where.append("t.category = %(category)s"); p["category"] = category
    if query:
        where.append("(t.description ilike %(q)s or t.merchant ilike %(q)s)"); p["q"] = f"%{query}%"
    if min_amount is not None:
        where.append("t.amount >= %(min_amount)s"); p["min_amount"] = min_amount
    if transaction_types:
        where.append("t.transaction_type = any(%(types)s)"); p["types"] = transaction_types
    order = "desc" if newest_first else "asc"
    return conn.execute(
        f"""
        select t.id, t.account_id, t."timestamp", t.description, t.merchant, t.amount, t.signed_amount, t.currency,
               t.transaction_type, t.category, t.subcategory, t.source, t.financial_cycle_id,
               t.balance_after, t.is_recurring, t.recurring_group_id
        from transactions t
        where {' and '.join(where)}
        order by t."timestamp" {order}, t.seq {order}
        limit %(limit)s offset %(offset)s
        """,
        p,
    ).fetchall()


def budgets_for(conn: psycopg.Connection, user_id: str) -> list[Row]:
    return conn.execute("select * from budgets where user_id = %s order by category", (user_id,)).fetchall()
