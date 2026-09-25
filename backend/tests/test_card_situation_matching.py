"""Cards bind by the persona's own record (applies_when), not by job-type label.

LLM-off. Loads the service by path (no app package, no API key).
"""

import importlib.util
import json
import os

HERE = os.path.dirname(__file__)
SERVICES = os.path.normpath(os.path.join(HERE, "..", "app", "services"))


def _load():
    spec = importlib.util.spec_from_file_location(
        "mcs_situation_under_test", os.path.join(SERVICES, "mechanism_card_service.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mcs = _load()


def setup_function(_fn):
    mcs._cache = None
    os.environ.pop("RESEARCH_CONTEXT_ENABLED", None)


def _person(archetype, **facts):
    circumstances = {"lived_poverty", "owns_vehicle", "owns_computer", "internet_use",
                     "went_without_care", "owns_bank_account", "money_decision"}
    rows = [{"field": k, "value": v} for k, v in facts.items() if k in circumstances]
    top = {k: v for k, v in facts.items() if k not in circumstances}
    return {"actor_archetype": archetype, "circumstances": rows, **top}


def _ids(profile):
    return [c["id"] for c in mcs.cards_for_persona(profile)]


def _claims(*texts):
    return [{"text": t, "needs": []} for t in texts]


def _texts(card):
    return [c["text"] for c in card["claims"]]


# ── the cases that motivated this ──────────────────────────────────────────

def test_struggling_professional_no_longer_gets_the_middle_class_card():
    # Itumeleng Phiri in the clinic panel: professional label, often short of food.
    p = _person("urban_professional", race="African/Black", employment_status="Employed",
                lived_poverty="high", owns_vehicle="none", owns_computer="none")
    assert "middle-class-status-identity" not in _ids(p)


def test_better_off_household_now_gets_it():
    # No card listed "affluent_urban_household", so all 30 of them got nothing.
    p = _person("affluent_urban_household", race="African/Black", employment_status="Employed",
                lived_poverty="none", owns_vehicle="own")
    assert "middle-class-status-identity" in _ids(p)


# ── rule semantics ─────────────────────────────────────────────────────────

CARD = {"id": "t", "claims": _claims("m"), "applies_when": [
    {"owns_vehicle": ["none"], "geotype": ["Traditional"]},
    {"time_to_health_facility": ["90 minutes and more"]},
]}


def test_all_fields_in_a_clause_must_hold():
    facts = mcs.situation_facts(_person("x", owns_vehicle="none", geotype="Urban"))
    assert mcs.situation_match_strength(CARD, facts) == 0


def test_any_clause_is_enough():
    facts = mcs.situation_facts(_person("x", time_to_health_facility="90 minutes and more"))
    assert mcs.situation_match_strength(CARD, facts) == 1


def test_missing_data_never_hands_out_a_card():
    assert mcs.situation_match_strength(CARD, mcs.situation_facts(_person("x"))) == 0


def test_age_becomes_a_band():
    assert mcs.situation_facts({"age": 19})["age_band"] == "15-24"
    assert mcs.situation_facts({"age": 61})["age_band"] == "60+"
    assert "age_band" not in mcs.situation_facts({"age": None})


def test_rules_can_name_province_and_education():
    card = {"id": "t", "claims": _claims("m"),
            "applies_when": [{"province": ["Limpopo"], "education": ["Tertiary"]}]}
    near = mcs.situation_facts({"province": "Limpopo", "education": "Tertiary"})
    far = mcs.situation_facts({"province": "Gauteng", "education": "Tertiary"})
    assert mcs.situation_match_strength(card, near) == 2
    assert mcs.situation_match_strength(card, far) == 0


def test_closest_fit_comes_first_and_no_cap_by_default():
    cards = [
        {"id": "broad", "claims": _claims("m"), "applies_when": [{"geotype": ["Urban"]}]},
        {"id": "close", "claims": _claims("m"),
         "applies_when": [{"geotype": ["Urban"], "owns_vehicle": ["none"]}]},
        {"id": "third", "claims": _claims("m"), "applies_when": [{"owns_vehicle": ["none"]}]},
    ]
    mcs._cache = cards
    ids = _ids(_person("x", geotype="Urban", owns_vehicle="none"))
    assert ids[0] == "close"
    assert set(ids) == {"broad", "close", "third"}


def test_citations_keep_every_fit_while_the_rendered_block_stays_capped():
    cards = [{"id": f"c{i}", "citation": [f"Paper {i}"], "claims": _claims(f"when x, y{i}"),
              "applies_when": [{"geotype": ["Urban"]}]} for i in range(4)]
    mcs._cache = cards
    out = mcs.attach_research_context({"geotype": "Urban"}, cap=2)
    assert len(out["research_citations"]) == 4
    assert out["research_context"].count("From ") == 2


MIXED = {"id": "mixed", "topic_tags": ["bank"], "applies_when": [{"geotype": ["Urban"]}],
         "claims": [{"text": "for everyone", "needs": [], "vocabulary": ["shared word"]},
                    {"text": "for the poor", "needs": [{"lived_poverty": ["high"]}],
                     "vocabulary": ["poor word"]}]}


def test_a_scoped_claim_reaches_only_the_people_it_describes():
    mcs._cache = [MIXED]
    secure = mcs.cards_for_persona(_person("x", geotype="Urban", lived_poverty="none"))
    poor = mcs.cards_for_persona(_person("x", geotype="Urban", lived_poverty="high"))
    assert _texts(secure[0]) == ["for everyone"]
    assert _texts(poor[0]) == ["for everyone", "for the poor"]


def test_a_left_out_claim_takes_its_vocabulary_with_it():
    mcs._cache = [MIXED]
    secure = mcs.cards_for_persona(_person("x", geotype="Urban", lived_poverty="none"))
    block = mcs.render_research_context(secure)
    assert "shared word" in block
    assert "poor word" not in block


def test_a_card_with_every_claim_scoped_out_is_not_handed_out():
    mcs._cache = [{**MIXED, "claims": [MIXED["claims"][1]]}]
    assert _ids(_person("x", geotype="Urban", lived_poverty="none")) == []


def test_the_prompt_gate_narrows_claims_too():
    mcs._cache = [MIXED]
    profile = {**_person("x", geotype="Urban", lived_poverty="none"),
               "research_citations": [{"card_id": "mixed"}]}
    used = mcs.cards_for_question(profile, "a bank account")
    assert _texts(used[0]) == ["for everyone"]


def test_middle_class_people_do_not_get_the_removed_income_insecure_claim():
    def claims(poverty):
        p = _person("urban_professional", race="African/Black", employment_status="Employed",
                    lived_poverty=poverty, owns_vehicle="own")
        return " ".join(_texts(next(c for c in mcs.cards_for_persona(p)
                                    if c["id"] == "middle-class-status-identity")))
    assert "income-insecure" not in claims("none")
    assert "Black Tax" in claims("none")
    assert "income-insecure" not in claims("low")


def test_learner_studies_reach_parents_only_as_borrowed():
    # The learners were studied, not their parents: a parent hears it as what
    # learners like their child say, marked as borrowed.
    card = {c["id"]: c for c in mcs.load_cards()}["learner-motivation-grade12-sa"]
    learner = {"ghs_role": "learner"}
    parent = {"ghs_role": "guardian_parent", "learner_fee_bands": "No fees"}
    assert mcs.situation_match_strength(card, learner) >= 1
    assert "_borrowed" not in mcs.narrowed_to(card, learner)
    assert 0 < mcs.situation_match_strength(card, parent) < 1
    assert mcs.narrowed_to(card, parent)["_borrowed"] is True
    assert mcs.situation_match_strength(card, {"ghs_role": "guardian_parent",
                                               "learner_fee_bands": "R20 001–R40 000 per year"}) == 0


def test_a_card_without_rules_falls_back_to_its_label():
    mcs._cache = [{"id": "legacy", "claims": _claims("m"), "segment_tags": ["learner"]}]
    assert _ids({"actor_archetype": "learner"}) == ["legacy"]
    assert _ids({"actor_archetype": "civic_moderate"}) == []


# ── the shipped set ────────────────────────────────────────────────────────

def test_every_shipped_card_says_who_it_describes():
    known = set(mcs._SITUATION_FIELDS) | {
        "age_band", "youth_age_band", "lived_poverty", "owns_vehicle", "owns_computer", "owns_bank_account",
        "internet_use", "money_decision", "went_without_care", "electricity_reliability",
        "health_service_satisfaction", "health_authority_trust",
        # GHS household circumstances (#112)
        "housing_tenure", "solar_panels", "home_security", "water_interruptions",
        "water_backup", "transport_to_work", "recycles", "learner_fee_bands"}
    for card in mcs.load_cards():
        rules = card.get("applies_when")
        assert rules, card["id"]
        for clause in rules + (card.get("borrowed_when") or []) + [c for claim in card["claims"] for c in claim["needs"]]:
            assert clause and set(clause) <= known, (card["id"], clause)


def test_every_shipped_claim_with_its_own_rule_reaches_someone():
    # A rule no one in the library meets drops the claim from every prompt, silently.
    path = os.path.join(HERE, "..", "app", "data", "persona_library", "personas.json")
    with open(path, encoding="utf-8") as fh:
        everyone = [mcs.situation_facts(p) for p in json.load(fh)["personas"]]
    for card in mcs.load_cards():
        fits = [f for f in everyone if mcs.situation_match_strength(card, f)]
        for claim in card["claims"]:
            if claim["needs"]:
                assert any(mcs._clause_strength(claim["needs"], f) for f in fits), \
                    (card["id"], claim["text"][:60])


# ── A claim reaches only the group its study was about ─────────────────────────
# youth-clinic-privacy-stigma-sa rests on two studies: young women 18-24 (Nyblade,
# claims 0-2), and school learners 16+, boys and girls (Strauss, claim 4). Claim 3
# draws on both. Without per-claim `needs`, a 16-year-old boy was told nurses scold
# him like a daughter for asking about contraception, and 15-year-olds got claims from
# studies that recruited from 16.

YOUTH = "youth-clinic-privacy-stigma-sa"


def _youth_claims(profile):
    card = next(c for c in mcs.load_cards() if c["id"] == YOUTH)
    view = mcs.narrowed_to(card, mcs.situation_facts(profile)) \
        if mcs.situation_match_strength(card, mcs.situation_facts(profile)) else None
    if not view:
        return None
    kept = {c["text"] for c in view["claims"]}
    return [i for i, c in enumerate(card["claims"]) if c["text"] in kept]


def test_youth_age_band_splits_where_youth_studies_recruit():
    assert [mcs._youth_age_band(a) for a in (15, 16, 17, 18, 24, 25)] == \
        ["under-16", "16-17", "16-17", "18-24", "18-24", "25+"]
    # The coarse band the older cards use is unchanged.
    assert mcs._age_band(15) == mcs._age_band(24) == "15-24"


def test_young_woman_gets_the_young_women_claims():
    # Claims 0-3. The HIV-testing claim comes from the learner study, so not for her.
    assert _youth_claims({"gender": "Female", "age": 21}) == [0, 1, 2, 3]


def test_every_young_person_the_card_fits_hears_all_of_it():
    # Rebuilt from young people's own accounts across three studies (staff views
    # left out), so its findings are not split by which study a claim came from.
    assert _youth_claims({"gender": "Female", "age": 18, "ghs_role": "learner"}) == [0, 1, 2, 3]
    assert _youth_claims({"gender": "Male", "age": 16, "ghs_role": "learner"}) == [0, 1, 2, 3]


def test_under_16_gets_nothing():
    assert _youth_claims({"gender": "Female", "age": 15, "ghs_role": "learner"}) is None


def test_young_man_not_in_school_gets_nothing():
    assert _youth_claims({"gender": "Male", "age": 20}) is None


def test_youth_card_stays_off_for_a_general_clinic_pitch():
    card = next(c for c in mcs.load_cards() if c["id"] == YOUTH)
    assert not mcs.topic_matches(card, "Book a nurse visit at the clinic on WhatsApp and "
                                       "get your chronic meds delivered.")
    assert mcs.topic_matches(card, "A free HIV testing van at high schools.")
