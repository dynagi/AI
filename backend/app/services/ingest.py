"""The one door into the ledger.

Bank/AA data, the Demo Bank Simulator, manual entries and CSV imports ALL come
through `ingest()`. There is no CSV-only or bank-only data model:

    RawTransaction -> normalize -> insert -> rebuild balances & cycles
                   -> recurring detection -> alerts -> insights -> (Supabase Realtime)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

import psycopg

from app.logging_utils import log_event
from app.providers.base import RawTransaction
from app.services.alerts import evaluate_alerts, upsert_alert
from app.services.categorization import Categorizer
from app.services.insights import refresh_insights
from app.services.ledger_service import InsertedTxn, insert_transactions, lock_account, rebuild_account
from app.services.normalizer import MalformedTransaction, normalize
from app.services.recurring import refresh_recurring
from app.services.summaries import sync_summaries


@dataclass
class IngestSummary:
    inserted: int = 0
    duplicates: int = 0
    malformed: int = 0
    errors: list[str] = field(default_factory=list)
    balance: Optional[Decimal] = None
    new_cycle_started: bool = False
    active_cycle_id: Optional[str] = None
    inserted_transactions: list[InsertedTxn] = field(default_factory=list)
    alerts: list[dict] = field(default_factory=list)


def touch_data_source(
    conn: psycopg.Connection, user_id: str, account_id: str, source_type: str, label: str, added: int
) -> None:
    row = conn.execute(
        "select id from data_sources where user_id = %s and account_id = %s and source_type = %s",
        (user_id, account_id, source_type),
    ).fetchone()
    if row:
        conn.execute(
            "update data_sources set record_count = record_count + %s, last_synced_at = now(), status = 'ACTIVE' where id = %s and user_id = %s",
            (added, row["id"], user_id),
        )
    else:
        conn.execute(
            "insert into data_sources (user_id, account_id, source_type, label, record_count, last_synced_at) values (%s, %s, %s, %s, %s, now())",
            (user_id, account_id, source_type, label, added),
        )


def ingest(
    conn: psycopg.Connection,
    *,
    user_id: str,
    account_id: str,
    raws: list[RawTransaction],
    source: str,
    analyze: bool = True,
) -> IngestSummary:
    lock_account(conn, user_id, account_id)

    categorizer = Categorizer(conn, user_id)
    normalized, summary = [], IngestSummary()
    for i, raw in enumerate(raws, start=1):
        try:
            normalized.append(normalize(raw, source, categorizer))
        except MalformedTransaction as exc:
            summary.malformed += 1
            summary.errors.append(f"row {i}: {exc}")
    log_event("transaction.normalized", user_id=user_id, account_id=account_id, source=source,
              received=len(raws), valid=len(normalized), malformed=summary.malformed)

    inserted = insert_transactions(conn, user_id, account_id, normalized)
    summary.inserted = len(inserted.inserted)
    summary.duplicates = inserted.duplicates
    summary.inserted_transactions = inserted.inserted

    rb = rebuild_account(conn, user_id, account_id)
    summary.balance = rb.balance
    summary.active_cycle_id = rb.active_cycle_id
    summary.new_cycle_started = bool(rb.new_cycle_ids) and rb.active_cycle_id in rb.new_cycle_ids

    if analyze:
        refresh_recurring(conn, user_id, account_id)
        for cycle_id, is_new in sync_summaries(conn, user_id, account_id):
            if is_new and len(inserted.inserted) <= 25:  # a cycle just closed during a live event, not a bulk import
                row = conn.execute("select title from monthly_summaries where financial_cycle_id = %s and user_id = %s", (cycle_id, user_id)).fetchone()
                summary.alerts.append(upsert_alert(
                    conn, user_id, cycle_id=cycle_id, alert_type="SUMMARY_READY", severity="info", title="Monthly summary ready",
                    message=f"{row['title']} has been generated, with key observations and action items.",
                    dedupe_key=f"summary:{cycle_id}", evidence={"cycle_id": cycle_id}))
        summary.alerts += evaluate_alerts(
            conn, user_id, account_id, inserted=inserted.inserted, new_cycle_ids=rb.new_cycle_ids
        )
        refresh_insights(conn, user_id, account_id)

    log_event("ledger.updated", user_id=user_id, account_id=account_id, inserted=summary.inserted,
              duplicates=summary.duplicates, new_cycle=summary.new_cycle_started, alerts=len(summary.alerts))
    return summary
