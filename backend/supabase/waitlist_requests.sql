-- Waitlist requests: people with no account asking for access (app/api/waitlist.py).
-- The operator marks a row 'invited'; the sign-up triggers then let that email in.
-- Model: app/data/model/waitlist_request.json
--
-- Reconstructed read-only from the hosted project on 2026-09-14. Idempotent.

create table if not exists public.waitlist_requests (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,                      -- stored lower-case by the backend
  full_name text,
  note text,
  status text not null default 'pending',          -- 'pending' | 'invited'
  created_at timestamptz not null default now(),
  invited_at timestamptz
);

-- Stamp invited_at when the status flips to invited.
create or replace function public.waitlist_requests_stamp_invited()
returns trigger language plpgsql security definer set search_path to 'public'
as $$
begin
  if new.status = 'invited' and old.status is distinct from new.status then
    new.invited_at := now();
  end if;
  return new;
end;
$$;

drop trigger if exists waitlist_requests_stamp_invited on public.waitlist_requests;
create trigger waitlist_requests_stamp_invited
  before update on public.waitlist_requests
  for each row execute function public.waitlist_requests_stamp_invited();

-- RLS on with no policies: only the backend (service_role) reads or writes.
alter table public.waitlist_requests enable row level security;
