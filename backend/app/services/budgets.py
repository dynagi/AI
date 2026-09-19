"""Category budgets, measured against the CURRENT ACTIVE cycle.

Budgets are not savings targets: a budget caps one category, a savings target is
about how much of the cycle's income is left over.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

import psycopg

from app.services import queries


def budget_status(conn: psycopg.Connection, user_id: str, account_id: str) -> list[dict]:
    cycle = queries.active_cycle(conn, user_id, account_id)
    budgets = queries.budgets_for(conn, user_id)
    if not budgets:
        return []
    spent_by_cat: dict[str, Decimal] = {}
    if cycle:
        spent_by_cat = {r["category"]: r["total"] for r in queries.category_breakdown(conn, user_id, str(cycle["id"]))}
    out = []
    for b in budgets:
        spent = spent_by_cat.get(b["category"], Decimal("0"))
        pct = (spent / b["amount"] * 100) if b["amount"] else Decimal("0")
        out.append(
            {
                "id": str(b["id"]),
                "category": b["category"],
                "amount": b["amount"],
                "spent": spent,
                "remaining": b["amount"] - spent,
                "percent_used": round(float(pct), 1),
                "cycle_id": str(cycle["id"]) if cycle else None,
            }
        )
    return sorted(out, key=lambda x: -x["percent_used"])


def set_budget(conn: psycopg.Connection, user_id: str, category: str, amount: Decimal) -> dict:
    return conn.execute(
        """
        insert into budgets (user_id, category, amount) values (%s, %s, %s)
        on conflict (user_id, category) do update set amount = excluded.amount
        returning *
        """,
        (user_id, category, amount),
    ).fetchone()


def delete_budget(conn: psycopg.Connection, user_id: str, budget_id: str) -> bool:
    cur = conn.execute("delete from budgets where id = %s and user_id = %s", (budget_id, user_id))
    return cur.rowcount > 0
