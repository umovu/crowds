"""The persona library, the build word lists, and every rule that names a persona fact
agree with app/data/model/persona.json. LLM-off.

Why: card rules, objection grounds and belief triggers name persona fields and exact
answers. A misspelt field or a look-alike dash matches nobody and nothing fails.
"""

import importlib.util
import json
import os
import sys

import pytest

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(BACKEND, "scripts"))

import attitude_donor_adapter as ada  # noqa: E402

# By file path, and app.services only inside tests: importing that package while
# tests are collected pins SimulationRunner to the real data root before
# test_sim_start_and_credits points it at a temp one.
_spec = importlib.util.spec_from_file_location(
    "data_model_under_test", os.path.join(BACKEND, "app", "services", "data_model.py"))
dm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dm)

SCHEMA = dm.load("persona")
FIELDS = SCHEMA["fields"]
TOPICS = SCHEMA["attitude_row"]["topics"]
CIRCUMSTANCES = SCHEMA["circumstance_row"]["fields"]
LIBRARY = os.path.join(BACKEND, "app", "data", "persona_library", "personas.json")


def _library():
    if not os.path.exists(LIBRARY):
        pytest.skip("persona library not built in this environment")
    with open(LIBRARY, encoding="utf-8") as fh:
        return json.load(fh)["personas"]


# ── the library ────────────────────────────────────────────────────────────

def test_every_library_persona_fits_the_model():
    problems = dm.library_problems(_library())
    assert not problems, f"{len(problems)} problem(s):\n" + "\n".join(problems[:20])


# ── the model itself: where every measured fact came from ─────────────────

def test_every_measured_field_names_its_survey_and_questions():
    sources = SCHEMA["sources"]
    for name, spec in FIELDS.items():
        if spec["layer"] != "measured":
            continue
        assert spec.get("source"), f"{name} is measured but names no survey"
        for s in spec["source"]:
            assert s["survey"] in sources, f"{name} names unknown survey {s['survey']!r}"
            assert s["items"], f"{name} names no question codes for {s['survey']}"
    for name, entry in list(TOPICS.items()) + list(CIRCUMSTANCES.items()):
        assert entry["source"]["survey"] in sources, name
        assert entry["source"]["items"], name


def test_derived_fields_say_what_they_are_made_from():
    for name, spec in FIELDS.items():
        if spec["layer"] == "derived":
            assert spec.get("source") or spec.get("note"), name


def test_row_sources_are_known_surveys():
    pools = SCHEMA["attitude_row"]["sources"] + SCHEMA["circumstance_row"]["sources"]
    for pool in pools:
        assert pool.split(":")[0] in SCHEMA["sources"], pool


def test_groups_are_defined_by_real_fields():
    for name, spec in FIELDS.items():
        assert spec["carried_by"] == "some" or spec["carried_by"] in SCHEMA["groups"], name
    for group, g in SCHEMA["groups"].items():
        for field in g["when"]:
            assert field in FIELDS, f"group {group} is defined by unknown field {field}"


# ── the build word lists agree with the model ─────────────────────────────

def test_attitude_topics_match_the_fuser():
    assert {t: v["stances"] for t, v in TOPICS.items()} == ada.ATTITUDE_VOCAB
    with_question = {t for t, v in TOPICS.items() if "primary_item" in v["source"]}
    assert with_question == set(ada._DIM_PRIMARY_ITEM)
    for topic, (item, asked) in ada._DIM_PRIMARY_ITEM.items():
        assert TOPICS[topic]["source"]["primary_item"] == item
        assert TOPICS[topic]["source"]["asked"] == asked


def test_circumstances_match_the_adapter():
    """Circumstances come from two surveys now, so each half is checked against
    the build that writes it: Afrobarometer's against the donor adapter, GHS's
    against the geography pass. A field belonging to neither is a field nothing
    can write."""
    import add_ghs_geography as ghs

    afrobarometer = {f: v["values"] for f, v in CIRCUMSTANCES.items()
                     if v["source"]["survey"] == "afrobarometer_r9_sa"}
    assert afrobarometer == ada.CIRCUMSTANCE_VOCAB

    # metro is declared against QLFS, where it is measured on the persona's own
    # survey row. The original 375 carry a metro drawn from GHS instead, which is
    # a row-level source, not a second survey for the field.
    from_ghs = {f: v["values"] for f, v in CIRCUMSTANCES.items()
                if v["source"]["survey"] in ("ghs_2025", "qlfs_2026_q1")}
    # The household pass (add_ghs_household) writes children at school and medical
    # aid off the same survey, as optional rows.
    household = {"learners_in_household", "ghs_role", "learner_fee_bands", "medical_aid"}
    assert set(from_ghs) == {"metro", "dwelling", "rdp_housing"} | household
    assert all(CIRCUMSTANCES[f].get("optional") for f in household)
    assert CIRCUMSTANCES["metro"]["source"]["survey"] == "qlfs_2026_q1"
    assert set(from_ghs["dwelling"]) == set(ghs._DWELLING.values())
    assert ghs._TOWNSHIP_DWELLINGS <= set(from_ghs["dwelling"])
    assert set(from_ghs["rdp_housing"]) == {"yes", "no"}

    import add_ghs_household as hh
    assert set(hh._RELATION_ROLE.values()) <= set(from_ghs["ghs_role"])
    assert set(from_ghs["learners_in_household"]) == {str(n) for n in range(hh.MAX_LEARNERS + 1)}
    assert set(from_ghs["medical_aid"]) == {"True", "False"}

    assert set(afrobarometer) | set(from_ghs) == set(CIRCUMSTANCES)


