-- 001_extensions.sql
-- Extensions and shared helpers. Safe to re-run.

create schema if not exists extensions;

-- pgcrypto is used by the demo seed (password hashing for the demo auth user).
create extension if not exists pgcrypto with schema extensions;

-- Keeps updated_at current on every UPDATE.
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;
