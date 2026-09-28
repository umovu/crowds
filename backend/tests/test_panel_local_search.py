"""Panels search the place a pitch names once per round and show what they found."""

import os

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

from app.services import panel_round_service, query_context  # noqa: E402
from app.services.prompt_reframer import ImpactReframer  # noqa: E402


def test_round_search_hands_the_block_to_prompts_and_the_rest_to_the_screen(monkeypatch):
    monkeypatch.setattr(query_context, "local_report", lambda t: {
        "place": "Sunnyside, Pretoria", "queries": ["q"], "status": "found",
        "block": "NEAR YOU ...", "points": ["p"], "sources": []})
    block, shown = panel_round_service._local_search("a clinic in Sunnyside")
    assert block == "NEAR YOU ..."
    assert "block" not in shown and shown["points"] == ["p"]


def test_a_broken_search_never_breaks_the_round(monkeypatch):
    def boom(t):
        raise RuntimeError("serper down")
    monkeypatch.setattr(query_context, "local_report", boom)
    assert panel_round_service._local_search("a clinic in Sunnyside") == (None, None)


def test_the_local_block_reaches_the_persona_prompt():
    profile = {"name": "Thandi", "age": 40, "occupation": "nurse", "province": "Gauteng"}
    prompt = ImpactReframer().reframe("a clinic in Sunnyside", profile, mode="panel",
                                      local_block="NEAR YOU (Sunnyside, Pretoria)\n- fact")
    assert "NEAR YOU (Sunnyside, Pretoria)" in prompt


def test_search_results_carry_a_link_and_site_name(monkeypatch):
    # The context blocks cite "link" and "source"; the search tool used to return
    # only "url", so every sources list came out empty.
    from app.services import serper_service as ss

    class Resp:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"organic": [{"title": "t", "link": "https://www.news24.com/a", "snippet": "s"}]}

    monkeypatch.setattr(ss.requests, "post", lambda *a, **k: Resp())
    svc = ss.SerperService()
    svc.api_key = "k"
    item = svc.search("q")["results"][0]
    assert item["link"] == "https://www.news24.com/a"
    assert item["source"] == "news24.com"
