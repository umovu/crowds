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


# ── what the page shows ────────────────────────────────────────────────────
# The page lists what the web search found and which points this room hears.
# It must be the same points the prompt gets, not a second reading of the news.

def _news(monkeypatch, block, saved=True):
    from app.services import sa_context
    monkeypatch.setattr(sa_context, "_enabled", lambda: True)
    monkeypatch.setattr(sa_context, "_read_cache", lambda: block if saved else None)
    monkeypatch.setattr(sa_context, "current_sa_realities", lambda snapshot=None: block)
    return sa_context


def test_the_page_shows_what_the_prompt_gets(monkeypatch):
    sc = _news(monkeypatch, BLOCK)
    out = sc.news_for_pitch(CLINIC)
    prompt_points = [l[2:] for l in relevant_realities(BLOCK, CLINIC).splitlines()
                     if l.startswith("- ") and "news24" not in l]
    assert out["points"] == prompt_points
    assert out["total"] == 6
    assert out["as_of"] == "10 September 2026"
    assert out["sources"] == [{"label": "news24.com", "link": ""}]
    assert out["from_saved"] is True


def test_a_pitch_the_news_does_not_touch_shows_none_used(monkeypatch):
    out = _news(monkeypatch, BLOCK).news_for_pitch(EVENTS_APP)
    assert out["points"] == [] and out["total"] == 6


def test_a_source_link_is_kept(monkeypatch):
    block = BLOCK.replace("- news24.com\n", "- News24 (https://www.news24.com/a)\n")
    out = _news(monkeypatch, block, saved=False).news_for_pitch(CLINIC)
    assert out["sources"] == [{"label": "News24", "link": "https://www.news24.com/a"}]
    assert out["from_saved"] is False


def test_no_search_says_so(monkeypatch):
    assert _news(monkeypatch, None, saved=False).news_for_pitch(CLINIC)["found"] is False


def test_a_search_result_keeps_its_address(monkeypatch):
    # SerperService names the address `url`; the block read only `link`, so it
    # never listed a single source.
    from app.services import sa_context

    class Serper:
        def is_available(self):
            return True

        def search(self, q, num_results=6):
            return {"success": True, "results": [
                {"title": "t", "snippet": "Clinics are out of insulin.",
                 "url": "https://www.news24.com/health/a"}]}

    monkeypatch.setattr(sa_context, "SerperService", Serper)
    got = sa_context._gather_snippets()[0]
    assert got["link"] == "https://www.news24.com/health/a"
    assert got["source"] == "news24.com"
    assert "news24.com (https://www.news24.com/health/a)" in sa_context._render_sources([got])


def test_social_posts_encyclopedias_and_company_blogs_are_not_news():
    from app.services.sa_context import _trusted
    assert _trusted("https://www.news24.com/health/a")
    assert _trusted("https://www.gov.za/news")
    assert not _trusted("https://www.facebook.com/GlobalSouthWorld/videos/1")
    assert not _trusted("https://en.wikipedia.org/wiki/South_African_energy_crisis")
    assert not _trusted("https://www.reslink.org/blogs/load-shedding-ended")
    assert not _trusted("https://m.youtube.com/watch?v=1")
    assert not _trusted("")


# ── a claim counts on its main subject, not a passing word ────────────────────
# Seen on 28 September 2026: "Crime costs ... R700 billion" reached a R200 diabetes
# pitch as a cost-of-living point.

LIVE = (
    "CURRENT SOUTH AFRICAN CONTEXT (source-based, as of 28 September 2026) —\n"
    "- A family of four needs about R39,710.90 a month for basic living costs.\n"
    "- Crime costs South Africa’s economy up to R700 billion per year.\n"
    "- Essential medicines like insulin are out of stock in public clinics.\n"
    "- Electricity tariffs are rising, pushing more people to consider solar.\n"
)
DIABETES = "A clinic service that manages your diabetes for R200 a month."


def test_a_claim_about_crime_is_not_a_cost_of_living_claim():
    out = relevant_realities(LIVE, DIABETES)
    assert "Crime costs" not in out
    assert "insulin" in out
    assert "R39,710.90" in out


def test_each_claim_has_one_subject():
    from app.services.sa_context import _claim_subject
    assert _claim_subject("Crime costs South Africa’s economy up to R700 billion per year.") == "safety"
    assert _claim_subject("Essential medicines like insulin are out of stock in public clinics.") == "health"
    assert _claim_subject("Electricity tariffs are rising, pushing more people to consider solar.") == "power"
    assert _claim_subject("A family of four needs about R39,710.90 a month for basic living costs.") == "cost"


def test_the_daily_search_is_asked_to_cover_health():
    # The day's points vary with the search; health dropped out on 28 September.
    import inspect
    from app.services import sa_context
    assert "public health" in inspect.getsource(sa_context._distil)
