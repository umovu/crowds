"""Picking people, cards and facts by exact persona facts, checked against the persona
class. LLM-off.

Pickers used to name fields and answers as plain strings: a typo matched nobody and
nothing failed. Now every group rule and card-rule field is built from the model.
"""

import json
import os

import pytest

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
LIBRARY = os.path.join(BACKEND, "app", "data", "persona_library", "personas.json")


def _library():
    if not os.path.exists(LIBRARY):
        pytest.skip("persona library not built in this environment")
    with open(LIBRARY, encoding="utf-8") as fh:
        return json.load(fh)["personas"]


# ── names and answers are checked ───────────────────────────────────────────

def test_a_misspelt_fact_fails_straight_away():
    from app.model.persona import FACT
    assert FACT.medical_aid == "medical_aid"
    assert FACT.internet_use == "internet_use"      # a circumstance
    assert FACT.gov_trust == "gov_trust"            # an attitude topic
    with pytest.raises(AttributeError, match="actor_archtype"):
        FACT.actor_archtype


def test_an_answer_no_persona_can_have_fails_straight_away():
    from app.model.persona import FACT, persona_is
    with pytest.raises(ValueError, match="Rural"):
        persona_is(FACT.geotype, "Rural")
    with pytest.raises(ValueError, match="sometimes"):
        persona_is(FACT.gov_trust, "sometimes")


def test_a_picker_reads_a_record_a_seat_and_an_object_the_same_way():
    from app.model import LibraryPersona
    from app.model.persona import FACT, persona_is
    persona = _library()[0]
    stance = next(r["stance"] for r in persona["attitudes"] if r["topic"] == "gov_trust")
    picker = persona_is(FACT.gov_trust, stance)
    seat = {**persona, "id": 0, "library_id": persona["id"], "budget_tier": "moderate"}
    assert picker(persona) and picker(seat) and picker(LibraryPersona.model_validate(persona))
    assert LibraryPersona.model_validate(persona).fact("gov_trust") == stance


# ── the real pickers ────────────────────────────────────────────────────────

def test_every_group_rule_is_built_from_the_model():
    import inspect
    from app.services import panel_service
    source = inspect.getsource(panel_service)
    block = source[source.index("SEGMENTS = {"): source.index("ATTITUDE_SEGMENT_DIMS")]
    assert 'p.get("' not in block, "a group rule still reads a field by plain string"


def test_groups_pick_the_people_the_facts_describe():
    from app.services import panel_service
    people = _library()
    learners = {p["id"] for p in people if panel_service.SEGMENTS["learners"]["predicate"](p)}
    assert learners == {p["id"] for p in people if p["actor_archetype"] == "learner"}
    frustrated = {p["id"] for p in people if panel_service.SEGMENTS["clinic_frustrated"]["predicate"](p)}
    assert frustrated == {p["id"] for p in people if any(
        r["topic"] == "health_service_satisfaction" and r["stance"] == "dissatisfied" for r in p["attitudes"])}
    assert frustrated


def test_card_rule_fields_are_checked_against_the_model():
    from app.model.persona import fact_names
    from app.services import mechanism_card_service as mcs
    assert set(mcs._SITUATION_FIELDS) <= fact_names()


def test_the_library_hands_out_typed_people():
    from app.services.persona_library import PersonaLibrary
    library = PersonaLibrary(LIBRARY)
    if not os.path.exists(LIBRARY):
        pytest.skip("persona library not built in this environment")
    people = library.people()
    assert len(people) == len(_library())
    first = people[0]
    assert library.person(first.id).name == first.name
    assert isinstance(first.age, int)


# ── the picker list shows library personas only ────────────────────────────

def test_the_persona_picker_lists_library_personas_only():
    if not os.path.exists(LIBRARY):
        pytest.skip("persona library not built in this environment")
    from flask import Flask
    from app.api import research
    with Flask("picking-test").app_context():
        body = research.list_personas().get_json()
    assert body["count"] == len(_library())
    assert {p["level"] for p in body["personas"]} == {"library"}


def test_an_old_cached_persona_is_no_longer_served():
    import glob
    cached = [f for root in (BACKEND, os.path.dirname(BACKEND))
              for f in glob.glob(os.path.join(root, "uploads", "persona_cache", "*.json"))]
    if not cached:
        pytest.skip("no legacy cache in this checkout")
    from flask import Flask
    from app.api import research
    old_id = os.path.basename(cached[0])[:-5]
    with Flask("picking-test").app_context():
        response = research.get_persona(old_id)
    status = response[1] if isinstance(response, tuple) else response.status_code
    assert status == 404
