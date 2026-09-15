-- Access control: a single row holding the invite-only switch.
-- Model: app/data/model/access_control.json
--
-- Reconstructed read-only from the hosted project on 2026-09-14. Idempotent.
-- Run waitlist_requests.sql first: enforce_invite_only reads that table.

create table if not exists public.access_control (
  id boolean primary key default true check (id),  -- only one row can exist
  invite_only boolean not null default true,
  updated_at timestamptz not null default now()
);

insert into public.access_control (id) values (true) on conflict (id) do nothing;

-- Block sign-up unless invite-only is off, the operator invited the user, or the
-- email is marked invited in the request queue.
create or replace function public.enforce_invite_only()
returns trigger language plpgsql security definer set search_path to 'public'
as $$
declare
  enforced boolean := true;
  was_requested boolean := false;
begin
  select invite_only into enforced from public.access_control where id;
  if not coalesce(enforced, true) then
    return new;
  end if;

  -- Operator-issued invite: Supabase sets invited_at when creating the user.
  -- Let it through, and keep the request queue in step so the person doesn't
  -- also show up as still waiting.
  if new.invited_at is not null then
    update public.waitlist_requests
       set status = 'invited'
     where lower(email) = lower(new.email)
       and status <> 'invited';
    return new;
  end if;

  -- Otherwise the email must already be marked invited in the request queue.
  select true into was_requested
  from public.waitlist_requests
  where lower(email) = lower(new.email)
    and status = 'invited'
  limit 1;

  if coalesce(was_requested, false) then
    return new;
  end if;

  raise exception 'Crowds is invite-only. Ask for access at https://crowds.co.za.'
    using errcode = 'check_violation';
end;
$$;

drop trigger if exists enforce_invite_only on auth.users;
create trigger enforce_invite_only
  before insert on auth.users
  for each row execute function public.enforce_invite_only();

-- RLS on with no policies: only the backend and the dashboard touch this row.
alter table public.access_control enable row level security;
