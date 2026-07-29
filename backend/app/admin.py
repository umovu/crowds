"""
Admin actions reachable from a link — currently one-tap waitlist approval.

  GET /admin/approve?user=<id>&token=<ADMIN_APPROVE_TOKEN>

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
