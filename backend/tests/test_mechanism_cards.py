"""Unit tests for mechanism_card_service (Phase 5 research grounding) — LLM off.

Pins the deterministic contract:
  * binding is archetype-in-segment_tags lookup, most-specific card first, capped
  * coverage honesty: unknown/uncovered archetype -> no cards, no profile keys
  * RESEARCH_CONTEXT_ENABLED=0 disables binding entirely
  * rendered block carries the citation, the mechanisms, and the precedence
    line (measured attitudes outrank group-level patterns) — and no digits
    (numbers must never enter prompts via cards)
  * attach_research_context only adds keys when something bound

Loads the module directly (mirrors test_library_cast.py) to avoid the heavy
app.services __init__.
"""

import importlib.util
import os
import re
import sys

HERE = os.path.dirname(__file__)
SERVICES = os.path.normpath(os.path.join(HERE, "..", "app", "services"))


def _load_service():
    spec = importlib.util.spec_from_file_location(
        "mechanism_card_service", os.path.join(SERVICES, "mechanism_card_service.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mcs = _load_service()


def setup_function(_fn):
    # Fresh cache + flag per test.
    mcs._cache = None
    os.environ.pop("RESEARCH_CONTEXT_ENABLED", None)


def test_cards_load_and_have_schema():
    cards = mcs.load_cards()
    assert len(cards) >= 10, "expected the shipped card set"
    for c in cards:
        assert c["id"] and c["mechanisms"] and c["segment_tags"]
        assert c.get("claim_type") == "qualitative"


def test_binding_is_deterministic_and_specific_first():
    a = mcs.cards_for_archetype("communal_farmer")
    b = mcs.cards_for_archetype("communal_farmer")
    assert a == b, "same archetype must bind identically every call"
    assert 1 <= len(a) <= mcs.DEFAULT_CARD_CAP
    ids = [c["id"] for c in a]
    assert "communal-cattle-asset-logic" in ids or "farmer-stock-theft-exposure" in ids
    # specificity: every returned card is at least as specific as the next
    tag_counts = [len(c["segment_tags"]) for c in a]
    assert tag_counts == sorted(tag_counts)


def test_coverage_honesty_no_match_no_keys():
    assert mcs.cards_for_archetype("economic_migrant") == []
    profile = {"actor_archetype": "economic_migrant", "name": "X"}
    out = mcs.attach_research_context(profile)
    assert "research_context" not in out and "research_citations" not in out


def test_flag_off_disables_binding():
    os.environ["RESEARCH_CONTEXT_ENABLED"] = "0"
    assert mcs.cards_for_archetype("communal_farmer") == []
    profile = {"actor_archetype": "communal_farmer"}
    assert "research_context" not in mcs.attach_research_context(profile)


def test_render_block_contract():
    cards = mcs.cards_for_archetype("communal_farmer")
    block = mcs.render_research_context(cards)
    assert block.startswith("# Research-grounded context")
    assert "your own outlook prevails" in block            # precedence line
    # projection guard: documented patterns about unstated features must be
    # raised as questions/conditions, never asserted as product facts
    assert "React ONLY to what is actually described" in block
    assert "From " in block                                 # citation surfaced
    # No digits in the CONTENT lines (mechanisms/vocabulary). Citation lines
    # ("From ...") legitimately carry publication years — provenance, not data.
    for line in block.splitlines():
        if line.strip().startswith("- ") or line.strip().startswith("Vocabulary"):
            assert not re.search(r"\d", line), f"digit in card content line: {line!r}"


def test_economic_tags_filter_by_tier():
    # middle-class-status-identity is tagged moderate/loose; a tight-tier
    # urban_professional must not bind it, a loose one may.
    tight = mcs.cards_for_archetype("urban_professional", cap=99, budget_tier="tight")
    loose = mcs.cards_for_archetype("urban_professional", cap=99, budget_tier="loose")
    assert "middle-class-status-identity" not in [c["id"] for c in tight]
    assert "middle-class-status-identity" in [c["id"] for c in loose]
    # township-sample learner cards must not bind for a loose-tier learner
    loose_learner = [c["id"] for c in mcs.cards_for_archetype("learner", cap=99, budget_tier="loose")]
    assert "youth-mobile-airtime-economy" not in loose_learner
    # untagged (class-blind) cards apply to every tier
    assert "incentivized-learning-engagement" in loose_learner


def test_no_tier_means_no_economic_filtering():
    # Policy casts carry no budget_tier: binding must be tier-blind (back-compat).
    untiered = [c["id"] for c in mcs.cards_for_archetype("learner", cap=99)]
    assert "youth-mobile-airtime-economy" in untiered


def test_attach_respects_profile_tier():
    p_loose = {"actor_archetype": "learner", "budget_tier": "loose"}
    out = mcs.attach_research_context(p_loose, cap=99)
    assert all(c["card_id"] != "youth-mobile-airtime-economy"
               for c in out.get("research_citations", []))
    p_tight = {"actor_archetype": "learner", "budget_tier": "tight"}
    out = mcs.attach_research_context(p_tight, cap=99)
    assert any(c["card_id"] == "youth-mobile-airtime-economy"
               for c in out["research_citations"])


def test_attach_adds_both_keys_when_bound():
    profile = {"actor_archetype": "communal_farmer", "name": "Test"}
    out = mcs.attach_research_context(profile)
    assert out["research_context"]
    assert out["research_citations"]
    for cit in out["research_citations"]:
        assert cit["card_id"] and isinstance(cit["citation"], list)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        setup_function(fn)
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
