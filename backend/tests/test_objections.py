"""LLM-off tests for the objection classifier (app/services/objections.py).

The whole point of this module is that the fit card's "how many hit the same
wall" number is assertable without a model. If these tests ever need one, the
logic has moved to the wrong layer.

Imported dependency-light (the module has no service deps) so AgentSociety2 —
which demands AGENTSOCIETY_LLM_API_KEY — never gets pulled in.
"""

import importlib.util
import os

HERE = os.path.dirname(__file__)
SERVICES = os.path.normpath(os.path.join(HERE, "..", "app", "services"))

_spec = importlib.util.spec_from_file_location(
    "objections_under_test", os.path.join(SERVICES, "objections.py"))
objections = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(objections)


# ── classify ───────────────────────────────────────────────────────────────

def test_classify_empty_is_empty():
    assert objections.classify("") == []
    assert objections.classify(None) == []


def test_classify_finds_the_obvious_wall():
    text = "If it goes wrong, who do I talk to? There is no branch near me."
    assert "no_human_support" in objections.classify(text)


def test_classify_is_case_insensitive():
    assert objections.classify("BIOMETRIC scanning") == objections.classify(
        "biometric scanning")


def test_classify_returns_stable_order():
    # Two types present; order must follow OBJECTION_TYPES, not text order.
    text = "The government promised this and I don't trust it — show me proof."
    got = objections.classify(text)
    order = list(objections.OBJECTION_TYPES)
    assert got == sorted(got, key=order.index)


def test_classify_counts_a_type_once_per_response():
    # Three no_human_support words, one hit — the tally counts PEOPLE, not
    # keyword occurrences.
    text = "I want a branch, a teller, a real person."
    assert objections.classify(text).count("no_human_support") == 1


def test_every_type_has_a_label_and_a_vocab():
    for otype in objections.OBJECTION_TYPES:
        assert otype in objections.LABELS
        assert objections.VOCAB.get(otype)


# ── tally / top ────────────────────────────────────────────────────────────

def test_tally_counts_people_not_mentions():
    responses = [
        "No branch, no teller, no one to speak to.",
        "There's no one to talk to.",
        "The price is fine.",
    ]
    assert objections.tally(responses)["no_human_support"] == 2


def test_tally_omits_types_nobody_raised():
    counts = objections.tally(["I need a branch."])
    assert "interest_scepticism" not in counts


def test_top_ranks_by_count_then_stable_order():
    responses = [
        "I need a branch to talk to someone.",
        "There is no one to speak to at all.",
        "The monthly fee worries me.",
    ]
    top = objections.top(responses)
    assert top[0]["id"] == "no_human_support"
    assert top[0]["count"] == 2
    assert top[0]["label"] == objections.LABELS["no_human_support"]


def test_top_respects_the_limit():
    text = ("branch, internet, fingerprint, fees, taxi fare, trust, "
            "interest rate, government")
    assert len(objections.top([text], limit=2)) == 2


def test_top_on_silence_is_empty_not_a_zero_row():
    assert objections.top(["", ""]) == []


def test_top_is_deterministic_across_calls():
    responses = ["a branch and a fee", "a fee and a branch"]
    assert objections.top(responses) == objections.top(responses)


# ── is_condition ───────────────────────────────────────────────────────────

def test_condition_is_recognised():
    assert objections.is_condition("I would use it only if there's a branch.")


def test_flat_refusal_is_not_a_condition():
    assert not objections.is_condition("I will not share my line. Full stop.")


def test_unmatched_text_defaults_to_not_a_condition():
    # The honest default: we did NOT hear a condition, rather than assuming one.
    assert not objections.is_condition("Twenty-nine rand is cheap.")
