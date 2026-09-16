"""Who the caller is, and whether they are through the waitlist.

  GET /api/account/status   {approved, email, waitlist_enabled}

Exempt from the waitlist gate (see `create_app`), because a user who is still waiting
must be able to load this to see the waitlist screen.

This is also where the operator's "someone joined the waitlist" ping fires: the
waitlist page calls it on load, which is the first moment we know a real, confirmed
person is sitting in the queue. The service makes it happen exactly once per user.
"""

import os
from urllib.parse import quote

from flask import g, jsonify, request

from . import account_bp
from ..services import signup_service


def _approve_link(user_id: str) -> str:
    """One-tap approve URL for the operator's ping (empty when not configured)."""
    token = os.environ.get("ADMIN_APPROVE_TOKEN", "")
    if not token:
        return ""
    base = os.environ.get("PUBLIC_API_URL", "").rstrip("/") or request.url_root.rstrip("/")
    return f"{base}/admin/approve?user={quote(user_id)}&token={quote(token)}"


@account_bp.route('/status', methods=['GET'])
def status():
    user = getattr(g, "user", None) or {}
    meta = user.get("user_metadata") or {}
    user_id = user.get("sub")
    email = user.get("email") or ""
    name = meta.get("full_name") or meta.get("name") or ""

    approved = signup_service.is_approved(user_id, email, name)
    if not approved:
        signup_service.ping_operator_about_waiting_user(
            user_id, email, name, _approve_link(user_id))

    return jsonify({"success": True, "data": {
        "approved": approved,
        "email": user.get("email"),
        "waitlist_enabled": signup_service.gate_enabled(),
    }})
