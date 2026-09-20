-- 020_rls_policies.sql
-- Row Level Security: every financial table is isolated by user_id.
--
-- Model:
--   * Browsers (anon key + the user's JWT) may only SELECT their OWN rows.
--     This is what Supabase Realtime uses, so realtime also respects RLS.
--   * All writes go through the FastAPI backend, which connects with a
--     privileged role and enforces the authenticated user id in code.
--     Clients therefore get no INSERT/UPDATE/DELETE policies at all, and the
--     table privileges are revoked below as a second line of defence.

do $$
declare
  t text;
begin
  foreach t in array array[
    'users', 'financial_accounts', 'transactions', 'category_rules',
    'financial_cycles', 'monthly_savings_targets', 'budgets', 'recurring_payments',
    'financial_insights', 'agent_alerts', 'agent_conversations', 'agent_messages',
    'data_sources', 'consents', 'financial_goals', 'goal_contributions', 'monthly_summaries',
    'monthly_summary_actions'
  ]
  loop
    execute format('alter table public.%I enable row level security', t);
  end loop;
end $$;

-- users: the row's own id is the owner.
drop policy if exists users_select_own on public.users;
create policy users_select_own on public.users
  for select to authenticated
  using (id = (select auth.uid()));

-- Every other table carries user_id directly.
do $$
declare
  t text;
begin
  foreach t in array array[
    'financial_accounts', 'transactions', 'category_rules',
    'financial_cycles', 'monthly_savings_targets', 'budgets', 'recurring_payments',
    'financial_insights', 'agent_alerts', 'agent_conversations', 'agent_messages',
    'data_sources', 'consents', 'financial_goals', 'goal_contributions', 'monthly_summaries',
    'monthly_summary_actions'
  ]
  loop
    execute format('drop policy if exists %I on public.%I', t || '_select_own', t);
    execute format(
      'create policy %I on public.%I for select to authenticated using (user_id = (select auth.uid()))',
      t || '_select_own', t
    );
  end loop;
end $$;

-- Clients can never write directly.
do $$
declare
  t text;
begin
  foreach t in array array[
    'users', 'financial_accounts', 'transactions', 'category_rules',
    'financial_cycles', 'monthly_savings_targets', 'budgets', 'recurring_payments',
    'financial_insights', 'agent_alerts', 'agent_conversations', 'agent_messages',
    'data_sources', 'consents', 'financial_goals', 'goal_contributions', 'monthly_summaries',
    'monthly_summary_actions'
  ]
  loop
    execute format('revoke insert, update, delete, truncate on public.%I from anon, authenticated', t);
    execute format('revoke all on public.%I from anon', t);
  end loop;
end $$;
