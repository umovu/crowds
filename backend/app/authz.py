"""
Resource ownership checks.

`auth.verify_request` proves WHO the caller is; it says nothing about WHAT they
may touch. Every route that takes a `<simulation_id>` or `<session_id>` from the
URL must additionally prove the caller owns that resource — otherwise any
signed-in user can read or delete another tenant's pitches, personas and
results by guessing/replaying an id (IDOR).

Semantics match `SimulationManager.list_simulations`, which is the behaviour the
listing endpoints already shipped with:

  - resource owned by the caller        -> allowed
  - resource with NO stored user_id     -> allowed (legacy, pre-auth records)
  - resource owned by someone else      -> denied

Denials return **404, not 403**: a 403 confirms the id exists, which turns the
endpoint into an existence oracle for enumerating other tenants' work.
"""

from flask import jsonify

from . import billing
from .utils.logger import get_logger

logger = get_logger("fub.authz")


def owns(resource_user_id) -> bool:
    """True if the current caller may access a resource with this owner id."""
    if not resource_user_id:
        return True  # legacy record with no owner recorded
    return resource_user_id == billing.current_user_id()


def deny_404(kind: str, resource_id: str, owner_id):
    """Build the not-found response for a failed ownership check, and log it.

    Logged at warning level with both ids: a burst of these is the signature of
    someone walking the id space.
    """
    logger.warning(
        "Ownership denied: caller=%s tried to access %s %s owned by %s",
        billing.current_user_id(), kind, resource_id, owner_id,
    )
    return jsonify({
        "success": False,
        "error": f"{kind.capitalize()} {resource_id} not found",
    }), 404


def check_panel_session(session_id: str):
    """Return None if the caller owns the panel session, else a response tuple.

    Also returns 404 when the session does not exist, so callers can use this as
    a single combined existence + ownership guard.
    """
    from .services import panel_service

    try:
        meta = panel_service.get_session(session_id)
    except ValueError:
        # Malformed id (traversal attempt) — same 404 as a miss, no detail back.
        logger.warning("Rejected malformed session id from caller=%s: %r",
                       billing.current_user_id(), session_id)
        meta = None
    if not meta:
        return jsonify({
            "success": False,
            "error": f"Session {session_id} not found",
        }), 404
    if not owns(meta.get("user_id")):
        return deny_404("session", session_id, meta.get("user_id"))
    return None


def check_simulation(simulation_id: str, missing_ok: bool = False):
    """Return None if the caller owns the simulation, else a response tuple.

    `missing_ok=True` lets a not-yet-existing id through to the handler instead
    of 404ing here. Needed for body-carried ids on endpoints like
    /prepare/status, which the UI polls *before* the sim exists and which must
    keep answering "not prepared" rather than "not found". A nonexistent sim has
    no owner to leak, so passing it through costs nothing.
    """
    from .services.simulation_manager import SimulationManager

    state = SimulationManager().get_simulation(simulation_id)
    if not state:
        if missing_ok:
            return None
        return jsonify({
            "success": False,
            "error": f"Simulation does not exist: {simulation_id}",
        }), 404
    if not owns(getattr(state, "user_id", None)):
        return deny_404("simulation", simulation_id, getattr(state, "user_id", None))
    return None
