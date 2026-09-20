-- 014_monthly_summary_actions.sql
-- Data-driven action items produced with a monthly summary. They are never deleted when a summary is
-- regenerated once the user has completed or dismissed them; only still-OPEN items are refreshed.
-- action_key is a deterministic slug (e.g. 'review:Shopping') so regeneration can match items up.

create table if not exists public.monthly_summary_actions (
  id          uuid primary key default gen_random_uuid(),
  summary_id  uuid not null references public.monthly_summaries (id) on delete cascade,
  user_id     uuid not null references public.users (id) on delete cascade,
  action_key  text not null,
  title       text not null,
  description text not null,
  priority    text not null default 'MEDIUM' check (priority in ('LOW', 'MEDIUM', 'HIGH')),
  category    text,
  evidence    jsonb not null default '{}'::jsonb,
  status      text not null default 'OPEN' check (status in ('OPEN', 'COMPLETED', 'DISMISSED')),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (summary_id, action_key)
);

create index if not exists idx_summary_actions_user on public.monthly_summary_actions (user_id, status);

drop trigger if exists trg_summary_actions_updated_at on public.monthly_summary_actions;
create trigger trg_summary_actions_updated_at
  before update on public.monthly_summary_actions
  for each row execute function public.set_updated_at();
