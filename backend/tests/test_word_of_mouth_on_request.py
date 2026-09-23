"""Word of mouth is asked only when the founder asks it. LLM-off.

Every pitch used to end with our own "would you tell anyone about it?", so every
answer ended on it: on the R150 clinic panel 12 of 12 closed on who they'd tell,
with the same closing phrases across people, on a pitch that never asked.
"""
import os

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

import pytest  # noqa: E402

from app.services import belief_relevance, mode_specs, panel_service  # noqa: E402

PITCH = ("A private clinic chain wants to launch a R150 pay-per-visit nurse service. "
         "You book on WhatsApp and see a nurse the same day, no referral needed.")


@pytest.fixture(params=["0", "1"], ids=["review", "decision"])
def framing(request, monkeypatch):
    monkeypatch.setenv("PANEL_DECISION_QUESTION", request.param)


def test_we_add_no_word_of_mouth_question(framing):
    for mode in ("panel", "product", "policy"):
        framed = panel_service.frame_pitch(PITCH, mode)
        assert not mode_specs.pitch_asks_word_of_mouth(framed), mode


def test_a_founders_own_ask_reaches_the_room(framing):
    asked = PITCH + " Would you tell your friends about it?"
    framed = panel_service.frame_pitch(asked, "panel")
    assert "Would you tell your friends about it?" in framed
    assert mode_specs.pitch_asks_word_of_mouth(framed)


def test_a_follow_up_can_ask_it_too(framing):
    framed = panel_service.frame_pitch(PITCH, "panel", probes=["Would you recommend it to others?"])
    assert mode_specs.pitch_asks_word_of_mouth(framed)


@pytest.mark.parametrize("text", [
    "Would you tell anyone about this?",
    "Would you recommend it?",
    "Would you recommend this to a friend?",
    "Is this something that spreads by word of mouth?",
    "Would you spread the word?",
    "Would you share it with your family?",
    "Would you tell people at church?",
])
def test_founder_phrasings_that_ask(text):
    assert mode_specs.pitch_asks_word_of_mouth(text)


@pytest.mark.parametrize("text", [
    PITCH,                                        # "no referral needed" is not an ask
    "Doctors recommend daily exercise. A R99 gym pass.",
    "Tell us your budget and we'll find a school.",
    "",
])
def test_pitches_that_do_not_ask(text):
    assert not mode_specs.pitch_asks_word_of_mouth(text)


def test_the_shared_question_selects_no_attitude_of_its_own(framing):
    # "tell anyone" is a social_voice trigger word, so our own ask used to spend a
    # reaction slot on it for every persona, whatever was pitched.
    assert "social_voice" not in belief_relevance.relevant_dimensions(
        panel_service.frame_pitch(PITCH, "panel"))
