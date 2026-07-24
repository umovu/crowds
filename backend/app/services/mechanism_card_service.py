"""
mechanism_card_service — deterministic binding of research mechanism cards
to cast personas (Phase 5 of the academic-grounding design).

Cards are human-reviewed distillations of SA research papers (see
backend/app/data/mechanism_cards/README.md and the extraction protocol in the
context-grounding pilot worktree). Each card carries qualitative reasoning
mechanisms, vocabulary, and citations for one or more persona archetypes.

Hard rules this module preserves:
  * LLM-free and deterministic — binding is a segment_tags set-membership
    lookup, assertable with the model off (same discipline as
    archetype_mapper / attitude_fuser).
  * Cards contribute reasoning context only — never identity, never numbers.
    The rendered block instructs the model that the persona's own measured
    attitudes outrank the cards' group-level patterns.
  * Coverage honesty — an archetype with no matching card gets nothing
    (no forced binding to the nearest non-match).

Flag: RESEARCH_CONTEXT_ENABLED (env, default on). "0"/"false"/"off" disables
binding entirely, reverting the sim to pre-Phase-5 behavior.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, List

logger = logging.getLogger(__name__)

_CARDS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "data", "mechanism_cards"
))

# Max cards injected per persona. Broad archetypes bind up to 5 cards
# (~25 mechanisms) — too much prompt for the sim tier's thousands of calls.
# Specificity ranking (below) makes the cap keep the RIGHT cards.
DEFAULT_CARD_CAP = 2

_cache: List[Dict] | None = None


def _enabled() -> bool:
    return os.environ.get("RESEARCH_CONTEXT_ENABLED", "1").strip().lower() not in (
        "0", "false", "off", "no",
    )


def load_cards(cards_dir: str = _CARDS_DIR) -> List[Dict]:
    """All mechanism cards on disk (module-cached; README.md is skipped)."""
    global _cache
    if _cache is not None:
        return _cache
    cards: List[Dict] = []
    if os.path.isdir(cards_dir):
        for fname in sorted(os.listdir(cards_dir)):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(cards_dir, fname), "r", encoding="utf-8") as f:
                    card = json.load(f)
                if card.get("id") and card.get("mechanisms"):
                    cards.append(card)
            except Exception as e:  # noqa: BLE001 — one bad file must not kill the cast path
                logger.warning(f"mechanism card {fname} unreadable, skipped: {e}")
    _cache = cards
    return cards


# Archetypes that are RURAL by definition. A card naming one of these is about a
# rural activity (subsistence/market farming, livestock), so it is "rural-scoped".
_RURAL_ARCHETYPES = {"communal_farmer", "smallholder_emerging_farmer"}
# QLFS/GHS geotype values that count as rural for binding.
_RURAL_GEOTYPES = {"Traditional", "Farms"}


def _is_rural_scoped(card: Dict) -> bool:
    """A card is rural-scoped if any of its segment_tags is a rural archetype — i.e. its
    studied population lives and works rurally (farming, livestock)."""
    return bool(_RURAL_ARCHETYPES & set(card.get("segment_tags") or []))


def cards_for_archetype(
    archetype: str,
    cap: int = DEFAULT_CARD_CAP,
    budget_tier: str | None = None,
    geotype: str | None = None,
) -> List[Dict]:
    """Cards whose segment_tags contain `archetype`, most specific first.

    Specificity = fewer segment_tags (a card naming one archetype knows its
    population better than one naming eight). Ties break on card id so the
    result is fully deterministic. Empty when the flag is off, the archetype
    is blank, or nothing matches (coverage honesty — never force-bind).

    `budget_tier` (product-mode casts only) additionally filters on the card's
    `economic_tags` — the tiers the paper's studied population maps to, set by
    the human at extraction time. A card without economic_tags applies to all
    tiers (back-compat and the honest default for class-blind studies). Policy
    casts have no tier, so no filtering happens there.

    `geotype` guards RURAL-SCOPED cards. A broad archetype like
    `grant_dependent_survivor` lumps two lives together — an urban township grant
    recipient (no land) and a rural subsistence grower (lives inside the farming
    mechanisms). Without this, a farming card bound via the broad tag reached the
    urban persona too (measured: 57 mis-bindings across the farm cards, e.g. a
    KwaMashu grant recipient handed "price taker / market surplus" reasoning). A
    persona binds a rural-scoped card only if they are a farmer themselves
    (archetype in _RURAL_ARCHETYPES) OR live rurally. `geotype=None` (unknown, e.g.
    a pre-rebuild persona) is left untouched — the guard only tightens where the
    settlement is actually known.
    """
    if not archetype or not _enabled():
        return []
    matched = [c for c in load_cards() if archetype in (c.get("segment_tags") or [])]
    if budget_tier:
        matched = [c for c in matched
                   if not c.get("economic_tags") or budget_tier in c["economic_tags"]]
    # Rural-scope coherence: drop a rural-scoped card for an urban non-farmer persona.
    if geotype is not None and archetype not in _RURAL_ARCHETYPES \
            and geotype not in _RURAL_GEOTYPES:
        matched = [c for c in matched if not _is_rural_scoped(c)]
    matched.sort(key=lambda c: (len(c.get("segment_tags") or []), c.get("id", "")))
    return matched[:cap]


def render_research_context(cards: List[Dict]) -> str:
    """The pilot-validated prompt block (Stage 6, 15/15 hoop-test pass),
    closed by the precedence rule: measured survey data about THIS person
    outranks documented patterns about people LIKE this person."""
    if not cards:
        return ""
    lines = ["# Research-grounded context for people like you (reason through this; do not quote it verbatim)"]
    for c in cards:
        citation = c.get("citation")
        cite = citation[0] if isinstance(citation, list) and citation else str(citation or "")
        lines.append(f"\nFrom {cite} [{c.get('claim_type', 'qualitative')}]:")
        lines.extend(f"  - {m}" for m in c.get("mechanisms", []))
        if c.get("vocabulary"):
            lines.append(f"  Vocabulary people like you use: {', '.join(c['vocabulary'])}")
    lines.append(
        "\nThese are documented patterns for people in your situation — where they "
        "conflict with your own stated outlook and beliefs, your own outlook prevails."
        "\nThe patterns describe how people like you respond to specific product/policy "
        "features. React ONLY to what is actually described to you: if a pattern "
        "concerns a feature (e.g. leaderboards, public rankings, removal rules) that "
        "is NOT stated, do not assume the product has it — raise it as a question or "
        "a condition ('if this ranks my child publicly, then...'), never as a fact."
    )
    return "\n".join(lines)


def citations_for(cards: List[Dict]) -> List[Dict]:
    """Provenance records for the run/UI: which research backed this persona."""
    out = []
    for c in cards:
        citation = c.get("citation")
        out.append({
            "card_id": c.get("id"),
            "citation": citation if isinstance(citation, list) else [str(citation or "")],
            "confidence": c.get("confidence", ""),
        })
    return out


def attach_research_context(profile: Dict, cap: int = DEFAULT_CARD_CAP) -> Dict:
    """Mutate-and-return: attach research_context/research_citations to a cast
    profile when its archetype binds cards. No-op (and no keys added) when
    nothing binds or the flag is off — an absent key IS the honest signal."""
    bound = cards_for_archetype(
        profile.get("actor_archetype", ""),
        cap=cap,
        budget_tier=profile.get("budget_tier"),
        geotype=profile.get("geotype"),
    )
    if bound:
        profile["research_context"] = render_research_context(bound)
        profile["research_citations"] = citations_for(bound)
    return profile
