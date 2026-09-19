-- 005_financial_cycles.sql
-- A financial cycle is one salary-to-salary spending period.
--
-- The boundary is the exact timestamp of a SALARY transaction (not midnight,
-- not the calendar month). Cycles are never deleted when a new one starts: the
-- old cycle is CLOSED (end_at = the new salary's timestamp) and kept forever.
--
--   opening_balance      = account balance immediately AFTER the salary landed
--   carried_over_balance = account balance immediately BEFORE the salary landed
--                          (money that was already there; never income)

create table if not exists public.financial_cycles (
  id                    uuid primary key default gen_random_uuid(),
  user_id               uuid not null references public.users (id) on delete cascade,
  account_id            uuid not null references public.financial_accounts (id) on delete cascade,
  start_at              timestamptz not null,
  end_at                timestamptz,                       -- null while ACTIVE
  salary_transaction_id uuid references public.transactions (id) on delete set null,
  opening_balance       numeric(14, 2) not null default 0,
  carried_over_balance  numeric(14, 2) not null default 0,
  closing_balance       numeric(14, 2),
  income_total          numeric(14, 2) not null default 0, -- SALARY + OTHER_INCOME + INTEREST
  other_inflow_total    numeric(14, 2) not null default 0, -- TRANSFER_IN (money from other people/accounts)
  refund_total          numeric(14, 2) not null default 0,
  expense_total         numeric(14, 2) not null default 0, -- gross EXPENSE transactions only
  transaction_count     integer not null default 0,
  savings_target        numeric(14, 2),                    -- mirrors monthly_savings_targets
  status                text not null default 'ACTIVE' check (status in ('ACTIVE', 'CLOSED')),
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),
  check (end_at is null or end_at > start_at)
);

-- At most one ACTIVE cycle per account.
create unique index if not exists uq_financial_cycles_one_active
  on public.financial_cycles (account_id) where status = 'ACTIVE';

create index if not exists idx_financial_cycles_user_start
  on public.financial_cycles (user_id, start_at desc);

drop trigger if exists trg_financial_cycles_updated_at on public.financial_cycles;
create trigger trg_financial_cycles_updated_at
  before update on public.financial_cycles
  for each row execute function public.set_updated_at();

-- transactions.financial_cycle_id -> financial_cycles.id
-- (added here because cycles did not exist yet when 004 ran)
do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'fk_transactions_financial_cycle'
  ) then
    alter table public.transactions
      add constraint fk_transactions_financial_cycle
      foreign key (financial_cycle_id) references public.financial_cycles (id)
      on delete set null;
  end if;
end $$;
