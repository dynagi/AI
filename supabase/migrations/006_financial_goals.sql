-- 006_financial_goals.sql
-- Long-term financial goals (purchase, emergency fund, travel, education, custom).
-- Separate from the per-cycle savings target (008) and from category budgets (009).
--
-- goals.status is the lifecycle the USER controls (ACTIVE / PAUSED / COMPLETED).
-- The analysis status (ON_TRACK / AT_RISK / BEHIND / COMPLETED) is computed from the ledger, never stored.

create table if not exists public.financial_goals (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references public.users (id) on delete cascade,
  name           text not null check (length(trim(name)) > 0),
  goal_type      text not null default 'CUSTOM'
                 check (goal_type in ('PURCHASE', 'EMERGENCY_FUND', 'TRAVEL', 'EDUCATION', 'CUSTOM')),
  target_amount  numeric(14, 2) not null check (target_amount > 0),
  current_amount numeric(14, 2) not null default 0 check (current_amount >= 0),
  target_date    date not null,
  priority       text not null default 'MEDIUM' check (priority in ('LOW', 'MEDIUM', 'HIGH')),
  status         text not null default 'ACTIVE' check (status in ('ACTIVE', 'PAUSED', 'COMPLETED')),
  completed_at   timestamptz,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

create index if not exists idx_goals_user on public.financial_goals (user_id, status);

drop trigger if exists trg_goals_updated_at on public.financial_goals;
create trigger trg_goals_updated_at
  before update on public.financial_goals
  for each row execute function public.set_updated_at();
