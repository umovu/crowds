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
        assert c["id"] and c["claims"] and c["segment_tags"]
        assert c.get("claim_type") in ("qualitative", "mixed_methods")


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


_TIERED = [
    {"id": "middle-tier", "segment_tags": ["urban_professional"], "economic_tags": ["moderate", "loose"],
     "claims": [{"text": "a", "needs": [], "chain_id": "C1", "passages": ["P1"], "objections": [], "vocabulary": []}]},
    {"id": "tight-tier", "segment_tags": ["learner"], "economic_tags": ["tight"],
     "claims": [{"text": "b", "needs": [], "chain_id": "C1", "passages": ["P1"], "objections": [], "vocabulary": []}]},
    {"id": "class-blind", "segment_tags": ["learner"],
     "claims": [{"text": "c", "needs": [], "chain_id": "C1", "passages": ["P1"], "objections": [], "vocabulary": []}]},
]


def test_economic_tags_filter_by_tier(monkeypatch):
    # A card tagged moderate/loose must not bind a tight-tier persona; a tight-only
    # card must not bind a loose one; an untagged card binds every tier.
    monkeypatch.setattr(mcs, "_cache", _TIERED)
    tight = [c["id"] for c in mcs.cards_for_archetype("urban_professional", cap=99, budget_tier="tight")]
    loose = [c["id"] for c in mcs.cards_for_archetype("urban_professional", cap=99, budget_tier="loose")]
    assert "middle-tier" not in tight and "middle-tier" in loose
    loose_learner = [c["id"] for c in mcs.cards_for_archetype("learner", cap=99, budget_tier="loose")]
    assert "tight-tier" not in loose_learner and "class-blind" in loose_learner


def test_no_tier_means_no_economic_filtering(monkeypatch):
    # Policy casts carry no budget_tier: binding must be tier-blind (back-compat).
    monkeypatch.setattr(mcs, "_cache", _TIERED)
    assert "tight-tier" in [c["id"] for c in mcs.cards_for_archetype("learner", cap=99)]


def _learner(age, poverty):
    return {"actor_archetype": "learner", "ghs_role": "learner", "age": age,
            "circumstances": [{"field": "lived_poverty", "value": poverty}]}


def test_attach_follows_the_persona_record_not_the_tier_label(monkeypatch):
    # Cards bind by situation (applies_when on the persona's own record): a card about
    # learners who go short reaches a sixteen-year-old whose record says so, not one
    # whose record says they are comfortable.
    card = {**_TIERED[2], "id": "goes-short", "applies_when": [
        {"ghs_role": ["learner"], "lived_poverty": ["moderate", "high"]}]}
    monkeypatch.setattr(mcs, "_cache", [card])
    out = mcs.attach_research_context(_learner(16, "none"), cap=99)
    assert not out.get("research_citations")
    out = mcs.attach_research_context(_learner(16, "high"), cap=99)
    assert [c["card_id"] for c in out["research_citations"]] == ["goes-short"]


def test_attach_adds_both_keys_when_bound():
    profile = {"actor_archetype": "communal_farmer", "name": "Test",
               "farm_market_orientation": "subsistence", "geotype": "Traditional"}
    out = mcs.attach_research_context(profile)
    assert out["research_context"]
    assert out["research_citations"]
    for cit in out["research_citations"]:
        assert cit["card_id"] and isinstance(cit["citation"], list)


def test_fintech_card_requires_bank_access_and_regular_internet_use():
    def profile(bank, internet):
        return {"circumstances": [
            {"field": "owns_bank_account", "value": bank},
            {"field": "internet_use", "value": internet},
        ]}

    no_bank = [c["id"] for c in mcs.cards_for_persona(profile("none", "daily"))]
    banked = [c["id"] for c in mcs.cards_for_persona(profile("own", "daily"))]
    assert "fintech-adoption-trust" not in no_bank
    assert "fintech-adoption-trust" in banked


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        setup_function(fn)
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")


# ── claims scoped by what the pitch is about (`about`) ─────────────────────

def _seat(card_id, **facts):
    """A profile bound to one card, with the facts its gate reads."""
    rows = [{"field": k, "value": v} for k, v in facts.pop("circumstances", {}).items()]
    return {"research_citations": [{"card_id": card_id}], "circumstances": rows, **facts}


def _claims(profile, question):
    cards = mcs.cards_for_question(profile, question) or []
    return {cl["chain_id"] for c in cards for cl in c["claims"]}, {c["id"] for c in cards}


_UNINSURED_WOMAN = dict(geotype="Urban", medical_aid="False", gender="Female",
                        circumstances={"lived_poverty": "low"})
_BLACK_TAX_PAYER = dict(race="African/Black", employment_status="Employed",
                        circumstances={"lived_poverty": "low"})


