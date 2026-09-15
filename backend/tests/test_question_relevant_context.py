"""News claims and research cards reach a panel prompt only when the question is about them.

LLM-off. Uses the real cached context block shape and the real card set.
"""

import os

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

from app.services import mechanism_card_service as mcs  # noqa: E402
from app.services.sa_context import relevant_realities  # noqa: E402

BLOCK = (
    "CURRENT SOUTH AFRICAN CONTEXT (source-based, as of 10 September 2026) —\n"
    "treat these as the up-to-date reality; do NOT assume a past crisis still\n"
    "applies unless it appears below:\n"
    "- Unemployment is rising, with the official rate at 33.6% in the second quarter of 2026.\n"
    "- Poverty, inequality and unemployment remain structural obstacles to development.\n"
    "- Immigration is one of the most divisive political issues, with emotions running high.\n"
    "- South Africa has had no load shedding since 16 May 2025, but Eskom warns blackouts could return.\n"
    "- Public health facilities face medicine shortages, with only 35% of essential medicines available.\n"
    "- Households are under pressure from the cost of living crisis.\n"
    "\nSources searched (snippets only, not independently verified):\n"
    "- news24.com\n"
)

CLINIC = ("A clinic near your home that sees you the same day, with no queue, "
          "for R150 a visit. You book on WhatsApp")
EVENTS_APP = "A free community app that lists weekend events, church services and sports fixtures."


# ── news claims ────────────────────────────────────────────────────────────

def test_clinic_pitch_keeps_only_health_and_cost_claims():
    out = relevant_realities(BLOCK, CLINIC)
    assert "medicine shortages" in out
    assert "cost of living" in out
    assert "Unemployment is rising" not in out
    assert "Immigration" not in out
    assert "load shedding" not in out


def test_unrelated_question_gets_no_block_at_all():
    assert relevant_realities(BLOCK, EVENTS_APP) is None


def test_claims_are_capped():
    q = "jobs, clinics, water, electricity, crime, prices and foreigners"
    kept = [l for l in relevant_realities(BLOCK, q, limit=3).splitlines()
            if l.startswith("- ") and "news24" not in l]
    assert len(kept) == 3


def test_sources_footer_is_never_counted_as_a_claim():
    out = relevant_realities(BLOCK, CLINIC)
    assert out.rstrip().endswith("- news24.com")


# ── research cards ─────────────────────────────────────────────────────────

def _bound(*card_ids):
    return {"research_context": "stored block",
            "research_citations": [{"card_id": cid} for cid in card_ids]}


def test_every_card_says_what_it_is_about():
    mcs._cache = None
    for card in mcs.load_cards():
        assert card.get("topic_tags"), card["id"]


def test_clinic_pitch_uses_neither_fintech_nor_status_card():
    mcs._cache = None
    profile = _bound("middle-class-status-identity", "fintech-adoption-trust")
    assert mcs.cards_for_question(profile, CLINIC) == []


def test_a_banking_pitch_uses_the_fintech_card():
    mcs._cache = None
    profile = _bound("middle-class-status-identity", "fintech-adoption-trust")
    used = mcs.cards_for_question(profile, "A digital bank account with no monthly fees.")
    assert [c["id"] for c in used] == ["fintech-adoption-trust"]


def test_tags_match_whole_words_only():
    card = {"topic_tags": ["car"]}
    assert not mcs.topic_matches(card, "a clinic that takes care of you")
    assert mcs.topic_matches(card, "a car you can rent")


def test_a_legacy_profile_without_citations_keeps_its_block():
    assert mcs.cards_for_question({"research_context": "old"}, CLINIC) is None
    assert mcs.cards_for_question({}, CLINIC) == []


# ── the sim path applies the same subject gate ─────────────────────────────

def _sim_context(question):
    import asyncio
    from app.services.opinion_agent import OpinionCitizenAgent
    mcs._cache = None
    profile = {
        "name": "Test Person", "persona": "A test persona.", "age": 40,
        "research_context": "STORED BLOCK",
        "research_citations": [{"card_id": "fintech-adoption-trust"},
                               {"card_id": "stokvels-calibration"}],
    }
    agent = OpinionCitizenAgent(id=1, profile=dict(profile), name="Test Person")
    return asyncio.run(agent.character_context(detail="full", question=question))


def test_sim_prompt_drops_cards_the_scenario_is_not_about():
    ctx = _sim_context(CLINIC)
    assert "Research-grounded" not in ctx
    assert "STORED BLOCK" not in ctx


def test_sim_prompt_keeps_the_card_the_scenario_is_about():
    ctx = _sim_context("A digital bank account with no monthly fees.")
    assert "Research-grounded" in ctx
    assert "fintech" in ctx.lower() or "mobile banking" in ctx.lower()


def test_sim_prompt_without_a_question_keeps_the_stored_block():
    assert "STORED BLOCK" in _sim_context("")
