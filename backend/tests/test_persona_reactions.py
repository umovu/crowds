"""Persona reactions: how a persona behaves comes from its measured attitudes, not from a
model-written voice guide.

Loaded by path so it runs with no model and no API key (importing app.services pulls
AgentSociety2, which refuses to start without one).
"""

import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_HERE, "..")
sys.path.insert(0, os.path.join(_BACKEND, "scripts"))

_spec = importlib.util.spec_from_file_location(
    "belief_relevance_reactions_target",
    os.path.join(_BACKEND, "app", "services", "belief_relevance.py"))
br = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(br)

import attitude_donor_adapter as ada  # noqa: E402
from attitude_fuser import _REACTION_PHRASING  # noqa: E402


def _rows(**stances):
    return [{"topic": k, "stance": v} for k, v in stances.items()]


# The two library personas this was designed on, with their real measured stances.
CRAIG = _rows(social_trust="mid", business_trust="low", pays_for_quality="yes",
              gov_trust="mid", official_responsiveness="high",
              councillor_responsiveness="mid")
DIMAKATSO = _rows(social_trust="high", business_trust="mid", pays_for_quality="yes",
                  gov_trust="high", official_responsiveness="high",
                  councillor_responsiveness="high")

PITCH = ("A new app from a private company, R50 a month, "
         "that your neighbours recommend.")

CATCH = _REACTION_PHRASING["business_trust"]["low"]
NEIGHBOURS = _REACTION_PHRASING["social_trust"]["high"]
PRICE_OK = _REACTION_PHRASING["pays_for_quality"]["yes"]


def test_every_attitude_has_a_reaction_at_both_ends():
    """The rule that stops a measured attitude going mute a third time."""
    for dim, bands in ada.ATTITUDE_VOCAB.items():
        required = set(bands) - {"mid", "mixed", "neutral"}
        assert set(_REACTION_PHRASING.get(dim, {})) == required, dim


def test_neutral_middles_produce_nothing():
    assert br.reactions(_rows(social_trust="mid", business_trust="mid")) == []


def test_same_pitch_splits_two_people_by_their_own_data():
    craig = br.reactions_for(CRAIG, PITCH, 5)
    dima = br.reactions_for(DIMAKATSO, PITCH, 5)

    # Craig doubts companies; the neighbours don't move him (his social trust is mid).
    assert CATCH in craig
    assert NEIGHBOURS not in craig

    # Dimakatso trusts people, and has no company suspicion to bring.
    assert NEIGHBOURS in dima
    assert CATCH not in dima

    # Both measured "would pay more for better" — same data, same line.
    assert PRICE_OK in craig and PRICE_OK in dima


def test_only_reactions_the_question_touches_are_sent():
    """No filler. Craig's crime_fear reaction has nothing to do with an app pitch."""
    craig = CRAIG + _rows(crime_fear="low")
    safety = _REACTION_PHRASING["crime_fear"]["low"]
    assert safety in [text for text, _pair in br.reactions(craig)]
    assert safety not in br.reactions_for(craig, PITCH, 5)


def test_a_question_touching_nothing_gets_no_reactions():
    assert br.reactions_for(CRAIG, "What is your favourite colour?", 5) == []


def test_custom_agent_ratings_derive_no_reactions():
    """Custom agents carry 0-10 ratings, not vocab stances, and keep their own text."""
    custom = [{"topic": "business_trust", "rating": 2, "description": "wary"}]
    assert br.reactions(custom) == []


def test_reactions_never_mention_manner():
    """Behaviour, not delivery — nothing about pace, length or how clever someone sounds."""
    banned = ("speaks", "speak ", "talks", "fast", "slow to speak", "vocabulary",
              "articulate", "rambl", "accent", "formal")
    for bands in _REACTION_PHRASING.values():
        for sentence in bands.values():
            low = sentence.lower()
            assert not any(b in low for b in banned), sentence


def test_selection_is_deterministic():
    assert br.reactions_for(CRAIG, PITCH, 3) == br.reactions_for(CRAIG, PITCH, 3)
