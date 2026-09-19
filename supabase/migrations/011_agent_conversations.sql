-- 011_agent_conversations.sql

create table if not exists public.agent_conversations (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references public.users (id) on delete cascade,
  title      text not null default 'New conversation',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_conversations_user on public.agent_conversations (user_id, updated_at desc);

drop trigger if exists trg_conversations_updated_at on public.agent_conversations;
create trigger trg_conversations_updated_at
  before update on public.agent_conversations
  for each row execute function public.set_updated_at();
