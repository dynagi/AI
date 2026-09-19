-- demo_user.sql
-- A confirmed Supabase Auth user for the demo, plus the matching profile row.
--   email:    demo@finpilot.test
--   password: FinPilot-Demo-2026
-- Run order: demo_user, demo_account, demo_cycles, demo_transactions, demo_targets, demo_budgets.
-- Safe to re-run (ON CONFLICT DO NOTHING).

insert into auth.users (
  instance_id, id, aud, role, email, encrypted_password, email_confirmed_at,
  raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
  confirmation_token, email_change, email_change_token_new, recovery_token
) values (
  '00000000-0000-0000-0000-000000000000', 'a1b2c3d4-0000-4000-8000-000000000001', 'authenticated', 'authenticated', 'demo@finpilot.test',
  extensions.crypt('FinPilot-Demo-2026', extensions.gen_salt('bf')), now(),
  '{"provider":"email","providers":["email"]}', '{"display_name":"Demo User"}', now(), now(),
  '', '', '', ''
) on conflict (id) do nothing;

insert into auth.identities (id, user_id, identity_data, provider, provider_id, last_sign_in_at, created_at, updated_at)
values (
  'ec770e60-5f23-5094-9b36-ceb1aee1283a', 'a1b2c3d4-0000-4000-8000-000000000001',
  jsonb_build_object('sub', 'a1b2c3d4-0000-4000-8000-000000000001', 'email', 'demo@finpilot.test', 'email_verified', true),
  'email', 'a1b2c3d4-0000-4000-8000-000000000001', now(), now(), now()
) on conflict (id) do nothing;

-- The auth trigger normally creates this row; inserting explicitly keeps the seed self-contained.
insert into public.users (id, email, display_name)
values ('a1b2c3d4-0000-4000-8000-000000000001', 'demo@finpilot.test', 'Demo User')
on conflict (id) do nothing;
