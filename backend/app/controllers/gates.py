"""Turning a quota decision into an HTTP answer.

`billing_service` answers with a `Gate`, because the rules must be testable without a
request in flight. Routes need a Flask response, so the conversion lives here — one
copy, used by the controllers.

The shape matters: the frontend shows the upgrade modal on `code == "upgrade_required"`,
so a refusal must keep carrying it.
"""

from flask import jsonify

from ..services import billing_service


def _refusal(gate):
    return jsonify({"success": False, "error": gate.message, "code": gate.code}), 402


def panel_quota(user_id):
    """None when the user may run a panel, or a 402 response when they may not."""
    gate = billing_service.check_panel_quota(user_id)
    return None if gate.allowed else _refusal(gate)


def sim_quota(user_id):
    """None when the user may run a simulation, or a 402 response when they may not."""
    gate = billing_service.check_sim_quota(user_id)
    return None if gate.allowed else _refusal(gate)
