"""
PanelService — pitch sessions against the persona library, no simulation needed.

A panel session is a small cast selected from the pre-built persona library
(persona_retrieval keeps it representative + relevance-tilted) and written to
disk in the same file layout as a simulation directory (agentsociety_profiles.json
+ document_context.json). That layout is the InterviewService contract, so the
whole interview stack — per-agent Q&A, batch impact rounds, dashboards — runs
against a session unchanged: a session is a sim dir without a sim.

Session creation is deterministic and LLM-free: cast selection, grant detection
and budget tiers are all computed from real persona data, assertable with the
model switched off. Only pitch rounds (run through InterviewService) call the LLM.

Sessions live in Config.PANEL_SESSION_DATA_DIR, apart from sim dirs, so
simulation listings never pick them up.
"""

import json
import os
import random
import re
import shutil
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..utils.logger import get_logger
from .income_seeder import detect_grant, GRANT_PROVENANCE
from .mode_specs import budget_tier
from . import mechanism_card_service
from . import objections
from .persona_library import get_library
from .persona_retrieval import select_for_query

logger = get_logger("fub.panel_service")

PROFILES_FILE = "agentsociety_profiles.json"
CONTEXT_FILE = "document_context.json"
META_FILE = "panel_session.json"
ROUNDS_DIR = "rounds"

MAX_CAST_SIZE = 50
DEFAULT_CAST_SIZE = 12


# ── Segments: named, deterministic slices of the library ───────────────────
# A segment is a user-facing group ("Unemployed", "Grant recipients") backed by
# a pure predicate over real library fields — never an LLM judgement. Picking
# one turns the panel into a focus group: sampling stays deterministic, but the
# representative-cross-section machinery is deliberately bypassed — the user
# explicitly asked for one room of one group. "everyone" keeps the
# representative + tilt path from persona_retrieval.
SEGMENTS = {
    "everyone": {
        "label": "Everyone (representative SA)",
        "description": "The real SA mix — grant and informal voices dominate, as in the population",
        "predicate": None,
    },
    "unemployed": {
        "label": "Unemployed",
        "description": "Unemployed and discouraged job seekers",
        "predicate": lambda p: p.get("employment_status") in ("Unemployed", "Discouraged job seeker"),
    },
    "grant_recipients": {
        "label": "Grant recipients",
        "description": "Households living on SASSA grants",
        "predicate": lambda p: p.get("actor_archetype") == "grant_dependent_survivor",
    },
    "informal_traders": {
        "label": "Informal traders",
        "description": "Spaza and street traders",
        "predicate": lambda p: p.get("actor_archetype") == "informal_trader",
    },
    "small_business": {
        "label": "Small business owners",
        "description": "Formal small-business owners",
        "predicate": lambda p: p.get("actor_archetype") == "small_business_owner",
    },
    "youth": {
        "label": "Youth (under 35)",
        "description": "Ages 18–34, all employment statuses",
        "predicate": lambda p: isinstance(p.get("age"), int) and p["age"] < 35,
    },
    # Farmers (QLFS 2026Q1 farm-role build) — the agritech customer base.
    "farmers": {
        "label": "Farmers & agri",
        "description": "Subsistence and smallholder farmers — agri products, rural policy",
        "predicate": lambda p: p.get("actor_archetype") in (
            "communal_farmer", "smallholder_emerging_farmer"),
    },
    "smallholder_owners": {
        "label": "Smallholder farm owners",
        "description": "Farm owners who sell for income and control farm spend",
        "predicate": lambda p: p.get("actor_archetype") == "smallholder_emerging_farmer",
    },
    # Salaried professionals (QLFS formal professional/managerial build) — the
    # segment that can afford recurring-cost products; answers "tune the message
    # for people who can pay" without guessing from broader employment status.
    "professionals": {
        "label": "Salaried professionals",
        "description": "Salaried professionals and managers — likely paying customers",
        "predicate": lambda p: p.get("actor_archetype") == "urban_professional",
    },
    "employed": {
        "label": "Employed",
        "description": "In formal employment",
        "predicate": lambda p: p.get("employment_status") == "Employed",
    },
    # Education roles (GHS 2025 library build) — counts stay 0 until the
    # education personas are built into the library.
    "learners": {
        "label": "Learners",
        "description": "High-school learners, ages 15–18",
        "predicate": lambda p: p.get("actor_archetype") == "learner",
    },
    "guardians": {
        "label": "Parents & guardians",
        "description": "Household heads with school-age children",
        "predicate": lambda p: p.get("actor_archetype") in ("guardian_parent", "gogo_guardian"),
    },
    "gogo_guardians": {
        "label": "Gogo guardians",
        "description": "Grandparents raising learners (~39% of SA)",
        "predicate": lambda p: p.get("actor_archetype") == "gogo_guardian",
    },
    "educators": {
        "label": "Educators",
        "description": "Teachers from the QLFS professional pool",
        "predicate": lambda p: p.get("actor_archetype") == "educator",
    },
    # Fee status (GHS) — households already spending on education vs no-fee-school
    # households. Works across learners (fees_band) and guardians (learner_fee_bands),
    # so a paid-product pitch can target families with proven education spend.
    "fee_paying": {
        "label": "Fee-paying households",
        "description": "Families already paying school fees",
        "predicate": lambda p: _pays_school_fees(p),
    },
    "no_fee_school": {
        "label": "No-fee-school households",
        "description": "No-fee schools — toughest affordability test",
        "predicate": lambda p: _no_fee_only(p),
    },
    # Role x fee-tier splits (GHS). "Fee-paying" alone mixes R100/yr and R80k/yr
    # households — different in kind for a priced product. Threshold R4,000/yr is
    # derived from the library's band distribution (gap between the <=R2k cluster
    # and the R4k+ cluster; tracks the no-fee/former-Model-C divide). Guardians
    # are the PAYER panel for a priced pitch; learners are the USER panel.
    "guardians_low_fee": {
        "label": "Guardians — low-fee schools",
        "description": "Parents paying up to R4,000/yr fees — tight budgets",
        "predicate": lambda p: p.get("actor_archetype") in ("guardian_parent", "gogo_guardian")
        and _fee_tier(p) == "low_fee",
    },
    "guardians_high_fee": {
        "label": "Guardians — high-fee schools",
        "description": "Parents paying over R4,000/yr fees — spend headroom",
        "predicate": lambda p: p.get("actor_archetype") in ("guardian_parent", "gogo_guardian")
        and _fee_tier(p) == "high_fee",
    },
    "learners_no_fee": {
        "label": "Learners — no-fee schools",
        "description": "Learners at no-fee schools",
        "predicate": lambda p: p.get("actor_archetype") == "learner" and _fee_tier(p) == "no_fee",
    },
    "learners_low_fee": {
        "label": "Learners — low-fee schools",
        "description": "Learners at low-fee schools (to R4,000/yr)",
        "predicate": lambda p: p.get("actor_archetype") == "learner" and _fee_tier(p) == "low_fee",
    },
    "learners_high_fee": {
        "label": "Learners — high-fee schools",
        "description": "Learners at high-fee schools (over R4,000/yr)",
        "predicate": lambda p: p.get("actor_archetype") == "learner" and _fee_tier(p) == "high_fee",
    },
    "guardians_no_fee": {
        "label": "Guardians — no-fee schools",
        "description": "Parents at no-fee schools — no current fee spend",
        "predicate": lambda p: p.get("actor_archetype") in ("guardian_parent", "gogo_guardian")
        and _fee_tier(p) == "no_fee",
    },
}

