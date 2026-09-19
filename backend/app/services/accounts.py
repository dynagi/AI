"""Accounts, consents and data-source connection flows."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

import psycopg

from app.demo.dataset import DEMO_OPENING_BALANCE
from app.logging_utils import log_event
from app.providers.registry import get_provider
from app.services import queries
from app.services.ingest import IngestSummary, ingest, touch_data_source
from app.services.ledger_service import lock_account

PROVIDER_ACCOUNT_DEFAULTS = {
    "demo_bank": dict(name="Demo Bank Account", source="demo", opening=DEMO_OPENING_BALANCE, ds="demo_bank", label="Demo Bank (Sandbox)"),
    "aa_sandbox": dict(name="AA Sandbox Account", source="bank", opening=Decimal("0"), ds="aa_sandbox", label="Account Aggregator Sandbox"),
}


class ConsentError(Exception):
    pass


def create_manual_account(conn: psycopg.Connection, user_id: str, name: str, opening_balance: Decimal) -> dict:
    row = conn.execute(
        """
        insert into financial_accounts (user_id, name, account_type, currency, current_balance, opening_balance, source, status)
        values (%s, %s, 'manual', 'INR', %s, %s, 'manual', 'ACTIVE') returning *
        """,
        (user_id, name, opening_balance, opening_balance),
    ).fetchone()
    conn.execute(
        "insert into data_sources (user_id, account_id, source_type, label, record_count) values (%s, %s, 'manual', 'Manual Transactions', 0)",
        (user_id, row["id"]),
    )
    log_event("account.created", user_id=user_id, account_id=str(row["id"]), source="manual")
    return row


def request_consent(conn: psycopg.Connection, user_id: str, provider_id: str) -> dict:
    if provider_id not in PROVIDER_ACCOUNT_DEFAULTS:
        raise ConsentError("Unknown provider.")
    existing = conn.execute(
        """select 1 from financial_accounts where user_id = %s and status = 'ACTIVE' and source = %s""",
        (user_id, PROVIDER_ACCOUNT_DEFAULTS[provider_id]["source"]),
    ).fetchone()
    if existing:
        raise ConsentError("This account is already connected.")
    provider = get_provider(provider_id)
    to_date = date.today()
    from_date = to_date - timedelta(days=210)
    purpose = "View your transaction history to power spending insights, budgets, savings tracking and recurring-payment detection."
    req = provider.create_consent_request(user_id, purpose, from_date, to_date, "daily")
    row = conn.execute(
        """
        insert into consents (user_id, provider, status, purpose, from_date, to_date, fetch_frequency, external_ref)
        values (%s, %s, 'PENDING', %s, %s, %s, 'daily', %s) returning *
        """,
        (user_id, provider_id, purpose, from_date, to_date, req.external_ref),
    ).fetchone()
    return {
        "consent_id": str(row["id"]), "provider": provider_id, "account_label": req.account_label,
        "is_sandbox": req.is_sandbox, "purpose": purpose, "data_requested": "Transaction history",
        "from_date": from_date, "to_date": to_date, "fetch_frequency": "daily",
    }


def decide_consent(conn: psycopg.Connection, user_id: str, consent_id: str, approve: bool) -> dict:
    consent = conn.execute(
        "select * from consents where id = %s and user_id = %s for update", (consent_id, user_id)
    ).fetchone()
    if consent is None:
        raise ConsentError("This consent request could not be found.")
    if consent["status"] != "PENDING":
        raise ConsentError("This consent has already been decided.")

    if not approve:
        conn.execute("update consents set status = 'REJECTED' where id = %s and user_id = %s", (consent_id, user_id))
        log_event("consent.rejected", user_id=user_id, consent_id=consent_id)
        return {"status": "REJECTED"}

    provider = get_provider(consent["provider"])
    defaults = PROVIDER_ACCOUNT_DEFAULTS[consent["provider"]]
    session = provider.create_data_session(consent["external_ref"])  # raises if the provider is unavailable
    raws = provider.fetch_transactions(session.account_ref, consent["from_date"], consent["to_date"])

    acct = conn.execute(
        """
        insert into financial_accounts (user_id, name, account_type, currency, current_balance, opening_balance, source, status, last_synced_at)
        values (%s, %s, 'savings', 'INR', %s, %s, %s, 'ACTIVE', now()) returning *
        """,
        (user_id, defaults["name"], defaults["opening"], defaults["opening"], defaults["source"]),
    ).fetchone()
    aid = str(acct["id"])
    conn.execute(
        "update consents set status = 'APPROVED', approved_at = now(), account_id = %s where id = %s and user_id = %s",
        (aid, consent_id, user_id),
    )
    log_event("consent.approved", user_id=user_id, consent_id=consent_id)

    summary = ingest(conn, user_id=user_id, account_id=aid, raws=raws, source=provider.source_tag)
    touch_data_source(conn, user_id, aid, defaults["ds"], defaults["label"], summary.inserted)
    from app.services.demo_service import ensure_analytics

    ensure_analytics(conn, user_id, aid)
    return {"status": "APPROVED", "account_id": aid, "inserted": summary.inserted, "duplicates": summary.duplicates,
            "malformed": summary.malformed}


def refresh_account(conn: psycopg.Connection, user_id: str, account_id: str) -> IngestSummary:
    acct = queries.get_account(conn, user_id, account_id)
    if acct is None:
        raise ConsentError("Account not found.")
    if acct["status"] != "ACTIVE":
        raise ConsentError("This account is disconnected. Reconnect it to refresh data.")
    provider_id = {"demo": "demo_bank", "bank": "aa_sandbox"}.get(acct["source"])
    if provider_id is None:
        raise ConsentError("Manual accounts have nothing to refresh.")
    provider = get_provider(provider_id)
    raws = provider.refresh_data(str(acct["id"]))
    summary = ingest(conn, user_id=user_id, account_id=account_id, raws=raws, source=provider.source_tag)
    touch_data_source(conn, user_id, account_id, PROVIDER_ACCOUNT_DEFAULTS[provider_id]["ds"], PROVIDER_ACCOUNT_DEFAULTS[provider_id]["label"], summary.inserted)
    return summary


def disconnect_account(conn: psycopg.Connection, user_id: str, account_id: str) -> None:
    acct = lock_account(conn, user_id, account_id, require_active=False)
    provider_id = {"demo": "demo_bank", "bank": "aa_sandbox"}.get(acct["source"])
    if provider_id:
        try:
            get_provider(provider_id).disconnect_account(str(acct["id"]))
        except Exception as exc:  # provider unreachable: still disconnect locally, keep the data
            log_event("account.disconnect_provider_failed", user_id=user_id, error=str(exc))
    conn.execute("update financial_accounts set status = 'DISCONNECTED' where id = %s and user_id = %s", (account_id, user_id))
    conn.execute("update data_sources set status = 'DISCONNECTED' where account_id = %s and user_id = %s and source_type <> 'manual'", (account_id, user_id))
    conn.execute("update consents set status = 'REVOKED' where account_id = %s and user_id = %s and status = 'APPROVED'", (account_id, user_id))
    log_event("account.disconnected", user_id=user_id, account_id=account_id)
