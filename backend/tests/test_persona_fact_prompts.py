"""Library persona prompts built from measured facts picked by the pitch. LLM-off.

Behind PERSONA_FACT_PROMPTS. Covers: the tags and wording in the data model are complete,
a pitch pulls facts for every part it touches (a WhatsApp clinic pitch keeps internet
use), unrelated facts stay out, and the story is gone from every place it reached a
prompt while custom agents keep theirs.
"""

import asyncio
import importlib.util
import json
import os

import pytest

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _by_path(name, rel):
    """No app.services import at collection (see test_persona_data_model)."""
    spec = importlib.util.spec_from_file_location(name, os.path.join(BACKEND, *rel.split("/")))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pf = _by_path("persona_facts_under_test", "app/services/persona_facts.py")
dm = _by_path("data_model_for_fact_tests", "app/services/data_model.py")
SCHEMA = dm.load("persona")
PARTS = pf._load("pitch_parts.json")["parts"]

CLINIC = ("A clinic near your home that sees you the same day, with no queue, "
          "for R150 a visit. You book on WhatsApp")
BANK = "A digital bank account with no monthly fees."
SPORTS = "A community sports day on Saturday."
STORY = "STORY-MARKER I grew up poor and the clinic always failed me."
SUMMARY = "SUMMARY-MARKER A struggling learner."


def _circ(**values):
    return [{"field": f, "value": v, "source": "afrobarometer_r9_sa", "match_quality": "exact"}
            for f, v in values.items()]


def _musa(**extra):
    """Shaped like the real Musa Sithole record (GHS learner, Eastern Cape village)."""
    p = {
        "name": "Musa Sithole", "source_entity_type": "library_persona", "age": 17,
        "gender": "Male", "province": "Eastern Cape", "geotype": "Traditional",
        "education": "Secondary not completed", "employment_status": "Other not economically active",
        "occupation": "Learner (School)", "ghs_role": "learner", "current_grade": "Grade 8",
        "edu_institution": "School", "monthly_household_income_rand": 5000.0, "receives_grant": True,
        "medical_aid": False, "usual_health_facility": "Public sector: Clinic",
        "transport_to_health_facility": "Walking", "time_to_health_facility": "30–89 minutes",
        "internet_at_home": True, "computer_in_home": True, "fees_band": "No fees",
        "guardian_type": "grandparent", "marriage_status": "Never married",
        "persona": SUMMARY, "background_story": STORY, "group_affiliation": "Youth club",
        "circumstances": _circ(lived_poverty="moderate", went_without_care="sometimes",
                               owns_vehicle="household", owns_computer="own", owns_bank_account="own",
                               owns_television="household", internet_use="weekly",
                               money_decision="joint", news_social="daily"),
        "attitudes": [], "beliefs": [],
    }
    p.update(extra)
    return p


@pytest.fixture
def facts_on(monkeypatch):
    monkeypatch.setenv("PERSONA_FACT_PROMPTS", "1")


# ── the data model's tags and wording ─────────────────────────────────────

def _prompt_blocks():
    for name, spec in SCHEMA["fields"].items():
        if spec.get("prompt"):
            yield name, spec, spec["prompt"]
    for name, spec in SCHEMA["circumstance_row"]["fields"].items():
        if spec.get("prompt"):
            yield name, {"type": "string", "allowed": spec["values"]}, spec["prompt"]


def test_every_tag_names_a_real_pitch_part():
    for name, _spec, block in _prompt_blocks():
        assert block.get("core") or block.get("about"), f"{name} is neither core nor tagged"
        for part in block.get("about", []):
            assert part in PARTS, f"{name} is tagged with unknown part {part!r}"


def test_every_answer_has_wording():
    for name, spec, block in _prompt_blocks():
        wording = block["say"]
        if isinstance(wording, str):
            assert "{value}" in wording, name
        elif spec["type"] == "string":
            missing = [v for v in spec.get("allowed", [])
                       if v not in wording and v not in block.get("skip", [])]
            assert not missing, f"{name} has no wording for {missing}"
        else:
            assert set(wording) <= {"true", "false"}, name


def test_wording_never_carries_a_model_written_field():
    for name, spec, _block in _prompt_blocks():
        assert spec.get("layer", "measured") in ("measured", "derived"), name


def test_every_part_is_used_by_some_fact():
    tagged = {p for _n, _s, b in _prompt_blocks() for p in b.get("about", [])}
    assert set(PARTS) == tagged


