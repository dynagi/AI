"""The agent's tool layer: the ONLY way the model can see financial data.

  * Every tool is bound to the authenticated user's id (from the verified JWT) when the tool set is built.
    No tool takes a user id, so the model cannot ask for anyone else's data. Cycle ids it passes are
    checked against that user before use.
  * Every number comes from a database query or the deterministic services (never from the model).
  * A tool that has nothing to report says so explicitly instead of returning something made up.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Callable, Optional
from zoneinfo import ZoneInfo

import psycopg
from langchain_core.tools import StructuredTool

from app.agent.serialize import jsonable
from app.config import get_settings
from app.logging_utils import log_event
from app.services import queries
from app.services.analytics import daily_spending, monthly_trends
from app.services.budgets import budget_commitments, budget_status
from app.services.goals import goals_overview
from app.services.comparison import compare_cycles, cycle_summary, progress_vs_previous
from app.services.cycle_state import as_of, cycle_label, get_target, savings_progress_for
from app.services.cashflow_risk import check_upcoming_financial_risk
from app.services.dashboard import upcoming_obligations
from app.services.engagement import build_briefing, simulate_purchase
from app.services.recurring import list_recurring

ConnFactory = Callable[[], AbstractContextManager]


@dataclass
class ToolContext:
    user_id: str
    connect: ConnFactory
    account_id: Optional[str] = None


NO_ACCOUNT = {"error": "no_account", "message": "This user has no connected or manual account yet, so there is no financial data."}
NO_CYCLE = {"error": "no_cycle", "message": "There is no financial cycle yet (no salary or transactions have been recorded)."}


def _resolve_cycle(conn: psycopg.Connection, ctx: ToolContext, account: dict, ref: Optional[str]):
    active = queries.active_cycle(conn, ctx.user_id, str(account["id"]))
    if ref in (None, "", "current"):
        return active
    if ref == "previous":
        return queries.previous_cycle(conn, ctx.user_id, active) if active else None
    try:
        cyc = queries.get_cycle(conn, ctx.user_id, ref)  # scoped by user_id: another user's id resolves to None
    except psycopg.Error:
        conn.rollback()
        return None
    return cyc


def build_tools(ctx: ToolContext) -> list[StructuredTool]:
    tz = ZoneInfo(get_settings().app_timezone)

    def run(name: str, body: Callable[[psycopg.Connection, dict], object]):
        log_event("agent.tool_invoked", user_id=ctx.user_id, tool=name)
        try:
            with ctx.connect() as conn:
                account = queries.primary_account(conn, ctx.user_id, ctx.account_id)
                if account is None:
                    return NO_ACCOUNT
                return jsonable(body(conn, account))
        except Exception as exc:  # never leak internals to the model; it will report the failure
            log_event("agent.tool_error", user_id=ctx.user_id, tool=name, error=type(exc).__name__)
            return {"error": "tool_failed", "message": f"{name} could not be completed."}

    def with_cycle(name: str, ref: Optional[str], body: Callable[[psycopg.Connection, dict, dict], object]):
        def inner(conn, account):
            cyc = _resolve_cycle(conn, ctx, account, ref)
            if cyc is None:
                return {**NO_CYCLE, "requested": ref or "current"}
            return body(conn, account, cyc)

        return run(name, inner)

    # ------------------------------------------------------------------ tools

    def get_current_balance() -> dict:
        """Current balance of the user's account right now. This is money in the account, NOT income."""
        return run("get_current_balance", lambda c, a: {
            "account_name": a["name"], "currency": a["currency"], "current_balance": a["current_balance"],
            "opening_balance": a["opening_balance"], "as_of": as_of(c, ctx.user_id, str(a["id"])),
            "last_synced_at": a["last_synced_at"],
        })

    def get_current_cycle() -> dict:
        """The active financial cycle (salary-to-salary period): when it started, the balance right after the
        salary, and the balance that was already there before the salary."""
        def body(c, a):
            cyc = queries.active_cycle(c, ctx.user_id, str(a["id"]))
            if cyc is None:
                return NO_CYCLE
            now = as_of(c, ctx.user_id, str(a["id"]))
            return {
                "cycle_id": str(cyc["id"]), "label": cycle_label(cyc, tz), "status": cyc["status"],
                "start_at": cyc["start_at"], "starts_with_salary": cyc["salary_transaction_id"] is not None,
                "opening_balance_after_salary": cyc["opening_balance"],
                "balance_carried_over_before_salary": cyc["carried_over_balance"],
                "days_elapsed": round((now - cyc["start_at"]).total_seconds() / 86400, 2),
            }
        return run("get_current_cycle", body)

    def get_current_cycle_summary() -> dict:
        """Income, expenses, refunds, other inflows, savings and category breakdown for the CURRENT financial
        cycle. Use this for 'how much have I spent this month/cycle'. Never sum all-time history instead."""
        return with_cycle("get_current_cycle_summary", "current", lambda c, a, cyc: cycle_summary(c, ctx.user_id, cyc))

    def get_transaction_history(limit: int = 20, category: Optional[str] = None, cycle: str = "current") -> dict:
        """Recent transactions (newest first) with amounts, direction and balance after each. `cycle` is
        'current', 'previous', 'all', or a cycle id. `category` filters by category name."""
        def body(c, a):
            cid = None
            if cycle != "all":
                cyc = _resolve_cycle(c, ctx, a, cycle)
                if cyc is None:
                    return {**NO_CYCLE, "requested": cycle}
                cid = str(cyc["id"])
            rows = queries.list_transactions(c, ctx.user_id, account_id=str(a["id"]), cycle_id=cid, category=category, limit=min(limit, 100))
            return {"count": len(rows), "transactions": [_txn(r) for r in rows]}
        return run("get_transaction_history", body)

    def get_transactions_between_dates(start_date: str, end_date: str, category: Optional[str] = None, limit: int = 50) -> dict:
        """Transactions from start_date up to and including end_date (YYYY-MM-DD, India time)."""
        def body(c, a):
            s = datetime.fromisoformat(start_date).replace(tzinfo=tz)
            e = datetime.fromisoformat(end_date).replace(tzinfo=tz) + timedelta(days=1)
            rows = queries.list_transactions(c, ctx.user_id, account_id=str(a["id"]), start=s, end=e, category=category, limit=min(limit, 200))
            return {"start_date": start_date, "end_date": end_date, "count": len(rows), "transactions": [_txn(r) for r in rows]}
        return run("get_transactions_between_dates", body)

    def get_category_breakdown(cycle: str = "current") -> dict:
        """Spending per category for a cycle ('current', 'previous' or a cycle id), largest first, with the share of expenses.
        Only categories with real transactions appear."""
        return with_cycle("get_category_breakdown", cycle, lambda c, a, cyc: {
            "cycle": cycle_label(cyc, tz), "total_expenses": cyc["expense_total"],
            "categories": cycle_summary(c, ctx.user_id, cyc)["categories"]})

    def get_monthly_summary(cycle: str = "previous") -> dict:
        """The stored monthly financial summary of a cycle ('previous' = last completed cycle, 'current', or a cycle id):
        overview, income, expenses, savings, savings rate, top categories, previous-cycle comparison, recurring commitments,
        unusual activity, goal progress, budget status, key observations and action items."""
        def body(c, a):
            cyc = _resolve_cycle(c, ctx, a, cycle)
            if cyc is None:
                return {**NO_CYCLE, "requested": cycle}
            from app.services import summaries as summ

            existing = summ.summary_for_cycle(c, ctx.user_id, str(cyc["id"]))
            if existing is None or (cyc["status"] == "ACTIVE"):
                summ.generate_summary(c, ctx.user_id, str(cyc["id"]))
                existing = summ.summary_for_cycle(c, ctx.user_id, str(cyc["id"]))
            content = existing["content"]
            return {
                "title": existing["title"], "is_final": existing["is_final"], "income": existing["income_total"],
                "expenses": existing["expense_total"], "savings": existing["savings_total"], "savings_rate": existing["savings_rate"],
                "top_category": existing["top_category"], "previous_cycle_expenses": existing["previous_cycle_expenses"],
                "expense_change": existing["expense_change"], "top_categories": content["top_categories"],
                "previous_comparison": content["previous_comparison"], "recurring": content["recurring"],
                "unusual_activity": content["unusual_activity"], "goals": content["goals"], "budgets": content["budgets"],
                "observations": [o["text"] for o in content["observations"]],
                "action_items": [{"title": x["title"], "description": x["description"], "priority": x["priority"], "status": x["status"]}
                                 for x in existing["actions"]],
            }
        return run("get_monthly_summary", body)

    def get_monthly_action_items(status: str = "OPEN") -> dict:
        """The user's data-driven action items from their monthly summaries (status OPEN, COMPLETED or DISMISSED)."""
        def body(c, a):
            from app.services import summaries as summ

            summ.sync_summaries(c, ctx.user_id, str(a["id"]))
            rows = c.execute(
                """select a.title, a.description, a.priority, a.category, a.status, ms.title as summary
                   from monthly_summary_actions a join monthly_summaries ms on ms.id = a.summary_id
                   where a.user_id = %s and a.status = %s
                   order by ms.period_start desc, case a.priority when 'HIGH' then 0 when 'MEDIUM' then 1 else 2 end limit 30""",
                (ctx.user_id, status.upper())).fetchall()
            return {"status": status.upper(), "count": len(rows), "items": rows} if rows else \
                {"status": status.upper(), "count": 0, "message": f"There are no {status.lower()} action items."}
        return run("get_monthly_action_items", body)

    def get_monthly_trends(limit: int = 6) -> dict:
        """Income, expenses, savings and top category for the last N financial cycles (oldest first), with each cycle's
        change versus the one before it. Use for 'show me my spending trend'."""
        return run("get_monthly_trends", lambda c, a: {"cycles": monthly_trends(c, ctx.user_id, str(a["id"]), min(max(limit, 2), 12))})

    def get_daily_spending(days: int = 7) -> dict:
        """Expense totals per calendar day for the last N days, plus today's and yesterday's totals and the average daily spend.
        Use for 'how much did I spend today / yesterday'."""
        return run("get_daily_spending", lambda c, a: daily_spending(c, ctx.user_id, str(a["id"]), min(max(days, 1), 60)))

    def get_budget_commitments() -> dict:
        """How much of the budget is already committed: money already spent + recurring payments still expected before the
        cycle ends, against the monthly spending limit (income minus savings target, else the sum of category budgets).
        Also the remaining flexible capacity, with the calculation explained."""
        return run("get_budget_commitments", lambda c, a: budget_commitments(c, ctx.user_id, str(a["id"])))

    def get_financial_goals() -> dict:
        """The user's long-term goals (purchase, emergency fund, travel, education, custom) with target, current amount,
        remaining, progress, target date, required monthly contribution and on-track status."""
        def body(c, a):
            ov = goals_overview(c, ctx.user_id, str(a["id"]))
            return ov if ov["goals"] else {"count": 0, "message": "The user has not created any financial goals."}
        return run("get_financial_goals", body)

    def _pick_goals(goals: list[dict], goal: Optional[str]) -> list[dict]:
        if not goal:
            return goals
        g = goal.strip().lower()
        return [x for x in goals if g == x["id"].lower() or g in x["name"].lower() or g.replace(" ", "_") == x["goal_type"].lower()]

    def get_goal_progress(goal: Optional[str] = None) -> dict:
        """Progress of one goal (name, e.g. 'laptop' or 'emergency fund') or all goals: amounts, percent complete, days left,
        status ON_TRACK / AT_RISK / BEHIND / COMPLETED and an explanation of how the current savings pace affects it."""
        def body(c, a):
            ov = goals_overview(c, ctx.user_id, str(a["id"]))
            picked = _pick_goals(ov["goals"], goal)
            if not picked:
                return {"count": 0, "message": "No matching goal was found." if goal else "The user has not created any financial goals."}
            return {"count": len(picked), "goals": picked}
        return run("get_goal_progress", body)

    def get_goal_projection(goal: Optional[str] = None) -> dict:
        """Projected completion for a goal (or all): required monthly contribution vs the monthly savings actually available
        from the user's own cycles (after higher-priority goals), and the projected completion date."""
        def body(c, a):
            ov = goals_overview(c, ctx.user_id, str(a["id"]))
            picked = _pick_goals(ov["goals"], goal)
            if not picked:
                return {"count": 0, "message": "No matching goal was found." if goal else "The user has not created any financial goals."}
            return {
                "combined": ov["combined"],
                "goals": [{k: g[k] for k in ("name", "goal_type", "status", "remaining_amount", "target_date", "days_remaining",
                                             "required_monthly_contribution", "allocated_monthly_savings",
                                             "projected_completion_date", "message")} for g in picked],
            }
        return run("get_goal_projection", body)

    def compare_cycles_tool(cycle_a: str = "previous", cycle_b: str = "current") -> dict:
        """Compare two financial cycles (default: previous vs current). Returns totals, differences (B minus A),
        category changes, largest transactions and a data-derived explanation."""
        def body(c, a):
            ca, cb = _resolve_cycle(c, ctx, a, cycle_a), _resolve_cycle(c, ctx, a, cycle_b)
            if ca is None or cb is None:
                return {"error": "cycle_not_found", "message": "One of the requested cycles does not exist (there may be no previous cycle yet)."}
            return compare_cycles(c, ctx.user_id, ca, cb)
        return run("compare_cycles", body)

    def compare_categories(cycle_a: str = "previous", cycle_b: str = "current") -> dict:
        """Category-by-category spending change between two cycles (default previous vs current), biggest movers first."""
        def body(c, a):
            ca, cb = _resolve_cycle(c, ctx, a, cycle_a), _resolve_cycle(c, ctx, a, cycle_b)
            if ca is None or cb is None:
                return {"error": "cycle_not_found", "message": "One of the requested cycles does not exist."}
            cmp = compare_cycles(c, ctx.user_id, ca, cb)
            return {"cycle_a": cmp["a"]["label"], "cycle_b": cmp["b"]["label"], "changes": cmp["category_changes"][:10]}
        return run("compare_categories", body)

    def get_recurring_payments() -> dict:
        """Recurring payments detected from history (>= 3 evenly spaced payments): merchant, average amount,
        frequency, last payment, next expected payment, confidence."""
        def body(c, a):
            rows = list_recurring(c, ctx.user_id)
            monthly = sum((r["average_amount"] for r in rows if r["frequency"] == "monthly"), Decimal("0"))
            return {"count": len(rows), "estimated_monthly_total": monthly, "payments": [
                {"merchant": r["merchant"], "category": r["category"], "average_amount": r["average_amount"], "frequency": r["frequency"],
                 "last_payment": r["last_payment"], "next_expected_payment": r["next_expected_payment"], "confidence": r["confidence"]}
                for r in rows]}
        return run("get_recurring_payments", body)

    def get_budget_status() -> dict:
        """Category budgets vs spending in the current cycle (budget, spent, remaining, percent used)."""
        def body(c, a):
            rows = budget_status(c, ctx.user_id, str(a["id"]))
            return {"count": len(rows), "budgets": rows} if rows else {"count": 0, "message": "The user has not set any category budgets."}
        return run("get_budget_status", body)

    def get_savings_target() -> dict:
        """The savings target the USER set for the current cycle (or that none has been set)."""
        def body(c, a):
            cyc = queries.active_cycle(c, ctx.user_id, str(a["id"]))
            if cyc is None:
                return NO_CYCLE
            t = get_target(c, ctx.user_id, str(cyc["id"]))
            return {"cycle_id": str(cyc["id"]), "target_set": t is not None, "target_amount": t} if t is not None else \
                {"cycle_id": str(cyc["id"]), "target_set": False, "message": "The user has not set a savings target for this cycle."}
        return run("get_savings_target", body)

    def get_savings_progress() -> dict:
        """Progress towards the current cycle's savings target: income, spending, planned spending limit,
        remaining capacity, estimated and projected savings, and ON_TRACK / AT_RISK / NO_TARGET status."""
        return with_cycle("get_savings_progress", "current", lambda c, a, cyc: savings_progress_for(c, ctx.user_id, cyc).as_dict())

    def get_recent_large_transactions(limit: int = 5, cycle: str = "current") -> dict:
        """The largest expenses in a cycle (default current), biggest first."""
        return with_cycle("get_recent_large_transactions", cycle, lambda c, a, cyc: {
            "cycle": cycle_label(cyc, tz),
            "transactions": [{"id": str(t["id"]), "timestamp": t["timestamp"], "merchant": t["merchant"], "description": t["description"],
                              "amount": t["amount"], "category": t["category"]} for t in queries.largest_expenses(c, ctx.user_id, str(cyc["id"]), min(limit, 20))]})

    def get_unusual_transactions() -> dict:
        """Unusual activity detected in the current cycle (high single-day spending, large transactions, category
        spikes vs the user's own average). Each item lists the evidence it was based on."""
        def body(c, a):
            cyc = queries.active_cycle(c, ctx.user_id, str(a["id"]))
            if cyc is None:
                return NO_CYCLE
            rows = c.execute(
                """select alert_type, severity, title, message, evidence, created_at from agent_alerts
                   where user_id = %s and financial_cycle_id = %s
                     and alert_type in ('HIGH_SPENDING','LARGE_TRANSACTION','CATEGORY_SPIKE') order by created_at desc""",
                (ctx.user_id, str(cyc["id"]))).fetchall()
            return {"count": len(rows), "items": rows} if rows else {"count": 0, "message": "Nothing unusual has been detected in the current cycle."}
        return run("get_unusual_transactions", body)

    def get_previous_cycle_total() -> dict:
        """Total income, expenses and savings of the previous (closed) cycle."""
        def body(c, a):
            cyc = queries.active_cycle(c, ctx.user_id, str(a["id"]))
            prev = queries.previous_cycle(c, ctx.user_id, cyc) if cyc else None
            if prev is None:
                return {"error": "no_previous_cycle", "message": "There is no previous cycle to compare with yet."}
            s = cycle_summary(c, ctx.user_id, prev)
            return {k: s[k] for k in ("id", "label", "status", "income", "expenses", "refunds", "net_spend", "savings", "savings_rate", "top_categories")}
        return run("get_previous_cycle_total", body)

    def get_remaining_before_previous_cycle() -> dict:
        """How much more the user can spend this cycle before reaching the previous cycle's total expenses
        (or by how much it has already been exceeded)."""
        def body(c, a):
            cyc = queries.active_cycle(c, ctx.user_id, str(a["id"]))
            if cyc is None:
                return NO_CYCLE
            prev = queries.previous_cycle(c, ctx.user_id, cyc)
            res = progress_vs_previous(cycle_summary(c, ctx.user_id, cyc), prev)
            return res or {"error": "no_previous_cycle", "message": "There is no previous cycle to compare with yet."}
        return run("get_remaining_before_previous_cycle", body)

    def get_upcoming_obligations_tool(within_days: int = 30) -> dict:
        """Recurring payments expected within the next N days (default 30) and their total."""
        return run("get_upcoming_obligations", lambda c, a: upcoming_obligations(c, ctx.user_id, str(a["id"]), within_days))

    def get_upcoming_financial_risks(within_days: int = 30) -> dict:
        """Cash-flow check of upcoming recurring payments: risk_level (SAFE/WATCH/AT_RISK/SHORTFALL), current balance,
        each upcoming payment with due date and days remaining, expected income (salary) before the payments,
        projected balance, safety buffer, savings-target impact, budget impact and a ready warning_message.
        Use for 'do I have upcoming payments', 'will I have enough for my subscriptions', 'can I afford my bills'.
        Read-only: FinPilot never pays, cancels or moves money."""
        return run("get_upcoming_financial_risks", lambda c, a: check_upcoming_financial_risk(c, ctx.user_id, str(a["id"]), within_days))

    def simulate_purchase_tool(amount: float, label: str = "Purchase", days_from_now: int = 0) -> dict:
        """WHAT-IF: how a hypothetical one-off spend of `amount` rupees (called `label`, `days_from_now` days ahead, 0 = today)
        would change the user's cash-flow risk level, lowest balance, savings target and budget. Hypothetical only:
        nothing is recorded or paid. Use for 'what if I buy...' and 'can I afford...' questions."""
        amt = Decimal(str(amount))
        if amt <= 0 or amt > Decimal("1e10"):
            return {"error": "invalid_amount", "message": "The amount must be greater than zero."}
        days = max(0, min(int(days_from_now), 90))
        return run("simulate_purchase", lambda c, a: simulate_purchase(c, ctx.user_id, str(a["id"]), amt, label, days))

    def get_daily_briefing() -> dict:
        """Today's short briefing: cash-flow risk, next payment, spending streak (days in a row under the user's usual
        non-recurring daily spend), badge, no-spend days and savings status."""
        return run("get_daily_briefing", lambda c, a: build_briefing(c, ctx.user_id, str(a["id"])))

    fns = [
        get_current_balance, get_current_cycle, get_current_cycle_summary, get_transaction_history,
        get_transactions_between_dates, get_category_breakdown, (compare_cycles_tool, "compare_cycles"), compare_categories,
        get_previous_cycle_total, get_remaining_before_previous_cycle, get_recurring_payments,
        (get_upcoming_obligations_tool, "get_upcoming_obligations"), get_budget_status, get_budget_commitments,
        get_financial_goals, get_goal_progress, get_goal_projection, get_savings_target, get_savings_progress,
        get_recent_large_transactions, get_unusual_transactions, get_monthly_summary, get_monthly_trends,
        get_daily_spending, get_monthly_action_items, get_upcoming_financial_risks,
        (simulate_purchase_tool, "simulate_purchase"), get_daily_briefing,
    ]
    tools = []
    for f in fns:
        fn, name = f if isinstance(f, tuple) else (f, f.__name__)
        tools.append(StructuredTool.from_function(func=fn, name=name, description=(fn.__doc__ or "").strip()))
    return tools


def _txn(r: dict) -> dict:
    return {
        "id": str(r["id"]), "timestamp": r["timestamp"], "merchant": r["merchant"], "description": r["description"],
        "transaction_type": r["transaction_type"], "direction": "in" if r["signed_amount"] > 0 else "out",
        "amount": r["amount"], "signed_amount": r["signed_amount"], "category": r["category"],
        "balance_after": r["balance_after"], "is_recurring": r["is_recurring"],
    }
