"""Generates supabase/seed/demo_*.sql from the deterministic demo dataset.

    cd backend && .venv/Scripts/python -m scripts.generate_seed

The SQL files are committed; re-run this only if app/demo/dataset.py changes. Balances, cycle ids and
cycle totals are computed by the same ledger engine the backend uses, so the seeded data is already
consistent and a rebuild changes nothing.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.demo.dataset import (
    CYCLE_EXPENSE_TOTALS, DEMO_OPENING_BALANCE, DEMO_SAVINGS_TARGET_TO_SET, generate_demo_history,
)
from app.ledger import LedgerTxn, rebuild
from app.services.categorization import merchant_key
from app.services.recurring import detect_from_rows

NS = uuid.UUID("6f1a5d2e-7c4b-4b8e-9d3a-1f0e2c3b4a5d")
USER_ID = "a1b2c3d4-0000-4000-8000-000000000001"
ACCOUNT_ID = "a1b2c3d4-0000-4000-8000-0000000000a1"
DEMO_EMAIL = "demo@finpilot.test"
DEMO_PASSWORD = "FinPilot-Demo-2026"
OUT = Path(__file__).resolve().parents[2] / "supabase" / "seed"


def uid(kind: str, key: str) -> str:
    return str(uuid.uuid5(NS, f"{kind}:{key}"))


def q(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, Decimal)):
        return str(v)
    if isinstance(v, datetime):
        return f"'{v.isoformat(sep=' ')}'"
    return "'" + str(v).replace("'", "''") + "'"


def write(name: str, body: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(body, encoding="utf-8")
    print(f"wrote {name} ({len(body.splitlines())} lines)")


def main() -> None:
    history = generate_demo_history()
    txn_ids = [uid("txn", r.external_id) for r in history]
    ledger = [LedgerTxn(txn_ids[i], r.timestamp, i + 1, r.transaction_type, r.amount, r.metadata) for i, r in enumerate(history)]
    result = rebuild(DEMO_OPENING_BALANCE, ledger)

    cycle_uid = {c.key: uid("cycle", c.key) for c in result.cycles}
    final_balance = result.final_balance
    assert final_balance == DEMO_OPENING_BALANCE, final_balance
    for c, expected in zip(result.cycles, CYCLE_EXPENSE_TOTALS):
        assert c.expense_total == Decimal(expected), (c.key, c.expense_total, expected)

    # Recurring payments, detected from the same rows the backend detector would see.
    expense_rows = [
        {"id": txn_ids[i], "timestamp": r.timestamp, "description": r.description, "merchant": r.merchant,
         "amount": r.amount, "category": r.category}
        for i, r in enumerate(history) if r.transaction_type == "EXPENSE"
    ]
    recurring = detect_from_rows(expense_rows)
    member_group = {mid: r["recurring_group_id"] for r in recurring for mid in r["member_ids"]}

    # ---------------------------------------------------------------- demo_user.sql
    write("demo_user.sql", f"""-- demo_user.sql
-- A confirmed Supabase Auth user for the demo, plus the matching profile row.
--   email:    {DEMO_EMAIL}
--   password: {DEMO_PASSWORD}
-- Run order: demo_user, demo_account, demo_cycles, demo_transactions, demo_targets, demo_budgets.
-- Safe to re-run (ON CONFLICT DO NOTHING).

insert into auth.users (
  instance_id, id, aud, role, email, encrypted_password, email_confirmed_at,
  raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
  confirmation_token, email_change, email_change_token_new, recovery_token
) values (
  '00000000-0000-0000-0000-000000000000', {q(USER_ID)}, 'authenticated', 'authenticated', {q(DEMO_EMAIL)},
  extensions.crypt({q(DEMO_PASSWORD)}, extensions.gen_salt('bf')), now(),
  '{{"provider":"email","providers":["email"]}}', '{{"display_name":"Demo User"}}', now(), now(),
  '', '', '', ''
) on conflict (id) do nothing;

