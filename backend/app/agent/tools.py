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
from app.services.budgets import budget_status
from app.services.comparison import compare_cycles, cycle_summary, progress_vs_previous
from app.services.cycle_state import as_of, cycle_label, get_target, savings_progress_for
from app.services.dashboard import upcoming_obligations
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

    def get_monthly_summary(month: Optional[str] = None) -> dict:
        """Totals for a CALENDAR month (YYYY-MM, default current). Note this is not a salary cycle; for the
        salary-to-salary period use get_current_cycle_summary."""
        def body(c, a):
            now = as_of(c, ctx.user_id, str(a["id"])).astimezone(tz)
            y, m = (int(x) for x in month.split("-")) if month else (now.year, now.month)
            start = datetime(y, m, 1, tzinfo=tz)
            end = datetime(y + (m == 12), 1 if m == 12 else m + 1, 1, tzinfo=tz)
            row = c.execute(
                """
                select coalesce(sum(amount) filter (where transaction_type in ('SALARY','OTHER_INCOME','INTEREST')), 0) as income,
                       coalesce(sum(amount) filter (where transaction_type = 'TRANSFER_IN'), 0) as other_inflows,
                       coalesce(sum(amount) filter (where transaction_type = 'REFUND'), 0) as refunds,
                       coalesce(sum(amount) filter (where transaction_type = 'EXPENSE'), 0) as expenses,
                       count(*) as transaction_count
                from transactions where user_id = %s and account_id = %s and "timestamp" >= %s and "timestamp" < %s
                """,
                (ctx.user_id, str(a["id"]), start, end),
            ).fetchone()
            cats = c.execute(
                """select category, sum(amount) as total from transactions
                   where user_id = %s and account_id = %s and transaction_type = 'EXPENSE' and "timestamp" >= %s and "timestamp" < %s
                   group by category order by total desc""",
                (ctx.user_id, str(a["id"]), start, end),
            ).fetchall()
            if row["transaction_count"] == 0:
                return {"month": f"{y}-{m:02d}", "message": "No transactions in this calendar month."}
            return {"month": f"{y}-{m:02d}", "type": "calendar_month", **row, "categories": cats}
        return run("get_monthly_summary", body)

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

    fns = [
        get_current_balance, get_current_cycle, get_current_cycle_summary, get_transaction_history,
        get_transactions_between_dates, get_monthly_summary, (compare_cycles_tool, "compare_cycles"), compare_categories,
        get_recurring_payments, get_budget_status, get_savings_target, get_savings_progress,
        get_recent_large_transactions, get_unusual_transactions, get_previous_cycle_total,
        get_remaining_before_previous_cycle, (get_upcoming_obligations_tool, "get_upcoming_obligations"),
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
