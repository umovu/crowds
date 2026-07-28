"""
Waitlist / manual approval gate.

Anyone can sign up, but a new account lands in `public.profiles` with
approved=false (a Postgres trigger on auth.users creates the row). Until an
admin flips that flag in the Supabase table editor, every /api/* call is
rejected with 403 + code "waitlist" and the frontend shows the waitlist screen.

Fail-open on infrastructure trouble, fail-closed on a real "false":
  - no SUPABASE_SERVICE_ROLE_KEY / SUPABASE_URL -> gate is off entirely (dev)
  - WAITLIST_ENABLED=false                      -> gate is off (kill switch)
  - lookup errors / timeouts                    -> caller is let through, so a
    Supabase blip never locks out approved users
  - row exists and says false                   -> blocked
  - row missing (trigger didn't fire)           -> created as pending, blocked

Env:
  SUPABASE_URL                  (already used for auth)
  SUPABASE_SERVICE_ROLE_KEY     server-side only, bypasses RLS
  WAITLIST_ENABLED              'false' turns the gate off (default: on)
"""

import os
import time

import requests
from flask import g, jsonify

from .utils.logger import get_logger

logger = get_logger("fub.approval")

# Approval rarely changes, and the check runs on every /api call — cache the
# answer briefly so we don't hit Supabase once per request. A newly approved
# user waits at most this long (and can force it with a page refresh + retry).
_CACHE_TTL_SECONDS = 60
_cache: dict[str, tuple[float, bool]] = {}


def _service_key() -> str:
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def _supabase_url() -> str:
    return os.environ.get("SUPABASE_URL", "").rstrip("/")


def waitlist_enabled() -> bool:
    """The gate is on when Supabase is configured and not explicitly disabled."""
    if os.environ.get("WAITLIST_ENABLED", "").lower() == "false":
        return False
    if os.environ.get("AUTH_DISABLED", "").lower() == "true":
        return False
    return bool(_service_key() and _supabase_url())


def _rest_headers() -> dict:
    key = _service_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _create_pending(user_id: str, email: str, name: str) -> None:
    """Insert a pending profile for a user whose trigger row is missing."""
    try:
        requests.post(
            f"{_supabase_url()}/rest/v1/profiles",
            json={"id": user_id, "email": email, "full_name": name, "approved": False},
            headers={**_rest_headers(), "Prefer": "resolution=ignore-duplicates"},
            timeout=10,
        )
    except Exception as e:
        logger.warning("Could not create pending profile for %s: %s", user_id, e)


def is_approved(user_id: str, email: str = "", name: str = "") -> bool:
    """True if this user may use the app. See module docstring for failure modes."""
    if not waitlist_enabled() or not user_id:
        return True

    hit = _cache.get(user_id)
    if hit and hit[0] > time.time():
        return hit[1]

    try:
        resp = requests.get(
            f"{_supabase_url()}/rest/v1/profiles",
            params={"id": f"eq.{user_id}", "select": "approved"},
            headers=_rest_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
    except Exception as e:
        logger.warning("Approval lookup failed for %s: %s (failing open)", user_id, e)
        return True

    if rows:
        approved = bool(rows[0].get("approved"))
    else:
        # No row: the auth.users trigger didn't fire (e.g. the user predates it).
        # Queue them rather than silently granting access.
        _create_pending(user_id, email, name)
        approved = False

    _cache[user_id] = (time.time() + _CACHE_TTL_SECONDS, approved)
    return approved


def invalidate(user_id: str) -> None:
    _cache.pop(user_id, None)


def current_user_approved() -> bool:
    user = getattr(g, "user", None) or {}
    meta = user.get("user_metadata") or {}
    return is_approved(
        user.get("sub"),
        user.get("email") or "",
        meta.get("full_name") or meta.get("name") or "",
    )


def verify_approved():
    """Gate the current request. Returns a 403 response, or None to continue."""
    if current_user_approved():
        return None
    return jsonify({
        "success": False,
        "error": "Your account is on the waitlist. We'll email you when it's approved.",
        "code": "waitlist",
    }), 403
