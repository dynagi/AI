-- 012_agent_messages.sql
-- user_id is stored on every message so row level security is a simple
-- equality check (no join back to the conversation).

create table if not exists public.agent_messages (
  id              uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.agent_conversations (id) on delete cascade,
  user_id         uuid not null references public.users (id) on delete cascade,
  role            text not null check (role in ('user', 'assistant', 'tool')),
  content         text not null,
  tool_calls      jsonb,
  created_at      timestamptz not null default now()
);

create index if not exists idx_messages_conversation on public.agent_messages (conversation_id, created_at);