# ── reading the pitch ─────────────────────────────────────────────────────

def test_the_clinic_pitch_touches_every_part_it_names():
    assert set(pf.pitch_parts(CLINIC)) == {"health", "online", "money", "getting_there"}


def test_whole_words_only():
    assert "online" not in pf.pitch_parts("Apply for a loan")
    assert "online" in pf.pitch_parts("A new app for loans")


def test_panel_framing_adds_no_parts():
    from app.services import panel_service
    assert pf.pitch_parts(panel_service.frame_pitch(SPORTS, "panel")) == []


# ── picking facts ─────────────────────────────────────────────────────────

def test_a_whatsapp_clinic_pitch_keeps_the_digital_facts():
    used = set(pf.fields_used(_musa(), CLINIC))
    assert {"internet_use", "internet_at_home", "computer_in_home"} <= used
    assert {"time_to_health_facility", "medical_aid", "went_without_care"} <= used
    assert {"monthly_household_income_rand", "receives_grant"} <= used


def test_the_household_survey_wins_over_the_matched_respondent():
    lines = [f["line"] for f in pf.picked_facts(_musa(computer_in_home=False), CLINIC)]
    assert "There is no computer in your household." in lines
    assert "You have your own computer." not in lines


def test_the_matched_respondent_answer_is_used_when_the_household_survey_is_silent():
    musa = _musa()
    musa.pop("computer_in_home")
    assert "You have your own computer." in [f["line"] for f in pf.picked_facts(musa, CLINIC)]


def test_every_replacement_names_a_real_field():
    for name, _spec, block in _prompt_blocks():
        if "replaced_by" in block:
            assert block["replaced_by"] in SCHEMA["fields"], name


def test_who_they_live_with_is_always_said():
    """A left-out household fact gets guessed: Nokwanda, who lives with her grandparent,
    answered "my mother" on a clinic pitch that did not carry it."""
    for pitch in (CLINIC, BANK, SPORTS):
        lines = [f["line"] for f in pf.picked_facts(_musa(), pitch)]
        assert "You live with your grandparent." in lines, pitch
        assert "Marital status: Never married." in lines, pitch


def test_household_facts_are_core_in_the_model():
    for field in ("marriage_status", "guardian_type", "guards_grandchildren", "learners_in_household"):
        assert SCHEMA["fields"][field]["prompt"].get("core"), field


def test_the_prompt_tells_the_ai_not_to_invent_household_members():
    assert pf.render(_musa(), CLINIC).endswith(pf.NO_GUESSING)


def test_a_clinic_pitch_leaves_out_facts_it_does_not_touch():
    used = set(pf.fields_used(_musa(), CLINIC))
    assert not used & {"owns_television", "fees_band", "edu_institution"}


def test_a_bank_pitch_leaves_out_the_clinic():
    used = set(pf.fields_used(_musa(), BANK))
    assert "owns_bank_account" in used and "internet_use" in used
    assert not used & {"time_to_health_facility", "medical_aid", "usual_health_facility"}


def test_an_unrelated_pitch_gets_only_the_core_facts():
    picked = pf.picked_facts(_musa(), SPORTS)
    assert picked and all(f["why"] == "always" for f in picked)


def test_lines_are_the_survey_answers_in_plain_words():
    lines = [f["line"] for f in pf.picked_facts(_musa(), CLINIC)]
    assert "Time to reach your usual health facility: 30–89 minutes." in lines
    assert "You go online a few times a week." in lines
    assert "Your household's income is about R5 000 a month." in lines
    assert not any("Learner (School)" in line for line in lines), "status words are skipped"


def test_same_persona_and_pitch_give_the_same_lines():
    assert pf.render(_musa(), CLINIC) == pf.render(_musa(), CLINIC)


# ── the story is gone from every prompt path ──────────────────────────────

def test_switch_is_off_by_default(monkeypatch):
    monkeypatch.delenv("PERSONA_FACT_PROMPTS", raising=False)
    assert not pf.uses_facts(_musa())


def test_panel_prompt_uses_facts_not_the_story(facts_on, monkeypatch):
    monkeypatch.setenv("HISTORICAL_BACKTEST", "1")  # no live news lookup in a unit test
    from app.services.prompt_reframer import ImpactReframer
    prompt = ImpactReframer().reframe(CLINIC, _musa(), mode="panel")
    assert pf.HEADER in prompt
    assert "30–89 minutes" in prompt and "a few times a week" in prompt
    assert "STORY-MARKER" not in prompt and "SUMMARY-MARKER" not in prompt


