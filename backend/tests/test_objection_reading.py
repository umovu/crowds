"""The reading layer: walls need a mood and grounds, praise lands as a pull.

LLM-off. Loaded by path so AgentSociety2 (which demands an API key) never imports.
The mention layer's own tests, and the benchmark reproduction gate, stay as they were.
"""

import importlib.util
import json
import os

HERE = os.path.dirname(__file__)
SERVICES = os.path.normpath(os.path.join(HERE, "..", "app", "services"))

_spec = importlib.util.spec_from_file_location(
    "objections_reading_under_test", os.path.join(SERVICES, "objections.py"))
objections = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(objections)


def walls(text, facts=None):
    return objections.read(text, facts)["walls"]


def pulls(text, facts=None):
    return objections.read(text, facts)["pulls"]


# ── the bug this layer exists for ──────────────────────────────────────────

COMPLIMENTS = [
    "I love that it is free and there is no monthly fee at all.",
    "I trust this because my neighbour used it and it worked well for her.",
    "The clinic is close so I do not need taxi fare. That is what sells it for me.",
    "Being able to speak to a real person is exactly why I would use it.",
    "I would gladly pay extra for this, it is worth it.",
    "This is great, no complaints from me.",
]


def test_the_mention_layer_still_logs_compliments_as_walls():
    """Recorded, not endorsed: this is the benchmark contract, unchanged."""
    assert sum(1 for c in COMPLIMENTS if objections.classify(c)) == 5


def test_no_compliment_reads_as_a_wall():
    for text in COMPLIMENTS:
        assert walls(text) == [], text


def test_compliments_land_as_pulls():
    assert "low_cost" in pulls(COMPLIMENTS[0])
    assert "trusted_source" in pulls(COMPLIMENTS[1])
    assert "close_to_home" in pulls(COMPLIMENTS[2])
    assert "human_help" in pulls(COMPLIMENTS[3])
    assert "worth_paying_for" in pulls(COMPLIMENTS[4])


# ── real walls still count ─────────────────────────────────────────────────

def test_a_worry_is_a_wall():
    assert "fee_sensitivity" in walls("The monthly fee is what worries me.")


def test_a_condition_is_a_wall():
    assert "no_human_support" in walls(
        "I would use it, as long as there is a branch when it breaks.")


def test_a_bare_negation_is_a_wall():
    assert "no_human_support" in walls("No. And there is no branch to sort it out.")


def test_a_stated_need_is_a_wall():
    assert "no_human_support" in walls("I would use this. I just want someone to talk to.")


def test_free_is_not_a_fee_complaint_but_a_catch_is():
    assert walls("It's free, that's great.") == []
    assert "fee_sensitivity" in walls("Nothing is free, there is always a catch.")


def test_mood_is_judged_per_sentence():
    text = "Cheap enough for me. But if it breaks, is there a branch?"
    assert walls(text) == ["no_human_support"]
    assert "low_cost" in pulls(text)


def test_cues_never_match_inside_a_word():
    # The mention layer finds 'rate' in 'great' and 'fare' in 'welfare'.
    assert "interest_scepticism" not in walls("This is not great.")
    assert "cost_of_access" not in walls("I worry about welfare.")


# ── grounds ────────────────────────────────────────────────────────────────

CAR_OWNER_IN_TOWN = {"owns_vehicle": "own", "geotype": "Urban", "went_without_care": "never"}
NO_CAR_RURAL = {"owns_vehicle": "none", "geotype": "Traditional"}
TAXI_WORRY = "The taxi fare to get there worries me."


def test_wall_without_grounds_is_dropped():
    assert "cost_of_access" in walls(TAXI_WORRY)
    assert "cost_of_access" not in walls(TAXI_WORRY, CAR_OWNER_IN_TOWN)


def test_wall_with_grounds_is_kept():
    assert "cost_of_access" in walls(TAXI_WORRY, NO_CAR_RURAL)


def test_missing_data_is_not_evidence_against_a_person():
    assert "cost_of_access" in walls(TAXI_WORRY, {})


def test_pull_grounds_apply_too():
    text = "I would gladly pay extra for this, it is worth it."
    cannot_pay = {"pays_for_quality": "no", "lived_poverty": "high"}
    assert "worth_paying_for" not in pulls(text, cannot_pay)


def test_persona_facts_reads_library_shape():
    profile = {
        "geotype": "Farms",
        "circumstances": [{"field": "owns_vehicle", "value": "none"}],
        "attitudes": [{"topic": "social_trust", "stance": "high"}],
    }
    assert objections.persona_facts(profile) == {
        "geotype": "Farms", "owns_vehicle": "none", "social_trust": "high"}
    assert objections.persona_facts(None) == {}


# ── ranking ────────────────────────────────────────────────────────────────

def test_top_walls_uses_profiles_in_parallel():
    responses = [TAXI_WORRY, TAXI_WORRY]
    profiles = [
        {"circumstances": [{"field": "owns_vehicle", "value": "own"}], "geotype": "Urban"},
        {"circumstances": [{"field": "owns_vehicle", "value": "none"}], "geotype": "Urban"},
    ]
    top = objections.top_walls(responses, profiles)
    assert top == [{"id": "cost_of_access",
                    "label": objections.LABELS["cost_of_access"], "count": 1}]


def test_top_pulls_has_the_same_shape_and_is_deterministic():
    top = objections.top_pulls(COMPLIMENTS)
    assert all(set(row) == {"id", "label", "count"} for row in top)
    assert top == objections.top_pulls(COMPLIMENTS)


# ── the data file ──────────────────────────────────────────────────────────

def test_every_type_in_the_data_file_is_complete():
    with open(objections._VOCAB_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    for section in ("walls", "pulls"):
        for type_id, row in data[section].items():
            assert row.get("label"), type_id
            assert row.get("cues"), type_id
            assert row.get("source"), type_id
            assert isinstance(row.get("grounds"), list), type_id


def test_no_type_id_is_both_a_wall_and_a_pull():
    assert not set(objections.OBJECTION_TYPES) & set(objections.PULL_TYPES)
