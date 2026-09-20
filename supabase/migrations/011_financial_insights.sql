-- 011_financial_insights.sql
-- Observations shown on the dashboard. Every insight carries `evidence`
-- (the numbers and transaction ids it was computed from) so nothing is shown
-- without supporting data.

create table if not exists public.financial_insights (
  id                 uuid primary key default gen_random_uuid(),
  user_id            uuid not null references public.users (id) on delete cascade,
  financial_cycle_id uuid references public.financial_cycles (id) on delete cascade,
  insight_type       text not null,
  severity           text not null default 'info' check (severity in ('info', 'warning', 'critical')),
  title              text not null,
  message            text not null,
  evidence           jsonb not null default '{}'::jsonb,
  dedupe_key         text not null,
  dismissed          boolean not null default false,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (user_id, dedupe_key)
);

create index if not exists idx_insights_user_created on public.financial_insights (user_id, created_at desc);

drop trigger if exists trg_insights_updated_at on public.financial_insights;
create trigger trg_insights_updated_at
  before update on public.financial_insights
  for each row execute function public.set_updated_at();
