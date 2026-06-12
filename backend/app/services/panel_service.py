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
import shutil
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..utils.logger import get_logger
from .income_seeder import detect_grant, GRANT_PROVENANCE
from .mode_specs import budget_tier
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
        "label": "Everyone",
        "description": "Representative cross-section of SA, tilted toward your pitch",
        "predicate": None,
    },
    "unemployed": {
        "label": "Unemployed",
        "description": "Unemployed and discouraged job seekers (QLFS employment status)",
        "predicate": lambda p: p.get("employment_status") in ("Unemployed", "Discouraged job seeker"),
    },
    "grant_recipients": {
        "label": "Grant recipients",
        "description": "Households surviving on SASSA grants",
        "predicate": lambda p: p.get("actor_archetype") == "grant_dependent_survivor",
    },
    "informal_traders": {
        "label": "Informal traders",
        "description": "Spaza, street and informal-economy operators",
        "predicate": lambda p: p.get("actor_archetype") == "informal_trader",
    },
    "small_business": {
        "label": "Small business owners",
        "description": "Formal small-business operators",
        "predicate": lambda p: p.get("actor_archetype") == "small_business_owner",
    },
    "youth": {
        "label": "Youth (under 35)",
        "description": "18-34, across employment statuses",
        "predicate": lambda p: isinstance(p.get("age"), int) and p["age"] < 35,
    },
    "employed": {
        "label": "Employed",
        "description": "Formally employed (QLFS employment status)",
        "predicate": lambda p: p.get("employment_status") == "Employed",
    },
    # Education roles (GHS 2025 library build) — counts stay 0 until the
    # education personas are built into the library.
    "learners": {
        "label": "Learners",
        "description": "High-school-age learners (15-18) in the school system (GHS)",
        "predicate": lambda p: p.get("actor_archetype") == "learner",
    },
    "guardians": {
        "label": "Parents & guardians",
        "description": "Heads/spouses of households with school-age learners (GHS)",
        "predicate": lambda p: p.get("actor_archetype") in ("guardian_parent", "gogo_guardian"),
    },
    "gogo_guardians": {
        "label": "Gogo guardians",
        "description": "Grandparent-headed learner households (~39% of SA learners)",
        "predicate": lambda p: p.get("actor_archetype") == "gogo_guardian",
    },
    "educators": {
        "label": "Educators",
        "description": "Teachers (QLFS professional pool, role assigned)",
        "predicate": lambda p: p.get("actor_archetype") == "educator",
    },
    # Fee status (GHS) — households already spending on education vs no-fee-school
    # households. Works across learners (fees_band) and guardians (learner_fee_bands),
    # so a paid-product pitch can target families with proven education spend.
    "fee_paying": {
        "label": "Fee-paying households",
        "description": "Learners/guardians already paying school fees (GHS) — proven education spend",
        "predicate": lambda p: _pays_school_fees(p),
    },
    "no_fee_school": {
        "label": "No-fee-school households",
        "description": "Learners/guardians at no-fee schools (GHS) — tightest affordability test",
        "predicate": lambda p: _no_fee_only(p),
    },
}


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


def _build_profile(persona: Dict[str, Any], agent_id: int, mode: str) -> Dict[str, Any]:
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

    if mode == "product":
        is_grant, grant_type, grant_amount = detect_grant(
            actor_archetype=profile.get("actor_archetype"),
            occupation=profile.get("occupation"),
            background_story=profile.get("background_story"),
        )
        if is_grant:
            profile["is_grant_dependent"] = True
            profile["grant_type"] = grant_type
            if grant_amount is not None:
                profile["monthly_income_rand"] = grant_amount
                profile["income_provenance"] = GRANT_PROVENANCE
        profile["budget_tier"] = budget_tier(
            archetype=profile.get("actor_archetype"),
            is_institutional=bool(profile.get("is_institutional", False)),
            occupation=profile.get("occupation"),
            group_affiliation=profile.get("group_affiliation"),
            grant_income=grant_amount if is_grant else None,
            # GHS personas carry surveyed household income — the strongest real
            # signal; overrides grant/archetype inference inside budget_tier.
            household_income_rand=profile.get("monthly_household_income_rand"),
        )

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
                    cast.append(candidate)
                    allocation[seg_id] += 1
                    progressed = True
                    break
        if not progressed:
            break
    return cast, allocation


def create_session(
    pitch: str,
    mode: str = "product",
    n: int = DEFAULT_CAST_SIZE,
    province: Optional[str] = None,
    seed: Optional[int] = None,
    segment: Optional[str] = None,
    segments: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create a panel session: select a cast, compute economics, write the dir.

    Deterministic for a given (pitch, n, province, seed, segments) — no LLM
    calls. `segments` mixes several named library slices with even seat
    allocation; `segment` is the single-group shorthand. None/"everyone" keeps
    the representative + pitch-tilted selection. Returns the session metadata
    including the roster summary.
    """
    if not (pitch or "").strip():
        raise ValueError("pitch text is required")
    mode = (mode or "product").strip().lower()
    if mode not in ("policy", "product"):
        raise ValueError(f"mode must be 'policy' or 'product', got '{mode}'")

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

    if seg_list == ["everyone"]:
        cast = select_for_query(n, pitch, province=province, seed=seed, library=library)
        allocation = {"everyone": len(cast)}
    else:
        cast, allocation = _mixed_cast(seg_list, n, seed, province, library)
    profiles = [_build_profile(p, i, mode) for i, p in enumerate(cast)]
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
    if mode == "product":
        meta["budget_tier_distribution"] = _tier_distribution(profiles)
    _write_json(os.path.join(sdir, META_FILE), meta)

    logger.info(f"Created panel session {session_id}: {len(profiles)} personas, mode={mode}, seed={seed}")
    return meta


def _count_by(profiles: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for p in profiles:
        v = p.get(key) or "unknown"
        counts[v] = counts.get(v, 0) + 1
    return counts


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    return _read_json(os.path.join(session_dir(session_id), META_FILE))


def list_sessions() -> List[Dict[str, Any]]:
    """All session metas, newest first."""
    out = []
    base = _base_dir()
    for name in os.listdir(base):
        meta = _read_json(os.path.join(base, name, META_FILE))
        if meta:
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
    return round_num


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


def frame_pitch(pitch: str, mode: str) -> str:
    """Wrap the raw pitch text the way it reaches agents.

    Product mode uses founder framing — describing the product, asking for an
    honest reaction. Never a buy solicitation (product honesty rule). LLM-free.
    """
    text = (pitch or "").strip()
    if mode != "product":
        return text
    return (
        f"I'm putting this in front of you: {text}\n"
        "I want your honest reaction — what works, what doesn't, what would put you off."
    )
