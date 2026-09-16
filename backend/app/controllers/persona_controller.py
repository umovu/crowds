"""Browsing the curated persona library.

  GET /api/research/personas              the list for the side panel
  GET /api/research/personas/<persona_id> one persona's full profile

Library personas only. The old runtime cache held model-generated personas and is
no longer served: no persona in a room may be model-authored (CLAUDE.md). The ids
here are the same ids the panel segments' `members` lists use, so picks line up on
the frontend.
"""

from flask import jsonify

from . import persona_bp
from ..services.persona_library import get_library
from ..utils.logger import get_logger

logger = get_logger("fub.controller.persona")

#: Hex-only, so a stray path cannot become a library lookup.
_HEX = set("0123456789abcdef")


def _card(persona: dict) -> dict:
    """The metadata the side-panel list shows for one persona."""
    return {
        "id":         persona.get("id") or (persona.get("name") or "")[:32],
        "name":       persona.get("name") or "Unknown",
        "archetype":  persona.get("actor_archetype") or "",
        "age":        persona.get("age"),
        "gender":     persona.get("gender"),
        "occupation": persona.get("occupation"),
        "province":   persona.get("province"),
        "fees_band":         persona.get("fees_band"),
        "learner_fee_bands": persona.get("learner_fee_bands") or [],
        # Living-standard proxy band, stamped at library load (services/lsm_proxy.py).
        # Pure asset score, no LLM.
        "lsm_proxy":  persona.get("lsm_proxy"),
        "level":      "library",
    }


@persona_bp.route("/personas", methods=["GET"])
def list_personas():
    """Every library persona, metadata only, sorted by archetype then name."""
    try:
        personas = [_card(p) for p in get_library().all()]
    except Exception as e:  # noqa: BLE001
        logger.error("List personas failed: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500
    personas.sort(key=lambda p: (p["archetype"] or "", p["name"] or ""))
    return jsonify({"success": True, "count": len(personas), "personas": personas})


@persona_bp.route("/personas/<persona_id>", methods=["GET"])
def get_persona(persona_id: str):
    """One persona's full stored profile, by its stable library id.

    The response keeps its old shape (profile / meta / markdown) so the frontend's
    getPersona() consumer does not branch. Library personas have no rendered
    sidecar, so `markdown` is always empty.
    """
    if not persona_id or any(c not in _HEX for c in persona_id.lower()):
        return jsonify({"success": False, "error": "Invalid persona id"}), 400
    try:
        persona = get_library().get(persona_id)
    except Exception as e:  # noqa: BLE001
        logger.error("Library lookup for persona %s failed: %s", persona_id[:12], e)
        persona = None
    if not persona:
        return jsonify({"success": False, "error": "Persona not found"}), 404
    return jsonify({
        "success":  True,
        "profile":  persona,
        "meta":     {"level": "library", "entity": persona.get("name"),
                     "type": persona.get("actor_archetype")},
        "markdown": "",
    })
