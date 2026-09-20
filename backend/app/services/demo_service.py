"""Demo Bank Simulator: posts simulated bank events into the SAME ingest pipeline a real bank feed would use.

Every simulated transaction is flagged metadata.simulated = true so a demo can be reset without touching
seeded or user data. Amounts, balances, cycles and alerts are all calculated by the normal ledger code:
the simulator only supplies the event.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Optional

import psycopg

from app.demo.dataset import DEMO_NEXT_SALARY_TIME, IST
from app.providers.base import RawTransaction
from app.services import queries
from app.services.cycle_state import as_of
from app.services.alerts import evaluate_alerts
from app.services.ingest import IngestSummary, ingest
from app.services.insights import refresh_insights
from app.services.ledger_service import lock_account, rebuild_account
from app.services.recurring import refresh_recurring
from app.services.summaries import sync_summaries

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


# On the demo day, events after the salary land at these times (IST); after the list runs out, every 30 minutes.
DEMO_SLOTS = [time(11, 35), time(11, 40), time(12, 5)]


def default_timestamp(conn: psycopg.Connection, user_id: str, account_id: str, transaction_type: str) -> datetime:
    """Deterministic demo clock.

    * SALARY: 30 Sep 2026 11:27:04 IST (or 30 days after the latest salary if that one is already used).
    * Other events, once the demo salary has landed: 11:35, 11:40, 12:05, then every 30 minutes, always strictly after
      the latest entry, so the scripted demo reads Swiggy 11:35 AM, Rahul 11:40 AM, Amazon 12:05 PM.
    * Before the demo salary exists: 8 minutes after the latest entry (still inside the old cycle).
    """
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
    if latest is None:
        return DEMO_NEXT_SALARY_TIME
    if latest >= DEMO_NEXT_SALARY_TIME:  # the demo salary has landed: follow the scripted clock
        day = DEMO_NEXT_SALARY_TIME.replace(hour=0, minute=0, second=0, microsecond=0)
        for t in DEMO_SLOTS:
            slot = day.replace(hour=t.hour, minute=t.minute)
            if slot > latest:
                return slot
        return max(latest, day.replace(hour=12, minute=5)) + timedelta(minutes=30)
    return latest + STEP


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
    sync_summaries(conn, user_id, account_id)
    ensure_analytics(conn, user_id, account_id)
    return {"removed": removed, "balance": rb.balance}


CASHFLOW_DEMO_BALANCE = Decimal("1000")
CASHFLOW_DEMO_PAYMENT = Decimal("2000")
CASHFLOW_DEMO_DAYS = 5


def setup_cashflow_scenario(conn: psycopg.Connection, user_id: str, account_id: str) -> dict:
    """Demo data for the cash-flow warning: balance Rs 1,000, a Rs 2,000 subscription due in 5 days, no salary before it.

    The subscription is made REAL history the normal way: three simulated monthly payments (90, 60 and 30 days before
    the due date), which recurring detection then picks up. The balance is brought down with a transfer to the user's
    own savings account. Everything is flagged simulated, so "Reset" removes it. Other simulated events are cleared
    first so the scenario is always the same.
    """
    reset_simulated(conn, user_id, account_id)
    now = as_of(conn, user_id, account_id)
    due = (now + timedelta(days=CASHFLOW_DEMO_DAYS)).astimezone(IST).replace(hour=10, minute=0, second=0, microsecond=0)
    for days_before in (90, 60, 30):
        simulate_transaction(
            conn, user_id=user_id, account_id=account_id, transaction_type="EXPENSE", amount=CASHFLOW_DEMO_PAYMENT,
            merchant="CloudVault Pro", description="CLOUDVAULT PRO SUBSCRIPTION", category="Subscriptions",
            timestamp=due - timedelta(days=days_before),
        )
    balance = queries.get_account(conn, user_id, account_id)["current_balance"]
    if balance > CASHFLOW_DEMO_BALANCE:
        simulate_transaction(
            conn, user_id=user_id, account_id=account_id, transaction_type="TRANSFER_OUT",
            amount=balance - CASHFLOW_DEMO_BALANCE, timestamp=max(now, due - timedelta(days=CASHFLOW_DEMO_DAYS)) + timedelta(minutes=1),
        )
    ensure_analytics(conn, user_id, account_id)
    from app.services.cashflow_risk import check_upcoming_financial_risk  # local import: avoids a demo <-> risk cycle at import time
    return check_upcoming_financial_risk(conn, user_id, account_id)


def ensure_analytics(conn: psycopg.Connection, user_id: str, account_id: str) -> None:
    """Populate insights/alerts for an account whose ledger was loaded by SQL seed (nothing ran the ingest pipeline)."""
    cycle = queries.active_cycle(conn, user_id, account_id)
    if cycle is None:
        return
    sync_summaries(conn, user_id, account_id)  # summaries for closed cycles loaded by seed or import
    has = conn.execute(
        "select 1 from financial_insights where user_id = %s and financial_cycle_id = %s limit 1", (user_id, cycle["id"])
    ).fetchone()
    if not has:
        evaluate_alerts(conn, user_id, account_id, inserted=[], new_cycle_ids=[])
        refresh_insights(conn, user_id, account_id)
