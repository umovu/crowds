"""
income_seeder — deterministic, LLM-free income signals for personas.

First piece (implemented): GRANT BENEFICIARIES. Grant recipients (~28M / ~⅓ of
SA) break the occupation→income model — many have no occupation income; the grant
IS the income, and its amount is *published policy*, i.e. a real KNOWN number, not
an estimate. So for these personas we attach the real grant value as income with
provenance "grant_schedule" — the highest-integrity income source in the system.

Detection uses ONLY signals already present on a persona (actor_archetype,
occupation, background_story, the safety_economic need). No persona-generation
change, no persona_cache bump. Everything here is a pure function, assertable with
the LLM switched off.

(Occupation→income distribution seeding is a separate, larger piece gated behind a
data-sourcing spike — see the plan; not implemented here.)
"""

import json
import os
from typing import Any, Dict, Optional, Tuple

from ..utils.logger import get_logger

logger = get_logger("fub.income_seeder")

GRANT_PROVENANCE = "grant_schedule"

# safety_economic (0–100) at/below this corroborates grant dependency.
_SAFETY_ECONOMIC_CRITICAL = 20

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),  # backend/
    "data", "sa_grant_amounts.json",
)

_GRANTS_CACHE: Optional[Dict[str, Any]] = None


def _load_grants() -> Dict[str, Any]:
    """Load and cache the SASSA grant amounts table (real published policy)."""
    global _GRANTS_CACHE
    if _GRANTS_CACHE is None:
        try:
            with open(_DATA_PATH, "r", encoding="utf-8") as f:
                _GRANTS_CACHE = json.load(f)
        except Exception as e:
            logger.warning(f"Grant amounts table unavailable ({e}); grant tracking inert.")
            _GRANTS_CACHE = {"grants": {}, "effective_date": None}
    return _GRANTS_CACHE


def grant_effective_date() -> Optional[str]:
    return _load_grants().get("effective_date")


def _match_grant_type(text: str) -> Optional[str]:
    """Return the most specific grant key whose keyword appears in `text`.

    Specific grants are checked before the generic catch-all so e.g. "old age
    pension" maps to older_person, not generic. Pure keyword match — no LLM.
    """
    grants = _load_grants().get("grants", {})
    blob = (text or "").lower()
    # Specific types first; "generic" last as a fallback.
    ordered = [k for k in grants if k != "generic"] + (["generic"] if "generic" in grants else [])
    for key in ordered:
        for kw in grants[key].get("keywords", []):
            if kw in blob:
                return key
    return None


def detect_grant(
    actor_archetype: Optional[str] = None,
    occupation: Optional[str] = None,
    background_story: Optional[str] = None,
    safety_economic: Optional[int] = None,
) -> Tuple[bool, Optional[str], Optional[int]]:
    """Detect grant dependency from EXISTING persona signals only.

    Returns (is_grant_dependent, grant_type, monthly_grant_amount_rand).

    Logic (deterministic):
      1. Scan occupation + background_story for a specific grant keyword → that type.
      2. The `grant_dependent_survivor` archetype with no specific keyword →
         the generic grant.
      3. Critically-low safety_economic alone does NOT trigger (too weak on its
         own — poverty ≠ grant), but it upgrades an otherwise-ambiguous archetype
         signal. It is corroborating, never sufficient.
    """
    text = " ".join(filter(None, [str(occupation or ""), str(background_story or "")]))
    gtype = _match_grant_type(text)

    arch = (actor_archetype or "").strip().lower()
    is_grant_archetype = arch == "grant_dependent_survivor"

    try:
        se = int(safety_economic) if safety_economic is not None else None
    except (TypeError, ValueError):
        se = None

    if gtype is None:
        # No explicit grant mention. Only the grant archetype (optionally
        # corroborated by low economic security) implies a generic grant.
        if is_grant_archetype:
            gtype = "generic"
        else:
            return (False, None, None)

    grants = _load_grants().get("grants", {})
    spec = grants.get(gtype) or grants.get("generic") or {}
    amount = spec.get("monthly_amount")
    return (True, gtype, amount)


def grant_label(grant_type: Optional[str]) -> Optional[str]:
    if not grant_type:
        return None
    spec = _load_grants().get("grants", {}).get(grant_type, {})
    return spec.get("label")
