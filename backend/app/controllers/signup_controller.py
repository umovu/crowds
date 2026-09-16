"""Getting in, for people who have no account yet.

  POST /api/waitlist/request         {email, name?, note?}
  POST /api/waitlist/password-reset  {email}

Auth-exempt on purpose (see `create_app`): the caller is a stranger. Nothing here
creates an auth user — it files a request the operator reviews.

Both routes answer the same way whether or not the email is already known, so the
form never tells a stranger who has applied. The rules live in signup_service.
"""

from flask import jsonify, request

from . import signup_bp
from ..services import signup_service


def _caller_ip() -> str:
    return (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.remote_addr or "?")


def _answer(outcome):
    key = "data" if outcome.ok else "error"
    body = {"message": outcome.message} if outcome.ok else outcome.message
    return jsonify({"success": outcome.ok, key: body}), outcome.status


@signup_bp.route('/request', methods=['POST'])
def request_access():
    data = request.get_json(silent=True) or {}
    return _answer(signup_service.request_access(
        email=data.get("email"),
        name=data.get("name"),
        note=data.get("note"),
        caller_ip=_caller_ip(),
    ))


@signup_bp.route('/password-reset', methods=['POST'])
def password_reset():
    import os
    data = request.get_json(silent=True) or {}
    return _answer(signup_service.send_password_reset(
        email=data.get("email"),
        caller_ip=_caller_ip(),
        app_url=os.environ.get("PUBLIC_APP_URL", ""),
    ))
