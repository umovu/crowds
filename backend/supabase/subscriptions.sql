-- Subscriptions: one row per user — the plan and the free-tier counters.
-- The billing source of truth (see app/billing.py). Model: app/data/model/subscription.json
--
-- Reconstructed read-only from the hosted project on 2026-09-14. The live table was
-- created in the dashboard; this file records it so the repo matches. Idempotent.

create table if not exists public.subscriptions (
  user_id uuid primary key references auth.users(id) on delete cascade,
  plan text not null default 'free' check (plan = any (array['free'::text, 'paid'::text])),
  status text not null default 'active',          -- 'active' | 'cancelled'
  panel_used integer not null default 0,
  paystack_customer_code text,
  paystack_subscription_code text,                 -- not written by the backend today
  current_period_end timestamptz,                  -- not written by the backend today
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),   -- no trigger keeps this fresh
  sim_used integer not null default 0
);

-- Every new account gets a free row.
create or replace function public.handle_new_user_subscription()
returns trigger language plpgsql security definer set search_path to ''
as $$
begin
  insert into public.subscriptions (user_id, plan)
  values (new.id, 'free') on conflict (user_id) do nothing;
  return new;
end; $$;

drop trigger if exists on_auth_user_created_subscription on auth.users;
create trigger on_auth_user_created_subscription
  after insert on auth.users
  for each row execute function public.handle_new_user_subscription();

-- RLS: a user reads only their own row. The backend writes with service_role.
alter table public.subscriptions enable row level security;

drop policy if exists "read own subscription" on public.subscriptions;
create policy "read own subscription"
  on public.subscriptions for select to authenticated
  using ((select auth.uid()) = user_id);
