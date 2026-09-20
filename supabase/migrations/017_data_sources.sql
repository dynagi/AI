-- 017_data_sources.sql
-- One row per way data enters FinPilot for a user (Demo Bank, AA sandbox,
-- manual entry, CSV imports). Powers Settings > Financial Data Sources.

create table if not exists public.data_sources (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references public.users (id) on delete cascade,
  account_id     uuid references public.financial_accounts (id) on delete set null,
  source_type    text not null check (source_type in ('demo_bank', 'aa_sandbox', 'manual', 'csv', 'statement')),
  label          text not null,
  status         text not null default 'ACTIVE' check (status in ('ACTIVE', 'DISCONNECTED', 'ERROR')),
  record_count   integer not null default 0,
  last_synced_at timestamptz,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

create index if not exists idx_data_sources_user on public.data_sources (user_id);

drop trigger if exists trg_data_sources_updated_at on public.data_sources;
create trigger trg_data_sources_updated_at
  before update on public.data_sources
  for each row execute function public.set_updated_at();
