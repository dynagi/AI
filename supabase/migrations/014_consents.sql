-- 014_consents.sql
-- Account Aggregator style consent lifecycle (sandbox / demo only in this build).

create table if not exists public.consents (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.users (id) on delete cascade,
  account_id      uuid references public.financial_accounts (id) on delete set null,
  provider        text not null check (provider in ('demo_bank', 'aa_sandbox')),
  status          text not null default 'PENDING'
                  check (status in ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'REVOKED')),
  purpose         text not null,
  from_date       date not null,
  to_date         date not null,
  fetch_frequency text not null default 'daily',
  external_ref    text,
  created_at      timestamptz not null default now(),
  approved_at     timestamptz,
  expires_at      timestamptz
);

create index if not exists idx_consents_user on public.consents (user_id);
