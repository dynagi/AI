-- 008_recurring_payments.sql
-- Recurring payments detected from real transaction history (never invented).

create table if not exists public.recurring_payments (
  id                    uuid primary key default gen_random_uuid(),
  user_id               uuid not null references public.users (id) on delete cascade,
  recurring_group_id    text not null,
  merchant              text not null,
  category              text not null,
  average_amount        numeric(14, 2) not null,
  frequency             text not null check (frequency in ('weekly', 'monthly', 'quarterly', 'yearly')),
  last_payment          timestamptz not null,
  next_expected_payment timestamptz not null,
  confidence            numeric(4, 2) not null check (confidence >= 0 and confidence <= 1),
  occurrences           integer not null,
  active                boolean not null default true,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),
  unique (user_id, recurring_group_id)
);

create index if not exists idx_recurring_user on public.recurring_payments (user_id) where active;

drop trigger if exists trg_recurring_updated_at on public.recurring_payments;
create trigger trg_recurring_updated_at
  before update on public.recurring_payments
  for each row execute function public.set_updated_at();
