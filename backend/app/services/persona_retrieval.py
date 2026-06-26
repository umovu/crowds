"""
persona_retrieval — pick a simulation cast from the library: representative, tilted.

Given a user's scenario, select N personas that are BOTH relevant to the scenario and
still a realistic cross-section of South Africa. The danger we design against is the
echo chamber: "taxi query → only taxi operators" produces a skewed room that throws
away the survey-grounded representativeness the library was built for. A real
stress-test needs the relevant voices PLUS the skeptic, the elder, the uninterested.

So selection = representative base + bounded relevance tilt:
  * Base seats are allocated across archetypes in proportion to the library's own mix
    (which tracks SA reality from QLFS).
  * A tilt upweights relevant archetypes/province, but is CAPPED so relevant segments
    gain seats without crowding everyone else out.
  * A floor guarantees a minimum spread of distinct archetypes, so the room is never
    one note.

The core (select_for_query) is LLM-free and deterministic — testable with the model
off. Turning a free-text query into a tilt can later use a cheap LLM; here we accept
an explicit tilt or derive one with simple keyword matching, keeping the
representativeness engine fully assertable.
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

from .persona_library import PersonaLibrary, get_library
from ..utils.logger import get_logger

logger = get_logger("fub.persona_retrieval")

# How strongly a relevant archetype may be upweighted over its baseline share.
# 3.0 = a relevant archetype can get up to ~3x its natural seats — noticeable tilt,
# but bounded so the rest of the room survives.
MAX_TILT = 3.0
# At least this many DISTINCT archetypes must appear in any cast of reasonable size,
# so a tilted room still has a spread of voices (anti-echo-chamber floor).
MIN_DISTINCT_ARCHETYPES = 4

# Lightweight keyword → archetype hints for deriving a tilt from free text without an
# LLM. Deliberately small and honest; the LLM layer (future) can produce richer tilts.
_KEYWORD_ARCHETYPES = {
    "taxi": ["informal_trader", "small_business_owner"],
    "spaza": ["informal_trader", "small_business_owner"],
    "informal": ["informal_trader"],
    "unemploy": ["unemployed_youth", "disillusioned_dropout"],
    "youth": ["unemployed_youth"],
    "grant": ["grant_dependent_survivor"],
    "pension": ["grant_dependent_survivor"],
    "small business": ["small_business_owner"],
    "entrepreneur": ["small_business_owner"],
    "community": ["community_leader"],
    "service delivery": ["community_leader", "civic_moderate"],
}

_PROVINCES = [
    "Gauteng", "Western Cape", "KwaZulu-Natal", "Eastern Cape",
    "Limpopo", "Mpumalanga", "North West", "Free State", "Northern Cape",
]


def derive_tilt(query: str) -> Tuple[Dict[str, float], Optional[str]]:
    """Derive an (archetype_weights, province) tilt from free text — LLM-free.

    Returns archetype→multiplier (>1 means upweight) and an optional province focus.
    Conservative: only tilts on clear keyword/province mentions; otherwise no tilt
    (→ a purely representative sample).
    """
    q = (query or "").lower()
    weights: Dict[str, float] = {}
    for kw, archs in _KEYWORD_ARCHETYPES.items():
        if kw in q:
            for a in archs:
                weights[a] = min(MAX_TILT, weights.get(a, 1.0) + 1.0)
    province = next((p for p in _PROVINCES if p.lower() in q), None)
    return weights, province


def select_for_query(
    n: int,
    query: str = "",
    *,
    tilt: Optional[Dict[str, float]] = None,
    province: Optional[str] = None,
    library: Optional[PersonaLibrary] = None,
    seed: int = 0,
) -> List[Dict]:
    """Select n personas: representative base, bounded tilt toward query relevance.

    `tilt`/`province` override the keyword-derived tilt when given (e.g. from an LLM
    query parser). Deterministic for a seed. Never returns an echo chamber: relevant
    archetypes are upweighted but capped, and a spread floor is enforced.
    """
    lib = library or get_library()
    personas = lib.all()
    if not personas:
        logger.warning("Persona library empty — cannot select a cast.")
        return []
    if n >= len(personas):
        return list(personas)

    if tilt is None:
        tilt, derived_province = derive_tilt(query)
        province = province or derived_province

    rng = random.Random(seed)

    # Per-persona weight: baseline 1.0, multiplied by the archetype tilt, and by a
    # province boost when a province focus is set (province-relevant personas get more
    # seats, but other provinces still appear).
    def weight(p: Dict) -> float:
        w = 1.0
        a = p.get("actor_archetype")
        if a in tilt:
            w *= tilt[a]
        if province and p.get("province") == province:
            w *= 1.5
        return w

    weighted = [(p, weight(p)) for p in personas]

    # Weighted sampling WITHOUT replacement, deterministic.
    # Names are de-duplicated: the library reuses common SA names heavily (e.g.
    # ~55 personas literally named "Thabo Mokoena"), and a cast with duplicate
    # names breaks the run — the feed shows "[Thabo Mokoena] said …" for several
    # different people, agents respond to a smeared namesake, and name-keyed UI
    # (chat, stance spectrum) merges them. One name per cast.
    chosen: List[Dict] = []
    chosen_names: set = set()
    pool = list(weighted)
    while pool and len(chosen) < n:
        total = sum(w for _, w in pool)
        r = rng.uniform(0, total)
        acc = 0.0
        for idx, (p, w) in enumerate(pool):
            acc += w
            if acc >= r:
                pool.pop(idx)
                nm = (p.get("name") or "").strip().lower()
                if nm and nm in chosen_names:
                    break  # drop this namesake; redraw on the next iteration
                chosen.append(p)
                if nm:
                    chosen_names.add(nm)
                break

    # Anti-echo-chamber floor: if the tilt collapsed diversity, swap in personas of
    # missing archetypes (from the unchosen pool) until we hit the spread floor or run
    # out. Keeps a tilted room from becoming one note.
    target_distinct = min(MIN_DISTINCT_ARCHETYPES, n, len({p.get("actor_archetype") for p in personas}))
    distinct = {p.get("actor_archetype") for p in chosen}
    if len(distinct) < target_distinct:
        leftovers = [p for p, _ in pool]
        rng.shuffle(leftovers)
        for p in leftovers:
            nm = (p.get("name") or "").strip().lower()
            # Don't reintroduce a duplicate name via the diversity swap.
            if p.get("actor_archetype") not in distinct and not (nm and nm in chosen_names):
                # Replace the most over-represented archetype's last pick.
                from collections import Counter
                counts = Counter(c.get("actor_archetype") for c in chosen)
                most_common_arch = counts.most_common(1)[0][0]
                for i in range(len(chosen) - 1, -1, -1):
                    if chosen[i].get("actor_archetype") == most_common_arch:
                        removed_nm = (chosen[i].get("name") or "").strip().lower()
                        chosen[i] = p
                        chosen_names.discard(removed_nm)
                        if nm:
                            chosen_names.add(nm)
                        break
                distinct = {c.get("actor_archetype") for c in chosen}
                if len(distinct) >= target_distinct:
                    break

    return chosen
