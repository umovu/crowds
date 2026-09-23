"""Panels run one path: the pitch decides what applies, not a policy/product guess.

LLM-off. Sim casts (mode "policy") and old saved sessions are left as they were.
"""

import json
import os

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

from app.services import panel_service, sa_context  # noqa: E402
from app.services.interview_service import InterviewService  # noqa: E402
from app.services.prompt_reframer import ImpactReframer  # noqa: E402

PERSONA = {"id": "lib1", "name": "Lerato", "actor_archetype": "urban_professional",
           "occupation": "Professionals"}


def test_panel_profiles_always_carry_a_budget_tier():
    assert panel_service._build_profile(dict(PERSONA), 1, "panel").get("budget_tier")


def test_sim_policy_casts_are_unchanged():
    assert "budget_tier" not in panel_service._build_profile(dict(PERSONA), 1, "policy")


def test_one_framing_reads_for_an_announcement(monkeypatch):
    # The review framing; the decision framing has its own tests (test_panel_decision_question).
    monkeypatch.setenv("PANEL_DECISION_QUESTION", "0")
    framed = panel_service.frame_pitch("The water will be cut for three days.", "panel")
    assert "The water will be cut for three days." in framed
    assert "need to know first" in framed
    assert "putting this in front of you" not in framed


def test_the_framing_itself_names_no_subject():
    """Boilerplate must not steer relevance. The first unified wording ("what would
    work for you") made every panel pull unemployment news, economy beliefs and a
    youth-jobs card. The word-of-mouth ask used to be the one exception (it selected
    social_voice for everyone); it is now asked per person, so nothing is selected."""
    from app.services import belief_relevance, mechanism_card_service
    from app.services.sa_context import _topics_in
    boilerplate = panel_service.frame_pitch("", "panel")
    assert _topics_in(boilerplate) == set()
    assert belief_relevance.relevant_dimensions(boilerplate) == []
    mechanism_card_service._cache = None
    assert not [c["id"] for c in mechanism_card_service.load_cards()
                if mechanism_card_service.topic_matches(c, boilerplate)]


def test_old_sessions_keep_their_framing():
    assert panel_service.frame_pitch("A tariff change.", "policy").startswith("A tariff change.")
    assert "putting this in front of you" in panel_service.frame_pitch("A lantern.", "product")


def test_budget_reality_only_when_a_price_is_stated(monkeypatch):
    monkeypatch.setattr(sa_context, "current_sa_realities", lambda snapshot=None: None)
    profile = {"name": "Lerato", "budget_tier": "moderate"}
    reframer = ImpactReframer()
    priced = reframer.reframe("A clinic that sees you today for R150 a visit.", dict(profile), mode="panel")
    free = reframer.reframe("The water will be cut for three days.", dict(profile), mode="panel")
    assert "YOUR BUDGET REALITY" in priced
    assert "YOUR BUDGET REALITY" not in free


def test_interview_service_accepts_panel_sessions(tmp_path):
    sdir = tmp_path / "panel_x"
    sdir.mkdir()
    (sdir / "document_context.json").write_text(json.dumps({"mode": "panel"}), encoding="utf-8")
    (sdir / "agentsociety_profiles.json").write_text("[]", encoding="utf-8")
    assert InterviewService("panel_x", base_dir=str(tmp_path)).mode == "panel"
