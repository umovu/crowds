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
    # Education (GHS library roles)
    "student": ["learner", "guardian_parent"],
    "learner": ["learner", "guardian_parent"],
    "school": ["learner", "guardian_parent"],
    "matric": ["learner", "guardian_parent"],
    "edtech": ["learner", "guardian_parent"],
    "tutoring": ["learner", "guardian_parent"],
    # Farming (QLFS farm-role build)
    "farm": ["communal_farmer", "smallholder_emerging_farmer"],
    "cattle": ["communal_farmer", "smallholder_emerging_farmer"],
    "livestock": ["communal_farmer", "smallholder_emerging_farmer"],
    "crop": ["communal_farmer", "smallholder_emerging_farmer"],
    "agri": ["communal_farmer", "smallholder_emerging_farmer"],
    # Salaried professionals (QLFS professional build)
    "professional": ["urban_professional"],
    "corporate": ["urban_professional"],
    "salaried": ["urban_professional"],
    # Well-off households. Without these a product for people with money got the
    # national mix (tests/data/cast_cases.json measured it).
    "premium": ["urban_professional", "affluent_urban_household", "comfortable_household"],
    "luxury": ["urban_professional", "affluent_urban_household", "comfortable_household"],
    "private school": ["affluent_urban_household", "comfortable_household"],
    "independent school": ["affluent_urban_household", "comfortable_household"],
    "medical aid": ["urban_professional", "affluent_urban_household", "comfortable_household"],
    "suburb": ["affluent_urban_household", "comfortable_household"],
    "homeowner": ["affluent_urban_household", "comfortable_household"],
    "retirement": ["urban_professional", "comfortable_household"],
    "annuity": ["urban_professional", "comfortable_household"],
    "investment": ["urban_professional", "affluent_urban_household"],
    "commercial farm": ["affluent_agricultural_household", "rural_landholding_household"],
    "landowner": ["affluent_agricultural_household", "rural_landholding_household"],
    # Traders
    "trader": ["informal_trader"],
    "vendor": ["informal_trader"],
    "hawker": ["informal_trader"],
    # Family roles
    "parents": ["guardian_parent"],
    "guardian": ["guardian_parent", "gogo_guardian"],
    "grandmother": ["gogo_guardian"],
    "grandchild": ["gogo_guardian"],
    "gogo": ["gogo_guardian"],
    # Public health users (older and grant-reliant people carry most chronic care)
    "clinic": ["grant_dependent_survivor", "gogo_guardian"],
    "chronic": ["grant_dependent_survivor", "gogo_guardian"],
    "medication": ["grant_dependent_survivor", "gogo_guardian"],
}

_PROVINCES = [
    "Gauteng", "Western Cape", "KwaZulu-Natal", "Eastern Cape",
    "Limpopo", "Mpumalanga", "North West", "Free State", "Northern Cape",
]

# Fewer personas than this in a metro and a room asked for it would be the same
# faces every run. 15 is a 12-seat room plus a little slack.
MIN_METRO_POOL = 15

# The province prefix Stats SA puts on every `Metro_code` label, so a metro focus
# can widen to its own province on the way down.
_METRO_PROVINCES = {
    "WC": "Western Cape", "EC": "Eastern Cape", "NC": "Northern Cape",
    "FS": "Free State", "KZN": "KwaZulu-Natal", "NW": "North West",
    "GP": "Gauteng", "MP": "Mpumalanga", "LP": "Limpopo",
}


# How much of a room goes to the place a pitch names, when one is named and the
# library can fill it. 0.6 leaves a real minority of outsiders rather than a token
# one, and is low enough that the anti-echo-chamber floor still has room to work.
PLACE_SHARE = 0.6


def _draw(pool: List[Tuple[Dict, float]], n: int, rng: random.Random,
          chosen: List[Dict], chosen_names: set) -> List[Dict]:
    """Weighted sampling WITHOUT replacement, deterministic, appending to `chosen`.

    Names are de-duplicated: the library reuses common SA names heavily (e.g.
    ~55 personas literally named "Thabo Mokoena"), and a cast with duplicate
    names breaks the run — the feed shows "[Thabo Mokoena] said …" for several
    different people, agents respond to a smeared namesake, and name-keyed UI
    (chat, stance spectrum) merges them. One name per cast.

    Returns whoever was left undrawn, for the diversity floor to swap from.
    """
    pool = list(pool)
    target = len(chosen) + max(0, n)
    while pool and len(chosen) < target:
        total = sum(w for _, w in pool)
        if total <= 0:
            break
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
    return [p for p, _ in pool]


