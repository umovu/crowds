-- Operator context: one saved "about my business" block per user.
-- Run this in the Supabase SQL editor (Dashboard > SQL). Idempotent.

create table if not exists public.operator_context (
  user_id uuid primary key references auth.users(id) on delete cascade,
  body text not null default '',
  updated_at timestamptz not null default now()
);

-- Keep updated_at fresh on writes
create or replace function public.operator_context_set_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end; $$;

drop trigger if exists operator_context_updated_at on public.operator_context;
create trigger operator_context_updated_at
  before update on public.operator_context
  for each row execute function public.operator_context_set_updated_at();

-- RLS: users can read/write only their own row. Backend uses service_role (bypasses RLS).
alter table public.operator_context enable row level security;

drop policy if exists "operator_context_select_own" on public.operator_context;
create policy "operator_context_select_own"
  on public.operator_context for select
  using (auth.uid() = user_id);

drop policy if exists "operator_context_insert_own" on public.operator_context;
create policy "operator_context_insert_own"
  on public.operator_context for insert
  with check (auth.uid() = user_id);

drop policy if exists "operator_context_update_own" on public.operator_context;
create policy "operator_context_update_own"
  on public.operator_context for update
  using (auth.uid() = user_id);

drop policy if exists "operator_context_delete_own" on public.operator_context;
create policy "operator_context_delete_own"
  on public.operator_context for delete
  using (auth.uid() = user_id);
