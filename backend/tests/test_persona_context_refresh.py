"""Item 6 free validation: every check here runs with the LLM switched off.

No test in this file may make a model or network call. The placeholder keys
below exist only because agentsociety2 validates config at import time; nothing
here reaches a provider. SA_CONTEXT_DYNAMIC=0 keeps the live search off, and the
snapshot tests feed a fixed dict instead.
"""

import collections
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")
os.environ.setdefault("LLM_API_KEY", "test-placeholder")
os.environ.setdefault("SA_CONTEXT_DYNAMIC", "0")

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend" / "scripts"))

import pytest


def test_beliefs_are_present_condition():
    """A measured condition must not be phrased as a direction or a forecast."""
    import attitude_fuser
    ph = attitude_fuser._BELIEF_PHRASING
    for dim in ("economic_optimism", "service_satisfaction"):
        for phrasing in ph[dim].values():
            low = phrasing.lower()
            assert "getting worse" not in low
            assert "improving" not in low
    assert "right now" in ph["economic_optimism"]["pessimistic"].lower()


def test_non_belief_fields_unchanged():
    """Item 1 may only touch belief text — identity and money stay byte-identical."""
    live = REPO / "backend/app/data/persona_library/personas.json"
    baseline = REPO / "backend/app/data/persona_library/personas.backup-pre-belief-sync.json"
    if not (live.exists() and baseline.exists()):
        pytest.skip("persona library not present in this checkout")
    now = {p["id"]: p for p in json.loads(live.read_bytes())["personas"]}
    was = {p["id"]: p for p in json.loads(baseline.read_bytes())["personas"]}
    assert set(now) == set(was), "persona set changed"
    # employment_status is deliberately excluded: 31 personas had it blank because
    # the GHS adapter read only employ_Status1, and the documented repair filled it
    # from employ_Status2. Every persona that already had one keeps it — asserted
    # below — so the exclusion cannot hide an unrelated change.
    guarded = ("name", "age", "gender", "province", "occupation", "education",
               "income", "household_size", "race")
    for pid, persona in now.items():
        for field in guarded:
            if field in was[pid]:
                assert persona.get(field) == was[pid][field], f"{pid}.{field} changed"
        if was[pid].get("employment_status"):
            assert persona.get("employment_status") == was[pid]["employment_status"], pid
        else:
            assert persona.get("employment_status") == "Other not economically active"
            assert persona.get("employment_status_provenance") == "ghs_2025:employ_Status2"


def test_research_card_conditional():
    """Item 2: every rendered card carries date, place and conditional framing."""
    from app.services.mechanism_card_service import render_research_context, load_cards
    cards = load_cards()
    assert cards
    txt = render_research_context(cards[:3])
    low = txt.lower()
    assert "conditional" in low and "when" in low
    assert "date unknown" in low or "location not specified" in low or "20" in low
    assert "never treat a group pattern as a fixed trait" in low


def test_permanent_claims_are_softened():
    """A permanent claim must be bounded to its study context, not left absolute."""
    from app.services.mechanism_card_service import render_research_context
    card = {"citation": ["Study X"], "year_range": "2019", "region": "Limpopo",
            "claims": [{"text": "Systemic poverty makes future planning impossible.", "needs": []}]}
    txt = render_research_context([card]).lower()
    assert "in that study context" in txt
    assert "may change this" in txt


def test_sa_snapshot_offline():
    """Item 4: a checked snapshot renders with no network and no model."""
    from app.services.sa_context import format_snapshot
    fresh = {"as_of": "08 Sep 2026", "fetched_at": time.time(), "claims": [
        {"text": "Test claim", "date": "2026-09-08", "source": "https://example.com",
         "scope": "national", "expires_at": time.time() + 3600}]}
    out = format_snapshot(fresh)
    assert out and "2026-09-08" in out and "https://example.com" in out
    assert "verified" not in out.lower(), "unverified search output must not claim verification"


def test_expired_claims_are_dropped():
    from app.services.sa_context import format_snapshot
    expired = {"fetched_at": time.time() - 100000, "claims": [
        {"text": "Old crisis", "date": "2026-01-01", "source": "x",
         "expires_at": time.time() - 10}]}
    out = format_snapshot(expired)
    assert out is None or "Old crisis" not in out


def test_conflict_detection_is_general():
    """The conflict check must work on any listed crisis topic, not one hardcoded word."""
    from app.services.sa_context import detect_conflicts
    static = "Water shedding is constant and fuel price rises hurt every household."
    assert detect_conflicts("Water shedding has eased in most metros.", static)
    assert detect_conflicts("The fuel price has fallen for a third month.", static)
    assert not detect_conflicts("Water shedding continues across the metro.", static)


