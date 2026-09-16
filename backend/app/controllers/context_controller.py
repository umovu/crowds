"""Operator context — one saved business description per user.

  GET /api/context   the caller's saved description
  PUT /api/context   replace it

The GET fails open: an unauthenticated caller, or an unconfigured Supabase, reads as
empty rather than an error, because a blank business description is a normal state and
the panel prompt treats it as one. The PUT does not — writing needs a known user.
"""

from flask import jsonify, request

from . import context_bp
from ..auth import current_user_id
from ..repositories import operator_context_repository as oc

#: Longer descriptions are truncated, not refused.
MAX_LEN = 1500


@context_bp.route("", methods=["GET"])
def get_context():
    user_id = current_user_id()
    # Fail-open: unauthenticated / Supabase not configured -> empty
    if not user_id:
        return jsonify({"success": True, "data": {"body": "", "updated_at": None}})
    # updated_at is not critical for v1; fetch if needed later
    return jsonify({"success": True,
                    "data": {"body": oc.get(user_id), "updated_at": None}})


@context_bp.route("", methods=["PUT"])
def put_context():
    user_id = current_user_id()
    if not user_id:
        return jsonify({"success": False, "error": "Not authenticated"}), 401

    body = (request.get_json(silent=True) or {}).get("body", "")
    if not isinstance(body, str):
        return jsonify({"success": False, "error": "body must be a string"}), 400

    body = body.strip()[:MAX_LEN]
    try:
        return jsonify({"success": True, "data": oc.save(user_id, body)})
    except Exception as e:  # noqa: BLE001
        return jsonify({"success": False, "error": str(e)}), 500