insert into auth.identities (id, user_id, identity_data, provider, provider_id, last_sign_in_at, created_at, updated_at)
values (
  {q(uid('identity', 'demo'))}, {q(USER_ID)},
  jsonb_build_object('sub', {q(USER_ID)}, 'email', {q(DEMO_EMAIL)}, 'email_verified', true),
  'email', {q(USER_ID)}, now(), now(), now()
) on conflict (id) do nothing;

-- The auth trigger normally creates this row; inserting explicitly keeps the seed self-contained.
insert into public.users (id, email, display_name)
values ({q(USER_ID)}, {q(DEMO_EMAIL)}, 'Demo User')
on conflict (id) do nothing;
""")

    # -------------------------------------------------------------- demo_account.sql
    first_ts, last_ts = history[0].timestamp, history[-1].timestamp
    write("demo_account.sql", f"""-- demo_account.sql
-- The demo bank account. Opening balance is money that was already in the account before the
-- ledger starts; it is never income. The seeded history nets to zero per cycle (an automatic
-- sweep moves the surplus to the user's own savings), so the balance is Rs 35,000 again right
-- before the September salary is credited from the Demo Bank Simulator.

insert into public.financial_accounts
  (id, user_id, name, account_type, currency, current_balance, opening_balance, source, status, last_synced_at)
values
  ({q(ACCOUNT_ID)}, {q(USER_ID)}, 'Demo Bank Account', 'savings', 'INR', {final_balance}, {DEMO_OPENING_BALANCE}, 'demo', 'ACTIVE', {q(last_ts)})
on conflict (id) do nothing;

insert into public.data_sources (id, user_id, account_id, source_type, label, status, record_count, last_synced_at)
values ({q(uid('ds', 'demo'))}, {q(USER_ID)}, {q(ACCOUNT_ID)}, 'demo_bank', 'Demo Bank (Sandbox)', 'ACTIVE', {len(history)}, {q(last_ts)})
on conflict (id) do nothing;

insert into public.consents
  (id, user_id, account_id, provider, status, purpose, from_date, to_date, fetch_frequency, external_ref, approved_at)
values
  ({q(uid('consent', 'demo'))}, {q(USER_ID)}, {q(ACCOUNT_ID)}, 'demo_bank', 'APPROVED',
   'View your transaction history to power spending insights, budgets and recurring-payment detection (sandbox).',
   {q(first_ts.date().isoformat())}, {q(last_ts.date().isoformat())}, 'daily', 'demo-consent-seed', {q(first_ts)})
on conflict (id) do nothing;
""")

    # --------------------------------------------------------------- demo_cycles.sql
    rows = []
    for c in result.cycles:
        rows.append(
            f"  ({q(cycle_uid[c.key])}, {q(USER_ID)}, {q(ACCOUNT_ID)}, {q(c.start_at)}, {q(c.end_at)}, {c.opening_balance}, "
            f"{c.carried_over_balance}, {q(c.closing_balance)}, {c.income_total}, {c.other_inflow_total}, {c.refund_total}, "
            f"{c.expense_total}, {c.transaction_count}, {q(c.status)})"
        )
    cycles_header = """-- demo_cycles.sql
-- Six salary-to-salary financial cycles. Five are CLOSED, the last (31 Aug -> next salary) is ACTIVE.
-- salary_transaction_id is linked at the end of demo_transactions.sql (the salary rows must exist first).
-- Each cycle starts at the exact timestamp its salary landed (11:27:04 IST).

insert into public.financial_cycles
  (id, user_id, account_id, start_at, end_at, opening_balance, carried_over_balance, closing_balance,
   income_total, other_inflow_total, refund_total, expense_total, transaction_count, status)
values
"""
    write("demo_cycles.sql", cycles_header + ",\n".join(rows) + "\non conflict (id) do nothing;\n")

    # ---------------------------------------------------------- demo_transactions.sql
    lines = []
    for i, r in enumerate(history):
        tid = txn_ids[i]
        st = result.txns[tid]
        meta = json.dumps({"seed": True, "categorization": {"method": "seed", "confidence": 1.0}})
        lines.append(
            f"  ({q(tid)}, {q(USER_ID)}, {q(ACCOUNT_ID)}, {q(r.timestamp)}, {q(r.description)}, {q(r.merchant)}, {r.amount}, "
            f"'INR', {q(r.transaction_type)}, {q(r.category)}, {q(r.subcategory)}, 'demo', {q(r.external_id)}, "
            f"{q(cycle_uid[st.cycle_key])}, {st.balance_after}, {q(tid in member_group)}, {q(member_group.get(tid))}, {q(meta)}::jsonb)"
        )
    salary_links = "\n".join(
        f"update public.financial_cycles set salary_transaction_id = {q(c.salary_transaction_id)} where id = {q(cycle_uid[c.key])};"
        for c in result.cycles if c.salary_transaction_id
    )
    rec_rows = ",\n".join(
        f"  ({q(uid('rec', r['recurring_group_id']))}, {q(USER_ID)}, {q(r['recurring_group_id'])}, {q(r['merchant'])}, {q(r['category'])}, "
        f"{r['average_amount']}, {q(r['frequency'])}, {q(r['last_payment'])}, {q(r['next_expected_payment'])}, {r['confidence']}, {r['occurrences']})"
        for r in recurring
    )
    write("demo_transactions.sql", f"""-- demo_transactions.sql
-- {len(history)} ledger rows across six cycles. amount is always positive; direction comes from
-- transaction_type. balance_after and financial_cycle_id were computed by the ledger engine.
-- Run AFTER demo_cycles.sql.
-- There is deliberately no insurance/EMI/loan spending in this dataset.

insert into public.transactions
  (id, user_id, account_id, "timestamp", description, merchant, amount, currency, transaction_type, category,
   subcategory, source, external_id, financial_cycle_id, balance_after, is_recurring, recurring_group_id, metadata)
values
""" + ",\n".join(lines) + f"""
on conflict (id) do nothing;

-- Link each cycle to the salary transaction that opened it.
{salary_links}

-- Recurring payments detected from the rows above (>= 3 evenly spaced payments each).
insert into public.recurring_payments
  (id, user_id, recurring_group_id, merchant, category, average_amount, frequency, last_payment,
   next_expected_payment, confidence, occurrences)
values
{rec_rows}
on conflict (user_id, recurring_group_id) do nothing;
""")

    # ------------------------------------------------------------- demo_targets.sql
    target_rows = ",\n".join(
        f"  ({q(uid('target', c.key))}, {q(USER_ID)}, {q(cycle_uid[c.key])}, 25000)" for c in result.cycles
    )
    write("demo_targets.sql", f"""-- demo_targets.sql
-- The user's own savings targets for the seeded cycles (Rs 25,000 each). The NEW cycle that starts
-- when the September salary is credited has no target on purpose: FinPilot asks the user to set it
-- (the live demo sets Rs {DEMO_SAVINGS_TARGET_TO_SET}).

insert into public.monthly_savings_targets (id, user_id, financial_cycle_id, target_amount)
values
{target_rows}
on conflict (financial_cycle_id) do nothing;

update public.financial_cycles fc
   set savings_target = t.target_amount
  from public.monthly_savings_targets t
 where t.financial_cycle_id = fc.id and fc.user_id = {q(USER_ID)};
""")

    # ------------------------------------------------------------- demo_budgets.sql
    budgets = [("Food", 7000), ("Shopping", 6000), ("Transport", 4000), ("Entertainment", 2000)]
    write("demo_budgets.sql", """-- demo_budgets.sql
-- Category budgets. Separate from the savings target; measured against the active cycle.

insert into public.budgets (id, user_id, category, amount)
values
""" + ",\n".join(f"  ({q(uid('budget', c))}, {q(USER_ID)}, {q(c)}, {a})" for c, a in budgets) + "\non conflict (user_id, category) do nothing;\n")

    print("balance before demo salary:", final_balance)


if __name__ == "__main__":
    main()
