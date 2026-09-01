"""
validate_health_surfacing - prove the conditional health block is honest, with
the LLM OFF.

Checks:

  1. The trigger list really comes from document_context_engine's healthcare
     domain (if the lazy import ever breaks, this fails loud instead of
     silently shrinking the trigger set).
  2. Seed matching is boundary-aware: health seeds match; unrelated seeds do
     not; "healthy economy" does NOT (the substring-matching false positive).
  3. build_health_block renders real GHS facts for a health seed and returns ""
     for unrelated seeds or personas without health fields.
  4. sa_context still fails safe to None when dynamic search is disabled.
  5. sa_world_facts.json carries the two health facts, valid per world_facts.

Run:  python backend/scripts/validate_health_surfacing.py
Exit 0 = all checks pass; 1 = any failure.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    # Import-time guard only: agentsociety2 demands an API key to import, but this
    # validator never calls an LLM.
    os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "offline-validator")
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

    sys.path.insert(0, os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")))

    from app.services.mode_specs import (
        _health_triggers, build_health_block, seed_is_health_adjacent)

    # ── 1. Trigger source integrity ─────────────────────────────────────────
    triggers = _health_triggers()
    for expected in ("health", "clinic", "medical aid", "healthcare"):
        assert expected in triggers, f"trigger '{expected}' missing: {triggers}"
    print(f"OK - {len(triggers)} health triggers sourced from document_context_engine.")

    # ── 2. Boundary-aware seed matching ─────────────────────────────────────
    assert seed_is_health_adjacent("New clinic medicine shortages announced")
    assert seed_is_health_adjacent("Healthcare reform debate")           # added word
    assert seed_is_health_adjacent("Is medical aid worth it?")           # multi-word
    assert not seed_is_health_adjacent("Taxi fare increase proposal")
    assert not seed_is_health_adjacent("The healthy economy grows")      # FP guard
    assert not seed_is_health_adjacent("")                               # no seed
    assert not seed_is_health_adjacent(None)
    print("OK - health seeds match; 'healthy economy' and unrelated seeds do not.")

    # ── 3. Conditional block rendering ──────────────────────────────────────
    st = {
        "medical_aid": False,
        "self_rated_health": "Fair",
        "has_disability": False,
        "usual_health_facility": "Public clinic",
        "health_facility_sector": "public",
        "transport_to_health_facility": "On foot",
        "time_to_health_facility": "More than 30 minutes",
    }
    block = build_health_block(st, "Clinic medicine shortages in Gauteng")
    assert "YOUR HEALTH REALITY" in block, "block missing for a health seed"
    for fact in ("none", "Fair", "Public clinic", "On foot"):
        assert fact in block, f"real fact '{fact}' not rendered"
    assert not build_health_block(st, "Taxi fare increase proposal"), \
        "block leaked into an unrelated sim"
    assert not build_health_block(st, "The healthy economy grows"), \
        "false-positive seed pulled the health block in"
    assert not build_health_block({}, "clinic shortages"), \
        "block rendered without any health facts"
    print("OK - block appears for health seeds only, carrying the real GHS facts.")

    # ── 4. sa_context fails safe when disabled ──────────────────────────────
    old = os.environ.get("SA_CONTEXT_DYNAMIC")
    os.environ["SA_CONTEXT_DYNAMIC"] = "0"
    try:
        from app.services.sa_context import current_sa_realities
        assert current_sa_realities() is None, \
            "sa_context did not return None with SA_CONTEXT_DYNAMIC=0"
    finally:
        if old is None:
            os.environ.pop("SA_CONTEXT_DYNAMIC", None)
        else:
            os.environ["SA_CONTEXT_DYNAMIC"] = old
    print("OK - sa_context returns None cleanly when search is disabled.")

    # ── 5. Health world facts present and valid ─────────────────────────────
    from app.services.world_facts import load_facts, is_valid_fact
    facts = {f["item"]: f for f in load_facts()}
    for item, expect in (("medical_aid_coverage_share", 16.54),
                         ("public_health_facility_dependence_share", 73.29)):
        f = facts.get(item)
        assert f, f"world fact '{item}' missing from sa_world_facts.json"
        assert is_valid_fact(f), f"world fact '{item}' is not valid (needs value+unit)"
        assert abs(float(f["value"]) - expect) < 0.01, \
            f"world fact '{item}' drifted: {f['value']} != {expect}"
    print("OK - both health world facts present with the real GHS values.")

    print("\nPASS - health surfacing is conditional, honest, and fail-safe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
