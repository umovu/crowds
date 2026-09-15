"""Fix 4: panels ask what a person would DO, briefly, not for a review. LLM-off.

Behind PANEL_DECISION_QUESTION. The review framing made answers open the same way
("my honest first reaction"), find "a catch" and name a dislike even when the person
would likely use the thing; answers ran to 230 words. The decision framing allows
"nothing", drops the stock probes, asks at most one extra question and sets a hard
length, with a trim in code as the backstop.
"""

import os

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

from app.services import mode_specs, panel_service, study_reader  # noqa: E402

PITCH = "A R150 nurse visit you book on WhatsApp, same day, no queue."


def _on(monkeypatch):
    monkeypatch.setenv("PANEL_DECISION_QUESTION", "1")


def test_off_by_default_the_framing_is_unchanged(monkeypatch):
    monkeypatch.delenv("PANEL_DECISION_QUESTION", raising=False)
    framed = panel_service.frame_pitch(PITCH, "panel")
    assert "need to know first" in framed
    assert "What would you do about it" not in framed


def test_it_asks_for_a_decision_in_a_few_sentences(monkeypatch):
    _on(monkeypatch)
    framed = panel_service.frame_pitch(PITCH, "panel")
    assert PITCH in framed
    assert "What would you do about it, if anything, and why?" in framed
    assert '"Nothing" is a fine answer.' in framed
    assert "at most 3 short sentences, under 60 words" in framed
    assert "don't like" not in framed and "honest reaction" not in framed and "For example" not in framed


def test_stock_probes_are_dropped_and_only_one_real_one_is_kept(monkeypatch):
    _on(monkeypatch)
    probes = [study_reader.BASE_PROBE["question"], study_reader.LENS_FALLBACK_PROBES["land"][0]["question"],
              "Could you afford it, and would it be worth it?", "What would make you trust or distrust it?"]
    framed = panel_service.frame_pitch(PITCH, "panel", probes=probes)
    assert "honest first reaction" not in framed and "first thing you'd assume" not in framed
    assert "Also: Could you afford it, and would it be worth it?" in framed
    assert "trust or distrust" not in framed


def test_stock_probes_match_the_study_reader():
    assert panel_service.STOCK_PROBES == (study_reader.BASE_PROBE["question"],
                                          study_reader.LENS_FALLBACK_PROBES["land"][0]["question"])


def test_word_of_mouth_is_still_asked(monkeypatch):
    _on(monkeypatch)
    assert "If you would tell anyone about it, say who." in panel_service.frame_pitch(PITCH, "panel")


def test_the_decision_wording_names_no_subject(monkeypatch):
    """Same rule as the review framing: boilerplate must not pull topics, beliefs or cards."""
    _on(monkeypatch)
    from app.services import belief_relevance, mechanism_card_service, persona_facts
    from app.services.sa_context import _topics_in
    boilerplate = panel_service.frame_pitch("", "panel")
    assert _topics_in(boilerplate) == set()
    assert belief_relevance.relevant_dimensions(boilerplate) in ([], ["social_voice"])
    assert persona_facts.pitch_parts(boilerplate) == []
    mechanism_card_service._cache = None
    assert not [c["id"] for c in mechanism_card_service.load_cards()
                if mechanism_card_service.topic_matches(c, boilerplate)]


def test_the_prompt_rules_carry_the_same_length(monkeypatch):
    monkeypatch.setenv("HISTORICAL_BACKTEST", "1")
    from app.services.prompt_reframer import ImpactReframer
    person = {"name": "Lerato", "budget_tier": "moderate"}
    _on(monkeypatch)
    on = ImpactReframer().reframe(PITCH, person, mode="panel")
    assert "at most 3 short sentences, under 60 words" in on
    assert "What does this mean for you" not in on
    monkeypatch.setenv("PANEL_DECISION_QUESTION", "0")
    off = ImpactReframer().reframe(PITCH, person, mode="panel")
    assert "2-5 sentences" in off and "What does this mean for you" in off


def test_the_trim_keeps_whole_sentences():
    text = "I would not book it. R150 is too much for me. My phone cannot get online. Maybe later. Nothing else."
    assert mode_specs.trim_to_sentences(text, 4) == "I would not book it. R150 is too much for me. My phone cannot get online. Maybe later."
    assert mode_specs.trim_to_sentences("I would try it once.", 4) == "I would try it once."
    assert mode_specs.trim_to_sentences("", 4) == ""


def test_sims_and_old_sessions_are_untouched(monkeypatch):
    _on(monkeypatch)
    assert panel_service.frame_pitch("A tariff change.", "policy").startswith("A tariff change.")
    assert "putting this in front of you" in panel_service.frame_pitch("A lantern.", "product")