def test_texture_generator_lists_are_in_the_model():
    import texture_generator as tg
    assert set(tg.FROZEN_FIELDS) <= set(FIELDS), set(tg.FROZEN_FIELDS) - set(FIELDS)
    assert all(FIELDS[f]["layer"] == "texture" for f in tg.TEXTURE_FIELDS)
    assert all(FIELDS[f]["layer"] == "retired" for f in tg._RETIRED_TEXTURE_FIELDS)


# ── rules that name persona facts ─────────────────────────────────────────

def test_situation_fields_are_persona_facts():
    from app.services import mechanism_card_service as mcs
    unknown = [f for f in mcs._SITUATION_FIELDS if dm.fact_answers(f) is None]
    assert not unknown


def test_card_rules_name_real_facts_and_answers():
    from app.services import mechanism_card_service as mcs
    mcs._cache = None
    problems = []
    for card in mcs.load_cards():
        problems += dm.rule_problems(card["id"], card.get("applies_when"))
    assert not problems, "\n".join(problems)


def test_objection_grounds_name_real_facts_and_answers():
    with open(os.path.join(BACKEND, "app", "data", "objection_vocab.json"), encoding="utf-8") as fh:
        vocab = json.load(fh)
    problems = []
    for section in ("walls", "pulls"):
        for type_id, entry in vocab[section].items():
            problems += dm.rule_problems(f"{section}.{type_id}", entry.get("grounds"))
    assert not problems, "\n".join(problems)


def test_belief_triggers_cover_every_topic():
    from app.services import belief_relevance as br
    assert set(br._DIM_TRIGGERS) == set(TOPICS)
    for topic, band in br._NEGATIVE_BAND.items():
        assert band in TOPICS[topic]["stances"], topic


# ── the checker catches the mistakes it exists for ────────────────────────

def _valid_persona():
    """A civic persona built from the model alone, so these run without the library."""
    p = {}
    for name, spec in FIELDS.items():
        if spec["carried_by"] != "everyone":
            continue
        kind = spec["type"]
        if kind == "attitude_rows":
            row_spec = SCHEMA["attitude_row"]
            p[name] = []
            for topic, t in TOPICS.items():
                row = {"topic": topic, "stance": t["stances"][0],
                       "source": row_spec["sources"][0], "match_quality": row_spec["match_quality"][0]}
                if "primary_item" in t["source"]:
                    row.update(measured_question=t["source"]["primary_item"],
                               measured_asked=t["source"]["asked"], measured_answer=t["answers"][0])
                p[name].append(row)
        elif kind == "circumstance_rows":
            row_spec = SCHEMA["circumstance_row"]
            p[name] = [{"field": f, "value": c["values"][0], "source": row_spec["sources"][0],
                        "match_quality": row_spec["match_quality"][0]} for f, c in CIRCUMSTANCES.items()]
        elif "allowed" in spec:
            p[name] = spec["allowed"][0]
        elif kind == "string":
            p[name] = {"id": "0123456789abcdef", "survey_respondent": "SAF0001"}.get(name, "text")
        else:
            p[name] = {"integer": 30, "number": 1.0, "boolean": False, "list": ["text"]}[kind]
    return p


def test_a_persona_built_from_the_model_fits_it():
    assert dm.persona_problems(_valid_persona()) == []


def test_an_unknown_field_is_caught():
    p = _valid_persona()
    p["monthly_income"] = 9000
    assert any("'monthly_income'" in x for x in dm.persona_problems(p))


def test_a_household_field_on_a_non_household_persona_is_caught():
    p = _valid_persona()
    p["medical_aid"] = True
    assert any("ghs_household" in x for x in dm.persona_problems(p))


def test_a_household_persona_missing_its_clinic_data_is_caught():
    p = _valid_persona()
    p["source_survey"] = "ghs_2025"
    assert any("'usual_health_facility'" in x for x in dm.persona_problems(p))


def test_an_answer_outside_the_list_is_caught():
    p = _valid_persona()
    p["geotype"] = "Rural"
    assert any("'Rural'" in x for x in dm.persona_problems(p))


def test_a_missing_attitude_is_caught():
    p = _valid_persona()
    p["attitudes"] = [r for r in p["attitudes"] if r["topic"] != "social_voice"]
    assert any("social_voice" in x for x in dm.persona_problems(p))


def test_a_survey_answer_from_the_wrong_question_is_caught():
    p = _valid_persona()
    row = next(r for r in p["attitudes"] if r["topic"] == "gov_trust")
    row["measured_question"] = "Q37D"
    assert any("Q37D" in x for x in dm.persona_problems(p))


def test_a_card_rule_with_a_look_alike_dash_is_caught():
    real = next(v for v in FIELDS["time_to_health_facility"]["allowed"] if v.startswith("30"))
    look_alike = real.replace("–", "-")
    assert look_alike != real, "the survey label is expected to use an en dash"
    assert dm.rule_problems("card", [{"time_to_health_facility": [look_alike]}])
    assert not dm.rule_problems("card", [{"time_to_health_facility": [real]}])


def test_a_rule_naming_a_fact_nobody_has_is_caught():
    assert dm.rule_problems("card", [{"owns_car": ["own"]}])


# ── the app says so when a loaded library drifts ──────────────────────────

def test_library_load_warns_when_a_persona_does_not_fit(tmp_path, monkeypatch):
    from app.services import persona_library as pl
    path = tmp_path / "personas.json"
    path.write_text(json.dumps({"personas": [{"name": "Stray", "age": 30}]}), encoding="utf-8")
    warnings = []
    monkeypatch.setattr(pl, "_seed_from_storage", lambda _p: False)
    monkeypatch.setattr(pl.logger, "warning", lambda msg, *a: warnings.append(msg % a if a else msg))
    lib = pl.PersonaLibrary(str(path)).load()
    assert len(lib.all()) == 1, "a drifted library still loads"
    assert any("data model" in w for w in warnings)
