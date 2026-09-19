-- 015_realtime.sql
-- Publish ledger tables through Supabase Realtime so the dashboard updates the
-- moment a transaction is written, with no page refresh.
--
-- REPLICA IDENTITY FULL lets Realtime deliver the complete old/new row (and
-- lets row level security filters such as user_id=eq.<uid> work on UPDATEs).
-- The publication block is guarded so this file also runs on a plain Postgres
-- (for local testing) where the supabase_realtime publication does not exist.

alter table public.transactions        replica identity full;
alter table public.financial_accounts  replica identity full;
alter table public.financial_cycles    replica identity full;
alter table public.agent_alerts        replica identity full;
alter table public.financial_insights  replica identity full;

do $$
declare
  t text;
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    foreach t in array array[
      'transactions', 'financial_accounts', 'financial_cycles',
      'agent_alerts', 'financial_insights'
    ]
    loop
      if not exists (
        select 1 from pg_publication_tables
        where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = t
      ) then
        execute format('alter publication supabase_realtime add table public.%I', t);
      end if;
    end loop;
  end if;
end $$;
