-- 007_goal_contributions.sql
-- Money the user sets aside for a goal. A contribution raises the goal's current_amount only; it is NOT
-- an expense and does not touch the account ledger or the cycle's expense totals.

create table if not exists public.goal_contributions (
  id         uuid primary key default gen_random_uuid(),
  goal_id    uuid not null references public.financial_goals (id) on delete cascade,
  user_id    uuid not null references public.users (id) on delete cascade,
  amount     numeric(14, 2) not null check (amount > 0),
  "timestamp" timestamptz not null default now(),
  source     text not null default 'manual' check (source in ('manual', 'seed', 'import')),
  notes      text,
  created_at timestamptz not null default now()
);

create index if not exists idx_goal_contrib_goal on public.goal_contributions (goal_id, "timestamp" desc);
create index if not exists idx_goal_contrib_user on public.goal_contributions (user_id);
