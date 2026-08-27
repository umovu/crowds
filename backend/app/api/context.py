"""Operator context API — one saved business description per user."""

from flask import jsonify, request

from . import context_bp
from .. import billing
from ..services import operator_context as oc

MAX_LEN = 1500


@context_bp.route("", methods=["GET"])
def get_context():
    user_id = billing.current_user_id()
    # Fail-open: unauthenticated / Supabase not configured -> empty
    if not user_id:
        return jsonify({"success": True, "data": {"body": "", "updated_at": None}})
    body = oc.get_operator_context(user_id)
    # updated_at is not critical for v1; fetch if needed later
    return jsonify({"success": True, "data": {"body": body, "updated_at": None}})


@context_bp.route("", methods=["PUT"])
def put_context():
    user_id = billing.current_user_id()
    if not user_id:
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    data = request.get_json(silent=True) or {}
    body = data.get("body", "")
    if not isinstance(body, str):
        return jsonify({"success": False, "error": "body must be a string"}), 400
    body = body.strip()
    if len(body) > MAX_LEN:
        body = body[:MAX_LEN]
    try:
        saved = oc.save_operator_context(user_id, body)
        return jsonify({"success": True, "data": saved})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
