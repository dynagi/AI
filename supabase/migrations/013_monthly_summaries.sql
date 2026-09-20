-- 013_monthly_summaries.sql
-- One stored summary per financial cycle. Generated automatically when a cycle closes, and on demand.
-- The headline numbers are columns; the full report (categories, comparison, recurring, unusual activity,
-- goal progress, budget status, observations) is in `content`, all derived from the ledger.

create table if not exists public.monthly_summaries (
  id                      uuid primary key default gen_random_uuid(),
  user_id                 uuid not null references public.users (id) on delete cascade,
  financial_cycle_id      uuid not null references public.financial_cycles (id) on delete cascade,
  title                   text not null,
  period_start            timestamptz not null,
  period_end              timestamptz,                          -- null while the cycle is still ACTIVE
  income_total            numeric(14, 2) not null default 0,
  expense_total           numeric(14, 2) not null default 0,
  savings_total           numeric(14, 2) not null default 0,
  savings_rate            numeric(7, 2),                        -- percent; null when there is no income
  top_category            text,
  previous_cycle_expenses numeric(14, 2),
  expense_change          numeric(14, 2),                       -- this cycle minus the previous cycle
  is_final                boolean not null default false,       -- true once the cycle is CLOSED
  content                 jsonb not null default '{}'::jsonb,
  generated_at            timestamptz not null default now(),
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now(),
  unique (financial_cycle_id)
);

create index if not exists idx_summaries_user on public.monthly_summaries (user_id, period_start desc);

drop trigger if exists trg_summaries_updated_at on public.monthly_summaries;
create trigger trg_summaries_updated_at
  before update on public.monthly_summaries
  for each row execute function public.set_updated_at();
