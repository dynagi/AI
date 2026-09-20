"""Category budgets, budget commitments and the spending limit, measured against the CURRENT ACTIVE cycle.

Budgets are not savings targets: a budget caps one category; the savings target defines how much of the cycle's
income may be spent at all (income - target = planned spending limit).

"Committed" spending = what is already spent + recurring payments that are still expected before the cycle
ends. It is reported separately from "already spent" so the two are never confused.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import psycopg

from app.ledger import money
from app.services import queries
from app.services.cycle_state import as_of, get_target
from app.services.recurring import list_recurring

ZERO = Decimal("0.00")
INTERVAL_DAYS = {"weekly": 7.0, "monthly": 30.4375, "quarterly": 91.3125, "yearly": 365.25}
STALE_AFTER_DAYS = 7  # an expected payment this far overdue is treated as no longer happening


def expected_cycle_end(conn: psycopg.Connection, user_id: str, cycle: dict) -> datetime:
    """When the active cycle will probably end: start + the average length of the user's recent cycles (default 30 days)."""
    lengths = [
        (c["end_at"] - c["start_at"]).total_seconds() / 86400
        for c in queries.closed_cycles_before(conn, user_id, cycle, limit=3) if c["end_at"]
    ]
    days = sum(lengths) / len(lengths) if lengths else 30.0
    return cycle["start_at"] + timedelta(days=days)


