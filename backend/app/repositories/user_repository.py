"""The `profiles` table: who has an account, and whether the operator let them in.

A profile row is created by a Postgres trigger on auth.users, with approved=false.
Everything here reads or writes that row; deciding what to do about the answer is the
signup service's job.

Each function says plainly what it does when Supabase cannot be reached, because the
right answer differs: a gate check lets the caller through (a blip must not lock out
paying users), while anything that sends mail refuses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..models.accounts import Profile
from ..utils.logger import get_logger
from . import supabase

logger = get_logger("fub.repo.user")

TABLE = "profiles"

#: The columns a profile row carries. Asking for them by name means a new column
#: cannot silently change what this returns.
COLUMNS = "id,email,full_name,approved,requested_at,approved_at,notified_at"


@dataclass(frozen=True)
class Lookup:
    """What a profile read found. `reached` says whether Supabase answered at all.

    The caller needs those apart: no row means "queue this user", while a failed
    lookup means "let them through and try again". Reporting both from one read keeps
    the gate to a single call, since it runs on every /api request.
    """
    reached: bool
    profile: Optional[Profile] = None


def find(user_id: str) -> Lookup:
    """One profile, and whether the lookup itself succeeded."""
    if not supabase.enabled() or not user_id:
        return Lookup(reached=False)
    try:
        rows = supabase.rows(supabase.select(
            TABLE, {"id": f"eq.{user_id}", "select": COLUMNS, "limit": "1"}))
    except Exception as e:  # noqa: BLE001 - a lookup failure is not a crash
        logger.warning("Profile lookup failed for %s: %s", user_id, e)
        return Lookup(reached=False)
    return Lookup(reached=True,
                  profile=Profile.model_validate(rows[0]) if rows else None)


def get(user_id: str) -> Optional[Profile]:
    """One profile, or None when there is no row, no Supabase, or the lookup failed."""
    return find(user_id).profile


def approved_by_email(email: str) -> Optional[bool]:
    """True/False for an approved account, or None when we could not find out.

    None is not False: the caller must treat "unknown" differently from "not approved"
    (see signup_service.send_password_reset, which sends nothing unless it is True).
    """
    if not supabase.enabled() or not email:
        return None
    try:
        rows = supabase.rows(supabase.select(
            TABLE, {"email": f"eq.{email}", "select": "approved", "limit": "1"}))
    except Exception as e:  # noqa: BLE001
        logger.error("Approval lookup failed for %s: %s", email, e)
        return None
    return bool(rows[0].get("approved")) if rows else False


def create_pending(user_id: str, email: str, name: str) -> None:
    """Queue a user whose trigger row never arrived. Never raises."""
    if not supabase.enabled() or not user_id:
        return
    try:
        supabase.insert(TABLE,
                        {"id": user_id, "email": email, "full_name": name, "approved": False},
                        prefer="resolution=ignore-duplicates")
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not create pending profile for %s: %s", user_id, e)


def approve(user_id: str) -> bool:
    """Mark a user approved. False when the write did not happen."""
    if not supabase.enabled() or not user_id:
        return False
    try:
        resp = supabase.update(TABLE, {"id": f"eq.{user_id}"}, {"approved": True},
                               prefer="return=representation")
        return bool(supabase.rows(resp))
    except Exception as e:  # noqa: BLE001
        logger.warning("Approve failed for %s: %s", user_id, e)
        return False


def claim_notification(user_id: str) -> bool:
    """Claim the right to send this user's sign-up ping, exactly once.

    Stamps `notified_at` only while it is still null, so two concurrent requests
    cannot both fire: the second matches no rows.
    """
    if not supabase.enabled() or not user_id:
        return False
    try:
        resp = supabase.update(TABLE, {"id": f"eq.{user_id}", "notified_at": "is.null"},
                               {"notified_at": "now()"}, prefer="return=representation")
        return bool(supabase.rows(resp))
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not claim notification for %s: %s", user_id, e)
        return False


def send_recovery_mail(email: str, redirect_to: str) -> bool:
    """Ask Supabase to mail a password-reset link. False when it did not go out."""
    try:
        resp = supabase.auth_post("recover", {"email": email},
                                  {"redirect_to": redirect_to} if redirect_to else None)
        resp.raise_for_status()
        return True
    except Exception as e:  # noqa: BLE001
        logger.error("Could not send recovery mail to %s: %s", email, e)
        return False
