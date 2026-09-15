-- Profiles: one row per account, and whether the operator has approved it.
-- The waitlist gate reads `approved` on every API call (see app/approval.py).
-- Model: app/data/model/profile.json
--
-- Reconstructed read-only from the hosted project on 2026-09-14. Idempotent.
-- Run waitlist_requests.sql first: handle_new_user reads that table.

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  full_name text,
  approved boolean not null default false,
  requested_at timestamptz not null default now(),
  approved_at timestamptz,
  notified_at timestamptz                          -- stamped once, when the sign-up ping is sent
);

-- New account: a profile row, pre-approved when the operator invited the email.
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path to 'public'
as $$
declare
  pre_approved boolean := false;
begin
  if new.invited_at is not null then
    pre_approved := true;
  else
    select true into pre_approved
    from public.waitlist_requests r
    where lower(r.email) = lower(new.email)
      and r.status = 'invited'
    limit 1;
  end if;

  insert into public.profiles (id, email, full_name, approved, approved_at)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data ->> 'full_name', new.raw_user_meta_data ->> 'name'),
    coalesce(pre_approved, false),
    case when coalesce(pre_approved, false) then now() end
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Stamp approved_at when the flag flips on.
create or replace function public.profiles_stamp_approved()
returns trigger language plpgsql security definer set search_path to 'public'
as $$
begin
  if new.approved and (old.approved is distinct from new.approved) then
    new.approved_at := now();
  end if;
  return new;
end;
$$;

drop trigger if exists profiles_stamp_approved on public.profiles;
create trigger profiles_stamp_approved
  before update on public.profiles
  for each row execute function public.profiles_stamp_approved();

-- RLS: a user reads only their own row. The backend writes with service_role.
alter table public.profiles enable row level security;

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own"
  on public.profiles for select to authenticated
  using (auth.uid() = id);
