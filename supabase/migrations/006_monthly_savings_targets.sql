-- 006_monthly_savings_targets.sql
-- The savings target is chosen by the USER for a specific financial cycle.
-- FinPilot never invents one and never silently carries one over.

create table if not exists public.monthly_savings_targets (
  id                 uuid primary key default gen_random_uuid(),
  user_id            uuid not null references public.users (id) on delete cascade,
  financial_cycle_id uuid not null references public.financial_cycles (id) on delete cascade,
  target_amount      numeric(14, 2) not null check (target_amount >= 0),
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (financial_cycle_id)
);

create index if not exists idx_savings_targets_user on public.monthly_savings_targets (user_id);

drop trigger if exists trg_savings_targets_updated_at on public.monthly_savings_targets;
create trigger trg_savings_targets_updated_at
  before update on public.monthly_savings_targets
  for each row execute function public.set_updated_at();
