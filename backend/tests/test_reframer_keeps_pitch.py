"""The persona must always be asked the user's full question.

Regression: the reframer replaced the whole framed pitch with the first "if ..."
clause it found anywhere in it. Panel pitches end with "Would you tell anyone about
this? If so, who, and what would you say?", so every panel was asked
"so, who, and what would you say" and never saw the pitch itself.
"""

import os

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

from app.services.prompt_reframer import ImpactReframer  # noqa: E402

PITCH = ("A clinic near your home that sees you the same day, with no queue, "
         "for R150 a visit. You book on WhatsApp")
FRAMED = (PITCH + "\n\nLast: would you tell anyone about this? "
          "If so, who, and what would you say?")
PROFILE = {"name": "Test Person"}


def _question(text, mode):
    return ImpactReframer()._build_impact_question(text, PROFILE, "health", mode=mode)


def test_the_full_pitch_reaches_the_persona_in_both_modes():
    for mode in ("policy", "product"):
        q = _question(FRAMED, mode)
        assert PITCH in q, mode
        assert "If so, who, and what would you say?" in q, mode


def test_an_if_clause_in_the_pitch_does_not_replace_it():
    pitch = "Would you use a clinic near your home if it cost R150 a visit?"
    assert pitch in _question(pitch, "policy")