def upcoming_recurring(conn: psycopg.Connection, user_id: str, account_id: str, cycle: dict) -> list[dict]:
    """Recurring payments still expected before the cycle ends (not yet paid in this cycle)."""
    now = as_of(conn, user_id, account_id)
    end = expected_cycle_end(conn, user_id, cycle)
    items = []
    for r in list_recurring(conn, user_id):
        step = INTERVAL_DAYS.get(r["frequency"])
        nxt = r["next_expected_payment"]
        if not step or nxt < now - timedelta(days=STALE_AFTER_DAYS) or nxt > end:
            continue
        if r["frequency"] != "weekly" and r["last_payment"] >= cycle["start_at"]:
            continue  # already paid this cycle
        occurrences = 1 + int((end - nxt).total_seconds() / 86400 // step)
        items.append({
            "merchant": r["merchant"], "category": r["category"], "frequency": r["frequency"],
            "amount": money(r["average_amount"] * occurrences), "occurrences": occurrences, "expected_at": nxt,
            "confidence": r["confidence"],
        })
    return sorted(items, key=lambda i: i["expected_at"])


def _recent_discretionary_by_category(conn: psycopg.Connection, user_id: str, cycle: dict) -> dict[str, Decimal]:
    """Average non-recurring spend per category over the user's last <= 3 closed cycles."""
    ids = [str(c["id"]) for c in queries.closed_cycles_before(conn, user_id, cycle, limit=3)]
    if not ids:
        return {}
    rows = conn.execute(
        """
        select category, sum(amount) as total from transactions
        where user_id = %s and transaction_type = 'EXPENSE' and not is_recurring and financial_cycle_id = any(%s::uuid[])
        group by category
        """,
        (user_id, ids),
    ).fetchall()
    return {r["category"]: r["total"] / len(ids) for r in rows}


def budget_status(conn: psycopg.Connection, user_id: str, account_id: str) -> list[dict]:
    cycle = queries.active_cycle(conn, user_id, account_id)
    budgets = queries.budgets_for(conn, user_id)
    if not budgets:
        return []
    spent_by_cat: dict[str, Decimal] = {}
    upcoming_by_cat: dict[str, Decimal] = {}
    typical: dict[str, Decimal] = {}
    remaining_fraction = 0.0
    if cycle:
        cid = str(cycle["id"])
        spent_by_cat = {r["category"]: r["total"] for r in queries.category_breakdown(conn, user_id, cid)}
        for i in upcoming_recurring(conn, user_id, account_id, cycle):
            upcoming_by_cat[i["category"]] = upcoming_by_cat.get(i["category"], ZERO) + i["amount"]
        typical = _recent_discretionary_by_category(conn, user_id, cycle)
        now = as_of(conn, user_id, account_id)
        length = (expected_cycle_end(conn, user_id, cycle) - cycle["start_at"]).total_seconds() / 86400
        remaining_fraction = max(0.0, 1 - ((now - cycle["start_at"]).total_seconds() / 86400) / length) if length else 0.0

    out = []
    for b in budgets:
        cat, amount = b["category"], b["amount"]
        spent = spent_by_cat.get(cat, ZERO)
        upcoming = upcoming_by_cat.get(cat, ZERO)
        committed = spent + upcoming
        projected = committed + money(typical.get(cat, ZERO) * Decimal(str(remaining_fraction)))
        pct = float(spent / amount * 100) if amount else 0.0
        if spent > amount:
            status = "OVER_BUDGET"
        elif projected > amount or pct >= 80:
            status = "AT_RISK"
        else:
            status = "ON_TRACK"
        out.append({
            "id": str(b["id"]), "category": cat, "amount": amount, "spent": spent, "remaining": amount - spent,
            "percent_used": round(pct, 1), "upcoming_recurring": upcoming, "committed": committed,
            "projected_spend": projected, "status": status, "cycle_id": str(cycle["id"]) if cycle else None,
        })
    return sorted(out, key=lambda x: -x["percent_used"])


def budget_commitments(conn: psycopg.Connection, user_id: str, account_id: str) -> dict:
    """Answers "How much of my budget is already committed?" with the full calculation shown."""
    cycle = queries.active_cycle(conn, user_id, account_id)
    if cycle is None:
        return {"error": "no_cycle", "message": "There is no financial cycle yet, so there is nothing to commit."}
    cid = str(cycle["id"])
    upcoming = upcoming_recurring(conn, user_id, account_id, cycle)
    upcoming_total = sum((i["amount"] for i in upcoming), ZERO)
    spent = cycle["expense_total"] - cycle["refund_total"]

    target = get_target(conn, user_id, cid)
    category_budgets = queries.budgets_for(conn, user_id)
    category_total = sum((b["amount"] for b in category_budgets), ZERO)
    if target is not None and cycle["income_total"] > 0:
        limit, basis = cycle["income_total"] - target, "savings_target"
        basis_text = (f"income {cycle['income_total']:.2f} minus your savings target {target:.2f} "
                      "(the most you can spend and still save the target)")
    elif category_total > 0:
        limit, basis = category_total, "category_budgets"
        basis_text = "the sum of your category budgets"
    else:
        limit, basis, basis_text = None, "none", "no savings target or category budgets have been set"

    committed = spent + upcoming_total
    return {
        "cycle_id": cid,
        "budget_basis": basis,
        "budget_basis_explained": basis_text,
        "monthly_budget": limit,
        "already_spent": spent,
        "upcoming_recurring_expected": upcoming_total,
        "upcoming_recurring_items": upcoming,
        "committed_total": committed,
        "remaining_flexible_capacity": (limit - committed) if limit is not None else None,
        "percent_of_budget_committed": round(float(committed / limit * 100), 1) if limit else None,
        "calculation": "committed = already spent + recurring payments still expected before this cycle ends",
        "category_budgets": budget_status(conn, user_id, account_id),
    }


def budget_overview(conn: psycopg.Connection, user_id: str, account_id: str) -> dict:
    rows = budget_status(conn, user_id, account_id)
    total_budget = sum((r["amount"] for r in rows), ZERO)
    total_spent = sum((r["spent"] for r in rows), ZERO)
    return {
        "budgets": rows,
        "totals": {
            "total_budget": total_budget, "spent": total_spent, "remaining": total_budget - total_spent,
            "committed": sum((r["committed"] for r in rows), ZERO),
            "projected": sum((r["projected_spend"] for r in rows), ZERO),
        },
        "commitments": budget_commitments(conn, user_id, account_id),
    }


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
