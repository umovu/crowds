"""Word of mouth is only counted when the person's own survey record backs it.

LLM-off. `social_voice` (Afrobarometer Q8 discuss + Q10B joined others to raise an
issue) grounds both "would tell others" and "would warn others off"; a quiet person
saying "I'd tell everyone" is not counted, and a warning never reads as praise.
"""

import importlib.util
import os
import sys

HERE = os.path.dirname(__file__)
BACKEND = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(BACKEND, "scripts"))

_spec = importlib.util.spec_from_file_location(
    "objections_wom_under_test", os.path.join(BACKEND, "app", "services", "objections.py"))
objections = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(objections)

import attitude_donor_adapter as ada  # noqa: E402

TALKER = [{"topic": "social_voice", "stance": "high"}]
QUIET = [{"topic": "social_voice", "stance": "low"}]

TELL = "I would tell my sister about it, she needs this."
WARN = "I would tell my sister to stay away from it."


def _profile(rows):
    return {"attitudes": rows}


# ── reading ────────────────────────────────────────────────────────────────

def test_a_warning_is_not_a_recommendation():
    reading = objections.read(WARN)
    assert "would_recommend" not in reading["pulls"]
    assert "would_warn_others" in reading["walls"]


def test_a_recommendation_reads_as_one():
    assert "would_recommend" in objections.read(TELL)["pulls"]


def test_a_quiet_person_saying_they_would_tell_is_not_counted():
    facts = objections.persona_facts(_profile(QUIET))
    assert "would_recommend" not in objections.read(TELL, facts)["pulls"]
    assert "would_warn_others" not in objections.read(WARN, facts)["walls"]


def test_a_talker_saying_it_is_counted():
    facts = objections.persona_facts(_profile(TALKER))
    assert "would_recommend" in objections.read(TELL, facts)["pulls"]


def test_word_of_mouth_counts_people_not_seats():
    got = objections.word_of_mouth(
        [TELL, WARN, TELL, ""],
        [_profile(TALKER), _profile(TALKER), _profile(QUIET), _profile(TALKER)])
    assert got == {"would_tell": 1, "would_warn": 1, "heard": 3}


# Real answers from the unified clinic rerun, which the first reader scored as nobody
# telling anyone. Curly apostrophes are deliberate: that is what the model writes.
def test_mentioning_it_to_someone_counts_as_telling():
    facts = objections.persona_facts(_profile(TALKER))
    for said in [
        "I might mention it to a colleague or a neighbour, but I wouldn’t push it.",
        "I’d probably tell my sister and one friend from work, just to ask if they’ve "
        "heard of it — not to send them there blindly.",
        "I’d tell my partner straight away and the neighbours I talk to.",
    ]:
        assert "would_recommend" in objections.read(said, facts)["pulls"], said


def test_refusing_to_tell_is_not_telling():
    facts = objections.persona_facts(_profile(TALKER))
    for said in [
        "Honestly, I’d probably keep my thoughts to myself rather than tell anyone.",
        "I wouldn’t recommend it to my family.",
    ]:
        assert "would_recommend" not in objections.read(said, facts)["pulls"], said


def test_curly_apostrophes_read_like_straight_ones():
    assert objections.read("I can’t afford the fees.") == objections.read("I can't afford the fees.")


def test_the_new_wall_stays_out_of_the_benchmark_layer():
    assert "would_warn_others" in objections.READING_WALL_TYPES
    assert "would_warn_others" not in objections.OBJECTION_TYPES
    assert "would_warn_others" not in objections.classify(WARN)


# ── decoding the survey items ──────────────────────────────────────────────

def test_social_voice_bands_from_both_items():
    assert ada._ab_social_voice({"Q8": 0.0, "Q10B": 0.0}) == "low"
    assert ada._ab_social_voice({"Q8": 1.0, "Q10B": 1.0}) == "mid"
    assert ada._ab_social_voice({"Q8": 2.0, "Q10B": 4.0}) == "high"


def test_social_voice_needs_both_items():
    assert ada._ab_social_voice({"Q8": 2.0, "Q10B": 9.0}) is None
    assert ada._ab_social_voice({"Q8": -1.0, "Q10B": 3.0}) is None
    assert ada._ab_social_voice({}) is None


def test_both_measures_are_in_the_vocabulary():
    assert ada.ATTITUDE_VOCAB["social_voice"] == ["low", "mid", "high"]
    assert ada.ATTITUDE_VOCAB["neighbour_trust"] == ["low", "mid", "high"]
