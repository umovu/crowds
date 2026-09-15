"""Prompt layers that pushed every panel negative regardless of the question.

LLM-off. Each test pins one removed driver so it cannot quietly return.
"""

import os

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

from app.services.interview_service import InterviewService  # noqa: E402
from app.services.prompt_reframer import ImpactReframer  # noqa: E402

PITCH = "A clinic near your home that sees you the same day, for R150 a visit."


# ── the question ending ────────────────────────────────────────────────────

def test_the_ending_does_not_ask_for_fear_or_invented_detail():
    q = ImpactReframer()._build_impact_question(PITCH, {"name": "Thandi"}, "health", mode="policy")
    low = q.lower()
    assert "afraid" not in low
    assert "real people" not in low and "real places" not in low
    assert "what, if anything, would you do about it" in low


# ── "You care deeply about" ────────────────────────────────────────────────

TOPICS = ["Whether basic services will actually improve where I live"]
SERVICE_Q = "Will basic services improve where you live if the clinic opens?"


def test_library_persona_gets_no_model_written_stake():
    profile = {"source_entity_type": "library_persona", "interested_topics": TOPICS}
    stake = ImpactReframer()._find_personal_stake(profile, "health", SERVICE_Q)
    assert not (stake or "").startswith("You care deeply about")


def test_custom_agent_keeps_its_authored_stake():
    profile = {"source_entity_type": "custom_agent", "interested_topics": TOPICS}
    stake = ImpactReframer()._find_personal_stake(profile, "health", SERVICE_Q)
    assert (stake or "").startswith("You care deeply about")


# ── real income reaches the screen ─────────────────────────────────────────

def test_roster_carries_surveyed_household_income():
    svc = InterviewService.__new__(InterviewService)
    svc.profiles = [{"id": 1, "name": "Lerato", "monthly_household_income_rand": 18500,
                     "income_provenance": "ghs_2024"}]
    svc._load_agent_opinions = lambda: {}
    entry = svc.list_agents()[0]
    assert entry["monthly_household_income_rand"] == 18500
    assert entry["income_provenance"] == "ghs_2024"
