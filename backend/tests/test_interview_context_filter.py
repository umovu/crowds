"""The interview context agentsociety2 serialises must carry only what the question
touches.

`AgentBase.answer_external_question` JSON-dumps the WHOLE profile into the system prompt.
Before this filter, that silently re-injected every belief (undoing relevance selection)
and the retired model-written voice_guide / behavioral_tendencies. The base builder is
stubbed so this runs with no model, no workspace and no key.
"""

import os
from datetime import datetime

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

from agentsociety2 import PersonAgent  # noqa: E402

from app.services.opinion_agent import OpinionCitizenAgent  # noqa: E402

GOV = "Government and officials mostly don't act in people like me's interest."
ECON = "The economy is bad and my own prospects are poor right now."
SERVICE = "Basic services in my area are failing and complaints go nowhere."
PAYS = "I'll pay more if the service is genuinely better."

LIBRARY_PROFILE = {
    "name": "Test Person",
    "beliefs": [GOV, ECON, SERVICE, PAYS, "a", "b", "c", "d", "e"],
    "attitudes": [
        {"topic": "gov_trust", "stance": "low"},
        {"topic": "pays_for_quality", "stance": "yes"},
        {"topic": "business_trust", "stance": "low"},
        {"topic": "crime_fear", "stance": "low"},
    ],
    "voice_guide": "brings up load-shedding in every answer",
    "behavioral_tendencies": "complains about the municipality",
}

CUSTOM_PROFILE = {
    "name": "Custom Person",
    "beliefs": ["I run a spaza shop."],
    "attitudes": [{"topic": "business_trust", "rating": 2, "description": "wary"}],
    "voice_guide": "Talks like a shopkeeper.",
    "behavioral_tendencies": "Haggles.",
}


def _agent(profile, monkeypatch):
    def base_context(self, t):
        return {
            "profile": dict(profile),
            "skill_states": {"behavioral_tendencies": profile.get("behavioral_tendencies")},
        }
    monkeypatch.setattr(PersonAgent, "_build_external_question_context", base_context,
                        raising=False)
    return OpinionCitizenAgent(id=1, profile=dict(profile), name=profile["name"],
                               behavioral_tendencies=profile.get("behavioral_tendencies"))


def test_library_persona_context_follows_the_question(monkeypatch):
    agent = _agent(LIBRARY_PROFILE, monkeypatch)
    agent._context_question = "A private company app, R50 a month."
    ctx = agent._build_external_question_context(datetime.now())

    prof = ctx["profile"]
    assert PAYS in prof["beliefs"]
    assert len(prof["beliefs"]) <= 8
    assert "voice_guide" not in prof
    assert "behavioral_tendencies" not in prof
    assert "behavioral_tendencies" not in ctx["skill_states"]
    reactions = " ".join(prof["how_you_react"]).lower()
    assert "catch" in reactions          # business_trust low, touched by "company"
    assert "safety" not in reactions     # crime_fear, untouched by the question


def test_custom_agent_keeps_its_authored_voice(monkeypatch):
    agent = _agent(CUSTOM_PROFILE, monkeypatch)
    agent._context_question = "A private company app, R50 a month."
    prof = agent._build_external_question_context(datetime.now())["profile"]
    assert prof["voice_guide"] == "Talks like a shopkeeper."
    assert prof["beliefs"] == ["I run a spaza shop."]
    assert "how_you_react" not in prof
