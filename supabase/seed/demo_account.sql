-- demo_account.sql
-- The demo bank account. Opening balance is money that was already in the account before the
-- ledger starts; it is never income. The seeded history nets to zero per cycle (an automatic
-- sweep moves the surplus to the user's own savings), so the balance is Rs 35,000 again right
-- before the September salary is credited from the Demo Bank Simulator.

insert into public.financial_accounts
  (id, user_id, name, account_type, currency, current_balance, opening_balance, source, status, last_synced_at)
values
  ('a1b2c3d4-0000-4000-8000-0000000000a1', 'a1b2c3d4-0000-4000-8000-000000000001', 'Demo Bank Account', 'savings', 'INR', 35000.00, 35000, 'demo', 'ACTIVE', '2026-09-29 18:00:00+05:30')
on conflict (id) do nothing;

insert into public.data_sources (id, user_id, account_id, source_type, label, status, record_count, last_synced_at)
values ('2bc17cf5-6dfd-5595-a2f1-3311d1cf696f', 'a1b2c3d4-0000-4000-8000-000000000001', 'a1b2c3d4-0000-4000-8000-0000000000a1', 'demo_bank', 'Demo Bank (Sandbox)', 'ACTIVE', 236, '2026-09-29 18:00:00+05:30')
on conflict (id) do nothing;

insert into public.consents
  (id, user_id, account_id, provider, status, purpose, from_date, to_date, fetch_frequency, external_ref, approved_at)
values
  ('02aef039-c939-5a19-b250-bb24e63ad103', 'a1b2c3d4-0000-4000-8000-000000000001', 'a1b2c3d4-0000-4000-8000-0000000000a1', 'demo_bank', 'APPROVED',
   'View your transaction history to power spending insights, budgets and recurring-payment detection (sandbox).',
   '2026-03-31', '2026-09-29', 'daily', 'demo-consent-seed', '2026-03-31 11:27:04+05:30')
on conflict (id) do nothing;
