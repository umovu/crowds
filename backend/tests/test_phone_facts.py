"""Phone facts: "never uses the internet" is not "no WhatsApp". LLM-off.

Afrobarometer asks how often people use "the internet" (Q90i) and, separately, whether
they own a mobile phone (Q90f), whether it gets online (Q90g) and how often they use it
(Q90h). In R9 SA most people who said they never use the internet own a phone and use
it daily, so a WhatsApp pitch needs the phone facts, not only the internet one.
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

LIBRARY = os.path.join(BACKEND, "app", "data", "persona_library", "personas.json")
PHONE = ("owns_phone", "phone_internet", "phone_use")
WHATSAPP_CLINIC = "A R150 nurse visit. You book on WhatsApp and see a nurse the same day."


def _by_path(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(BACKEND, *rel.split("/")))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pf = _by_path("persona_facts_phone_test", "app/services/persona_facts.py")
objections = _by_path("objections_phone_test", "app/services/objections.py")


def _person(**circ):
    return {"name": "Test Person", "source_entity_type": "library_persona",
            "circumstances": [{"field": f, "value": v, "source": "afrobarometer_r9_sa",
                               "match_quality": "exact"} for f, v in circ.items()]}


# ── reading the survey ─────────────────────────────────────────────────────

def test_the_adapter_reads_the_phone_questions():
    out = ada._decode_ab_circumstances({"Q90I": 0.0, "Q90F": 2.0, "Q90G": 1.0, "Q90H": 4.0})
    assert out["internet_use"] == "never"
    assert (out["owns_phone"], out["phone_internet"], out["phone_use"]) == ("own", "yes", "daily")


def test_no_phone_of_their_own_leaves_phone_internet_unset():
    # Q90g "not applicable" (7): only asked of people who own a phone themselves.
    out = ada._decode_ab_circumstances({"Q90F": 1.0, "Q90G": 7.0, "Q90H": 3.0})
    assert out["owns_phone"] == "household"
    assert "phone_internet" not in out
    assert out["phone_use"] == "weekly"


# ── what the person is told ────────────────────────────────────────────────

def test_a_whatsapp_pitch_brings_the_phone_facts_not_only_never_online():
    person = _person(internet_use="never", owns_phone="own", phone_internet="yes", phone_use="daily")
    lines = [f["line"] for f in pf.picked_facts(person, WHATSAPP_CLINIC)]
    assert "You say you never use the internet." in lines
    assert "You have your own mobile phone." in lines
    assert "Your phone can get on the internet." in lines
    assert "You use a mobile phone every day." in lines
    assert "You do not use the internet." not in lines


def test_phone_facts_stay_out_of_a_pitch_that_is_not_about_phones():
    person = _person(owns_phone="own", phone_use="daily")
    assert pf.picked_facts(person, "A community sports day on Saturday.") == []


# ── objections ─────────────────────────────────────────────────────────────

def test_a_phone_that_cannot_get_online_grounds_a_data_objection():
    assert objections.has_grounds("digital_capability", {"phone_internet": "no"}) is True
    assert objections.has_grounds("digital_capability", {"owns_phone": "household"}) is True


def test_a_daily_phone_user_with_a_data_phone_has_no_phone_grounds():
    facts = {"owns_phone": "own", "phone_internet": "yes", "phone_use": "daily"}
    assert objections.has_grounds("digital_capability", facts) is False


# ── the model and the library ──────────────────────────────────────────────

def test_phone_facts_are_optional_but_the_rest_are_not():
    from app.models.persona import CIRCUMSTANCES, CircumstanceRow, _row_problems
    rows = [{"field": f, "value": e["values"][0], "source": "afrobarometer_r9_sa", "match_quality": "exact"}
            for f, e in CIRCUMSTANCES.items() if not e.get("optional")]
    assert {f for f, e in CIRCUMSTANCES.items() if e.get("optional")} == set(PHONE)
    assert _row_problems("p", rows, CircumstanceRow, "field", CIRCUMSTANCES) == []
    missing = _row_problems("p", rows[1:], CircumstanceRow, "field", CIRCUMSTANCES)
    assert any("rows missing" in m for m in missing)


def test_library_phone_facts_come_from_the_persona_s_own_respondent():
    if not os.path.exists(LIBRARY) or not os.path.exists(ada._AFROBAROMETER_PATH):
        pytest.skip("library or Afrobarometer file not in this checkout")
    import attach_phone_facts as apf
    with open(LIBRARY, encoding="utf-8") as fh:
        people = json.load(fh)["personas"]
    carrying = [p for p in people if any(r["field"] in PHONE for r in p["circumstances"])]
    if not carrying:
        pytest.skip("phone facts not attached to this library yet")
    by_id = apf.measured_by_respondent(ada._AFROBAROMETER_PATH)
    for p in carrying:
        measured = by_id[p["survey_respondent"]]
        for r in p["circumstances"]:
            if r["match_quality"] != "population_draw":
                assert measured.get(r["field"]) == r["value"], (p["name"], r["field"])
