"""
Admin actions reachable from a link — waitlist approval and email invites.

  GET /admin/approve?user=<id>&token=<ADMIN_APPROVE_TOKEN>
  GET /admin/invite?token=<ADMIN_APPROVE_TOKEN>              -> a one-box form
  POST /admin/invite (email + token in the form)             -> sends the invite

Deliberately outside /api/ so it carries no JWT: the operator taps it from a
Telegram message on their phone, where no Crowds session exists. The secret in
the URL is the whole authentication, so ADMIN_APPROVE_TOKEN must be long and
random (e.g. `python -c "import secrets;print(secrets.token_urlsafe(32))"`).
Unset = the route is off.

Env:
  ADMIN_APPROVE_TOKEN   long random string; also embedded in the ping link
"""

import os
import hmac
import re

import requests
from flask import Blueprint, request

from . import approval
from .utils.logger import get_logger

logger = get_logger("fub.admin")

admin_bp = Blueprint('admin', __name__)

_PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Crowds admin</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #FAFAFA; color: #141414;
         display: flex; align-items: center; justify-content: center;
         min-height: 100vh; margin: 0; padding: 24px; }}
  .box {{ background: #fff; border: 1px solid #E8E8E8; border-radius: 14px;
          padding: 32px; max-width: 420px; text-align: center; }}
  h1 {{ font-size: 1.3rem; margin: 0 0 10px; color: {colour}; }}
  p {{ color: #4a4a4a; margin: 0; font-size: 0.95rem; }}
</style>
<div class="box"><h1>{title}</h1><p>{body}</p></div>
"""


def _page(title: str, body: str, colour: str, code: int):
    return _PAGE.format(title=title, body=body, colour=colour), code, \
        {"Content-Type": "text/html; charset=utf-8"}


@admin_bp.route('/approve', methods=['GET'])
def approve():
    expected = os.environ.get("ADMIN_APPROVE_TOKEN", "")
    if not expected:
        return _page("Not available", "Approval links aren't configured on this server.",
                     "#C0392B", 503)
    if not hmac.compare_digest(request.args.get("token", ""), expected):
        logger.warning("Admin approve rejected: bad token")
        return _page("Not allowed", "That link isn't valid.", "#C0392B", 403)

    user_id = request.args.get("user", "")
    profile = approval.get_profile(user_id)
    if not profile:
        return _page("Not found", "No waitlist entry matches that link.", "#C0392B", 404)
    who = profile.get("email") or user_id
    if profile.get("approved"):
        return _page("Already approved", f"{who} already has access.", "#178048", 200)

    if not approval.approve(user_id):
        return _page("Didn't work", "Approving failed. Try the Supabase table instead.",
                     "#C0392B", 502)
    logger.info("Approved %s via admin link", who)
    return _page("Approved", f"{who} can use Crowds now.", "#178048", 200)


# ── Invite by email ──────────────────────────────────────────────────────────
#
# Supabase's own "Invite user" button fails here: the `enforce_invite_only`
# trigger on auth.users runs BEFORE INSERT, and GoTrue stamps invited_at only
# after the row is written — so the trigger sees a stranger and blocks it.
# This route does the two halves in the right order: mark the address invited
# in the request queue first, then ask GoTrue to send the mail, then approve
# the profile so the invitee lands in the app instead of the waitlist screen.

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]{2,}$")

_FORM = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Invite to Crowds</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #FAFAFA; color: #141414;
         display: flex; align-items: center; justify-content: center;
         min-height: 100vh; margin: 0; padding: 24px; }}
  .box {{ background: #fff; border: 1px solid #E8E8E8; border-radius: 14px;
          padding: 32px; max-width: 420px; width: 100%; }}
  h1 {{ font-size: 1.3rem; margin: 0 0 6px; }}
  p {{ color: #4a4a4a; margin: 0 0 18px; font-size: 0.95rem; }}
  input {{ width: 100%; box-sizing: border-box; padding: 12px 14px; font-size: 1rem;
          border: 1px solid #DADADA; border-radius: 10px; margin-bottom: 12px; }}
  button {{ width: 100%; padding: 12px; font-size: 1rem; border: 0; cursor: pointer;
           border-radius: 10px; background: #1E9E5A; color: #fff; }}
  .msg {{ margin: 0 0 14px; font-size: 0.95rem; color: {colour}; }}
</style>
<div class="box">
  <h1>Invite someone to Crowds</h1>
  <p>They get an email with a link to set a password. Access is on straight away.</p>
  <p class="msg">{message}</p>
  <form method="post">
    <input type="hidden" name="token" value="{token}">
    <input type="email" name="email" placeholder="name@example.com" required autofocus>
    <input type="text" name="name" placeholder="Their name (optional)">
    <button type="submit">Send invite</button>
  </form>
</div>
"""


def _form(token: str, message: str = "", colour: str = "#4a4a4a", code: int = 200):
    return _FORM.format(token=token, message=message, colour=colour), code, \
        {"Content-Type": "text/html; charset=utf-8"}


def _rest(path: str) -> str:
    return os.environ.get("SUPABASE_URL", "").rstrip("/") + path


def _service_headers() -> dict:
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    return {"apikey": key, "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"}


def _mark_invited(email: str, name: str) -> None:
    """Put the address in the request queue as 'invited' so the trigger allows it."""
    resp = requests.patch(
        _rest("/rest/v1/waitlist_requests"),
        params={"email": f"eq.{email}"},
        json={"status": "invited"},
        headers={**_service_headers(), "Prefer": "return=representation"},
        timeout=10,
    )
    resp.raise_for_status()
    if resp.json():
        return
    requests.post(
        _rest("/rest/v1/waitlist_requests"),
        json={"email": email, "full_name": name or None, "status": "invited"},
        headers={**_service_headers(), "Prefer": "resolution=ignore-duplicates"},
        timeout=10,
    ).raise_for_status()


@admin_bp.route('/invite', methods=['GET', 'POST'])
def invite():
    expected = os.environ.get("ADMIN_APPROVE_TOKEN", "")
    if not expected:
        return _page("Not available", "Invites aren't configured on this server.",
                     "#C0392B", 503)

    token = (request.form.get("token") or request.args.get("token") or "")
    if not hmac.compare_digest(token, expected):
        logger.warning("Admin invite rejected: bad token")
        return _page("Not allowed", "That link isn't valid.", "#C0392B", 403)

    if request.method == 'GET':
        return _form(token)

    email = (request.form.get("email") or "").strip().lower()
    name = (request.form.get("name") or "").strip()[:120]
    if not _EMAIL_RE.match(email):
        return _form(token, "That doesn't look like an email address.", "#C0392B", 400)
    if not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        return _form(token, "Supabase isn't configured on this server.", "#C0392B", 503)

    try:
        _mark_invited(email, name)
    except Exception as e:
        logger.error("Invite: could not queue %s: %s", email, e)
        return _form(token, "Couldn't reach the database. Try again.", "#C0392B", 502)

    base = (os.environ.get("PUBLIC_APP_URL") or "").rstrip("/")
    try:
        resp = requests.post(
            _rest("/auth/v1/invite"),
            json={"email": email,
                  "data": {"full_name": name} if name else {}},
            params={"redirect_to": f"{base}/auth/callback?next=/auth/reset"} if base else None,
            headers=_service_headers(),
            timeout=15,
        )
    except Exception as e:
        logger.error("Invite call failed for %s: %s", email, e)
        return _form(token, "Couldn't reach Supabase. Try again.", "#C0392B", 502)

    if resp.status_code == 422:
        return _form(token, f"{email} already has an account. "
                            "Send them a password reset instead.", "#C0392B", 409)
    if not resp.ok:
        logger.error("Invite rejected for %s: %s %s", email, resp.status_code, resp.text[:300])
        return _form(token, "Supabase refused the invite. Check the auth logs.",
                     "#C0392B", 502)

    user_id = (resp.json() or {}).get("id", "")
    if user_id and not approval.approve(user_id):
        logger.warning("Invited %s but couldn't auto-approve them", email)
        return _form(token, f"Invite sent to {email}, but approve them by hand "
                            "in Supabase → profiles.", "#B8860B", 200)

    logger.info("Invited %s via admin link", email)
    return _form(token, f"Invite sent to {email}. They can set a password now.",
                 "#178048", 200)