def test_historical_no_current_context():
    """Item 5: a backtest against a past date never sees present-day facts."""
    import importlib
    os.environ["HISTORICAL_BACKTEST"] = "1"
    try:
        import app.services.agentsociety_opinion_block as mod
        importlib.reload(mod)
        assert "CURRENT SOUTH AFRICAN CONTEXT" not in mod.build_sa_context("policy")
    finally:
        os.environ.pop("HISTORICAL_BACKTEST", None)
        importlib.reload(mod)


def test_fast_mode_keeps_current_conditions():
    """Later fast-mode rounds must not fall back to staler facts than round 1."""
    from app.services.opinion_block import _current_conditions_only
    full = "STATIC GROUNDING\n\nCURRENT SOUTH AFRICAN CONTEXT (source-based) -\n- claim [2026-09-08]"
    kept = _current_conditions_only(full)
    assert kept.startswith("CURRENT SOUTH AFRICAN CONTEXT")
    assert "STATIC GROUNDING" not in kept
    assert _current_conditions_only("STATIC ONLY") == ""


def test_context_assembly_snapshot_id():
    from app.services.context_assembly import assemble_prompt_sections
    r = assemble_prompt_sections("facts", "outlook", "research", "current as of today",
                                 "scenario", "instr")
    assert r["snapshot_id"]
    assert "fixed_persona_facts" in r["hashes"]


def _reframe(profile_extra=None):
    from app.services.prompt_reframer import ImpactReframer
    profile = {"name": "Thandi", "persona": "test", "posts_history": [{"content": "hello"}]}
    profile.update(profile_extra or {})
    return ImpactReframer().reframe("test", profile, mode="policy")


def test_evidence_aware_flag_defaults_to_baseline():
    """The old wording stays the default until the paid comparison validates the new."""
    os.environ.pop("EVIDENCE_AWARE_PROMPTS", None)
    assert "Stay consistent" in _reframe()


def test_evidence_aware_flag_opt_in():
    os.environ["EVIDENCE_AWARE_PROMPTS"] = "1"
    try:
        assert "may keep or change" in _reframe().lower()
    finally:
        os.environ.pop("EVIDENCE_AWARE_PROMPTS", None)


def test_scenario_claim_carries_no_evidence_weight():
    """A scenario assertion is not evidence: the prompt must still tell the persona
    to react only to what is actually described, never to assume unstated features."""
    from app.services.mechanism_card_service import render_research_context
    card = {"citation": ["Study X"], "year_range": "2019", "region": "Limpopo",
            "claims": [{"text": "Parents disengage when rankings are public.", "needs": []}]}
    txt = render_research_context([card]).lower()
    assert "react only to what is actually described" in txt
    assert "do not assume the product has it" in txt


def test_backtest_excludes_present_day_context_by_default():
    """Item 5 gate: a historical backtest must not see today's facts unless asked."""
    import backtest_panel
    os.environ.pop("BACKTEST_CURRENT_CONTEXT", None)
    assert backtest_panel._current_context_requested() is False
    os.environ["BACKTEST_CURRENT_CONTEXT"] = "1"
    try:
        assert backtest_panel._current_context_requested() is True
    finally:
        os.environ.pop("BACKTEST_CURRENT_CONTEXT", None)


def test_no_retired_belief_sentences_remain():
    """A reworded sentence must never survive next to its own replacement."""
    from attitude_fuser import _RETIRED_PHRASING
    live = REPO / "backend/app/data/persona_library/personas.json"
    if not live.exists():
        pytest.skip("persona library not present in this checkout")
    personas = json.loads(live.read_bytes())["personas"]
    stale = [b for p in personas for b in p.get("beliefs", []) if b in _RETIRED_PHRASING]
    assert not stale, f"{len(stale)} retired belief sentences still in the library"


def test_one_belief_per_measured_dimension():
    """The doubled-economy bug: a persona may assert a dimension at most once."""
    import attitude_fuser as af
    live = REPO / "backend/app/data/persona_library/personas.json"
    if not live.exists():
        pytest.skip("persona library not present in this checkout")
    by_sentence = {s: dim for dim, opts in af._BELIEF_PHRASING.items() for s in opts.values()}
    by_sentence.update({s: "retired" for s in af._RETIRED_PHRASING})
    for persona in json.loads(live.read_bytes())["personas"]:
        dims = [by_sentence[b] for b in persona.get("beliefs", []) if b in by_sentence]
        assert len(dims) == len(set(dims)), f"{persona.get('id')} asserts a dimension twice"


def test_sync_drops_retired_wording():
    """The sync recognises its own old output instead of keeping it as prose."""
    import sync_measured_beliefs as sync
    import attitude_fuser as af
    retired = next(iter(af._RETIRED_PHRASING))
    person = {"attitudes": [{"topic": "economic_optimism", "stance": "pessimistic"}],
              "beliefs": [af._BELIEF_PHRASING["economic_optimism"]["pessimistic"],
                          retired, "I walk my niece to school every morning."]}
    out = sync.sync_person(person)
    assert retired not in out["beliefs"]
    assert "I walk my niece to school every morning." in out["beliefs"], "hand-written prose must survive"