_LOW_FEE_CEILING = 4000  # R/yr — see segment comments above


def _band_upper(band: str):
    """Upper rand bound of a GHS fee-band string; 0 for 'No fees'; None if unparseable."""
    if not band:
        return None
    if band.strip().lower() == "no fees":
        return 0
    nums = [int(re.sub(r"[^\d]", "", n)) for n in re.findall(r"R[\d\s,  ]+", band)]
    if not nums:
        return None
    if band.strip().lower().startswith("more than"):
        return nums[-1] + 1
    return max(nums)


def _fee_tier(p: Dict[str, Any]):
    """no_fee | low_fee | high_fee | None (no fee data). Highest attached band wins:
    a guardian with one no-fee and one R8k learner is a high-fee household."""
    uppers = [u for u in (_band_upper(b) for b in _fee_bands(p)) if u is not None]
    if not uppers:
        return None
    top = max(uppers)
    if top == 0:
        return "no_fee"
    return "low_fee" if top <= _LOW_FEE_CEILING else "high_fee"


def _fee_bands(p: Dict[str, Any]) -> List[str]:
    """All school-fee bands attached to a persona: a learner's own (fees_band) or a
    guardian's across their learners (learner_fee_bands)."""
    bands = list(p.get("learner_fee_bands") or [])
    if p.get("fees_band"):
        bands.append(p["fees_band"])
    return bands


def _pays_school_fees(p: Dict[str, Any]) -> bool:
    """True if any attached fee band is a real paid amount (not 'No fees')."""
    return any(b and b != "No fees" for b in _fee_bands(p))


def _no_fee_only(p: Dict[str, Any]) -> bool:
    """True if the persona has fee data and ALL of it is 'No fees' (no paid band).
    Excludes personas with no fee data at all — this is a positive no-fee signal."""
    bands = _fee_bands(p)
    return bool(bands) and all(b == "No fees" for b in bands)


# Pitch → suggested segment(s). Deterministic keyword match, no LLM. A hit on
# any keyword suggests that segment; suggestions are ranked by hit count and
# capped at 2 so the hint stays a hint. The UI must SHOW the suggestion for the
# user to apply — never silently pre-select (a wrong silent default is worse
# than no default).
_SEGMENT_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "farmers": ("farm", "farmer", "livestock", "cattle", "herd", "crop", "agri",
                "maize", "harvest", "veld", "grazing", "abattoir", "kraal"),
    "professionals": ("professional", "premium", "executive", "corporate",
                      "salaried", "office worker", "high-income", "affluent"),
    "learners": ("learner", "student", "matric", "high school", "grade ",
                 "homework", "exam", "study app", "tutoring", "school subject"),
    "guardians": ("parent", "guardian", "school fees", "my child", "children's",
                  "your child", "for kids", "family plan"),
    "informal_traders": ("spaza", "street vendor", "hawker", "informal trader",
                         "taxi rank", "stall", "township shop"),
    "small_business": ("small business", "sme", "entrepreneur", "startup owner",
                       "merchant", "point of sale"),
    "unemployed": ("unemployed", "job seeker", "jobless", "work seeker"),
    "grant_recipients": ("grant", "sassa", "pension", "social relief"),
}


def suggest_segments(pitch: str, cap: int = 2) -> List[str]:
    """Suggest library segments for a pitch — deterministic keyword scoring.

    Returns up to `cap` segment ids ordered by keyword-hit count (ties broken
    alphabetically for determinism). Empty list when nothing matches — the
    caller falls back to 'everyone', which is the honest default.
    """
    blob = (pitch or "").lower()
    if not blob.strip():
        return []
    scores = {}
    for seg_id, keywords in _SEGMENT_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in blob)
        if hits:
            scores[seg_id] = hits
    ranked = sorted(scores, key=lambda s: (-scores[s], s))
    return ranked[:cap]


def list_segments() -> List[Dict[str, Any]]:
    """Segments with live library counts and member IDs — what the UI renders
    as group chips. `members` is the list of library persona IDs (the same
    IDs `/api/research/personas` exposes) that match the segment predicate,
    so the Cast picker can bulk-pick without re-implementing the predicates
    on the frontend."""
    personas = get_library().all()
    out = []
    for seg_id, seg in SEGMENTS.items():
        pred = seg["predicate"]
        members = [p.get("id") for p in personas if pred is None or pred(p)]
        members = [m for m in members if m]  # drop personas missing a stable id
        out.append({
            "id": seg_id,
            "label": seg["label"],
            "description": seg["description"],
            "count": len(members),
            "members": members,
        })
    return out


def _base_dir() -> str:
    d = Config.PANEL_SESSION_DATA_DIR
    os.makedirs(d, exist_ok=True)
    return d


