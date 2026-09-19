"""Demo Bank Simulator: posts simulated bank events into the SAME ingest pipeline a real bank feed would use.

Every simulated transaction is flagged metadata.simulated = true so a demo can be reset without touching
seeded or user data. Amounts, balances, cycles and alerts are all calculated by the normal ledger code:
the simulator only supplies the event.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import psycopg

from app.demo.dataset import DEMO_NEXT_SALARY_TIME
from app.providers.base import RawTransaction
from app.services import queries
from app.services.alerts import evaluate_alerts
from app.services.ingest import IngestSummary, ingest
from app.services.insights import refresh_insights
from app.services.ledger_service import lock_account, rebuild_account
from app.services.recurring import refresh_recurring

DEFAULT_MERCHANTS = {
    "SALARY": ("Employer Pvt Ltd", "SALARY CREDIT - EMPLOYER PVT LTD"),
    "TRANSFER_IN": ("Rahul", "Money received from Rahul"),
    "EXPENSE": ("Swiggy", "SWIGGY PAYMENT"),
    "REFUND": ("Amazon", "REFUND - AMAZON ORDER RETURN"),
    "OTHER_INCOME": ("Freelance Client", "FREELANCE PAYMENT"),
    "TRANSFER_OUT": ("Own Savings Account", "TRANSFER TO OWN SAVINGS"),
    "INTEREST": ("Demo Bank", "SAVINGS INTEREST CREDIT"),
}
STEP = timedelta(minutes=8)


def default_timestamp(conn: psycopg.Connection, user_id: str, account_id: str, transaction_type: str) -> datetime:
    """Deterministic demo clock: salary at 30 Sep 2026 11:27:04 IST, other events 8 minutes after the latest entry."""
    latest = conn.execute(
        'select max("timestamp") as ts from transactions where user_id = %s and account_id = %s', (user_id, account_id)
    ).fetchone()["ts"]
    if transaction_type == "SALARY":
        last_salary = conn.execute(
            """select max("timestamp") as ts from transactions
               where user_id = %s and account_id = %s and transaction_type = 'SALARY'""",
            (user_id, account_id),
        ).fetchone()["ts"]
        if last_salary is None or DEMO_NEXT_SALARY_TIME > last_salary:
            return DEMO_NEXT_SALARY_TIME
        return last_salary + timedelta(days=30)
    return (latest + STEP) if latest else DEMO_NEXT_SALARY_TIME


def simulate_transaction(
    conn: psycopg.Connection,
    *,
    user_id: str,
    account_id: str,
    transaction_type: str,
    amount: Decimal,
    merchant: Optional[str] = None,
    description: Optional[str] = None,
    timestamp: Optional[datetime] = None,
    category: Optional[str] = None,
) -> IngestSummary:
    lock_account(conn, user_id, account_id)
    ts = timestamp or default_timestamp(conn, user_id, account_id, transaction_type)
    d_merchant, d_desc = DEFAULT_MERCHANTS.get(transaction_type, (None, transaction_type.title()))
    merchant = merchant or d_merchant
    if description:
        desc = description
    elif merchant and merchant != d_merchant:
        desc = f"{merchant.upper()} {'PAYMENT' if transaction_type == 'EXPENSE' else transaction_type.replace('_', ' ')}"
    else:
        desc = d_desc
    raw = RawTransaction(
        timestamp=ts, description=desc, merchant=merchant, amount=amount, transaction_type=transaction_type,
        category=category, metadata={"simulated": True},
    )
    return ingest(conn, user_id=user_id, account_id=account_id, raws=[raw], source="demo")


def reset_simulated(conn: psycopg.Connection, user_id: str, account_id: str) -> dict:
    """Remove ONLY simulator-created transactions (metadata.simulated) and rebuild. Seeded/user data is untouched.

    Alerts and insights are derived data, so they are regenerated rather than patched.
    """
    lock_account(conn, user_id, account_id, require_active=False)
    removed = conn.execute(
        "delete from transactions where user_id = %s and account_id = %s and metadata ->> 'simulated' = 'true'",
        (user_id, account_id),
    ).rowcount
    rb = rebuild_account(conn, user_id, account_id)
    conn.execute("delete from agent_alerts where user_id = %s", (user_id,))
    conn.execute("delete from financial_insights where user_id = %s", (user_id,))
    refresh_recurring(conn, user_id, account_id)
    ensure_analytics(conn, user_id, account_id)
    return {"removed": removed, "balance": rb.balance}


def ensure_analytics(conn: psycopg.Connection, user_id: str, account_id: str) -> None:
    """Populate insights/alerts for an account whose ledger was loaded by SQL seed (nothing ran the ingest pipeline)."""
    cycle = queries.active_cycle(conn, user_id, account_id)
    if cycle is None:
        return
    has = conn.execute(
        "select 1 from financial_insights where user_id = %s and financial_cycle_id = %s limit 1", (user_id, cycle["id"])
    ).fetchone()
    if not has:
        evaluate_alerts(conn, user_id, account_id, inserted=[], new_cycle_ids=[])
        refresh_insights(conn, user_id, account_id)
