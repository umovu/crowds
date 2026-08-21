"""Attitudes survival test — the library ships attitudes as a LIST of
{topic, stance, source, match_quality} rows, but the psychological-state loader
used to require a dict and silently dropped every row. normalize_attitudes must
keep the measured stances. Runs with no LLM and no framework construction."""

import os

# importing opinion_agent pulls in agentsociety2, which demands an API key at
# import time. It is only a presence check — nothing is called — so a placeholder
# keeps the test LLM-free.
os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

from app.services.opinion_agent import normalize_attitudes


def test_library_list_shape_is_kept():
    library_rows = [
        {"topic": "gov_trust", "stance": "low", "source": "afrobarometer_r9_sa", "match_quality": "exact"},
        {"topic": "infrastructure", "stance": "high", "source": "afrobarometer_r9_sa", "match_quality": "donor"},
    ]
    out = normalize_attitudes(library_rows)
    assert out == {"gov_trust": "low", "infrastructure": "high"}


def test_custom_agent_rating_shape_maps_to_stance():
    custom_rows = [
        {"topic": "education", "rating": 2, "description": "schools let us down"},
        {"topic": "safety", "rating": 5, "description": "somewhere in the middle"},
        {"topic": "water", "rating": 9, "description": "taps must run"},
    ]
    out = normalize_attitudes(custom_rows)
    assert out == {"education": "oppose", "safety": "neutral", "water": "support"}


def test_plain_dict_is_passed_through():
    assert normalize_attitudes({"gov_trust": "low"}) == {"gov_trust": "low"}


def test_malformed_inputs_return_empty():
    assert normalize_attitudes(None) == {}
    assert normalize_attitudes("not a list") == {}
    assert normalize_attitudes([]) == {}
    assert normalize_attitudes([{"no_topic": "x"}]) == {}
    assert normalize_attitudes([42]) == {}