def _metro_of(persona: Dict) -> Optional[str]:
    """The persona's imputed metro, or None if the library predates that pass.

    Lives in `circumstances` beside the other measured fields rather than at the
    top level, because it is drawn from GHS like they are — see
    scripts/add_ghs_geography.py for how sure any one placement is.
    """
    for row in persona.get("circumstances") or []:
        if row.get("field") == "metro":
            return row.get("value")
    return None


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


def derive_place(query: str) -> Tuple[Optional[str], Optional[str]]:
    """The (metro, province) a pitch points at, via the gazetteer — LLM-free.

    Reuses `query_context.detect_place` rather than a second place list, so
    "Sunnyside" resolves the same way for the cast as it does for the local
    facts block. Imported lazily: query_context pulls in Config, and the
    benchmark scripts import this module standalone with no app config.

    A named place that is not in a metro ("Upington", "Tzaneen") still yields its
    province — the province is the honest answer for it, and the alternative was
    no place focus at all, which is how a Northern Cape bakery got a room with no
    Northern Cape in it.
    """
    if not query:
        return None, None
    try:
        from .query_context import detect_place
    except (ImportError, ValueError):
        return None, None
    place = detect_place(query) or {}
    return place.get("metro") or None, place.get("province") or None


def derive_metro(query: str) -> Optional[str]:
    """The metro a pitch points at, or None. Thin wrapper over `derive_place`."""
    return derive_place(query)[0]


def describe_place(query: str, cast: List[Dict], *, province: Optional[str] = None,
                   metro: Optional[str] = None) -> Optional[Dict]:
    """What to tell the operator about where this room is, or None if nowhere.

    A room tilted to a place looks, in the roster, exactly like a room that
    wasn't — same names, same archetypes, and nobody says their city (metro has
    no prompt block, because it is a placement and not a fact about them). So
    the only place this shows up is here, said plainly: which place, how many
    seats it got, and how sure the placement is.

    `level` says which rung the picker actually used, because a pitch about
    Gqeberha that quietly fell back to the Eastern Cape must not be shown as a
    Gqeberha room.
    """
    if not cast:
        return None
    if metro is None and province is None:
        metro, province = derive_place(query)
        if metro and not province:
            province = _METRO_PROVINCES.get(metro.split(" - ")[0])
    if not (metro or province):
        return None

    seated_metro = sum(1 for p in cast if _metro_of(p) == metro) if metro else 0
    seated_province = sum(1 for p in cast if p.get("province") == province) if province else 0
    # The label follows the SEATS, not the pitch. A metro dropped by the
    # thin-bucket guard still lands a few of its people by chance through the
    # province tilt — East London seated 3 Buffalo City people out of a room the
    # picker had already widened to the Eastern Cape — and calling that a Buffalo
    # City room would be the exact overclaim this line exists to prevent. So a
    # metro only gets the label when it actually won the reserved seats.
    reserved = int(round(len(cast) * PLACE_SHARE))
    level = ("metro" if metro and seated_metro >= reserved
             else "province" if seated_province else "none")
    if level == "none":
        return None

    seats = seated_metro if level == "metro" else seated_province
    local = [p for p in cast
             if (_metro_of(p) == metro if level == "metro"
                 else p.get("province") == province)]
    # Province is on the persona's own survey row — it always was. Only the metro
    # can be a placement, so a province-level room has nothing to disclaim.
    measured = (len(local) if level == "province"
                else sum(1 for p in local if _placement_is_measured(p)))

    name = metro.split(" - ", 1)[-1] if level == "metro" else province
    return {
        "label": f"{name}, {province}" if level == "metro" and province else name,
        "level": level,
        "metro": metro if level == "metro" else None,
        "province": province,
        "seats": seats,
        "of": len(cast),
        # How many of those seats know where they live rather than having been
        # placed there. Shown so "7 of 12 in Tshwane" is never read as seven
        # people the survey found in Tshwane.
        "measured_seats": measured,
    }