def test_panel_prompt_keeps_the_story_when_the_switch_is_off(monkeypatch):
    monkeypatch.delenv("PERSONA_FACT_PROMPTS", raising=False)
    monkeypatch.setenv("HISTORICAL_BACKTEST", "1")
    from app.services.prompt_reframer import ImpactReframer
    prompt = ImpactReframer().reframe(CLINIC, _musa(), mode="panel")
    assert "STORY-MARKER" in prompt and pf.HEADER not in prompt


def test_custom_agents_keep_their_story(facts_on, monkeypatch):
    monkeypatch.setenv("HISTORICAL_BACKTEST", "1")
    from app.services.prompt_reframer import ImpactReframer
    prompt = ImpactReframer().reframe(CLINIC, _musa(source_entity_type="custom_agent"), mode="panel")
    assert "STORY-MARKER" in prompt


def test_a_whatsapp_panel_prompt_says_what_the_phone_can_do(facts_on, monkeypatch):
    # "Never uses the internet" is not "no WhatsApp": the phone facts must reach the
    # prompt too, or the AI guesses (a persona once said "I can book on my phone"
    # although her phone cannot get online).
    monkeypatch.setenv("HISTORICAL_BACKTEST", "1")
    from app.services.prompt_reframer import ImpactReframer
    person = _musa(circumstances=_circ(lived_poverty="low", internet_use="never", owns_phone="own",
                                       phone_internet="no", phone_use="daily", money_decision="joint"))
    prompt = ImpactReframer().reframe(CLINIC, person, mode="panel")
    for line in ("You say you never use the internet.", "You have your own mobile phone.",
                 "Your phone cannot get on the internet.", "You use a mobile phone every day."):
        assert line in prompt
    assert "STORY-MARKER" not in prompt


def test_never_answers_read_as_plain_sentences():
    circumstances = SCHEMA["circumstance_row"]["fields"]
    awkward = [f"{field}: {text}" for field, entry in circumstances.items()
               for text in ((entry.get("prompt") or {}).get("say") or {}).values()
               if text.rstrip(".").endswith(" never")]
    assert not awkward, awkward


def test_the_profile_dump_drops_the_story_and_left_out_facts(facts_on):
    musa = _musa()
    trimmed = pf.trim(musa, musa, BANK)
    assert "background_story" not in trimmed and "persona" not in trimmed
    assert "time_to_health_facility" not in trimmed and "medical_aid" not in trimmed
    assert "owns_bank_account" in {r["field"] for r in trimmed["circumstances"]}
    assert "owns_television" not in {r["field"] for r in trimmed["circumstances"]}
    assert trimmed["name"] == "Musa Sithole"


def test_sim_prompt_uses_facts_not_the_story(facts_on):
    from app.services.opinion_agent import OpinionCitizenAgent
    agent = OpinionCitizenAgent(id=1, profile=_musa(), name="Musa Sithole")
    ctx = asyncio.run(agent.character_context(detail="full", question=CLINIC))
    assert pf.HEADER in ctx and "30–89 minutes" in ctx
    assert "STORY-MARKER" not in ctx and "SUMMARY-MARKER" not in ctx


# ── what was used is recorded ─────────────────────────────────────────────

def test_facts_used_on_an_answer_fits_the_answer_model_and_names_real_facts():
    fields = pf.fields_used(_musa(), CLINIC)
    known = set(SCHEMA["fields"]) | set(SCHEMA["circumstance_row"]["fields"])
    assert set(fields) <= known
    spec = dm.load("answer")["answer_row"]["fields"]["facts_used"]
    problems = []
    dm._check_value("facts_used", fields, spec, problems)
    assert problems == []


def test_every_real_persona_gets_core_facts(facts_on):
    path = os.path.join(BACKEND, "app", "data", "persona_library", "personas.json")
    if not os.path.exists(path):
        pytest.skip("persona library not built in this environment")
    with open(path, encoding="utf-8") as fh:
        personas = json.load(fh)["personas"]
    empty = [p["name"] for p in personas if len(pf.picked_facts(p, SPORTS)) < 5]
    assert not empty, empty[:10]
