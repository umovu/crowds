"""
mechanism_card_service — deterministic binding of research mechanism cards
to cast personas (Phase 5 of the academic-grounding design).

Cards are human-reviewed distillations of SA research papers (see
backend/app/data/mechanism_cards/README.md and the extraction protocol in the
context-grounding pilot worktree). Each card carries citations and up to five
self-contained claims: a reasoning pattern with its own rule, sources, objections
and vocabulary.

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
import re
from typing import Dict, List

try:  # the sim subprocess and some tests load this module by file path, with no package
    from . import data_model as _data_model
except ImportError:
    _data_model = None

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
                if card.get("id") and card.get("claims"):
                    # A card off its model still loads (one bad card must not empty the
                    # cast path), but a rule that names a missing fact binds nobody, so say so.
                    if _data_model is not None:
                        problems = _data_model.mechanism_card_problems(card, fname)
                        if problems:
                            logger.warning(f"mechanism card {fname} does not match its data model: "
                                           f"{len(problems)} problem(s). First: {'; '.join(problems[:3])}")
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


def _format_card_header(c: Dict) -> str:
    citation = c.get("citation")
    cite = citation[0] if isinstance(citation, list) and citation else str(citation or "")
    claim = c.get("claim_type", "qualitative")
    year = (c.get("year_range") or "date unknown").strip() or "date unknown"
    region = (c.get("region") or "location not specified").strip() or "location not specified"
    conf = (c.get("confidence") or "").strip()
    header = f"From {cite} [{claim}] — {region}, {year}"
    if conf:
        header += f" — confidence/limits: {conf[:220]}"
    return header


def render_research_context(cards: List[Dict]) -> str:
    """Conditional, dated research block — each card shows when/where it was
    observed and under what conditions, so a past hardship is not read as a
    permanent trait. Preserves the pilot hoops and adds the Item 2 gate."""
    if not cards:
        return ""
    lines = [
        "# Research-grounded context for people like you (reason through this; do not quote it verbatim)",
        "Each card below is CONDITIONAL evidence: it describes what some people did "
        "WHEN specific conditions held, in a specific place and time. A credible "
        "improvement in those conditions may change the response, but past "
        "disappointment can still shape trust. Never treat a group pattern as a fixed trait.",
    ]
    for c in cards:
        lines.append(f"\n{_format_card_header(c)}:")
        vocabulary: List[str] = []
        for claim in c.get("claims", []):
            vocabulary += [v for v in claim.get("vocabulary") or [] if v not in vocabulary]
            txt = str(claim.get("text", "")).strip()
            if txt.lower().startswith("when ") or txt.lower().startswith("if ") or " when " in txt.lower() or " if " in txt.lower():
                lines.append(f"  - {txt}")
            else:
                lines.append(f"  - When the conditions described held, {txt[0].lower() + txt[1:] if txt else txt}")
            if "impossible" in txt.lower() or "always" in txt.lower() or "never" in txt.lower():
                lines[-1] += " — in that study context; a sustained improvement may change this, but trust recovers slowly."
        if vocabulary:
            lines.append(f"  Vocabulary people like you use: {', '.join(vocabulary)}")
    lines.append(
        "\nThese are documented patterns for people in your situation — where they "
        "conflict with your own stated outlook and beliefs, your own outlook prevails."
        "\nThe patterns describe how people like you responded UNDER the conditions and limits above. "
        "React ONLY to what is actually described to you: if a pattern "
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


def topic_matches(card: Dict, question: str) -> bool:
    """True when the question names one of the card's human-authored topic_tags.

    Whole-word match on both sides: a tag names a subject ("bank", "school"), and a
    stem match would let "car" fire inside "care". A card without topic_tags never
    matches — binding says WHO a card fits, topic_tags say WHAT it is about.
    """
    low = (question or "").lower()
    return any(re.search(r"(?<![a-z0-9])" + re.escape(str(t).lower()) + r"(?![a-z0-9])", low)
               for t in (card.get("topic_tags") or []))


def cards_for_question(profile: Dict, question: str, cap: int = DEFAULT_CARD_CAP):
    """The bound cards whose subject the question touches, or None for a legacy profile.

    Binding at cast build stays by archetype (who the research studied). This is the
    second gate, applied at prompt time: a clinic panel gave all twelve salaried
    professionals a middle-class-spending card and a fintech-trust card — about 80% of
    every prompt, on nothing the question was about.

    Returns None when the profile carries research_context but no citations (a cast
    built before citations existed), so the caller keeps its stored block rather than
    silently dropping evidence it cannot re-derive.
    """
    citations = profile.get("research_citations")
    if not citations:
        return None if profile.get("research_context") else []
    by_id = {c.get("id"): c for c in load_cards()}
    facts = situation_facts(profile)
    bound = [narrowed_to(by_id[c.get("card_id")], facts) for c in citations
             if isinstance(c, dict) and c.get("card_id") in by_id]
    return [c for c in bound if c and topic_matches(c, question)][:cap]


# ── Situation matching: WHO a card describes, read from the persona's own record ──
#
# Cards were bound by actor_archetype label alone. That handed a middle-class
# status card to a professional whose record says he is often short of food, and
# left 81 of 375 personas (every "affluent/comfortable/rural landholding household")
# with no card at all, because no card listed their label. A card now says, in its
# `applies_when`, which measured facts describe the population its research studied:
#
#   "applies_when": [ {"owns_vehicle": ["none"]},
#                     {"geotype": ["Traditional", "Farms"]} ]
#
# Each object is a clause whose fields must ALL hold; the card applies when ANY
# clause holds. A persona missing a field a clause needs does not satisfy that clause
# — a card needs evidence to be handed out (stricter than the objection grounds,
# where missing data never counts against someone, because a card shapes the whole
# answer). A card without `applies_when` falls back to the archetype binding above.

# Top-level record fields a clause may test, besides circumstances and attitudes.
# Checked against the persona class at import when the app package is there: a
# misspelt field fails loudly instead of quietly matching nobody.
try:
    from ..models.persona import FACT as _FACT
except ImportError:  # loaded by file path (sim subprocess, path-loaded tests)
    _FACT = None
_SITUATION_FIELDS = tuple(getattr(_FACT, f) if _FACT is not None else f for f in (
    "geotype", "employment_status", "is_neet", "informal", "ghs_role",
    "learners_in_household", "receives_grant", "farm_market_orientation",
    "farm_products", "health_facility_sector", "medical_aid",
    "transport_to_health_facility", "time_to_health_facility", "race", "gender",
    "province", "education",
))


def _age_band(age) -> str | None:
    try:
        years = int(age)
    except (TypeError, ValueError):
        return None
    if years < 25:
        return "15-24"
    if years < 35:
        return "25-34"
    if years < 60:
        return "35-59"
    return "60+"


def _youth_age_band(age) -> str | None:
    """A finer split than `age_band` for research on young people.

    `age_band` lumps 15 to 24 together, but youth studies recruit from 16 (school
    learners) or 18 (young adults), so a claim from an 18-24 study must not reach a
    15-year-old. Kept separate so the cards already written against 15-24 are unchanged.
    """
    try:
        years = int(age)
    except (TypeError, ValueError):
        return None
    if years < 16:
        return "under-16"
    if years < 18:
        return "16-17"
    if years < 25:
        return "18-24"
    return "25+"


def situation_facts(profile: Dict) -> Dict[str, str]:
    """A persona's measured facts, flattened to {field: value-as-string}.

    Same shape as objections.persona_facts (kept separate so this module stays
    import-light for the sim subprocess and path-loaded tests), plus the GHS
    top-level fields and a derived `age_band`.
    """
    facts: Dict[str, str] = {}
    for row in profile.get("circumstances") or []:
        if isinstance(row, dict) and row.get("field") and row.get("value") is not None:
            facts[row["field"]] = str(row["value"])
    for row in profile.get("attitudes") or []:
        if isinstance(row, dict) and row.get("topic") and row.get("stance"):
            facts[row["topic"]] = str(row["stance"])
    for field in _SITUATION_FIELDS:
        value = profile.get(field)
        if value not in (None, "", []):
            facts[field] = str(value)
    band = _age_band(profile.get("age"))
    if band:
        facts["age_band"] = band
    youth = _youth_age_band(profile.get("age"))
    if youth:
        facts["youth_age_band"] = youth
    return facts


def situation_match_strength(card: Dict, facts: Dict[str, str]) -> int:
    """0 when the card does not describe this persona; otherwise the size of the most
    specific clause that holds (more conditions met = a closer fit)."""
    return _clause_strength(card.get("applies_when"), facts)


def _clause_strength(clauses, facts: Dict[str, str]) -> int:
    best = 0
    for clause in clauses or []:
        if clause and all(facts.get(field) in allowed for field, allowed in clause.items()):
            best = max(best, len(clause))
    return best


# A card can bundle findings on different groups: the middle-class card carried a
# claim about the income-insecure next to claims about the settled middle class, and
# matching the card put all of them in a secure professional's prompt. Each claim
# carries its own `needs`, and its objections and vocabulary travel with it, so a
# claim left out of a prompt takes its words with it.

def narrowed_to(card: Dict, facts: Dict[str, str]) -> Dict | None:
    """The card as this persona's prompt should see it: only the claims about people
    like them. None when none are. A claim whose needs are [] is about everyone the
    card fits."""
    claims = card.get("claims") or []
    kept = [c for c in claims if not c.get("needs") or _clause_strength(c["needs"], facts)]
    if not kept:
        return None
    return card if len(kept) == len(claims) else {**card, "claims": kept}


def cards_for_persona(profile: Dict, cap: int | None = None) -> List[Dict]:
    """Every card whose situation this persona's record fits, closest fit first.

    Deliberately NOT capped by default. The cap belongs at prompt time, after
    cards_for_question keeps only cards about the question's subject — capping here
    first is how two cards reached nobody (crowded out by others on the same people)
    and how a relevant health card would lose to two unrelated ones.
    """
    if not _enabled():
        return []
    facts = situation_facts(profile)
    legacy_ids = None
    scored = []
    for card in load_cards():
        if card.get("applies_when"):
            strength = situation_match_strength(card, facts)
        else:
            if legacy_ids is None:
                legacy_ids = {c["id"] for c in cards_for_archetype(
                    profile.get("actor_archetype", ""), cap=99,
                    budget_tier=profile.get("budget_tier"), geotype=profile.get("geotype"))}
            strength = 1 if card["id"] in legacy_ids else 0
        view = narrowed_to(card, facts) if strength else None
        if view:
            scored.append((strength, view))
    scored.sort(key=lambda sc: (-sc[0], sc[1].get("id", "")))
    cards = [card for _strength, card in scored]
    return cards if cap is None else cards[:cap]


def attach_research_context(profile: Dict, cap: int = DEFAULT_CARD_CAP) -> Dict:
    """Mutate-and-return: attach research_context/research_citations to a cast
    profile when any card's situation fits it. No-op (and no keys added) when
    nothing fits or the flag is off — an absent key IS the honest signal.

    `research_citations` lists EVERY fitting card, so the prompt-time subject filter
    (cards_for_question) can choose among all of them. `research_context` renders only
    the closest `cap` fits, for callers that inject it unfiltered (the sim feed path),
    so their prompt size stays where it was.
    """
    bound = cards_for_persona(profile)
    if bound:
        profile["research_context"] = render_research_context(bound[:cap])
        profile["research_citations"] = citations_for(bound)
    return profile
