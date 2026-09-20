-- 009_budgets.sql
-- Category budgets (e.g. Food 5,000). Separate from the savings target.
-- A budget applies to every cycle; usage is always measured against the
-- CURRENT ACTIVE cycle's spending in that category.

create table if not exists public.budgets (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references public.users (id) on delete cascade,
  category   text not null,
  amount     numeric(14, 2) not null check (amount > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, category)
);

drop trigger if exists trg_budgets_updated_at on public.budgets;
create trigger trg_budgets_updated_at
  before update on public.budgets
  for each row execute function public.set_updated_at();