def test_hiv_disclosure_claims_stay_off_a_diabetes_pitch():
    claims, _ = _claims(_seat("paying-for-care-without-medical-aid-sa", **_UNINSURED_WOMAN),
                        "A clinic that helps you manage diabetes, R150 a visit.")
    assert claims and not claims & {"C1", "C2"}


def test_hiv_disclosure_claims_come_with_an_hiv_treatment_pitch():
    claims, _ = _claims(_seat("paying-for-care-without-medical-aid-sa", **_UNINSURED_WOMAN),
                        "Collect your ARVs at a pharmacy near work instead of the clinic, R50.")
    assert "C1" in claims


def test_the_delivery_claim_comes_with_a_home_delivery_pitch():
    claims, _ = _claims(_seat("paying-for-care-without-medical-aid-sa", **_UNINSURED_WOMAN),
                        "Your monthly medication delivered to your home for R30.")
    assert "C2" in claims


def test_black_tax_stays_off_a_trivial_pitch():
    _, cards = _claims(_seat("black-tax-obligation-sa", **_BLACK_TAX_PAYER),
                       "A shared ride to the taxi rank for R15 a trip, so you pay less.")
    assert "black-tax-obligation-sa" not in cards


def test_black_tax_speaks_on_funeral_cover_for_family():
    claims, _ = _claims(_seat("black-tax-obligation-sa", **_BLACK_TAX_PAYER),
                        "Funeral cover for R80 a month that covers your parents too.")
    assert {"C1", "C5"} <= claims


def test_black_tax_speaks_on_spending_on_yourself():
    claims, _ = _claims(_seat("black-tax-obligation-sa", **_BLACK_TAX_PAYER),
                        "A luxury weekend holiday package you pay for once.")
    assert "C2" in claims and "C5" not in claims


def test_the_reader_can_add_a_claim_its_words_missed(monkeypatch):
    # "starting a family" names none of the claim's words; the typed reader, when on,
    # can still say the pitch involves reproductive health.
    monkeypatch.setattr(mcs, "claims_touched",
                        lambda q, cards=None: {"paying-for-care-without-medical-aid-sa#C5"})
    claims, _ = _claims(_seat("paying-for-care-without-medical-aid-sa", **_UNINSURED_WOMAN),
                        "A clinic visit to talk about starting a family, R150.")
    assert "C5" in claims


def test_a_comfortable_renter_hears_only_the_security_claim():
    renter = dict(geotype="Urban", circumstances={"lived_poverty": "low", "housing_tenure": "rent"})
    owner = dict(geotype="Urban", circumstances={"lived_poverty": "low", "housing_tenure": "own"})
    pitch = "Armed response and a guard at the gate for R450 a month, if the rates and water fail too."
    assert _claims(_seat("going-private-when-the-state-fails-sa", **renter), pitch)[0] == {"C4"}
    assert _claims(_seat("going-private-when-the-state-fails-sa", **owner), pitch)[0] == {"C1", "C2", "C3", "C4"}


# ── borrowed_when: a close group gets the card, marked as borrowed ──────────

def _borrow_card():
    card = dict(next(c for c in mcs.load_cards() if c["id"] == "youth-waithood-identity"))
    card.update(applies_when=[{"ghs_role": ["learner"]}],
                borrowed_when=[{"ghs_role": ["guardian_parent"], "geotype": ["Urban"]}],
                borrowed_from="Heard from learners like your child")
    return card


def test_the_studied_group_gets_the_card_directly():
    card = _borrow_card()
    facts = {"ghs_role": "learner"}
    view = mcs.narrowed_to(card, facts)
    assert mcs.situation_match_strength(card, facts) >= 1
    assert "nearby group" not in mcs.render_research_context([view])


def test_a_close_group_gets_it_marked_borrowed_and_ranked_lower():
    card = _borrow_card()
    facts = {"ghs_role": "guardian_parent", "geotype": "Urban"}
    view = mcs.narrowed_to(card, facts)
    assert 0 < mcs.situation_match_strength(card, facts) < 1
    assert "heard from a nearby group" in mcs.render_research_context([view])


def test_someone_in_neither_gate_gets_nothing():
    assert mcs.situation_match_strength(_borrow_card(), {"ghs_role": "guardian_parent", "geotype": "Farms"}) == 0


def test_a_rural_teen_on_an_ordinary_clinic_pitch_hears_no_sexual_health_claim():
    teen = dict(geotype="Traditional", age=17)
    claims, cards = _claims(_seat("youth-clinic-candidacy-sa", **teen),
                            "A nurse you can see the same day for R150 a visit, no queue.")
    assert "youth-clinic-candidacy-sa" in cards
    assert {"C1", "C3", "C5"} <= claims and not claims & {"C2", "C4"}
