"""
Public waitlist API — the front door for people who have no account yet.

  POST /api/waitlist/request   {email, name?, note?}

Auth-exempt on purpose (see `create_app`): the caller is a stranger. Nothing
here creates an auth user — it only files a request the operator reviews, so
the operator decides who ever gets an account.

Always answers 200 with the same message, whether the email is new or already
queued. That keeps the form from telling a stranger who has already applied.
"""

import os
import re
import time

import requests
from flask import jsonify, request

from . import waitlist_bp
from .. import notify
from ..utils.logger import get_logger

logger = get_logger("fub.api.waitlist")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]{2,}$")
_MAX_NOTE = 1000
_MAX_NAME = 120

# Crude per-IP throttle so the open endpoint can't be hammered into the
# database or the Discord channel. In-process and best-effort; the point is to
# blunt a script, not to survive a determined flood.
_RATE_WINDOW_SECONDS = 3600
_RATE_MAX_PER_WINDOW = 5
_recent: dict[str, list[float]] = {}


def _rate_limited(ip: str) -> bool:
    now = time.time()
    hits = [t for t in _recent.get(ip, []) if t > now - _RATE_WINDOW_SECONDS]
    _recent[ip] = hits + [now]
    if len(_recent) > 5000:      # keep the dict from growing without bound
        _recent.clear()
    return len(hits) >= _RATE_MAX_PER_WINDOW


def _supabase_ready() -> bool:
    return bool(os.environ.get("SUPABASE_URL") and
                os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))


def _store(email: str, name: str, note: str) -> tuple[bool, bool]:
    """File the request. Returns (saved, is_new) — is_new is False on a repeat."""
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    url = os.environ["SUPABASE_URL"].rstrip("/")
    try:
        resp = requests.post(
            f"{url}/rest/v1/waitlist_requests",
            json={"email": email, "full_name": name, "note": note},
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                # Re-applying doesn't error, and doesn't wipe an existing
                # 'invited' status either — we only ever insert.
                "Prefer": "resolution=ignore-duplicates,return=representation",
            },
            timeout=10,
        )
        resp.raise_for_status()
        # Empty list = the email was already queued; that's still a success.
        return True, bool(resp.json())
    except Exception as e:
        logger.error("Could not save waitlist request for %s: %s", email, e)
        return False, False


@waitlist_bp.route('/request', methods=['POST'])
def create_request():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    name = (data.get("name") or "").strip()[:_MAX_NAME]
    note = (data.get("note") or "").strip()[:_MAX_NOTE]

    if not _EMAIL_RE.match(email):
        return jsonify({"success": False, "error": "Please enter a valid email address."}), 400

    ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
          or request.remote_addr or "?")
    if _rate_limited(ip):
        return jsonify({"success": False,
                        "error": "Too many requests. Try again later."}), 429

    if not _supabase_ready():
        logger.error("Waitlist request received but Supabase isn't configured")
        return jsonify({"success": False,
                        "error": "Requests aren't available right now."}), 503

    saved, is_new = _store(email, name, note)
    if not saved:
        return jsonify({"success": False,
                        "error": "Could not save your request. Please try again."}), 502

    if is_new:
        body = f"{name or '(no name given)'}\n{email}"
        if note:
            body += f"\n\n“{note}”"
        body += "\n\nReview in Supabase -> waitlist_requests, then invite them."
        notify.send_alert("New Crowds access request", body, f"mailto:{email}")

    return jsonify({"success": True, "data": {
        "message": "Thanks. We'll be in touch by email.",
    }})
