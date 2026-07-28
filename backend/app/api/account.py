"""
Account API — who the caller is and whether they're through the waitlist.

  GET /api/account/status   {approved, email, waitlist_enabled}

Exempt from the waitlist gate (see `create_app`), because a pending user must
be able to load this to see the waitlist screen.
"""

from flask import g, jsonify

from . import account_bp
from .. import approval


@account_bp.route('/status', methods=['GET'])
def status():
    user = getattr(g, "user", None) or {}
    return jsonify({"success": True, "data": {
        "approved": approval.current_user_approved(),
        "email": user.get("email"),
        "waitlist_enabled": approval.waitlist_enabled(),
    }})
