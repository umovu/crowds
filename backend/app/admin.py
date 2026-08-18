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


# ── Trial usage ──────────────────────────────────────────────────────────────
#
#   GET /admin/usage?token=<ADMIN_APPROVE_TOKEN>
#
# One table: who signed up, how much of their free trial they've spent, and
# when they last actually ran a panel. Trial counters come from Supabase
# (`subscriptions`); the "last panel" column comes from the panel session files
# on this server's data volume, which is the only place a real timestamp lives.

_USAGE_PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Crowds usage</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #FAFAFA; color: #141414;
         margin: 0; padding: 24px; }}
  h1 {{ font-size: 1.2rem; margin: 0 0 4px; }}
  p.sub {{ color: #6a6a6a; font-size: 0.85rem; margin: 0 0 18px; }}
  table {{ border-collapse: collapse; width: 100%; max-width: 900px;
           background: #fff; border: 1px solid #E8E8E8; border-radius: 10px; }}
  th, td {{ text-align: left; padding: 9px 12px; font-size: 0.87rem;
            border-bottom: 1px solid #F0F0F0; white-space: nowrap; }}
  th {{ background: #F6F6F6; font-weight: 600; }}
  tr:last-child td {{ border-bottom: none; }}
  .paid {{ color: #178048; font-weight: 600; }}
  .spent {{ color: #C0392B; font-weight: 600; }}
  .muted {{ color: #9a9a9a; }}
</style>
<h1>Trial usage</h1>
<p class="sub">{note}</p>
<table>
<tr><th>Email</th><th>Plan</th><th>Panels</th><th>Sims</th><th>Last panel</th><th>Approved</th></tr>
{rows}
</table>
"""


def _last_panel_runs() -> dict:
    """{user_id: (last_created_at, count)} read from panel session files."""
    out: dict = {}
    try:
        from app.services import panel_service
        for meta in panel_service.list_sessions(None):
            uid = meta.get("user_id")
            if not uid:
                continue
            created = meta.get("created_at") or ""
            last, count = out.get(uid, ("", 0))
            out[uid] = (max(last, created), count + 1)
    except Exception as e:
        logger.warning("Usage page: could not read panel sessions: %s", e)
    return out


@admin_bp.route('/usage', methods=['GET'])
def usage():
    expected = os.environ.get("ADMIN_APPROVE_TOKEN", "")
    if not expected:
        return _page("Not available", "The usage page isn't configured on this server.",
                     "#C0392B", 503)
    if not hmac.compare_digest(request.args.get("token", ""), expected):
        logger.warning("Admin usage rejected: bad token")
        return _page("Not allowed", "That link isn't valid.", "#C0392B", 403)
    if not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        return _page("Not available", "Supabase isn't configured on this server.",
                     "#C0392B", 503)

    try:
        profiles = requests.get(
            _rest("/rest/v1/profiles"),
            params={"select": "id,email,full_name,approved", "limit": "500"},
            headers=_service_headers(), timeout=15,
        )
        profiles.raise_for_status()
        subs = requests.get(
            _rest("/rest/v1/subscriptions"),
            params={"select": "user_id,plan,panel_used,sim_used,status", "limit": "500"},
            headers=_service_headers(), timeout=15,
        )
        subs.raise_for_status()
    except Exception as e:
        logger.error("Usage page lookup failed: %s", e)
        return _page("Didn't work", "Couldn't reach Supabase. Try again.", "#C0392B", 502)

    by_user = {s.get("user_id"): s for s in (subs.json() or [])}
    runs = _last_panel_runs()

    def sort_key(p):
        last, _ = runs.get(p.get("id"), ("", 0))
        return last
    people = sorted(profiles.json() or [], key=sort_key, reverse=True)

    from .billing import FREE_PANEL_LIMIT, FREE_SIM_LIMIT

    rows = []
    for p in people:
        sub = by_user.get(p.get("id")) or {}
        plan = sub.get("plan") or "free"
        panels = int(sub.get("panel_used") or 0)
        sims = int(sub.get("sim_used") or 0)
        last, _count = runs.get(p.get("id"), ("", 0))
        paid = plan == "paid"

        def cell(used, limit):
            if paid:
                return f'<span class="paid">{used}</span>'
            css = "spent" if used >= limit else ""
            return f'<span class="{css}">{used} / {limit}</span>'

        plan_cell = '<span class="paid">paid</span>' if paid else 'free'
        last_cell = last[:16].replace('T', ' ') if last else '<span class="muted">never</span>'
        appr_cell = 'yes' if p.get('approved') else '<span class="muted">pending</span>'
        who = p.get('email') or p.get('id')
        rows.append(
            "<tr>"
            f"<td>{who}</td>"
            f"<td>{plan_cell}</td>"
            f"<td>{cell(panels, FREE_PANEL_LIMIT)}</td>"
            f"<td>{cell(sims, FREE_SIM_LIMIT)}</td>"
            f"<td>{last_cell}</td>"
            f"<td>{appr_cell}</td>"
            "</tr>"
        )

    note = (f"{len(people)} accounts. Free trial is {FREE_PANEL_LIMIT} panels "
            f"and {FREE_SIM_LIMIT} sims. Newest activity first.")
    html = _USAGE_PAGE.format(note=note, rows="\n".join(rows) or
                              '<tr><td colspan="6" class="muted">No accounts yet.</td></tr>')
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}