def session_dir(session_id: str) -> str:
    return os.path.join(_base_dir(), session_id)


def _read_json(path: str) -> Optional[Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _write_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# Profiles built from the curated library carry this provenance; graph/research-
# derived profiles carry their entity type instead. The leak guard keys on it.
LIBRARY_PROVENANCE = "library_persona"


def assert_library_cast(profiles: List[Dict[str, Any]]) -> None:
    """Refuse a cast that contains any non-library (graph/research-authored)
    identity. A panel/library sim must draw WHO exists from the curated library;
    web research may only add CONTEXT, never invent agents (see CLAUDE.md / the
    web-research→persona-binding rule). Fails loud rather than letting a
    brand-or-news-derived persona ride in among data-grounded ones.

    LLM-free, pure — assertable with the model off.
    """
    leaked = [
        (p.get("name"), p.get("source_entity_type"))
        for p in profiles
        if p.get("source_entity_type") not in (LIBRARY_PROVENANCE, None)
    ]
    if leaked:
        names = ", ".join(f"{n} [{t}]" for n, t in leaked[:8])
        raise ValueError(
            f"Library/panel cast contains {len(leaked)} non-library identities "
            f"(graph/research-authored): {names}. Web research enriches CONTEXT, "
            f"it must not author agents. Rebuild the cast from the persona library."
        )


def _economic_fields(persona: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic economic fields (grant cohort + budget tier) from REAL
    persona data only. Pure function; the single source of truth shared by
    profile stamping (_build_profile) and selection-time affordability
    filtering (create_session budget_tiers) — one computation, so the tier a
    persona is FILTERED on is byte-identical to the tier stamped on their
    profile. Never an LLM estimate, never a purchase probability.
    """
    is_grant, grant_type, grant_amount = detect_grant(
        actor_archetype=persona.get("actor_archetype"),
        occupation=persona.get("occupation"),
        background_story=persona.get("background_story"),
    )
    fields: Dict[str, Any] = {}
    if is_grant:
        fields["is_grant_dependent"] = True
        fields["grant_type"] = grant_type
        if grant_amount is not None:
            fields["monthly_income_rand"] = grant_amount
            fields["income_provenance"] = GRANT_PROVENANCE
    fields["budget_tier"] = budget_tier(
        archetype=persona.get("actor_archetype"),
        is_institutional=bool(persona.get("is_institutional", False)),
        occupation=persona.get("occupation"),
        group_affiliation=persona.get("group_affiliation"),
        grant_income=grant_amount if is_grant else None,
        # GHS personas carry surveyed household income — the strongest real
        # signal; overrides grant/archetype inference inside budget_tier.
        household_income_rand=persona.get("monthly_household_income_rand"),
    )
    return fields


def _build_profile(persona: Dict[str, Any], agent_id: int, mode: str, segment_id=None) -> Dict[str, Any]:
    """Turn a library persona into an interview-ready agent profile.

    Pure function. Keeps every library field (attitudes, beliefs, voice_guide …)
    so the agent's identity prompt stays survey-grounded, renumbers the id for
    the session, and — in product mode — attaches the deterministic economic
    fields (grant cohort + budget tier) computed from real persona data only.
    """
    profile = dict(persona)
    profile["library_id"] = persona.get("id")
    profile["id"] = agent_id
    profile.setdefault("stance", "neutral")
    profile.setdefault("is_institutional", False)
    profile.setdefault("country", "South Africa")
    # Stamp library provenance so the leak guard can tell a curated persona from a
    # graph/research-authored one (library build sets this; older entries may lack it).
    profile.setdefault("source_entity_type", LIBRARY_PROVENANCE)

    if segment_id and segment_id != "everyone":
        profile["segment_id"] = segment_id
        profile["segment_label"] = SEGMENTS[segment_id]["label"]

    if mode == "product":
        profile.update(_economic_fields(profile))

    return profile


def _tier_distribution(profiles: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count of budget tiers across the cast — an affordability share computed
    from real data (allowed), never a purchase probability (banned)."""
    counts: Dict[str, int] = {}
    for p in profiles:
        tier = p.get("budget_tier")
        if tier:
            counts[tier] = counts.get(tier, 0) + 1
    return counts


def _mixed_cast(
    segment_ids: List[str],
    n: int,
    seed: int,
    province: Optional[str],
    library,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Draw a cast mixing several segments — seats split evenly, deduped.

    Round-robin draw: each segment's pool is shuffled deterministically, then
    segments take turns claiming one persona each (skipping anyone already
    seated — segments overlap) until n seats are filled or every pool is dry.
    Even allocation emerges naturally, and a small segment that runs out simply
    stops claiming while the others keep filling the room.

    Returns (cast, allocation) where allocation counts seats per segment.
    """
    rng = random.Random(seed)
    pools: Dict[str, List[Dict]] = {}
    for seg_id in segment_ids:
        pred = SEGMENTS[seg_id]["predicate"]
        pool = [p for p in library.all() if pred(p)]
        if province:
            pool = [p for p in pool if p.get("province") == province]
        rng.shuffle(pool)
        pools[seg_id] = pool

    if not any(pools.values()):
        raise ValueError(
            "No personas match the selected segments"
            + (f" in {province}" if province else "")
        )

    cast: List[Dict[str, Any]] = []
    seated_ids = set()
    allocation: Dict[str, int] = {seg_id: 0 for seg_id in segment_ids}
    while len(cast) < n and any(pools.values()):
        progressed = False
        for seg_id in segment_ids:
            if len(cast) >= n:
                break
            pool = pools[seg_id]
            while pool:
                candidate = pool.pop()
                if candidate.get("id") not in seated_ids:
                    seated_ids.add(candidate.get("id"))
                    candidate["segment_id"] = seg_id
                    cast.append(candidate)
                    allocation[seg_id] += 1
                    progressed = True
                    break
        if not progressed:
            break
    return cast, allocation


BUDGET_TIERS = ("tight", "moderate", "loose")


class _FilteredLibrary:
    """Minimal PersonaLibrary-shaped view over a pre-filtered persona list, so
    the affordability lens can reuse select_for_query/_mixed_cast unchanged."""

    def __init__(self, personas: List[Dict[str, Any]]):
        self._personas = personas

    def all(self) -> List[Dict[str, Any]]:
        return self._personas


def create_session(
    pitch: str,
    mode: str = "product",
    n: int = DEFAULT_CAST_SIZE,
    province: Optional[str] = None,
    seed: Optional[int] = None,
    segment: Optional[str] = None,
    segments: Optional[List[str]] = None,
    budget_tiers: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    pointer: Optional[str] = None,
    slots: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a panel session: select a cast, compute economics, write the dir.

    Deterministic for a given (pitch, n, province, seed, segments, budget_tiers)
    — no LLM calls. `segments` mixes several named library slices with even seat
    allocation; `segment` is the single-group shorthand. None/"everyone" keeps
    the representative + pitch-tilted selection.

    `budget_tiers` is the affordability lens: restrict the candidate pool to
    personas whose deterministic budget tier (real grant/household income data,
    archetype inference as fallback — see _economic_fields) is in the given set,
    e.g. ["moderate", "loose"] for "people whose budgets could absorb a priced
    product". An affordability FILTER from real data is sanctioned; a "% who
    would buy" score is not, and none is produced. Returns the session metadata
    including the roster summary.
    """
    if not (pitch or "").strip():
        raise ValueError("pitch text is required")
    mode = (mode or "product").strip().lower()
    if mode not in ("policy", "product"):
        raise ValueError(f"mode must be 'policy' or 'product', got '{mode}'")

    tier_list = [t.strip().lower() for t in (budget_tiers or []) if t and t.strip()]
    tier_list = list(dict.fromkeys(tier_list))
    for t in tier_list:
        if t not in BUDGET_TIERS:
            raise ValueError(f"unknown budget tier '{t}' — one of {list(BUDGET_TIERS)}")
    if set(tier_list) == set(BUDGET_TIERS):
        tier_list = []  # all tiers = no filter

    seg_list = [s.strip().lower() for s in (segments or ([segment] if segment else ["everyone"])) if s and s.strip()]
    seg_list = list(dict.fromkeys(seg_list)) or ["everyone"]  # dedupe, keep order
    for s in seg_list:
        if s not in SEGMENTS:
            raise ValueError(f"unknown segment '{s}' — one of {sorted(SEGMENTS)}")
    if "everyone" in seg_list and len(seg_list) > 1:
        raise ValueError("'everyone' is already the full mix — pick it alone or pick specific groups")

    n = max(1, min(int(n or DEFAULT_CAST_SIZE), MAX_CAST_SIZE))
    if seed is None:
        seed = int(time.time()) % 1_000_000

    library = get_library()
    if library.is_empty():
        raise RuntimeError(
            "Persona library is empty — run backend/scripts/build_library.py first."
        )

    # Affordability lens: restrict candidates by deterministic budget tier
    # BEFORE cast selection, using the same _economic_fields computation the
    # profiles get stamped with — filter and stamp can't drift apart.
    affordability_pool_size = None
    if tier_list:
        qualified = [p for p in library.all()
                     if _economic_fields(p)["budget_tier"] in tier_list]
        if not qualified:
            raise ValueError(
                f"No personas in budget tier(s) {tier_list}"
                + (f" in {province}" if province else "")
            )
        affordability_pool_size = len(qualified)
        library = _FilteredLibrary(qualified)

    if seg_list == ["everyone"]:
        cast = select_for_query(n, pitch, province=province, seed=seed, library=library)
        allocation = {"everyone": len(cast)}
    else:
        cast, allocation = _mixed_cast(seg_list, n, seed, province, library)
    profiles = [_build_profile(p, i, mode, p.get("segment_id")) for i, p in enumerate(cast)]
    # Research grounding (Phase 5): same card binding as the sim cast path in
    # simulation_manager — deterministic, LLM-free, no-op per persona when no
    # card matches or RESEARCH_CONTEXT_ENABLED=0.
    for p in profiles:
        mechanism_card_service.attach_research_context(p)
    # Guard: a panel cast is library-only by construction — this asserts it,
    # so a future code path that mixes in graph/research identities fails loud.
    assert_library_cast(profiles)

    session_id = f"panel_{uuid.uuid4().hex[:12]}"
    sdir = session_dir(session_id)
    os.makedirs(os.path.join(sdir, ROUNDS_DIR), exist_ok=True)

    _write_json(os.path.join(sdir, PROFILES_FILE), profiles)
    # Same shape InterviewService._load_mode expects from a sim dir.
    _write_json(os.path.join(sdir, CONTEXT_FILE), {
        "mode": mode,
        "panel_session": True,
        "pitch": pitch,
    })

    meta = {
        "session_id": session_id,
        "user_id": user_id,  # owner; scopes the session to its creator
        "pitch": pitch,
        "mode": mode,
        "segments": seg_list,
        "segment": seg_list[0],  # back-compat for single-group consumers
        "segment_label": " + ".join(SEGMENTS[s]["label"] for s in seg_list),
        "segment_allocation": {SEGMENTS[s]["label"]: c for s, c in allocation.items() if c},
        "cast_size": len(profiles),
        "requested_size": n,
        "seed": seed,
        "province": province,
        "created_at": datetime.now().isoformat(),
        "rounds_run": 0,
        "archetype_distribution": _count_by(profiles, "actor_archetype"),
        "province_distribution": _count_by(profiles, "province"),
    }
    if pointer:
        meta["pointer"] = pointer
        meta["slots"] = dict(slots or {})
    if mode == "product":
        meta["budget_tier_distribution"] = _tier_distribution(profiles)
    if tier_list:
        meta["budget_tier_filter"] = tier_list
        # Affordability share from real data (sanctioned): how many of the whole
        # library qualified — NOT a purchase probability (banned).
        meta["affordability_pool_size"] = affordability_pool_size
    _write_json(os.path.join(sdir, META_FILE), meta)

    logger.info(f"Created panel session {session_id}: {len(profiles)} personas, mode={mode}, seed={seed}")
    return meta


def add_segment(session_id: str, segment_id: str,
                seats: int = 6) -> Tuple[Dict[str, Any], List[int]]:
    """Seat a NEW segment in an existing session, and say who to interview.

    The "one segment didn't bite, try the next room" move. Everything about the
    session is append-only: existing profiles keep their agent ids and their
    saved rounds, so the two rooms sit side by side for the rest of the session
    instead of one overwriting the other.

    People already seated are skipped, so re-adding a segment that overlaps an
    existing one can seat fewer than `seats` — or nobody, which raises, because
    silently running a round against an empty room would look like a result.

    Returns (updated meta, agent_ids of the newly seated) — the caller pitches
    at exactly those ids.
    """
    meta = get_session(session_id)
    if not meta:
        raise FileNotFoundError(f"Session {session_id} not found")
    if segment_id not in SEGMENTS or segment_id == "everyone":
        raise ValueError(f"Unknown segment: {segment_id}")

    sdir = session_dir(session_id)
    profiles = _read_json(os.path.join(sdir, PROFILES_FILE)) or []
    # `library_id` is the library persona's own id (_build_profile stamps it);
    # `id` is the per-session agent number, which says nothing about identity.
    seated_library_ids = {p.get("library_id") for p in profiles
                          if p.get("library_id") is not None}

    pred = SEGMENTS[segment_id]["predicate"]
    province = meta.get("province")
    pool = [p for p in get_library().all() if pred(p)]
    if province:
        pool = [p for p in pool if p.get("province") == province]
    # Same deterministic draw as create_session: seeded shuffle, so re-running
    # the same add on the same session seats the same people.
    random.Random(meta.get("seed") or 0).shuffle(pool)
    pool = [p for p in pool if p.get("id") not in seated_library_ids]
    if not pool:
        raise ValueError(
            f"No one new from {SEGMENTS[segment_id]['label']} is available"
            + (f" in {province}" if province else "")
            + " — everyone matching is already in the room.")

    mode = meta.get("mode", "product")
    start = max((p.get("id") or 0) for p in profiles) + 1 if profiles else 0
    new_profiles = [_build_profile(p, start + i, mode, segment_id)
                    for i, p in enumerate(pool[:max(1, seats)])]
    for p in new_profiles:
        mechanism_card_service.attach_research_context(p)
    # Same guard as create_session: a panel cast stays library-only.
    assert_library_cast(new_profiles)

    profiles.extend(new_profiles)
    _write_json(os.path.join(sdir, PROFILES_FILE), profiles)

    seg_list = list(meta.get("segments") or [])
    # A session that started as "everyone" becomes a comparison the moment a
    # named room is added; the mix is no longer one of the candidates.
    seg_list = [s for s in seg_list if s != "everyone"]
    if segment_id not in seg_list:
        seg_list.append(segment_id)
    meta["segments"] = seg_list
    meta["segment_label"] = " + ".join(SEGMENTS[s]["label"] for s in seg_list)
    alloc = dict(meta.get("segment_allocation") or {})
    label = SEGMENTS[segment_id]["label"]
    alloc[label] = alloc.get(label, 0) + len(new_profiles)
    meta["segment_allocation"] = alloc
    meta["cast_size"] = len(profiles)
    meta["archetype_distribution"] = _count_by(profiles, "actor_archetype")
    meta["province_distribution"] = _count_by(profiles, "province")
    if mode == "product":
        meta["budget_tier_distribution"] = _tier_distribution(profiles)
    _write_json(os.path.join(sdir, META_FILE), meta)

    logger.info("Panel %s: seated %d from %s (cast now %d)",
                session_id, len(new_profiles), segment_id, len(profiles))
    return meta, [p["id"] for p in new_profiles]


def carry_probe(objection_id: Optional[str]) -> Optional[str]:
    """Turn an objection type from the last room into one follow-up question.

    This is what makes a re-pitch a conversation rather than a rerun: the wall
    the previous room hit becomes the thing the new room is asked about. Returns
    None for an unknown or absent id, so a bad value is a no-op, never an error.
    """
    if not objection_id or objection_id not in objections.LABELS:
        return None
    return (f"The last group we spoke to kept coming back to this: "
            f"{objections.LABELS[objection_id].lower()}. Does that land the "
            f"same way for you?")


def _count_by(profiles: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for p in profiles:
        v = p.get(key) or "unknown"
        counts[v] = counts.get(v, 0) + 1
    return counts


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    return _read_json(os.path.join(session_dir(session_id), META_FILE))


def rank_by_segment(session_id: str, meta: Dict[str, Any],
                    results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group a pitch round's reactions by the session's segments — the `fit`
    deliverable. Deterministic and LLM-free: each persona is assigned to the
    FIRST matching segment predicate (real library fields only, stable order),
    so the ranking never depends on a model. Returns [] when the session has
    fewer than two concrete segments or nothing maps.

    Every requested segment gets an entry — a group that drew zero (or no
    matching) members is an explicit empty row, so the UI can say "no one from
    this group was available" instead of the group vanishing. Empty rows rank
    last. The ordering IS the answer: segments rank by most won over (support
    count desc, then fewer opponents / unconvinced, then label asc for a stable,
    deterministic tie-break).

    Each row also carries the three fit-card readings, kept deliberately
    SEPARATE (collapsing them would be the banned single "would buy" score):

    - `stance_split` — what people said (LLM output, qualitative)
    - `budget_tiers` — what their real income supports (computed, never LLM)
    - `top_objections` — the wall this room kept hitting (deterministic
      keyword classifier, `objections.py`, no LLM)

    plus `seats` (how many of this segment were in the room) and `heard_count`
    (how many of them actually answered). A round where the two diverge is a
    degraded round, and the UI needs to be able to say so.
    """
    seg_ids = [s for s in (meta.get("segments") or []) if s and s != "everyone"]
    if len(seg_ids) < 2 or not results:
        return []
    profiles = _read_json(os.path.join(session_dir(session_id), PROFILES_FILE)) or []
    by_agent = {p.get("id"): p for p in profiles if p.get("id") is not None}
    groups = {s: [] for s in seg_ids}
    for r in results:
        profile = by_agent.get(r.get("agent_id"))
        if not profile:
            continue
        for seg_id in seg_ids:
            pred = SEGMENTS[seg_id]["predicate"]
            if pred is None or pred(profile):
                groups[seg_id].append(r)
                break
    # Seats are assigned by the SAME first-match walk over every profile in the
    # room, not just the ones that answered — so `budget_tiers` covers the whole
    # segment and doesn't quietly shrink when an interview fails.
    seat_profiles: Dict[str, List[Dict[str, Any]]] = {s: [] for s in seg_ids}
    for profile in profiles:
        for seg_id in seg_ids:
            pred = SEGMENTS[seg_id]["predicate"]
            if pred is None or pred(profile):
                seat_profiles[seg_id].append(profile)
                break
    out: List[Dict[str, Any]] = []
    for seg_id in seg_ids:
        members = groups[seg_id]
        seats = seat_profiles[seg_id]
        if not members:
            out.append({
                "segment_id": seg_id,
                "label": SEGMENTS[seg_id]["label"],
                "stance_split": {},
                "budget_tiers": _tier_distribution(seats),
                "top_objections": [],
                "seats": len(seats),
                "heard_count": 0,
                "members": [],
            })
            continue
        stances: Dict[str, int] = {}
        for r in members:
            s = r.get("stance_after") or "neutral"
            stances[s] = stances.get(s, 0) + 1
        out.append({
            "segment_id": seg_id,
            "label": SEGMENTS[seg_id]["label"],
            "stance_split": stances,
            "budget_tiers": _tier_distribution(seats),
            "top_objections": objections.top(
                [r.get("response") or "" for r in members]),
            "seats": len(seats),
            "heard_count": len(members),
            "members": [{
                "agent_id": r.get("agent_id"),
                "agent_name": r.get("agent_name") or f"Persona {r.get('agent_id')}",
                "stance_after": r.get("stance_after") or "neutral",
                "response": r.get("response"),
            } for r in members],
        })
    # Rank deterministically: support desc, then fewer oppose/concerned, then
    # label asc (stable sort keeps the label tie-break in order). Rows with no
    # members at all carry no signal, so they always sink to the bottom in
    # label order rather than ranking by an empty stance dict.
    empty = [e for e in out if not e["members"]]
    empty.sort(key=lambda s: s["label"].lower())
    ranked = [e for e in out if e["members"]]
    ranked.sort(key=lambda s: s["label"].lower())
    ranked.sort(key=lambda s: (s["stance_split"].get("support", 0),
                               -s["stance_split"].get("oppose", 0),
                               -s["stance_split"].get("concerned", 0)),
                reverse=True)
    return ranked + empty


def coverage_summary(meta: Dict[str, Any]) -> Dict[str, int]:
    """How much of the library this ranking actually looked at.

    The UI states this out loud ("compared across 4 of our 8 groups") rather
    than implying the whole market was searched. Our answer is bounded by our
    coverage, and saying so is what keeps the ranking an honest claim.
    """
    compared = [s for s in (meta.get("segments") or []) if s and s != "everyone"]
    return {
        "segments_compared": len(compared),
        # "everyone" is a mix, not a group you could switch to — it is never a
        # candidate room, so it must not inflate the denominator.
        "segments_available": len([s for s in SEGMENTS if s != "everyone"]),
    }


def latest_results(session_id: str) -> List[Dict[str, Any]]:
    """Every persona's most recent reaction, across all rounds of the session.

    A re-pitch only interviews the NEW room, so this round's results alone hold
    one segment. The compare strip is meant to show the rooms side by side, so
    the ranking is fed the union: each agent contributes once, from the latest
    round they answered in. Rounds are read in order, so later answers win.
    """
    by_agent: Dict[Any, Dict[str, Any]] = {}
    # Sort on the round number rather than trusting list_rounds' filename sort.
    # That sort is correct today only because save_round zero-pads to round_%03d;
    # "latest wins" is load-bearing here, so it shouldn't rest on the padding.
    rounds = sorted(list_rounds(session_id, include_results=True),
                    key=lambda r: r.get("round") or 0)
    for rnd in rounds:
        for r in ((rnd.get("result") or {}).get("results") or []):
            if r.get("agent_id") is not None:
                by_agent[r["agent_id"]] = r
    return list(by_agent.values())


COVERAGE_LOG = "coverage_gaps.jsonl"


def log_coverage_gap(session_id: str, meta: Dict[str, Any],
                     chosen: Optional[str] = None,
                     abandoned: Optional[List[str]] = None,
                     note: str = "") -> None:
    """Append one line about where our library did NOT have the user's people.

    This is the most valuable thing the fit strip produces for us. A ranking is
    only ever as good as the segments we have; the rooms a user walks away from
    — and the room they say we're missing — are demand-led evidence for what to
    build into the persona library next.

    Deliberately append-only JSONL next to the sessions, under DATA_ROOT: it
    survives a redeploy on the Railway volume, and nothing reads it at request
    time, so a write failure must never break the user's round.
    """
    line = {
        "ts": datetime.now().isoformat(),
        "user_id": meta.get("user_id"),
        "session_id": session_id,
        "pitch": (meta.get("pitch") or "")[:500],
        "segments_offered": [s for s in (meta.get("segments") or []) if s != "everyone"],
        "segment_chosen": chosen,
        "segments_abandoned": list(abandoned or []),
        "note": (note or "")[:1000],
    }
    try:
        path = os.path.join(_base_dir(), COVERAGE_LOG)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.warning("Coverage-gap log skipped for %s: %s", session_id, e)


def list_sessions(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Session metas, newest first.

    When `user_id` is given, returns only that user's sessions plus legacy
    ownerless ones (no `user_id` in meta) — never another user's. Pass None for
    the unscoped listing.
    """
    out = []
    base = _base_dir()
    for name in os.listdir(base):
        meta = _read_json(os.path.join(base, name, META_FILE))
        if not meta:
            continue
        owner = meta.get("user_id")
        if user_id is not None and owner and owner != user_id:
            continue
        out.append(meta)
    out.sort(key=lambda m: m.get("created_at") or "", reverse=True)
    return out


def delete_session(session_id: str) -> bool:
    sdir = session_dir(session_id)
    if not os.path.exists(os.path.join(sdir, META_FILE)):
        return False
    shutil.rmtree(sdir, ignore_errors=True)
    logger.info(f"Deleted panel session {session_id}")
    return True


def save_round(session_id: str, round_data: Dict[str, Any]) -> int:
    """Persist a pitch round under the session; returns the 1-based round number.

    Rounds are the unit of variant comparison: same cast + same seed across
    rounds means dashboard differences come from the pitch text, not the room.
    """
    sdir = session_dir(session_id)
    rdir = os.path.join(sdir, ROUNDS_DIR)
    os.makedirs(rdir, exist_ok=True)
    existing = [f for f in os.listdir(rdir) if f.startswith("round_") and f.endswith(".json")]
    round_num = len(existing) + 1
    round_data = {
        "round": round_num,
        "timestamp": datetime.now().isoformat(),
        **round_data,
    }
    _write_json(os.path.join(rdir, f"round_{round_num:03d}.json"), round_data)

    meta_path = os.path.join(sdir, META_FILE)
    meta = _read_json(meta_path) or {}
    meta["rounds_run"] = round_num
    _write_json(meta_path, meta)

    # Regenerate the human-readable session report after every round, so a
    # session dir always carries an inspectable REPORT.md next to the raw JSON.
    try:
        write_session_report(session_id)
    except Exception as e:  # noqa: BLE001 — the report is a convenience, never fail a round over it
        logger.warning(f"Session report generation failed for {session_id}: {e}")
    return round_num


def write_session_report(session_id: str) -> str:
    """Compose REPORT.md in the session dir: cast (with tiers + research cards),
    every round's responses and stances — the debugging trail, human-readable.
    Deterministic assembly of already-persisted JSON; no LLM."""
    sdir = session_dir(session_id)
    meta = _read_json(os.path.join(sdir, META_FILE)) or {}
    profiles = _read_json(os.path.join(sdir, PROFILES_FILE)) or []

    lines = [f"# Panel report — {session_id}", ""]
    lines.append(f"**Pitch:** {meta.get('pitch', '')}")
    lines.append(f"**Mode:** {meta.get('mode')} · **Segments:** {meta.get('segment_label')} "
                 f"· **Seed:** {meta.get('seed')} · **Created:** {meta.get('created_at')}")
    if meta.get("budget_tier_filter"):
        lines.append(f"**Affordability filter:** {meta['budget_tier_filter']} "
                     f"(qualified pool: {meta.get('affordability_pool_size')})")
    if meta.get("budget_tier_distribution"):
        lines.append(f"**Budget tiers in cast:** {meta['budget_tier_distribution']}")
    lines.append("")

    lines.append("## Cast")
    lines.append("")
    lines.append("| Name | Archetype | Province | Budget tier | Research cards |")
    lines.append("|---|---|---|---|---|")
    for p in profiles:
        cards = ", ".join(c.get("card_id", "?") for c in p.get("research_citations", [])) or "—"
        lines.append(f"| {p.get('name')} | {p.get('actor_archetype')} | {p.get('province')} "
                     f"| {p.get('budget_tier', '—')} | {cards} |")
    lines.append("")

    rdir = os.path.join(sdir, ROUNDS_DIR)
    round_files = sorted(f for f in (os.listdir(rdir) if os.path.isdir(rdir) else [])
                         if f.startswith("round_") and f.endswith(".json"))
    by_id = {p.get("id"): p for p in profiles}
    for fname in round_files:
        rd = _read_json(os.path.join(rdir, fname)) or {}
        lines.append(f"## Round {rd.get('round')} — {rd.get('timestamp', '')[:19]}")
        if rd.get("pitch") and rd.get("pitch") != meta.get("pitch"):
            lines.append(f"**Variant pitch:** {rd['pitch']}")
        lines.append("")
        results = (rd.get("result") or {}).get("results") or []
        for r in results:
            persona = by_id.get(r.get("agent_id"), {})
            name = r.get("agent_name") or persona.get("name") or f"agent {r.get('agent_id')}"
            arch = r.get("actor_archetype") or persona.get("actor_archetype", "")
            before, after = r.get("stance_before"), r.get("stance_after")
            if before and after:
                arrow = f" — {before} → {after}" + (" (changed)" if r.get("stance_changed") else "")
            else:
                arrow = ""
            lines.append(f"### {name} ({arch}, {r.get('budget_tier', persona.get('budget_tier', '—'))}){arrow}")
            answer = r.get("response") or r.get("answer") or r.get("opinion") or ""
            lines.append(str(answer).strip())
            lines.append("")

    path = os.path.join(sdir, "REPORT.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def list_rounds(session_id: str, include_results: bool = False) -> List[Dict[str, Any]]:
    """Round history, oldest first. Without `include_results` each entry is the
    round summary (pitch text + dashboard) — enough to compare variants."""
    rdir = os.path.join(session_dir(session_id), ROUNDS_DIR)
    if not os.path.isdir(rdir):
        return []
    rounds = []
    for fname in sorted(os.listdir(rdir)):
        if not (fname.startswith("round_") and fname.endswith(".json")):
            continue
        data = _read_json(os.path.join(rdir, fname))
        if not data:
            continue
        if include_results:
            rounds.append(data)
        else:
            rounds.append({
                "round": data.get("round"),
                "timestamp": data.get("timestamp"),
                "pitch": data.get("pitch"),
                "total_interviewed": data.get("result", {}).get("total_interviewed"),
                "impact_dashboard": data.get("result", {}).get("impact_dashboard"),
            })
    return rounds


def latest_round_exchange(session_id: str, agent_id: int) -> Optional[Dict[str, Any]]:
    """The agent's own reaction from the most recent pitch round, shaped as an
    interview_memory entry.

    Used to seed follow-up chats so the conversation starts from what the
    persona just said (and the stance they ended the round on) — while the
    rounds themselves stay stateless. The source/round markers let the chat
    layer dedupe the seed across repeated follow-ups."""
    for rd in reversed(list_rounds(session_id, include_results=True)):
        for res in (rd.get("result", {}).get("results") or []):
            if res.get("agent_id") == agent_id and not res.get("error") and res.get("response"):
                return {
                    "source": "pitch_round",
                    "round": rd.get("round"),
                    "question": (rd.get("pitch") or "")[:300],
                    "response": (res.get("response") or "")[:500],
                    "stance_before": res.get("stance_before", "neutral"),
                    "stance_after": res.get("stance_after", "neutral"),
                    "timestamp": rd.get("timestamp"),
                }
    return None


def frame_pitch(pitch: str, mode: str, probes: Optional[List[str]] = None) -> str:
    """Wrap the raw pitch text the way it reaches agents.

    Product mode uses founder framing — describing the product, asking for an
    honest reaction. Never a buy solicitation (product honesty rule). LLM-free.

    `probes` are the confirmed sub-questions from the study chips — each adds a
    line the persona still has to address. The base reaction is always invited;
    probes only narrow or widen what the panel is additionally asked.
    """
    text = (pitch or "").strip()
    if mode != "product":
        framed = text
    else:
        framed = (
            f"I'm putting this in front of you: {text}\n"
            "I want your honest reaction — what works, what doesn't, what would put you off."
        )
    active = [p for p in (probes or []) if (p or "").strip()]
    if active:
        framed += "\n\nAlso address these specifically:\n" + "\n".join("- " + p for p in active)
    return framed


def synthesize_panel_summary(pitch: str, results: List[Dict[str, Any]], mode: str = "product",
                             session_id: Optional[str] = None,
                             summary_contract: Optional[str] = None) -> str:
    """A short qualitative read of how the room reacted — the recurring
    objections and (qualitatively) what would move them — synthesized from the
    actual reaction text by the cheap sim-tier LLM (SIM_LLM_*).

    Deliberately bounded: the prompt forbids numbers, prices, percentages and any
    "who would buy" / validation score, so this never becomes a purchase metric.
    The real figures (stance split, who moved) are computed deterministically and
    shown alongside — never authored here. Returns "" on any failure so the
    deterministic summary stands on its own.

    A pre-rendered `summary_contract` (computed by the caller from the pointer's
    slots) only adds focus to the existing prompt — the hard rules above never
    relax. summary_contract=None reproduces today's prompt byte-for-byte. The
    contract string is assembled by the caller so this module never imports the
    pointers module (the import direction stays one-way: pointers -> panel_service).
    """
    reactions = [r for r in (results or []) if r.get("response") and "error" not in r]
    if not reactions:
        return ""

    lines = []
    for r in reactions[:24]:  # cap the roster to keep the call cheap
        name = r.get("agent_name") or f"Persona {r.get('agent_id')}"
        stance = r.get("stance_after") or "neutral"
        text = (r.get("response") or "").strip().replace("\n", " ")
        if len(text) > 320:
            text = text[:320] + "…"
        lines.append(f"- {name} [{stance}]: {text}")
    roster = "\n".join(lines)

    subject = "pitch" if mode == "product" else "announcement"
    system = (
        f"You brief a founder on how a room of real people reacted to their {subject}. "
        "Write 2-4 short, plain sentences: the prevailing mood, the recurring objections "
        "or themes across the reactions, and — qualitatively — what would move the room. "
        "Ground every claim in the reactions given. Hard rules: do NOT output any numbers, "
        "counts, percentages, prices, or a 'who would buy' / validation / conversion score; "
        "do NOT invent affordability figures. Qualitative synthesis only."
    )
    if summary_contract:
        system = f"{system}\n{summary_contract}"
    user = f"The {subject}:\n{pitch}\n\nThe reactions:\n{roster}\n\nBrief the founder:"

    api_key = os.environ.get("SIM_LLM_API_KEY") or os.environ.get("LLM_API_KEY") or ""
    base_url = os.environ.get("SIM_LLM_BASE_URL") or os.environ.get("LLM_BASE_URL") or ""
    model = os.environ.get("SIM_LLM_MODEL") or os.environ.get("LLM_MODEL_NAME") or ""
    if not (api_key and base_url and model):
        return ""

    def _generate(prev_judge=None) -> str:
        from openai import OpenAI
        retry_hint = ""
        if prev_judge is not None and prev_judge.reasoning:
            retry_hint = (
                f"\n\nA previous draft scored low. Fix this while staying grounded in the "
                f"reactions (no numbers, no invented claims):\n{prev_judge.reasoning}"
            )
        client = OpenAI(api_key=api_key, base_url=base_url)
        kwargs = dict(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user + retry_hint}],
            temperature=0.3,
            max_tokens=240,
        )
        # Skip "thinking" tokens where supported. Flag shape is provider-specific
        # (Qwen: enable_thinking; DeepSeek V4: thinking.type) — retry plain if the
        # provider rejects it.
        _m = (model or "").lower()
        if "qwen" in _m:
            _no_think = {"enable_thinking": False}
        elif "deepseek" in _m:
            _no_think = {"thinking": {"type": "disabled"}}
        else:
            _no_think = None
        try:
            if _no_think:
                resp = client.chat.completions.create(extra_body=_no_think, **kwargs)
            else:
                resp = client.chat.completions.create(**kwargs)
        except Exception:
            resp = client.chat.completions.create(**kwargs)
        return (resp.choices[0].message.content or "").strip()

    try:
        # Advisory judge: evaluate the summary against the raw reactions (its
        # ground truth), regenerating once on a low score. Off by default.
        from .judge_service import judge_enabled, get_judge_service, judge_best_of, record_judgement
        if judge_enabled():
            svc = get_judge_service()
            summary, judge_result, regenerated = judge_best_of(
                generate=_generate,
                judge=lambda s: svc.judge_panel_synthesis(s, pitch, roster),
            )
            record_judgement("panel_synthesis", judge_result, run_id=session_id,
                             regenerated=regenerated)
            return summary
        return _generate()
    except Exception as e:
        logger.warning(f"Panel summary synthesis failed: {e}")
        return ""