def _placement_is_measured(persona: Dict) -> bool:
    """True when this persona's metro came off their own survey row."""
    for row in persona.get("circumstances") or []:
        if row.get("field") == "metro":
            return row.get("match_quality") == "exact"
    return False


def select_for_query(
    n: int,
    query: str = "",
    *,
    tilt: Optional[Dict[str, float]] = None,
    province: Optional[str] = None,
    metro: Optional[str] = None,
    library: Optional[PersonaLibrary] = None,
    seed: int = 0,
) -> List[Dict]:
    """Select n personas: representative base, bounded tilt toward query relevance.

    `tilt`/`province`/`metro` override what the query itself implies (e.g. from an
    LLM query parser). Deterministic for a seed. Never returns an echo chamber:
    relevant archetypes are upweighted but capped, and a spread floor is enforced.
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
    if metro is None:
        metro, gazetteer_province = derive_place(query)
        province = province or gazetteer_province
    if metro and not province:
        province = _METRO_PROVINCES.get(metro.split(" - ")[0])

    # Thin-bucket guard: a metro the library barely covers cannot fill a room, and
    # boosting it would just seat the same handful of people every run. Below the
    # floor we drop to the province, which is a real answer rather than a thin one.
    if metro:
        in_metro = sum(1 for p in personas if _metro_of(p) == metro)
        if in_metro < MIN_METRO_POOL:
            logger.info("Metro %s has only %d personas (<%d) — falling back to %s.",
                        metro, in_metro, MIN_METRO_POOL, province or "no place tilt")
            metro = None

    rng = random.Random(seed)

    # Per-persona weight: baseline 1.0, multiplied by the archetype tilt. Place is
    # NOT a multiplier — see the seat reservation below for why.
    def weight(p: Dict) -> float:
        w = 1.0
        a = p.get("actor_archetype")
        if a in tilt:
            w *= tilt[a]
        return w

    weighted = [(p, weight(p)) for p in personas]

    # Place gets RESERVED SEATS, not a weight multiplier. A multiplier cannot do
    # this job: Tshwane is 6% of the library, so even a 2x boost left 1 Tshwane
    # person in a 12-seat "Pretoria" room, and Limpopo at 1.5x left one Limpopo
    # voice in a room about a Limpopo water tariff. The multiplier needed to fix
    # that is so large it stops being a tilt and becomes a filter with extra steps.
    # Reserving a share of the seats says the same thing honestly and bounds it:
    # PLACE_SHARE of the room is local, the rest stays a national cross-section, so
    # the outsider who doesn't already care is still in the room by construction.
    local: List[Tuple[Dict, float]] = []
    if metro:
        local = [(p, w) for p, w in weighted if _metro_of(p) == metro]
    elif province:
        local = [(p, w) for p, w in weighted if p.get("province") == province]

    chosen: List[Dict] = []
    chosen_names: set = set()

    if local:
        seats = min(int(round(n * PLACE_SHARE)), len(local))
        _draw(local, seats, rng, chosen, chosen_names)
        logger.info("Place focus %s: %d of %d seats local (pool %d).",
                    metro or province, len(chosen), n, len(local))

    # The rest of the room is drawn from everyone (locals included — a place with
    # more than its share of relevant voices should not be capped at the share).
    remaining = [(p, w) for p, w in weighted if p not in chosen]
    undrawn = _draw(remaining, n - len(chosen), rng, chosen, chosen_names)

    # Anti-echo-chamber floor: if the tilt collapsed diversity, swap in personas of
    # missing archetypes (from the unchosen pool) until we hit the spread floor or run
    # out. Keeps a tilted room from becoming one note.
    target_distinct = min(MIN_DISTINCT_ARCHETYPES, n, len({p.get("actor_archetype") for p in personas}))
    distinct = {p.get("actor_archetype") for p in chosen}
    if len(distinct) < target_distinct:
        leftovers = list(undrawn)
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


# ── Typed tilt: the same job as derive_tilt, read rather than keyword-matched ──
#
# `derive_tilt` can only fire on a word that happens to be in its table: a pitch
# about "minibus ranks" matches nothing, and the room falls back to a plain
# cross-section that misses the people the pitch is actually about. The typed
# tier reads the pitch instead and rates every archetype on one ladder.
#
# It stays a TILT, never a pick: the output is the same multiplier map, so
# MAX_TILT, the spread floor and the representative base all still apply, and a
# wrong rating is bounded by exactly the guards that already exist. Missing key,
# failed call or a flat answer falls back to the keyword tilt.

# A rung the model rates each archetype against. Index 0..3.
_RELEVANCE_LEVELS = [
    "Not affected by this at all",
    "Touched indirectly, would have an opinion but no stake",
    "Clearly affected, this lands on their situation",
    "This is exactly who it is aimed at",
]
# Rungs 2 and 3 mean "has a stake". A tilt needs most of the probability there.
_STAKE_FROM_LEVEL = 2
_MIN_STAKE = 0.5


def _archetype_descriptions(personas: List[Dict]) -> Dict[str, str]:
    """One plain description per archetype, summarised from the library itself.

    Written from the measured fields rather than by hand, so a description can
    never drift from who the archetype actually contains.
    """
    import statistics
    from collections import Counter, defaultdict

    groups: Dict[str, List[Dict]] = defaultdict(list)
    for p in personas:
        a = p.get("actor_archetype")
        if a:
            groups[a].append(p)

    def common(values) -> str:
        vals = [v for v in values if v not in (None, "")]
        return Counter(vals).most_common(1)[0][0] if vals else ""

    out: Dict[str, str] = {}
    for arch, members in groups.items():
        ages = [p["age"] for p in members if isinstance(p.get("age"), (int, float))]
        incomes = [p["monthly_household_income_rand"] for p in members
                   if isinstance(p.get("monthly_household_income_rand"), (int, float))
                   and p["monthly_household_income_rand"] > 0]
        grants = sum(1 for p in members if p.get("receives_grant"))
        bits = [arch.replace("_", " ")]
        if ages:
            bits.append(f"typically around {int(statistics.median(ages))} years old")
        status = common(p.get("employment_status") for p in members)
        if status:
            bits.append(f"mostly {status.lower()}")
        geo = common(p.get("geotype") for p in members)
        if geo:
            bits.append(f"mainly {geo.lower()} areas")
        if incomes:
            bits.append(f"household income around R{int(statistics.median(incomes)):,} a month")
        if members and grants * 2 >= len(members):
            bits.append("most receive a social grant")
        out[arch] = "; ".join(bits)
    return out


def _stake(answer: Dict) -> float:
    """Probability this archetype has a real stake (rung 2 or 3)."""
    probs = answer.get("probabilities") or {}
    return sum(float(v) for k, v in probs.items() if int(k) >= _STAKE_FROM_LEVEL)


def derive_tilt_typed(
    query: str,
    *,
    library: Optional[PersonaLibrary] = None,
) -> Optional[Tuple[Dict[str, float], Optional[str]]]:
    """Rate every archetype against the pitch in one typed call.

    Returns the same `(weights, province)` shape as `derive_tilt`, or None when
    the tier is unavailable or the call fails — callers fall back to keywords.
    """
    from ..utils import typesafe_client as ts

    if not query or not ts.enabled():
        return None

    lib = library or get_library()
    personas = lib.all()
    if not personas:
        return None

    descriptions = _archetype_descriptions(personas)
    if not descriptions:
        return None

    questions = {
        arch: ts.score_question(
            f"How much does this announcement or product land on this group of "
            f"South Africans: {desc}",
            _RELEVANCE_LEVELS,
        )
        for arch, desc in descriptions.items()
    }
    questions["_province"] = ts.choice_question(
        "Which South African province does this name or clearly point at?",
        {p: None for p in _PROVINCES} | {"not_stated": "No province is named or implied"},
    )

    answers = ts.ask(query, questions)
    if not answers:
        return None

    weights: Dict[str, float] = {}
    for arch in descriptions:
        answer = answers.get(arch) or {}
        stake = _stake(answer)
        if stake >= _MIN_STAKE:
            # Full stake earns the cap; the floor earns a mild nudge.
            weights[arch] = 1.0 + stake * (MAX_TILT - 1.0)

    prov_answer = answers.get("_province") or {}
    province = prov_answer.get("choice")
    if province == "not_stated" or (prov_answer.get("confidence") or 0.0) < 0.5:
        province = None

    logger.info("Typed tilt: %d archetype(s) upweighted, province=%s",
                len(weights), province)
    return weights, province
