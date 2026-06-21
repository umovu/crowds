"""
validate_panel_service — asserts the LLM-free panel session layer.

Everything here must pass with no model configured: session creation, cast
determinism, the economic fields (grant detection + budget tier from real data),
round persistence, and the InterviewService contract (a session dir loads like
a sim dir). Run from backend/:  python scripts/validate_panel_service.py
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# agentsociety2 validates these at import time; dummies are fine — nothing here
# ever calls a model (that's the point of this script).
os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "validate-dummy")
os.environ.setdefault("AGENTSOCIETY_LLM_API_BASE", "http://localhost:1")
os.environ.setdefault("AGENTSOCIETY_NANO_LLM_API_KEY", "validate-dummy")
os.environ.setdefault("AGENTSOCIETY_NANO_LLM_API_BASE", "http://localhost:1")
os.environ.setdefault("AGENTSOCIETY_NANO_LLM_MODEL", "validate-dummy")

# Point panel sessions at a scratch dir before app imports read Config.
_SCRATCH = tempfile.mkdtemp(prefix="panel_validate_")

from app.config import Config  # noqa: E402
Config.PANEL_SESSION_DATA_DIR = _SCRATCH

from app.services import panel_service  # noqa: E402
from app.services.interview_service import InterviewService  # noqa: E402
from app.services.prompt_reframer import ImpactReframer  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def main():
    pitch = "A R99/month prepaid solar lantern subscription for township households"

    # ── creation ─────────────────────────────────────────────────────────
    meta = panel_service.create_session(pitch=pitch, mode="product", n=10, seed=42)
    sid = meta["session_id"]
    check("session created", sid.startswith("panel_"))
    check("cast size respected", meta["cast_size"] == 10, f"got {meta['cast_size']}")
    check("tier distribution present (product)", sum(meta["budget_tier_distribution"].values()) == 10,
          str(meta.get("budget_tier_distribution")))

    # ── determinism: same seed → same cast; different seed → (almost surely) not ──
    meta2 = panel_service.create_session(pitch=pitch, mode="product", n=10, seed=42)
    svc1 = InterviewService(sid, base_dir=Config.PANEL_SESSION_DATA_DIR)
    svc2 = InterviewService(meta2["session_id"], base_dir=Config.PANEL_SESSION_DATA_DIR)
    cast1 = [a["library_id"] for a in svc1.list_agents()]
    cast2 = [a["library_id"] for a in svc2.list_agents()]
    check("same seed → identical cast", cast1 == cast2)
    meta3 = panel_service.create_session(pitch=pitch, mode="product", n=10, seed=43)
    svc3 = InterviewService(meta3["session_id"], base_dir=Config.PANEL_SESSION_DATA_DIR)
    cast3 = [a["library_id"] for a in svc3.list_agents()]
    check("different seed → different cast", cast1 != cast3)

    # ── InterviewService contract ────────────────────────────────────────
    check("mode loads from session dir", svc1.mode == "product", svc1.mode)
    agents = svc1.list_agents()
    check("roster has provenance", all(a.get("library_id") for a in agents))
    check("roster has budget tiers", all(a.get("budget_tier") in ("tight", "moderate", "loose") for a in agents))
    check("anti-echo-chamber spread", len({a["actor_archetype"] for a in agents}) >= 4,
          str({a["actor_archetype"] for a in agents}))

    # ── grant cohort: real income, real provenance ───────────────────────
    grant_agents = [a for a in agents if a.get("is_grant_dependent")]
    for a in grant_agents:
        check(f"grant agent {a['id']} tier from real income",
              a.get("income_provenance") == "grant_schedule" or a.get("monthly_income_rand") is None)

    # ── policy mode carries no economic fields ───────────────────────────
    meta_pol = panel_service.create_session(pitch="A new municipal water tariff", mode="policy", n=6, seed=1)
    svc_pol = InterviewService(meta_pol["session_id"], base_dir=Config.PANEL_SESSION_DATA_DIR)
    check("policy cast has no budget tiers", all(a.get("budget_tier") is None for a in svc_pol.list_agents()))
    check("policy meta has no tier distribution", "budget_tier_distribution" not in meta_pol)

    # ── reframer: budget reality injected in product mode only ──────────
    reframer = ImpactReframer()
    prod_profile = svc1.get_agent_profile(0)
    framed_prod = reframer.reframe(pitch, prod_profile, mode="product")
    framed_pol = reframer.reframe(pitch, prod_profile, mode="policy")
    check("product reframe shows budget reality", "YOUR BUDGET REALITY" in framed_prod)
    check("policy reframe hides budget reality", "YOUR BUDGET REALITY" not in framed_pol)
    check("product reframe separates want/afford", "wanting it and affording it are different" in framed_prod.lower())

    # ── rounds ───────────────────────────────────────────────────────────
    r1 = panel_service.save_round(sid, {"pitch": pitch, "result": {"total_interviewed": 10, "impact_dashboard": {}}})
    r2 = panel_service.save_round(sid, {"pitch": pitch + " v2", "result": {"total_interviewed": 10, "impact_dashboard": {}}})
    check("rounds number sequentially", (r1, r2) == (1, 2))
    rounds = panel_service.list_rounds(sid)
    check("round summaries listed", len(rounds) == 2 and rounds[0]["pitch"] == pitch)
    check("meta tracks rounds", panel_service.get_session(sid)["rounds_run"] == 2)

    # ── segments: deterministic group slices ─────────────────────────────
    segments = {s["id"]: s for s in panel_service.list_segments()}
    check("segments listed", {"everyone", "unemployed", "grant_recipients", "youth"} <= set(segments))
    # "everyone" tracks the current library size (grows as personas are added);
    # just assert it's the full set and named groups are non-empty.
    check("segment counts live",
          segments["everyone"]["count"] == len(panel_service.get_library().all())
          and segments["unemployed"]["count"] > 0,
          str({k: v["count"] for k, v in segments.items()}))
    meta_seg = panel_service.create_session(pitch=pitch, mode="product", n=10, seed=5, segment="unemployed")
    svc_seg = InterviewService(meta_seg["session_id"], base_dir=Config.PANEL_SESSION_DATA_DIR)
    seg_agents = svc_seg.list_agents()
    check("segment cast all unemployed", all(
        svc_seg.get_agent_profile(a["id"]).get("employment_status") in ("Unemployed", "Discouraged job seeker")
        for a in seg_agents))
    check("segment recorded on meta", meta_seg["segment"] == "unemployed" and meta_seg["segment_label"] == "Unemployed")
    meta_seg2 = panel_service.create_session(pitch=pitch, mode="product", n=10, seed=5, segment="unemployed")
    svc_seg2 = InterviewService(meta_seg2["session_id"], base_dir=Config.PANEL_SESSION_DATA_DIR)
    check("segment cast deterministic", [a["library_id"] for a in seg_agents] ==
          [a["library_id"] for a in svc_seg2.list_agents()])
    try:
        panel_service.create_session(pitch=pitch, segment="nonsense")
        check("unknown segment rejected", False)
    except ValueError:
        check("unknown segment rejected", True)
    # Oversized ask returns the whole slice, no padding from outside the group.
    meta_small = panel_service.create_session(pitch=pitch, mode="product", n=50, seed=2, segment="small_business")
    check("small segment returns whole slice", meta_small["cast_size"] == segments["small_business"]["count"],
          f"{meta_small['cast_size']} vs {segments['small_business']['count']}")

    # ── chat continuity plumbing (rounds stateless, chats sticky) ────────
    # Fixture round so latest_round_exchange has something to find.
    panel_service.save_round(meta3["session_id"], {"pitch": "v1 pitch", "result": {"results": [
        {"agent_id": 0, "response": "Round one reaction.", "stance_before": "neutral", "stance_after": "concerned"},
    ]}})
    panel_service.save_round(meta3["session_id"], {"pitch": "v2 pitch", "result": {"results": [
        {"agent_id": 0, "response": "Round two reaction.", "stance_before": "neutral", "stance_after": "oppose"},
        {"agent_id": 1, "error": "boom", "response": "Interview failed."},
    ]}})
    ex = panel_service.latest_round_exchange(meta3["session_id"], 0)
    check("seed comes from latest round", ex and ex["round"] == 2 and ex["response"] == "Round two reaction.", str(ex))
    check("seed skips errored agents", panel_service.latest_round_exchange(meta3["session_id"], 1) is None)
    check("seed None when agent never reacted", panel_service.latest_round_exchange(meta3["session_id"], 99) is None)

    base_profile = svc3.get_agent_profile(0)
    working = svc3._chat_profile(base_profile, memory_seed=ex)
    check("seed enters chat memory + stance adopted",
          working["interview_memory"][-1]["round"] == 2 and working["stance"] == "oppose")
    check("base profile untouched by chat overlay",
          "interview_memory" not in base_profile or base_profile.get("interview_memory") == [])
    # Persisted chat_state + same seed again → deduped, memory survives.
    fake_agent = type("A", (), {"init_state": {
        "interview_memory": working["interview_memory"] + [{"question": "follow-up?", "response": "an answer"}],
        "interview_count": 2, "stance": "oppose",
    }})()
    svc3._persist_chat_state(0, fake_agent)
    svc3b = InterviewService(meta3["session_id"], base_dir=Config.PANEL_SESSION_DATA_DIR)
    p0 = svc3b.get_agent_profile(0)
    check("chat state persisted to disk", p0.get("chat_state", {}).get("interview_count") == 2)
    working2 = svc3b._chat_profile(p0, memory_seed=ex)
    check("seed deduped on repeat follow-up",
          sum(1 for m in working2["interview_memory"] if m.get("source") == "pitch_round") == 1
          and len(working2["interview_memory"]) == 2)
    check("rounds stay blind to chat state", p0.get("stance", "neutral") == "neutral")

    # ── mixed segments: even split, dedup, exhaustion ────────────────────
    meta_mix = panel_service.create_session(
        pitch=pitch, mode="product", n=10, seed=11,
        segments=["unemployed", "informal_traders"])
    check("mix splits seats evenly",
          meta_mix["segment_allocation"] == {"Unemployed": 5, "Informal traders": 5},
          str(meta_mix["segment_allocation"]))
    svc_mix = InterviewService(meta_mix["session_id"], base_dir=Config.PANEL_SESSION_DATA_DIR)
    mix_ids = [a["library_id"] for a in svc_mix.list_agents()]
    check("mix has no duplicate personas", len(mix_ids) == len(set(mix_ids)))
    check("mix members belong to a chosen group", all(
        svc_mix.get_agent_profile(a["id"]).get("employment_status") in ("Unemployed", "Discouraged job seeker")
        or svc_mix.get_agent_profile(a["id"]).get("actor_archetype") == "informal_trader"
        for a in svc_mix.list_agents()))
    check("mix label joined", meta_mix["segment_label"] == "Unemployed + Informal traders")
    meta_mix2 = panel_service.create_session(
        pitch=pitch, mode="product", n=10, seed=11,
        segments=["unemployed", "informal_traders"])
    svc_mix2 = InterviewService(meta_mix2["session_id"], base_dir=Config.PANEL_SESSION_DATA_DIR)
    check("mix deterministic for seed", mix_ids == [a["library_id"] for a in svc_mix2.list_agents()])
    # Overlapping groups (youth ∩ unemployed is large) must still dedupe.
    meta_ov = panel_service.create_session(pitch=pitch, n=20, seed=3, segments=["unemployed", "youth"])
    svc_ov = InterviewService(meta_ov["session_id"], base_dir=Config.PANEL_SESSION_DATA_DIR)
    ov_ids = [a["library_id"] for a in svc_ov.list_agents()]
    check("overlapping mix dedupes", len(ov_ids) == len(set(ov_ids)) and len(ov_ids) == 20)
    # A small group runs dry; the other keeps filling the room.
    meta_dry = panel_service.create_session(pitch=pitch, n=30, seed=3, segments=["small_business", "unemployed"])
    alloc = meta_dry["segment_allocation"]
    check("small group exhausts, room still fills",
          alloc.get("Small business owners") == 8 and meta_dry["cast_size"] == 30, str(alloc))
    try:
        panel_service.create_session(pitch=pitch, segments=["everyone", "unemployed"])
        check("everyone+group rejected", False)
    except ValueError:
        check("everyone+group rejected", True)

    # ── leak guard: research/graph identities refused in a library cast ──
    from app.services.panel_service import assert_library_cast, LIBRARY_PROVENANCE
    # clean library cast passes
    assert_library_cast([{"name": "A", "source_entity_type": LIBRARY_PROVENANCE},
                         {"name": "B", "source_entity_type": None}])
    check("clean library cast accepted", True)
    leaked_caught = False
    try:
        assert_library_cast([
            {"name": "Thandeka", "source_entity_type": LIBRARY_PROVENANCE},
            {"name": "Thuto.io", "source_entity_type": "Organization"},  # research-authored
        ])
    except ValueError as e:
        leaked_caught = "non-library" in str(e)
    check("research/graph identity refused in cast", leaked_caught)
    # real sessions are always clean (built from the library)
    meta_leak = panel_service.create_session(pitch=pitch, n=6, seed=1, segment="everyone")
    svc_leak = InterviewService(meta_leak["session_id"], base_dir=Config.PANEL_SESSION_DATA_DIR)
    check("created session cast is all library-sourced",
          all(a.get("library_id") for a in svc_leak.list_agents()))

    # ── brand filter: Thuto-class entities don't become agents (LLM-off) ──
    from app.services.agent_profile_generator import AgentProfileGenerator as _G
    class _E:
        def __init__(s, name, t): s.name, s._t, s.summary = name, t, ""
        def get_entity_type(s): return s._t
    drop = lambda n, t: _G._deterministic_non_agent(_E(n, t)) is True
    keep = lambda n, t: _G._deterministic_non_agent(_E(n, t)) is False
    check("brand: Thuto.io dropped", drop("Thuto.io", "Organization"))
    check("brand: Thuto/Product dropped", drop("Thuto", "Product"))
    check("brand: EdtechApp type dropped (substring)", drop("Thuto", "EdtechApp"))
    check("brand: Coins/Currency type dropped (substring)", drop("Thuto Coins", "RewardCurrency"))
    check("real person kept", keep("Sipho Khumalo", "Person"))

    # ── fee-status predicates (pure, library-independent) ────────────────
    from app.services.panel_service import _pays_school_fees, _no_fee_only
    check("fee predicate: learner paying", _pays_school_fees({"fees_band": "R501-R1 000"}))
    check("fee predicate: learner no-fee", _no_fee_only({"fees_band": "No fees"}))
    check("fee predicate: guardian mixed counts as paying",
          _pays_school_fees({"learner_fee_bands": ["No fees", "R201-R300"]}))
    check("fee predicate: guardian all-no-fee",
          _no_fee_only({"learner_fee_bands": ["No fees", "No fees"]}))
    check("fee predicate: no fee data → neither",
          not _pays_school_fees({}) and not _no_fee_only({}))
    check("fee segments registered",
          {"fee_paying", "no_fee_school"} <= set(s["id"] for s in panel_service.list_segments()))

    # ── budget tier: real household income wins (GHS personas) ───────────
    from app.services.mode_specs import budget_tier as _bt
    check("hh income → tight", _bt("learner", household_income_rand=3000) == "tight")
    check("hh income → moderate", _bt("learner", household_income_rand=8000) == "moderate")
    check("hh income → loose", _bt("gogo_guardian", household_income_rand=40000) == "loose")
    check("hh income beats loose archetype", _bt("early_adopter", household_income_rand=2000) == "tight")
    check("archetype fallback intact (learner tight)", _bt("learner") == "tight")
    check("grant path intact", _bt("gogo_guardian", grant_income=1100) == "tight")

    # ── self-reported stance parsing (LLM-off) ───────────────────────────
    from app.services.opinion_agent import extract_self_reported_stance, stance_check_footer
    s, body = extract_self_reported_stance("Too pricey for me.\nSTANCE: oppose")
    check("stance line parsed + stripped", s == "oppose" and body == "Too pricey for me.")
    s, body = extract_self_reported_stance("I like it.\n**STANCE:** Won Over")
    check("product alias + markdown tolerated", s == "support" and body == "I like it.")
    s, body = extract_self_reported_stance("STANCE: concerned\nWait no.\nSTANCE: <support>")
    check("last stance line wins", s == "support")
    s, body = extract_self_reported_stance("No stance here at all.")
    check("missing stance → None, text intact", s is None and body == "No stance here at all.")
    s, body = extract_self_reported_stance("Hmm.\nSTANCE: bananas")
    check("garbled stance → None, text intact", s is None and body == "Hmm.\nSTANCE: bananas")
    check("product footer glosses the ladder", "won over" in stance_check_footer("product"))
    check("policy footer stays generic", "won over" not in stance_check_footer("policy"))

    # ── listing / deletion ───────────────────────────────────────────────
    check("sessions listed", any(s["session_id"] == sid for s in panel_service.list_sessions()))
    check("delete works", panel_service.delete_session(sid) and panel_service.get_session(sid) is None)

    # ── founder framing never solicits a purchase ────────────────────────
    framed = panel_service.frame_pitch(pitch, "product")
    check("founder framing, no buy solicitation", "would you buy" not in framed.lower() and "honest reaction" in framed)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(_SCRATCH, ignore_errors=True)
    sys.exit(code)
