"""The sameness measures behave on rooms whose answer is known. LLM-off.

scripts/sameness_benchmark.py spends real model calls; these pin its measuring half,
so a change in a benchmark number is a change in the answers, not in the ruler.
"""
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "scripts")))

import sameness_benchmark as sb  # noqa: E402

PITCH = "A R150 nurse visit you book on WhatsApp, same day, no queue."

ONE_VOICE = ["I'd try it once, my neighbours would want to know about it."] * 6
MANY_VOICES = [
    "My clinic has always helped me, so I see no reason to change.",
    "Money is tight since my husband lost his job; groceries come first.",
    "I already have a private doctor through my employer's scheme.",
    "At my age walking is hard, so anything closer matters to me.",
    "Honestly I'd wait until someone at church has used it.",
    "My sister is a nurse and says private rooms rush people.",
]


def test_identical_answers_are_as_alike_as_it_gets():
    m = sb.room_measures(ONE_VOICE, ["support"] * 6, PITCH)
    assert m["overlap"] == 1.0
    assert m["opening"] == 1.0
    assert m["stance_spread"] == 0.0


def test_different_answers_score_as_different():
    alike = sb.room_measures(ONE_VOICE, ["support"] * 6, PITCH)
    varied = sb.room_measures(MANY_VOICES, ["support", "oppose", "neutral"] * 2, PITCH)
    assert varied["overlap"] < alike["overlap"]
    assert varied["shared"] < alike["shared"]
    assert varied["opening"] < alike["opening"]
    assert varied["stance_spread"] == 1.0


def test_echoing_the_pitch_is_not_counted_as_sameness():
    # Everyone repeats the pitch's own words; that is the pitch, not the room.
    echo = [f"{PITCH} {tail}" for tail in (
        "My clinic works.", "Money is tight.", "I have a doctor.", "Too far for me.")]
    m = sb.room_measures(echo, ["neutral"] * 4, PITCH)
    assert m["shared"] == 0.0
    assert m["overlap"] < 0.2


def test_failed_interviews_are_left_out():
    m = sb.room_measures(MANY_VOICES + ["I have no comment on that.", ""], ["neutral"] * 8, PITCH)
    assert m["answered"] == len(MANY_VOICES)


def test_the_interval_is_across_rooms():
    s = sb._summary([0.1, 0.2, 0.3])
    assert s["mean"] == 0.2 and s["ci"] > 0
    assert sb._summary([0.5])["ci"] is None
