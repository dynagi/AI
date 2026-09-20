-- 012_agent_alerts.sql
-- Proactive alerts raised while a cycle is running (not at month end).
-- dedupe_key stops the same alert being raised repeatedly.

create table if not exists public.agent_alerts (
  id                 uuid primary key default gen_random_uuid(),
  user_id            uuid not null references public.users (id) on delete cascade,
  financial_cycle_id uuid references public.financial_cycles (id) on delete cascade,
  transaction_id     uuid references public.transactions (id) on delete set null,
  alert_type         text not null
                     check (alert_type in (
                       'NEW_CYCLE', 'HIGH_SPENDING', 'SAVINGS_AT_RISK',
                       'PREVIOUS_CYCLE_THRESHOLD', 'CATEGORY_SPIKE',
                       'BUDGET_THRESHOLD', 'LARGE_TRANSACTION', 'SAVINGS_TARGET_NEEDED',
                       'GOAL_AT_RISK', 'SUMMARY_READY')),
  severity           text not null default 'info' check (severity in ('info', 'warning', 'critical')),
  title              text not null,
  message            text not null,
  evidence           jsonb not null default '{}'::jsonb,
  dedupe_key         text not null,
  is_read            boolean not null default false,
  created_at         timestamptz not null default now(),
  unique (user_id, dedupe_key)
);

create index if not exists idx_alerts_user_created on public.agent_alerts (user_id, created_at desc);

-- Databases created before goals/summaries existed have the narrower check; widen it (safe to re-run).
alter table public.agent_alerts drop constraint if exists agent_alerts_alert_type_check;
alter table public.agent_alerts add constraint agent_alerts_alert_type_check
  check (alert_type in (
    'NEW_CYCLE', 'HIGH_SPENDING', 'SAVINGS_AT_RISK', 'PREVIOUS_CYCLE_THRESHOLD', 'CATEGORY_SPIKE',
    'BUDGET_THRESHOLD', 'LARGE_TRANSACTION', 'SAVINGS_TARGET_NEEDED', 'GOAL_AT_RISK', 'SUMMARY_READY'));
