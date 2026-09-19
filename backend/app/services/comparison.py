"""Cycle summaries and cycle-vs-cycle comparison (all numbers from the ledger)."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

import psycopg

from app.config import get_settings
from app.services import queries
from app.services.cycle_state import cycle_label
from app.services.savings import inr

ZERO = Decimal("0.00")


def _pct(change: Decimal, base: Decimal) -> Optional[float]:
    if not base:
        return None
    return round(float(change / base * 100), 1)


def cycle_summary(conn: psycopg.Connection, user_id: str, cycle: dict) -> dict:
    tz = ZoneInfo(get_settings().app_timezone)
    cid = str(cycle["id"])
    expenses, income, refunds = cycle["expense_total"], cycle["income_total"], cycle["refund_total"]
    net_spend = expenses - refunds
    savings = income - net_spend
    cats = queries.category_breakdown(conn, user_id, cid)
    recurring = queries.recurring_spend_in_cycle(conn, user_id, cid)
    return {
        "id": cid,
        "label": cycle_label(cycle, tz),
        "status": cycle["status"],
        "start_at": cycle["start_at"],
        "end_at": cycle["end_at"],
        "opening_balance": cycle["opening_balance"],
        "carried_over_balance": cycle["carried_over_balance"],
        "closing_balance": cycle["closing_balance"],
        "income": income,
        "other_inflows": cycle["other_inflow_total"],
        "refunds": refunds,
        "expenses": expenses,
        "net_spend": net_spend,
        "savings": savings,
        "savings_rate": round(float(savings / income * 100), 1) if income else None,
        "savings_target": cycle["savings_target"],
        "transaction_count": cycle["transaction_count"],
        "categories": [
            {"category": c["category"], "total": c["total"], "count": c["count"],
             "percent": round(float(c["total"] / expenses * 100), 1) if expenses else 0.0}
            for c in cats
        ],
        "top_categories": [{"category": c["category"], "total": c["total"]} for c in cats[:3]],
        "recurring_expenses": {"total": recurring["total"], "count": recurring["count"]},
        "largest_transactions": [
            {"id": str(t["id"]), "timestamp": t["timestamp"], "merchant": t["merchant"], "description": t["description"],
             "amount": t["amount"], "category": t["category"]}
            for t in queries.largest_expenses(conn, user_id, cid, limit=5)
        ],
    }


def compare_cycles(conn: psycopg.Connection, user_id: str, cycle_a: dict, cycle_b: dict) -> dict:
    """Difference = B - A (so with A = previous and B = current, negative means spending is lower so far)."""
    a, b = cycle_summary(conn, user_id, cycle_a), cycle_summary(conn, user_id, cycle_b)

    a_cats = {c["category"]: c["total"] for c in a["categories"]}
    b_cats = {c["category"]: c["total"] for c in b["categories"]}
    changes = []
    for cat in set(a_cats) | set(b_cats):
        av, bv = a_cats.get(cat, ZERO), b_cats.get(cat, ZERO)
        changes.append({"category": cat, "a": av, "b": bv, "change": bv - av, "change_percent": _pct(bv - av, av)})
    changes.sort(key=lambda c: abs(c["change"]), reverse=True)

    expense_diff = b["expenses"] - a["expenses"]
    result = {
        "a": a,
        "b": b,
        "expense_difference": expense_diff,
        "expense_change_percent": _pct(expense_diff, a["expenses"]),
        "income_difference": b["income"] - a["income"],
        "savings_difference": b["savings"] - a["savings"],
        "category_changes": changes,
        "top_increases": [c for c in changes if c["change"] > 0][:3],
        "top_decreases": sorted([c for c in changes if c["change"] < 0], key=lambda c: c["change"])[:3],
    }
    result["explanation"] = explain_comparison(result)
    return result


def explain_comparison(cmp: dict) -> list[str]:
    """Plain-language, fully data-derived explanation (no model involved)."""
    a, b = cmp["a"], cmp["b"]
    lines = []
    diff = cmp["expense_difference"]
    pct = cmp["expense_change_percent"]
    direction = "higher" if diff > 0 else "lower"
    if a["expenses"] == 0 and b["expenses"] == 0:
        return ["There are no expenses in either cycle to compare."]
    pct_txt = f" ({abs(pct):.1f}%)" if pct is not None else ""
    lines.append(
        f"Expenses in {b['label']} are {inr(abs(diff))}{pct_txt} {direction} than in {a['label']} "
        f"({inr(b['expenses'])} vs {inr(a['expenses'])})."
    )
    if b["status"] == "ACTIVE" and diff < 0:
        lines.append(f"The current cycle is still running, so it can spend {inr(abs(diff))} more before reaching the earlier cycle's total.")
    for c in cmp["top_increases"]:
        share = f", {c['change_percent']:+.1f}%" if c["change_percent"] is not None else ""
        lines.append(f"{c['category']} rose by {inr(c['change'])}{share} ({inr(c['a'])} → {inr(c['b'])}).")
    for c in cmp["top_decreases"]:
        share = f", {c['change_percent']:+.1f}%" if c["change_percent"] is not None else ""
        lines.append(f"{c['category']} fell by {inr(abs(c['change']))}{share} ({inr(c['a'])} → {inr(c['b'])}).")
    if b["largest_transactions"]:
        t = b["largest_transactions"][0]
        lines.append(f"The largest expense in {b['label']} was {inr(t['amount'])} at {t['merchant'] or t['description']}.")
    return lines


def progress_vs_previous(current: dict, previous: Optional[dict]) -> Optional[dict]:
    """'How much until last cycle's total?' card. Gross expenses vs gross expenses."""
    if previous is None:
        return None
    cur, prev = current["expenses"], previous["expense_total"]
    remaining = prev - cur
    if remaining >= 0:
        message = f"You can spend {inr(remaining)} more before reaching last cycle's total."
        exceeded = ZERO
    else:
        message = f"⚠️ You have exceeded last cycle's total by {inr(-remaining)}."
        exceeded = -remaining
    return {
        "current": cur,
        "previous": prev,
        "remaining": max(remaining, ZERO),
        "exceeded_by": exceeded,
        "percent_of_previous": round(float(cur / prev * 100), 1) if prev else None,
        "difference": cur - prev,
        "change_percent": _pct(cur - prev, prev),
        "message": message,
    }
