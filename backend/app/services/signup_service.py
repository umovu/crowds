"""Getting in: requesting access, the waitlist gate, and password resets.

Every rule about who may use the app lives here, and none of it needs Flask or a
network to run. Storage is the repositories' job; this module decides what an answer
means.

The two failure directions are deliberate and opposite:

  * The gate FAILS OPEN. If Supabase is unreachable the caller is let through, so a
    blip never locks out approved users. Only a row that actually says false blocks.
  * A password reset FAILS CLOSED. Unless we positively know the account is approved,
    no mail goes out.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..repositories import user_repository, waitlist_repository
from ..utils.logger import get_logger

logger = get_logger("fub.signup")

EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]{2,}$")
MAX_NAME = 120
MAX_NOTE = 1000

# A crude per-IP throttle, so an open endpoint cannot be hammered into the database
# or the operator's notifications. In-process and best-effort: the point is to blunt
# a script, not to survive a determined flood.
RATE_WINDOW_SECONDS = 3600
RATE_MAX_PER_WINDOW = 5
_recent: Dict[str, List[float]] = {}

# Approval rarely changes and the gate runs on every /api call, so the answer is
# cached briefly. A newly approved user waits at most this long.
CACHE_TTL_SECONDS = 60
_approved_cache: Dict[str, tuple] = {}

RESET_MESSAGE = ("If that email belongs to an approved account, a reset link "
                 "is on its way. Check your inbox and your spam folder.")


@dataclass(frozen=True)
class Outcome:
    """What the controller should say: `ok`, an HTTP status, and one plain sentence."""
    ok: bool
    status: int
    message: str


# ── the waitlist gate ───────────────────────────────────────────────────────
def gate_enabled() -> bool:
    """The gate is on when Supabase is configured and nothing switched it off."""
    if os.environ.get("WAITLIST_ENABLED", "").lower() == "false":
        return False
    if os.environ.get("AUTH_DISABLED", "").lower() == "true":
        return False
    from ..repositories import supabase
    return supabase.enabled()


def is_approved(user_id: str, email: str = "", name: str = "") -> bool:
    """May this user use the app? Fails open; see the module docstring."""
    if not gate_enabled() or not user_id:
        return True

    hit = _approved_cache.get(user_id)
    if hit and hit[0] > time.time():
        return hit[1]

    found = user_repository.find(user_id)
    if not found.reached:
        # The lookup itself failed. Let them through, and do not cache it, so the
        # next request tries again.
        return True
    if found.profile is None:
        # Supabase answered and there is no row: the auth.users trigger never fired
        # (e.g. the user predates it). Queue them rather than granting access.
        user_repository.create_pending(user_id, email, name)
        approved = False
    else:
        approved = bool(found.profile.approved)

    _approved_cache[user_id] = (time.time() + CACHE_TTL_SECONDS, approved)
    return approved


def invalidate(user_id: str) -> None:
    _approved_cache.pop(user_id, None)


def approve(user_id: str) -> bool:
    """Let a user in (the operator's one-tap link). False when the write failed."""
    if not gate_enabled() or not user_id:
        return False
    ok = user_repository.approve(user_id)
    if ok:
        invalidate(user_id)
    return ok


def profile(user_id: str):
    """The user's profile row, or None."""
    return user_repository.get(user_id)


# ── requesting access ───────────────────────────────────────────────────────
def _rate_limited(caller_ip: str) -> bool:
    now = time.time()
    hits = [t for t in _recent.get(caller_ip, []) if t > now - RATE_WINDOW_SECONDS]
    _recent[caller_ip] = hits + [now]
    if len(_recent) > 5000:          # keep the dict from growing without bound
        _recent.clear()
    return len(hits) >= RATE_MAX_PER_WINDOW


def request_access(email: str, name: str = "", note: str = "",
                   caller_ip: str = "?") -> Outcome:
    """File an access request. Answers the same either way, new or repeat."""
    email = (email or "").strip().lower()
    name = (name or "").strip()[:MAX_NAME]
    note = (note or "").strip()[:MAX_NOTE]

    if not EMAIL.match(email):
        return Outcome(False, 400, "Please enter a valid email address.")
    if _rate_limited(caller_ip):
        return Outcome(False, 429, "Too many requests. Try again later.")

    saved = waitlist_repository.add(email, name, note)
    if not saved.ok:
        from ..repositories import supabase
        if not supabase.enabled():
            return Outcome(False, 503, "Requests aren't available right now.")
        return Outcome(False, 502, "Could not save your request. Please try again.")

    if saved.is_new:
        _ping_operator_about_request(email, name, note)
    # The same answer whether the email is new or already queued, so the form never
    # tells a stranger who has applied.
    return Outcome(True, 200, "Thanks. We'll be in touch by email.")


def _ping_operator_about_request(email: str, name: str, note: str) -> None:
    from .. import notify
    body = f"{name or '(no name given)'}\n{email}"
    if note:
        body += f"\n\n“{note}”"
    body += "\n\nReview in Supabase -> waitlist_requests, then invite them."
    notify.send_alert("New Crowds access request", body, f"mailto:{email}")


def ping_operator_about_waiting_user(user_id: str, email: str, name: str,
                                     approve_link: str = "") -> bool:
    """Tell the operator someone is sitting in the queue. Fires at most once per user."""
    if not user_repository.claim_notification(user_id):
        return False
    from .. import notify
    body = f"{name or '(no name given)'}\n{email or '(unknown email)'}"
    body += "\n\nTap to approve." if approve_link else \
        "\n\nApprove them in the Supabase profiles table."
    return notify.send_alert("New Crowds waitlist sign-up", body, approve_link)


# ── password reset ──────────────────────────────────────────────────────────
def send_password_reset(email: str, caller_ip: str = "?",
                        app_url: str = "") -> Outcome:
    """Mail a reset link, but only to an account the operator already let in.

    Routed through the backend rather than the browser on purpose: calling Supabase's
    reset directly would mail a link to anyone ever created, approved or not.
    """
    email = (email or "").strip().lower()
    if not EMAIL.match(email):
        return Outcome(False, 400, "Please enter a valid email address.")
    if _rate_limited(caller_ip):
        return Outcome(False, 429, "Too many requests. Try again later.")

    from ..repositories import supabase
    if not supabase.enabled():
        logger.error("Password reset requested but Supabase is not configured")
        return Outcome(False, 503, "Password reset isn't available right now.")

    # Fails closed: None means "could not find out", and that sends nothing.
    if user_repository.approved_by_email(email) is True:
        base = (app_url or "").rstrip("/")
        redirect_to = f"{base}/auth/callback?next=/auth/reset" if base else ""
        user_repository.send_recovery_mail(email, redirect_to)
    else:
        logger.info("Password reset ignored for a non-approved address")

    # One answer either way, so this never reveals whether an account exists.
    return Outcome(True, 200, RESET_MESSAGE)
