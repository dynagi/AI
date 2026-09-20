"""Monthly financial summaries: stored per cycle, with data-driven observations and action items.

Nothing here is written by an LLM. Every observation and action item is a deterministic template filled with
numbers read from the ledger, and carries `evidence` (the figures / transaction ids it came from). If there is
no supporting data, the observation does not exist.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

import psycopg

from app.config import get_settings
from app.services import queries
from app.services.analytics import unusual_for_cycle
from app.services.budgets import budget_status as active_budget_status
from app.services.comparison import compare_cycles, cycle_summary
from app.services.cycle_state import cycle_label, get_target, savings_progress_for
from app.services.goals import goals_overview
from app.services.recurring import list_recurring
from app.services.savings import inr, inr0

ZERO = Decimal("0.00")
INCREASE_PCT, INCREASE_MIN = Decimal("20"), Decimal("1000")


class SummaryNotFound(Exception):
    pass


def _jsonable(v):
    return json.loads(json.dumps(v, default=str))


def _budgets_for_cycle(conn: psycopg.Connection, user_id: str, cycle: dict, account_id: str) -> list[dict]:
    if cycle["status"] == "ACTIVE":
        return [
            {"category": b["category"], "amount": b["amount"], "spent": b["spent"], "percent_used": b["percent_used"], "status": b["status"]}
            for b in active_budget_status(conn, user_id, account_id)
        ]
    spent = {r["category"]: r["total"] for r in queries.category_breakdown(conn, user_id, str(cycle["id"]))}
    out = []
    for b in queries.budgets_for(conn, user_id):
        s = spent.get(b["category"], ZERO)
        pct = float(s / b["amount"] * 100) if b["amount"] else 0.0
        out.append({"category": b["category"], "amount": b["amount"], "spent": s, "percent_used": round(pct, 1),
                    "status": "OVER_BUDGET" if s > b["amount"] else ("AT_RISK" if pct >= 80 else "ON_TRACK")})
    return sorted(out, key=lambda x: -x["percent_used"])


def build_summary(conn: psycopg.Connection, user_id: str, cycle: dict) -> dict:
    """The full report for one cycle: headline numbers, sections, observations, action items."""
    tz = ZoneInfo(get_settings().app_timezone)
    aid = str(cycle["account_id"])
    s = cycle_summary(conn, user_id, cycle)
    prev = queries.previous_cycle(conn, user_id, cycle)
    cmp = compare_cycles(conn, user_id, prev, cycle) if prev is not None else None

    recurring_all = list_recurring(conn, user_id)
    monthly_total = sum((r["average_amount"] for r in recurring_all if r["frequency"] == "monthly"), ZERO)
    rec_spent = s["recurring_expenses"]["total"]
    target = get_target(conn, user_id, str(cycle["id"]))
    unusual = unusual_for_cycle(conn, user_id, cycle, aid)
    goals = goals_overview(conn, user_id, aid)["goals"]
    budgets = _budgets_for_cycle(conn, user_id, cycle, aid)
    progress = savings_progress_for(conn, user_id, cycle)

    observations: list[dict] = []
    actions: list[dict] = []

    def obs(kind: str, text: str, **evidence):
        observations.append({"type": kind, "text": text, "evidence": evidence})

    def act(key: str, title: str, description: str, priority: str, category: Optional[str] = None, **evidence):
        actions.append({"action_key": key, "title": title, "description": description, "priority": priority,
                        "category": category, "evidence": evidence})

    expenses, savings = s["expenses"], s["savings"]

    # --- savings target
    if target is not None:
        gap = savings - target
        if gap >= 0:
            obs("savings_target", f"You saved {inr(savings)} against your {inr(target)} target, {inr(gap)} above it.",
                savings=savings, target=target)
        else:
            obs("savings_target", f"You saved {inr(savings)} against your {inr(target)} target, {inr(-gap)} short of it.",
                savings=savings, target=target)
            act("savings-target", "Savings target was missed",
                f"Savings were {inr(savings)} against a {inr(target)} target, a shortfall of {inr(-gap)}.",
                "HIGH", None, savings=savings, target=target)
    else:
        obs("savings_target", "No savings target was set for this cycle.")

    # --- comparison with the previous cycle
    top_increases = []
    if cmp:
        diff, pct = cmp["expense_difference"], cmp["expense_change_percent"]
        obs("previous_cycle",
            f"Expenses were {inr(abs(diff))}{f' ({abs(pct):.1f}%)' if pct is not None else ''} "
            f"{'higher' if diff > 0 else 'lower'} than the previous cycle ({inr(s['expenses'])} vs {inr(cmp['a']['expenses'])}).",
            current=s["expenses"], previous=cmp["a"]["expenses"])
        for c in cmp["category_changes"]:
            base = c["a"]
            if c["change"] >= INCREASE_MIN and base > 0 and c["change"] / base * 100 >= INCREASE_PCT:
                top_increases.append(c)
        for c in top_increases[:2]:
            obs("category_increase",
                f"{c['category']} spending increased from {inr(c['a'])} to {inr(c['b'])} ({c['change_percent']:+.0f}%).",
                category=c["category"], previous=c["a"], current=c["b"])
            tail = " if you want to maintain your savings target" if target is not None else ""
            act(f"review:{c['category']}", f"Review {c['category'].lower()} increase",
                f"Review the {inr(c['change'])} increase in {c['category'].lower()} expenses compared with the previous cycle{tail}.",
                "HIGH" if c["change"] >= Decimal("5000") else "MEDIUM", c["category"],
                previous=c["a"], current=c["b"], change=c["change"])
        stable = [c for c in cmp["category_changes"] if c["a"] > 0 and abs(c["change"]) / c["a"] * 100 <= 5 and c["b"] >= Decimal("5000")]
        for c in stable[:1]:
            obs("category_stable", f"{c['category']} remained stable at about {inr0(c['b'])}.", category=c["category"], current=c["b"], previous=c["a"])

    # --- recurring commitments
    if expenses > 0 and rec_spent > 0:
        share = int((rec_spent / expenses * 100).to_integral_value())
        obs("recurring", f"Recurring payments made up {share}% of this cycle's expenses ({inr(rec_spent)} of {inr(expenses)}).",
            recurring=rec_spent, expenses=expenses)
        if share >= 40:
            act("recurring-share", "Recurring commitments are a large share of spending",
                f"Recurring payments were {inr(rec_spent)} of {inr(expenses)} ({share}%); about {inr0(monthly_total)} of monthly recurring "
                f"payments are expected to continue.", "MEDIUM", None, recurring=rec_spent, expenses=expenses)

    # --- unusual activity
    for u in unusual[:3]:
        obs("unusual", u["message"], **_jsonable(u["evidence"]))
    for i, u in enumerate([u for u in unusual if u["type"] == "LARGE_TRANSACTION"][:1]):
        ev = u["evidence"]
        act(f"large:{ev['transaction_ids'][0]}", "Review a large transaction", u["message"], "LOW", None, **_jsonable(ev))

    # --- budgets
    for b in budgets:
        if b["status"] == "OVER_BUDGET":
            over = b["spent"] - b["amount"]
            obs("budget", f"{b['category']} spending of {inr(b['spent'])} is over its {inr(b['amount'])} budget by {inr(over)}.",
                category=b["category"], spent=b["spent"], budget=b["amount"])
            act(f"budget:{b['category']}", f"{b['category']} is over budget",
                f"{b['category']} spending is {inr(over)} over its {inr(b['amount'])} budget.", "HIGH" if over >= Decimal("2000") else "MEDIUM",
                b["category"], spent=b["spent"], budget=b["amount"])

    # --- spending capacity (only meaningful while the cycle is running)
    if cycle["status"] == "ACTIVE" and progress.remaining_spend_capacity is not None:
        cap = progress.remaining_spend_capacity
        if cap >= 0:
            obs("capacity", f"You have {inr(cap)} remaining before reaching your monthly spending limit.", remaining=cap)
            act("spending-capacity", "Remaining spending capacity",
                f"Your remaining spending capacity for the cycle is approximately {inr0(cap)} if you want to maintain your "
                f"{inr(progress.target)} savings target.", "MEDIUM", None, remaining=cap, target=progress.target)
        else:
            act("spending-capacity", "Spending limit exceeded",
                f"Spending is {inr(-cap)} above the level that keeps your {inr(progress.target)} savings target within reach.",
                "HIGH", None, over=-cap, target=progress.target)

    # --- goals
    for g in goals:
        if g["lifecycle"] != "ACTIVE" or g["status"] in (None, "COMPLETED"):
            continue
        pct = f"{g['progress_percent']:.1f}%"
        if g["status"] == "ON_TRACK":
            obs("goal", f"{g['name']} is {pct} complete and on track.", goal_id=g["id"], progress=g["progress_percent"])
            if g["goal_type"] == "EMERGENCY_FUND":
                act(f"goal:{g['id']}", "Continue contributing to your emergency fund",
                    f"{g['name']} is {pct} complete ({inr(g['current_amount'])} of {inr(g['target_amount'])}); "
                    f"it needs about {inr0(g['required_monthly_contribution'])} per month to finish by {g['target_date']:%d %b %Y}.",
                    "LOW", None, goal_id=g["id"])
            else:
                act(f"goal:{g['id']}", f"Current savings pace supports the {g['name']} goal",
                    f"{g['name']} is {pct} complete and needs about {inr0(g['required_monthly_contribution'])} per month; "
                    f"your current savings pace covers that.", "LOW", None, goal_id=g["id"])
        else:
            obs("goal", f"{g['name']} is {pct} complete and {'at risk' if g['status'] == 'AT_RISK' else 'behind'}.", goal_id=g["id"])
            act(f"goal:{g['id']}", f"{g['name']} needs a higher savings pace",
                f"{g['name']} needs about {inr0(g['required_monthly_contribution'])} per month, but about "
                f"{inr0(g['allocated_monthly_savings'] or 0)} per month is currently available for it.",
                "HIGH" if g["status"] == "BEHIND" else "MEDIUM", None, goal_id=g["id"])

    savings_rate = s["savings_rate"]
    headline = {
        "title": f"Financial summary: {cycle_label(cycle, tz)}",
        "period_start": cycle["start_at"], "period_end": cycle["end_at"],
        "income_total": s["income"], "expense_total": expenses, "savings_total": savings,
        "savings_rate": Decimal(str(savings_rate)) if savings_rate is not None else None,
        "top_category": s["top_categories"][0]["category"] if s["top_categories"] else None,
        "previous_cycle_expenses": cmp["a"]["expenses"] if cmp else None,
        "expense_change": cmp["expense_difference"] if cmp else None,
        "is_final": cycle["status"] == "CLOSED",
    }
    content = {
        "overview": {
            "income": s["income"], "other_inflows": s["other_inflows"], "refunds": s["refunds"], "expenses": expenses,
            "net_spend": s["net_spend"], "savings": savings, "savings_rate": savings_rate,
            "opening_balance": s["opening_balance"], "carried_over_balance": s["carried_over_balance"],
            "closing_balance": s["closing_balance"], "savings_target": target,
        },
        "top_categories": s["categories"][:3],
        "categories": s["categories"],
        "previous_comparison": (
            {"previous_label": cmp["a"]["label"], "previous_expenses": cmp["a"]["expenses"], "difference": cmp["expense_difference"],
             "change_percent": cmp["expense_change_percent"], "top_increases": cmp["top_increases"], "top_decreases": cmp["top_decreases"]}
            if cmp else None),
        "recurring": {"paid_in_cycle": rec_spent, "payments_in_cycle": s["recurring_expenses"]["count"],
                      "active_recurring_payments": len(recurring_all), "estimated_monthly_total": monthly_total},
        "unusual_activity": unusual,
        "goals": goals,
        "budgets": budgets,
        "observations": observations,
    }
    return {"headline": headline, "content": _jsonable(content), "actions": _jsonable(actions)}


def generate_summary(conn: psycopg.Connection, user_id: str, cycle_id: str) -> dict:
    cycle = queries.get_cycle(conn, user_id, cycle_id)
    if cycle is None:
        raise SummaryNotFound(cycle_id)
    built = build_summary(conn, user_id, cycle)
    h = built["headline"]
    row = conn.execute(
        """
        insert into monthly_summaries
          (user_id, financial_cycle_id, title, period_start, period_end, income_total, expense_total, savings_total,
           savings_rate, top_category, previous_cycle_expenses, expense_change, is_final, content, generated_at)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
        on conflict (financial_cycle_id) do update set
          title = excluded.title, period_start = excluded.period_start, period_end = excluded.period_end,
          income_total = excluded.income_total, expense_total = excluded.expense_total, savings_total = excluded.savings_total,
          savings_rate = excluded.savings_rate, top_category = excluded.top_category,
          previous_cycle_expenses = excluded.previous_cycle_expenses, expense_change = excluded.expense_change,
          is_final = excluded.is_final, content = excluded.content, generated_at = now()
        returning *
        """,
        (user_id, cycle_id, h["title"], h["period_start"], h["period_end"], h["income_total"], h["expense_total"],
         h["savings_total"], h["savings_rate"], h["top_category"], h["previous_cycle_expenses"], h["expense_change"],
         h["is_final"], json.dumps(built["content"])),
    ).fetchone()
    sid = str(row["id"])

    keys = []
    for a in built["actions"]:
        keys.append(a["action_key"])
        # A completed or dismissed item is history: only still-OPEN items are refreshed.
        conn.execute(
            """
            insert into monthly_summary_actions (summary_id, user_id, action_key, title, description, priority, category, evidence)
            values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (summary_id, action_key) do update set
              title = excluded.title, description = excluded.description, priority = excluded.priority,
              category = excluded.category, evidence = excluded.evidence
            where monthly_summary_actions.status = 'OPEN'
            """,
            (sid, user_id, a["action_key"], a["title"], a["description"], a["priority"], a["category"], json.dumps(a["evidence"])),
        )
    conn.execute(
        "delete from monthly_summary_actions where summary_id = %s and user_id = %s and status = 'OPEN' and not (action_key = any(%s))",
        (sid, user_id, keys),
    )
    return row


def sync_summaries(conn: psycopg.Connection, user_id: str, account_id: str) -> list[tuple[str, bool]]:
    """Make sure every CLOSED cycle has a final, up-to-date summary. Returns [(cycle_id, was_missing)] for those generated."""
    # A cycle that was closed and later re-opened (its closing salary was removed) no longer has a final summary.
    conn.execute(
        """delete from monthly_summaries ms using financial_cycles fc
           where ms.financial_cycle_id = fc.id and fc.account_id = %s and fc.user_id = %s and fc.status = 'ACTIVE' and ms.is_final""",
        (account_id, user_id),
    )
    rows = conn.execute(
        """
        select fc.id as cycle_id, ms.id as summary_id, ms.is_final, ms.income_total, ms.expense_total,
               fc.income_total as c_income, fc.expense_total as c_expense
        from financial_cycles fc left join monthly_summaries ms on ms.financial_cycle_id = fc.id
        where fc.user_id = %s and fc.account_id = %s and fc.status = 'CLOSED' order by fc.start_at
        """,
        (user_id, account_id),
    ).fetchall()
    generated = []
    for r in rows:
        stale = (r["summary_id"] is None or not r["is_final"] or r["income_total"] != r["c_income"] or r["expense_total"] != r["c_expense"])
        if stale:
            generated.append((str(r["cycle_id"]), r["summary_id"] is None))
            generate_summary(conn, user_id, str(r["cycle_id"]))
    return generated


def list_summaries(conn: psycopg.Connection, user_id: str) -> list[dict]:
    return conn.execute(
        """
        select ms.id, ms.financial_cycle_id, ms.title, ms.period_start, ms.period_end, ms.income_total, ms.expense_total,
               ms.savings_total, ms.savings_rate, ms.top_category, ms.previous_cycle_expenses, ms.expense_change, ms.is_final,
               ms.generated_at,
               (select count(*) from monthly_summary_actions a where a.summary_id = ms.id and a.status = 'OPEN') as open_actions
        from monthly_summaries ms where ms.user_id = %s order by ms.period_start desc
        """,
        (user_id,),
    ).fetchall()


def get_summary(conn: psycopg.Connection, user_id: str, summary_id: str) -> dict:
    try:
        row = conn.execute("select * from monthly_summaries where id = %s and user_id = %s", (summary_id, user_id)).fetchone()
    except psycopg.errors.InvalidTextRepresentation:
        conn.rollback()
        row = None
    if row is None:
        raise SummaryNotFound(summary_id)
    actions = conn.execute(
        """select id, action_key, title, description, priority, category, evidence, status, created_at, updated_at
           from monthly_summary_actions where summary_id = %s and user_id = %s
           order by (status = 'OPEN') desc, case priority when 'HIGH' then 0 when 'MEDIUM' then 1 else 2 end, created_at""",
        (summary_id, user_id),
    ).fetchall()
    return {**row, "actions": actions}


def summary_for_cycle(conn: psycopg.Connection, user_id: str, cycle_id: str) -> Optional[dict]:
    row = conn.execute("select id from monthly_summaries where financial_cycle_id = %s and user_id = %s", (cycle_id, user_id)).fetchone()
    return get_summary(conn, user_id, str(row["id"])) if row else None


def set_action_status(conn: psycopg.Connection, user_id: str, action_id: str, status: str) -> dict:
    if status not in ("OPEN", "COMPLETED", "DISMISSED"):
        raise ValueError("status must be OPEN, COMPLETED or DISMISSED")
    try:
        row = conn.execute(
            "update monthly_summary_actions set status = %s where id = %s and user_id = %s returning *", (status, action_id, user_id)
        ).fetchone()
    except psycopg.errors.InvalidTextRepresentation:
        conn.rollback()
        row = None
    if row is None:
        raise SummaryNotFound(action_id)
    return row


def open_actions(conn: psycopg.Connection, user_id: str, limit: int = 20) -> list[dict]:
    return conn.execute(
        """select a.id, a.title, a.description, a.priority, a.category, a.status, ms.title as summary_title, ms.id as summary_id
           from monthly_summary_actions a join monthly_summaries ms on ms.id = a.summary_id
           where a.user_id = %s and a.status = 'OPEN'
           order by ms.period_start desc, case a.priority when 'HIGH' then 0 when 'MEDIUM' then 1 else 2 end limit %s""",
        (user_id, limit),
    ).fetchall()
