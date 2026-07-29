"""
Account API — who the caller is and whether they're through the waitlist.

  GET /api/account/status   {approved, email, waitlist_enabled}

Exempt from the waitlist gate (see `create_app`), because a pending user must
be able to load this to see the waitlist screen.

This route is also where the operator's "someone joined the waitlist" ping
fires: the waitlist page calls it on load, which is the first moment we know a
real, confirmed person is sitting in the queue. `claim_notification` makes it
exactly once per user.
"""

import os
from urllib.parse import quote

from flask import g, jsonify, request

from . import account_bp
from .. import approval, notify
from ..utils.logger import get_logger

logger = get_logger("fub.api.account")


def _approve_link(user_id: str) -> str:
    """One-tap approve URL for the Telegram message (or '' if not configured)."""
    token = os.environ.get("ADMIN_APPROVE_TOKEN", "")
    if not token:
        return ""
    base = os.environ.get("PUBLIC_API_URL", "").rstrip("/") or request.url_root.rstrip("/")
    return f"{base}/admin/approve?user={quote(user_id)}&token={quote(token)}"


def _ping_operator(user_id: str, email: str, name: str) -> None:
    """Tell the operator a new person is waiting. Best-effort, fires once."""
    if not approval.claim_notification(user_id):
        return
    lines = [
        "<b>New Crowds waitlist sign-up</b>",
        f"Name: {name or '(not given)'}",
        f"Email: {email or '(unknown)'}",
    ]
    link = _approve_link(user_id)
    if link:
        lines.append(f'\n<a href="{link}">Tap to approve</a>')
    else:
        lines.append("\nApprove them in the Supabase profiles table.")
    notify.send_telegram("\n".join(lines))


@account_bp.route('/status', methods=['GET'])
def status():
    user = getattr(g, "user", None) or {}
    approved = approval.current_user_approved()
    if not approved:
        meta = user.get("user_metadata") or {}
        _ping_operator(
            user.get("sub"),
            user.get("email") or "",
            meta.get("full_name") or meta.get("name") or "",
        )
    return jsonify({"success": True, "data": {
        "approved": approved,
        "email": user.get("email"),
        "waitlist_enabled": approval.waitlist_enabled(),
    }})
