-- Run events: metadata about each panel/sim run. Never run content.
-- Run this in the Supabase SQL editor (Dashboard > SQL). Idempotent.
--
-- There is deliberately no column for pitch text, seed text, or any answer.
-- If you ever find yourself adding one, that is the design changing, not a fix.

create table if not exists public.run_events (
  id bigint generated always as identity primary key,
  ts timestamptz not null default now(),
  event text not null,                 -- 'start' | 'end'
  run_id text,                         -- session/sim id, pairs start with end
  user_id uuid references auth.users(id) on delete set null,
  run_type text,                       -- 'panel' | 'simulation'
  mode text,                           -- 'product' | 'policy'
  crowd_size int,
  duration_seconds numeric,
  status text,                         -- 'started' | 'ok' | 'failed'
  error_code text,
  model text,
  prompt_tokens int,
  completion_tokens int,
  total_tokens int,
  cost_usd numeric
);

create index if not exists run_events_user_ts on public.run_events (user_id, ts desc);
create index if not exists run_events_run_id on public.run_events (run_id);

-- RLS: a user reads only their own rows. The backend writes with service_role,
-- which bypasses RLS. No insert/update policy exists, so nothing but the
-- backend can write here.
alter table public.run_events enable row level security;

drop policy if exists "run_events_select_own" on public.run_events;
create policy "run_events_select_own"
  on public.run_events for select
  using (auth.uid() = user_id);

-- Handy view for the table browser: one row per user, cost and failure rate.
create or replace view public.run_events_by_user as
select
  user_id,
  count(*) filter (where event = 'end')                     as runs,
  count(*) filter (where status = 'failed')                 as failed,
  sum(coalesce(total_tokens, 0))                            as total_tokens,
  round(sum(coalesce(cost_usd, 0))::numeric, 4)             as total_cost_usd,
  max(ts)                                                   as last_seen
from public.run_events
group by user_id;
