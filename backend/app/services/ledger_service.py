"""Ledger persistence: insert transactions, then rebuild balances and cycles.

Everything here runs inside the caller's database transaction, with the account
row locked (SELECT ... FOR UPDATE), so two simultaneous writes to the same
account are serialized and balance_after can never be computed from stale data.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

import psycopg

from app.ledger import INITIAL_CYCLE_KEY, LedgerTxn, rebuild
from app.services.normalizer import NormalizedTransaction


class AccountNotFound(Exception):
    pass


class AccountNotActive(Exception):
    pass


@dataclass
class InsertedTxn:
    id: str
    transaction_type: str
    timestamp: datetime
    amount: Decimal
    category: str


@dataclass
class RebuildResult:
    balance: Decimal
    cycle_ids: dict[str, str]  # ledger cycle key -> financial_cycles.id
    new_cycle_ids: list[str]
    active_cycle_id: Optional[str]


@dataclass
class IngestResult:
    inserted: list[InsertedTxn] = field(default_factory=list)
    duplicates: int = 0
    rebuild: Optional[RebuildResult] = None


def lock_account(conn: psycopg.Connection, user_id: str, account_id: str, require_active: bool = True) -> dict:
    row = conn.execute(
        "select * from financial_accounts where id = %s and user_id = %s for update",
        (account_id, user_id),
    ).fetchone()
    if row is None:
        raise AccountNotFound(account_id)
    if require_active and row["status"] != "ACTIVE":
        raise AccountNotActive(account_id)
    return row


def insert_transactions(
    conn: psycopg.Connection, user_id: str, account_id: str, records: list[NormalizedTransaction]
) -> IngestResult:
    result = IngestResult()
    for r in records:
        row = conn.execute(
            """
            insert into transactions
              (user_id, account_id, "timestamp", description, merchant, amount, currency,
               transaction_type, category, subcategory, source, external_id, metadata)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (account_id, external_id) where external_id is not null do nothing
            returning id, transaction_type, "timestamp", amount, category
            """,
            (
                user_id, account_id, r.timestamp, r.description, r.merchant, r.amount, r.currency,
                r.transaction_type, r.category, r.subcategory, r.source, r.external_id,
                json.dumps(r.metadata),
            ),
        ).fetchone()
        if row is None:
            result.duplicates += 1
        else:
            result.inserted.append(
                InsertedTxn(str(row["id"]), row["transaction_type"], row["timestamp"], row["amount"], row["category"])
            )
    return result


def rebuild_account(conn: psycopg.Connection, user_id: str, account_id: str) -> RebuildResult:
    """Recompute balance_after, cycle assignment and cycle totals for one account.

    Idempotent: running it twice changes nothing the second time.
    """
    account = conn.execute(
        "select id, opening_balance from financial_accounts where id = %s and user_id = %s",
        (account_id, user_id),
    ).fetchone()
    if account is None:
        raise AccountNotFound(account_id)

    rows = conn.execute(
        """
        select id, seq, "timestamp", transaction_type, amount, metadata, balance_after, financial_cycle_id
        from transactions where account_id = %s and user_id = %s
        """,
        (account_id, user_id),
    ).fetchall()

    ledger = [
        LedgerTxn(str(r["id"]), r["timestamp"], r["seq"], r["transaction_type"], r["amount"], r["metadata"] or {})
        for r in rows
    ]
    result = rebuild(account["opening_balance"], ledger)

    existing = conn.execute(
        "select id, salary_transaction_id from financial_cycles where account_id = %s and user_id = %s",
        (account_id, user_id),
    ).fetchall()
    existing_by_key: dict[str, str] = {}
    for c in existing:
        key = str(c["salary_transaction_id"]) if c["salary_transaction_id"] else INITIAL_CYCLE_KEY
        existing_by_key[key] = str(c["id"])

    wanted_keys = {c.key for c in result.cycles}

    # Cycles that no longer exist (e.g. a demo salary was reset). Transactions fall back to NULL and
    # are re-pointed below.
    for key, cid in existing_by_key.items():
        if key not in wanted_keys:
            conn.execute("delete from financial_cycles where id = %s and user_id = %s", (cid, user_id))

    cycle_ids: dict[str, str] = {}
    new_cycle_ids: list[str] = []
    for c in result.cycles:  # chronological: earlier cycles are closed before the active one is written
        cid = existing_by_key.get(c.key)
        params = dict(
            start_at=c.start_at, end_at=c.end_at, salary_transaction_id=c.salary_transaction_id,
            opening_balance=c.opening_balance, carried_over_balance=c.carried_over_balance,
            closing_balance=c.closing_balance, income_total=c.income_total,
            other_inflow_total=c.other_inflow_total, refund_total=c.refund_total,
            expense_total=c.expense_total, transaction_count=c.transaction_count, status=c.status,
        )
        if cid is None:
            cid = str(uuid.uuid4())
            conn.execute(
                """
                insert into financial_cycles
                  (id, user_id, account_id, start_at, end_at, salary_transaction_id, opening_balance,
                   carried_over_balance, closing_balance, income_total, other_inflow_total, refund_total,
                   expense_total, transaction_count, status)
                values (%(id)s, %(user_id)s, %(account_id)s, %(start_at)s, %(end_at)s, %(salary_transaction_id)s,
                        %(opening_balance)s, %(carried_over_balance)s, %(closing_balance)s, %(income_total)s,
                        %(other_inflow_total)s, %(refund_total)s, %(expense_total)s, %(transaction_count)s, %(status)s)
                """,
                {**params, "id": cid, "user_id": user_id, "account_id": account_id},
            )
            new_cycle_ids.append(cid)
        else:
            conn.execute(
                """
                update financial_cycles set
                  start_at = %(start_at)s, end_at = %(end_at)s, salary_transaction_id = %(salary_transaction_id)s,
                  opening_balance = %(opening_balance)s, carried_over_balance = %(carried_over_balance)s,
                  closing_balance = %(closing_balance)s, income_total = %(income_total)s,
                  other_inflow_total = %(other_inflow_total)s, refund_total = %(refund_total)s,
                  expense_total = %(expense_total)s, transaction_count = %(transaction_count)s, status = %(status)s
                where id = %(id)s and user_id = %(user_id)s
                """,
                {**params, "id": cid, "user_id": user_id},
            )
        cycle_ids[c.key] = cid

    # Mirror the user's chosen savings target onto the cycle row.
    conn.execute(
        """
        update financial_cycles fc set savings_target = t.target_amount
        from monthly_savings_targets t
        where t.financial_cycle_id = fc.id and fc.account_id = %s and fc.user_id = %s
        """,
        (account_id, user_id),
    )

    # Write back only what changed.
    current = {str(r["id"]): (r["balance_after"], str(r["financial_cycle_id"]) if r["financial_cycle_id"] else None) for r in rows}
    updates = []
    for tid, state in result.txns.items():
        want = (state.balance_after, cycle_ids[state.cycle_key])
        if current.get(tid) != want:
            updates.append((want[0], want[1], tid))
    if updates:
        with conn.cursor() as cur:
            cur.executemany(
                "update transactions set balance_after = %s, financial_cycle_id = %s where id = %s",
                updates,
            )

    conn.execute(
        "update financial_accounts set current_balance = %s, last_synced_at = now() where id = %s and user_id = %s",
        (result.final_balance, account_id, user_id),
    )

    active = next((c for c in result.cycles if c.status == "ACTIVE"), None)
    return RebuildResult(
        balance=result.final_balance,
        cycle_ids=cycle_ids,
        new_cycle_ids=new_cycle_ids,
        active_cycle_id=cycle_ids[active.key] if active else None,
    )
