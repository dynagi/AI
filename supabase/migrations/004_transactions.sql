-- 004_transactions.sql
-- The ledger. Every ingestion path (demo bank, AA, manual, CSV) writes here.
--
-- amount is ALWAYS a positive magnitude. The direction of money is decided by
-- transaction_type (see signed_amount below), never by the sign of amount.

create table if not exists public.transactions (
  id                 uuid primary key default gen_random_uuid(),
  seq                bigint generated always as identity,  -- stable tie-breaker for equal timestamps
  user_id            uuid not null references public.users (id) on delete cascade,
  account_id         uuid not null references public.financial_accounts (id) on delete cascade,
  "timestamp"        timestamptz not null,
  description        text not null,
  merchant           text,
  amount             numeric(14, 2) not null check (amount > 0),
  currency           text not null default 'INR',
  transaction_type   text not null
                     check (transaction_type in (
                       'SALARY', 'OTHER_INCOME', 'TRANSFER_IN', 'TRANSFER_OUT',
                       'EXPENSE', 'REFUND', 'INTEREST', 'OTHER')),
  category           text not null default 'Other',
  subcategory        text,
  source             text not null
                     check (source in ('demo', 'bank', 'manual', 'csv', 'statement')),
  external_id        text,                       -- id from the source system, used for de-duplication
  financial_cycle_id uuid,                       -- FK added in 005_financial_cycles.sql
  balance_after      numeric(14, 2),             -- account balance immediately after this transaction
  is_recurring       boolean not null default false,
  recurring_group_id text,
  metadata           jsonb not null default '{}'::jsonb,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),

  -- +amount for money coming in, -amount for money going out (set by trigger below).
  -- A trigger-maintained column is used instead of a GENERATED column because generated
  -- columns are not published by logical replication, which breaks REPLICA IDENTITY FULL
  -- and would leave them out of Supabase Realtime payloads.
  signed_amount      numeric(14, 2)
);

-- OTHER is a debit unless metadata.direction = 'credit'. Mirrors app/ledger/engine.py.
create or replace function public.set_transaction_signed_amount()
returns trigger
language plpgsql
as $$
begin
  new.signed_amount :=
    case
      when new.transaction_type in ('SALARY', 'OTHER_INCOME', 'TRANSFER_IN', 'REFUND', 'INTEREST') then new.amount
      when new.transaction_type = 'OTHER' and new.metadata ->> 'direction' = 'credit' then new.amount
      else -new.amount
    end;
  return new;
end;
$$;

drop trigger if exists trg_transactions_signed_amount on public.transactions;
create trigger trg_transactions_signed_amount
  before insert or update of amount, transaction_type, metadata on public.transactions
  for each row execute function public.set_transaction_signed_amount();

create unique index if not exists uq_transactions_account_external
  on public.transactions (account_id, external_id)
  where external_id is not null;

create index if not exists idx_transactions_user_time    on public.transactions (user_id, "timestamp" desc);
create index if not exists idx_transactions_account_time on public.transactions (account_id, "timestamp", seq);
create index if not exists idx_transactions_cycle        on public.transactions (financial_cycle_id);
create index if not exists idx_transactions_user_cat     on public.transactions (user_id, category);

drop trigger if exists trg_transactions_updated_at on public.transactions;
create trigger trg_transactions_updated_at
  before update on public.transactions
  for each row execute function public.set_updated_at();

-- Persisted user corrections: merchant -> category. Applied to future transactions.
create table if not exists public.category_rules (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references public.users (id) on delete cascade,
  merchant_key text not null,
  category     text not null,
  subcategory  text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  unique (user_id, merchant_key)
);

drop trigger if exists trg_category_rules_updated_at on public.category_rules;
create trigger trg_category_rules_updated_at
  before update on public.category_rules
  for each row execute function public.set_updated_at();
