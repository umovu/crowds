"""The valence audit's counting, with no model in the loop."""
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "audit_card_valence",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "audit_card_valence.py"))
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)

CARDS = [
    {"id": "a", "segment_tags": ["learner", "gogo_guardian"]},
    {"id": "b", "segment_tags": ["learner"]},
]
LABELS = {
    "a#c0": {"card": "a", "valence": "barrier", "confidence": 0.9},
    "a#c1": {"card": "a", "valence": "motivator", "confidence": 0.9},
    "b#c0": {"card": "b", "valence": "barrier", "confidence": 0.9},
    "b#c1": {"card": "b", "valence": "neutral", "confidence": 0.9},
    "b#c2": {"card": "b", "valence": "barrier", "confidence": 0.2},
}


def test_skew_ignores_neutrals():
    assert audit.skew({"barrier": 3, "motivator": 1, "neutral": 99}) == 0.75
    assert audit.skew({"barrier": 0, "motivator": 0, "neutral": 5}) is None


def test_a_claim_counts_for_every_segment_its_card_names():
    by_segment, _, _ = audit.tally(LABELS, CARDS, 0.0)
    # gogo_guardian only sees card a; learner sees both.
    assert audit.skew(by_segment["gogo_guardian"]) == 0.5
    assert by_segment["learner"]["barrier"] == 3


def test_low_confidence_labels_are_dropped():
    by_segment, _, skipped = audit.tally(LABELS, CARDS, 0.5)
    assert skipped == 1
    assert by_segment["learner"]["barrier"] == 2
