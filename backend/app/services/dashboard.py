"""Dashboard read model. Every number returned here is read from Supabase-stored ledger data."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Optional

import psycopg

from app.services import queries
from app.services.alerts import list_alerts
from app.services.cashflow_risk import check_upcoming_financial_risk
from app.services.budgets import budget_commitments, budget_status
from app.services.comparison import cycle_summary, progress_vs_previous
from app.services.cycle_state import as_of, savings_progress_for
from app.services.goals import goals_overview
from app.services.insights import list_insights
from app.services.recurring import list_recurring
from app.services.summaries import list_summaries, open_actions


def upcoming_obligations(conn: psycopg.Connection, user_id: str, account_id: str, within_days: int = 30) -> dict:
    now = as_of(conn, user_id, account_id)
    cutoff = now + timedelta(days=within_days)
    rows = [r for r in list_recurring(conn, user_id) if now <= r["next_expected_payment"] <= cutoff]
    rows.sort(key=lambda r: r["next_expected_payment"])
    return {
        "within_days": within_days,
        "total": sum((r["average_amount"] for r in rows), Decimal("0")),
        "items": [
            {"merchant": r["merchant"], "category": r["category"], "amount": r["average_amount"],
             "frequency": r["frequency"], "expected_at": r["next_expected_payment"], "confidence": r["confidence"]}
            for r in rows
        ],
    }


def build_dashboard(conn: psycopg.Connection, user_id: str, account_id: Optional[str] = None) -> dict:
    account = queries.primary_account(conn, user_id, account_id)
    if account is None:
        return {"account": None}
    aid = str(account["id"])
    cycle = queries.active_cycle(conn, user_id, aid)

    out: dict = {
        "account": {
            "id": aid, "name": account["name"], "source": account["source"], "currency": account["currency"],
            "status": account["status"], "current_balance": account["current_balance"],
            "opening_balance": account["opening_balance"], "last_synced_at": account["last_synced_at"],
        },
        "as_of": as_of(conn, user_id, aid),
        "cycle": None,
        "previous_cycle": None,
        "progress_vs_previous": None,
        "savings": None,
        "spending_progress": None,
    }

    if cycle is not None:
        summary = cycle_summary(conn, user_id, cycle)
        prev = queries.previous_cycle(conn, user_id, cycle)
        progress = savings_progress_for(conn, user_id, cycle)
        out["cycle"] = summary
        out["previous_cycle"] = cycle_summary(conn, user_id, prev) if prev else None
        out["progress_vs_previous"] = progress_vs_previous(summary, prev)
        out["savings"] = {**progress.as_dict(), "needs_target": progress.status == "NO_TARGET"}
        out["spending_progress"] = {
            "spent": summary["expenses"],
            "net_spend": summary["net_spend"],
            "planned_spend_limit": progress.planned_spend_limit,
            "percent_of_limit": (
                round(float(summary["net_spend"] / progress.planned_spend_limit * 100), 1)
                if progress.planned_spend_limit else None
            ),
        }

    out["insights"] = list_insights(conn, user_id, limit=8)
    out["alerts"] = list_alerts(conn, user_id, limit=8)
    out["unread_alert_count"] = sum(1 for a in out["alerts"] if not a["is_read"])
    out["budgets"] = budget_status(conn, user_id, aid)
    recurring = list_recurring(conn, user_id)
    out["recurring"] = {
        "count": len(recurring),
        "monthly_total": sum((r["average_amount"] for r in recurring if r["frequency"] == "monthly"), Decimal("0")),
    }
    out["upcoming_obligations"] = upcoming_obligations(conn, user_id, aid)
    out["cashflow_risk"] = check_upcoming_financial_risk(conn, user_id, aid)
    out["recent_transactions"] = queries.list_transactions(conn, user_id, account_id=aid, limit=12)

    goals = goals_overview(conn, user_id, aid)
    out["goals"] = goals["goals"]
    out["goals_combined"] = goals["combined"]
    out["commitments"] = budget_commitments(conn, user_id, aid)
    summaries = list_summaries(conn, user_id)
    out["latest_summary"] = (
        {"id": str(summaries[0]["id"]), "title": summaries[0]["title"], "is_final": summaries[0]["is_final"]} if summaries else None
    )
    out["open_action_count"] = len(open_actions(conn, user_id, limit=100))
    return out