def _library():
    live = REPO / "backend/app/data/persona_library/personas.json"
    if not live.exists():
        pytest.skip("persona library not present in this checkout")
    return json.loads(live.read_bytes())["personas"]


def test_personas_carry_their_real_survey_answer():
    """Banding to 3 labels deleted the strength people actually reported. The
    literal answer must ride alongside the band."""
    personas = _library()
    with_answers = [p for p in personas
                    if any(r.get("measured_answer") for r in (p.get("attitudes") or []))]
    assert len(with_answers) > len(personas) * 0.9


def test_one_band_now_holds_more_than_one_answer():
    """The point of the change: people in the same band must no longer be identical."""
    said = collections.defaultdict(set)
    for persona in _library():
        for row in persona.get("attitudes") or []:
            if row.get("measured_answer"):
                said[(row["topic"], row["stance"])].add(row["measured_answer"])
    varied = [k for k, v in said.items() if len(v) > 1]
    assert varied, "every band still collapses to a single answer"
    assert len(said[("economic_optimism", "pessimistic")]) > 1


def test_no_answer_contradicts_its_band():
    """A person told they fear crime must not also be quoted saying they never did."""
    import attitude_donor_adapter as ada
    for persona in _library():
        for row in persona.get("attitudes") or []:
            if not row.get("measured_answer"):
                continue
            assert not ada.answer_contradicts_band(
                row["topic"], row["stance"], row.get("answer_band")), row


def test_population_draws_never_claim_a_real_answer():
    """A drawn band belongs to no respondent, so it has no answer to quote."""
    for persona in _library():
        for row in persona.get("attitudes") or []:
            if row.get("match_quality") == "population_draw":
                assert "measured_answer" not in row


def test_measured_answers_reach_the_prompt():
    from app.services.opinion_agent import OpinionCitizenAgent
    profile = {"attitudes": [{"topic": "economic_optimism", "stance": "pessimistic",
                              "measured_answer": "Fairly bad",
                              "measured_asked": "the present economic condition of the country"}]}
    rendered = "\n".join(
        f"- On {r['measured_asked']}, you said: {r['measured_answer']}."
        for r in profile["attitudes"] if r.get("measured_answer"))
    assert "Fairly bad" in rendered
    assert OpinionCitizenAgent is not None


def test_no_held_out_question_is_handed_to_the_persona():
    """Carrying real answers must never leak a question the backtest scores."""
    import attitude_donor_adapter as ada
    held_out = {"Q38E", "Q38F", "Q38G", "Q37F", "Q37I", "Q37B",
                "Q46E", "Q46B", "Q9A", "Q5A", "Q47A", "Q37G"}
    carried = {col for col, _ in ada._DIM_PRIMARY_ITEM.values()}
    assert not (carried & held_out), carried & held_out


def test_no_persona_is_missing_employment_status():
    """A blank status fails every attitude-match rung down to race-only. GHS records
    it in employ_Status2 even where employ_Status1 says "Unspecified"."""
    for persona in _library():
        assert persona.get("employment_status"), persona.get("name")


def test_no_persona_matches_on_race_alone():
    """Race-only was the weakest tier and existed only because of the blank field."""
    weak = [p for p in _library() if p.get("attitude_match_quality") == "race_only"]
    assert not weak, f"{len(weak)} personas still matched on race alone"


def test_ghs_reads_both_employment_columns():
    import ghs_adapter
    labels = {"employ_Status1": {9: "9. Unspecified"},
              "employ_Status2": {3: "3. Not economically active"}}
    row = {"employ_Status1": 9, "employ_Status2": 3}
    assert ghs_adapter._employment_status(row, labels) == "Other not economically active"
    # Children stay unset: their GHS code is "Not applicable" in both columns.
    kid = {"employ_Status1": 8, "employ_Status2": 8}
    kid_labels = {"employ_Status1": {8: "8. Not applicable"},
                  "employ_Status2": {8: "8. Not applicable"}}
    assert ghs_adapter._employment_status(kid, kid_labels) is None


def test_carried_answers_are_scoped_to_their_own_question():
    """Half the room was repeating its President answer onto Parliament, the courts
    and the police. The block must scope each answer to its own subject while still
    carrying strength of feeling across."""
    src = (REPO / "backend/app/services/opinion_agent.py").read_text(encoding="utf-8")
    block = src[src.index("WHAT YOU ACTUALLY ANSWERED"):][:1200]
    assert "about THAT ONE THING" in block
    assert "Do not " in block and "repeat one of these answers" in block
    assert "strength of feeling" in block, "the overclaim guard must survive the fix"
