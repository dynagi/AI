-- 003_financial_accounts.sql
-- A financial account (bank account, demo bank, manual ledger).
--
-- IMPORTANT: current_balance is what is in the account right now. It is NOT
-- income. opening_balance is the balance before the first ledger transaction
-- and is likewise never treated as income.

create table if not exists public.financial_accounts (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.users (id) on delete cascade,
  name            text not null,
  account_type    text not null default 'savings'
                  check (account_type in ('savings', 'current', 'manual')),
  currency        text not null default 'INR',
  current_balance numeric(14, 2) not null default 0,
  opening_balance numeric(14, 2) not null default 0,
  source          text not null
                  check (source in ('demo', 'bank', 'manual', 'csv', 'statement')),
  status          text not null default 'ACTIVE'
                  check (status in ('ACTIVE', 'DISCONNECTED', 'ERROR')),
  last_synced_at  timestamptz,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index if not exists idx_financial_accounts_user on public.financial_accounts (user_id);

drop trigger if exists trg_financial_accounts_updated_at on public.financial_accounts;
create trigger trg_financial_accounts_updated_at
  before update on public.financial_accounts
  for each row execute function public.set_updated_at();
