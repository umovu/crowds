"""The household pass fills children at school and medical aid from matched real people.

What these fix:

  * who counts as a parent, a grandparent guardian or neither, from GHS relations
  * a persona's own measured answer is never overwritten
  * the facts written for one persona are coherent, because they come off one donor
  * the grade says how far to trust one person, and a likely parent is never strong
  * the seats a group gets match what its members' own pools say
  * the same library gives the same answer every run
  * cards and pickers read the new rows, and a measured value still wins

LLM-free. Runs on a small synthetic GHS frame, so it needs no licensed microdata.
The accuracy test on the real survey is `add_ghs_household.py --validate`.
"""
import importlib.util
import os
import sys

import pandas as pd
import pytest

HERE = os.path.dirname(__file__)
SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, SCRIPTS)

import add_ghs_household as hh  # noqa: E402
import ghs_adapter as g  # noqa: E402


def _ctx(n, child=False, grandchild=False, fees=()):
    return {"learner_count": n, "any_child_of_head": child,
            "any_grandchild_of_head": grandchild, "fee_bands": list(fees)}


# ── Who counts as what ───────────────────────────────────────────────────────

def test_no_learners_means_none_whatever_the_relation():
    assert hh.learner_relation(g._REL_HEAD, 40, None) == "none"
    assert hh.learner_relation(g._REL_HEAD, 40, _ctx(0, child=True)) == "none"


def test_head_or_spouse_with_the_heads_child_at_school_is_a_parent():
    assert hh.learner_relation(g._REL_HEAD, 40, _ctx(1, child=True)) == "parent"
    assert hh.learner_relation(g._REL_SPOUSE, 38, _ctx(2, child=True)) == "parent"


def test_head_with_only_grandchildren_at_school_is_a_grandparent():
    assert hh.learner_relation(g._REL_HEAD, 66, _ctx(1, grandchild=True)) == "grandparent"


def test_a_mother_in_her_mothers_house_is_a_likely_parent():
    # She is the head's child; her own child is the head's grandchild.
    assert hh.learner_relation(g._REL_CHILD, 29, _ctx(1, grandchild=True)) == "likely_parent"


def test_an_older_adult_child_is_not_read_as_the_likely_parent():
    assert hh.learner_relation(g._REL_CHILD, 55, _ctx(1, grandchild=True)) == "other_adult"


def test_a_lodger_in_a_house_with_learners_is_another_adult():
    assert hh.learner_relation(9.0, 30, _ctx(2, child=True)) == "other_adult"


# ── Fee bands ────────────────────────────────────────────────────────────────

def test_the_dearest_fee_band_is_the_one_kept():
    bands = ["No fees", "R101–R200 per year", "R20 001–R40 000 per year", "R1 001–R2 000 per year"]
    assert hh._top_fee(bands) == "R20 001–R40 000 per year"
    assert hh._top_fee(["No fees"]) == "No fees"
    assert hh._top_fee([]) is None


def test_more_than_r80000_outranks_every_bounded_band():
    assert hh._fee_rank("More than R80 000 per year") > hh._fee_rank("R40 001–R80 000 per year")


# ── A synthetic GHS pool ─────────────────────────────────────────────────────

def _person(uqnr, age, relation, learners="0", fee=None, med=False, gender="Female",
            province="Gauteng", geo="Urban", race="African/Black", wgt=100.0,
            employment="Employed", hardship="never"):
    return {"uqnr": uqnr, "age": age, "person_wgt": wgt, "province": province,
            "gender": gender, "race": race, "geo": geo, "learner_relation": relation,
            "learners": learners, "fee_band": fee, "medical_aid": med,
            "employment": employment, "hardship": hardship}


def _pool():
    """120 women aged 30-40 in urban Gauteng: 60% parents, 40% no learners.
    Parents pay fees and have medical aid, so a coherent donor is checkable."""
    rows = []
    for i in range(72):
        rows.append(_person(f"p{i}", 30 + i % 11, "parent", learners="2",
                            fee="R20 001–R40 000 per year", med=True))
    for i in range(48):
        rows.append(_person(f"n{i}", 30 + i % 11, "none", learners="0", fee=None, med=False))
    return pd.DataFrame(rows)


def _persona(pid, **kw):
    base = {"id": pid, "name": f"P{pid}", "age": 35, "gender": "Female",
            "province": "Gauteng", "geotype": "Urban", "race": "African/Black"}
    base.update(kw)
    return base


# ── Coherence and never overwriting ──────────────────────────────────────────

def test_every_fact_for_one_persona_comes_from_one_donor():
    personas = [_persona(i) for i in range(20)]
    for p, r in zip(personas, hh.assign(personas, _pool())):
        f = {row["field"]: row["value"] for row in hh.rows_for(p, r)}
        if f.get("ghs_role") == "guardian_parent":
            assert f["learners_in_household"] == "2"
            assert f["learner_fee_bands"] == "R20 001–R40 000 per year"
            assert f["medical_aid"] == "True"
        else:
            assert f["learners_in_household"] == "0"
            assert "learner_fee_bands" not in f
            assert f["medical_aid"] == "False"


def test_a_measured_answer_is_never_overwritten():
    measured = _persona(1, learners_in_household=3, ghs_role="guardian_parent",
                        learner_fee_bands=["No fees per year"], medical_aid=False)
    result = hh.assign([measured], _pool())[0]
    assert hh.rows_for(measured, result) == []


def test_only_the_missing_fact_is_filled():
    # Measured medical aid, unknown children: only the children rows are written.
    p = _persona(1, medical_aid=True)
    fields = {row["field"] for row in hh.rows_for(p, hh.assign([p], _pool())[0])}
    assert "medical_aid" not in fields
    assert "learners_in_household" in fields


def test_learners_and_minors_are_not_targeted():
    people = [_persona(1, age=16), _persona(2, ghs_role="learner", age=19), _persona(3, age=35)]
    assert [p["id"] for p in hh._targets(people)] == [3]


def test_every_row_says_where_it_came_from():
    p = _persona(1)
    for row in hh.rows_for(p, hh.assign([p], _pool())[0]):
        assert row["source"] == hh.SOURCE
        assert row["source"].split(":")[0] == "ghs_2025"  # resolves to a known survey
        assert row["pool"] > 0 and 0.0 <= row["share"] <= 1.0
        assert row["grade"] in ("strong", "weak")


# ── Grades ───────────────────────────────────────────────────────────────────

def test_strong_needs_a_close_match_and_a_clear_majority():
    assert hh._grade("prov_geo_race_sex_age", 0.60) == "strong"
    assert hh._grade("prov_geo_race_sex_age", 0.59) == "weak"
    assert hh._grade("age", 0.95) == "weak"          # lost sex: never strong
    assert hh._grade("population", 0.95) == "weak"


def test_a_likely_parent_is_always_weak():
    assert hh._grade("prov_geo_race_sex_age", 0.99, "likely_parent") == "weak"


# ── Totals ───────────────────────────────────────────────────────────────────

def test_seats_always_sum_to_the_group():
    for n in (1, 7, 12, 31):
        assert sum(hh.quotas({"a": 0.6, "b": 0.3, "c": 0.1}, n).values()) == n


def test_a_group_gets_the_share_its_own_pools_say():
    # 60% of the pool are parents, so 20 personas like them get 12 parent seats.
    personas = [_persona(i) for i in range(20)]
    drawn = [r["donor"]["learner_relation"] for r in hh.assign(personas, _pool())]
    assert drawn.count("parent") == 12
    assert drawn.count("none") == 8


def test_the_same_library_gives_the_same_answer():
    personas = [_persona(i) for i in range(15)]
    first = [r["donor"]["uqnr"] for r in hh.assign(personas, _pool())]
    again = [r["donor"]["uqnr"] for r in hh.assign(personas, _pool())]
    assert first == again


def test_a_rare_persona_falls_back_to_a_looser_rung():
    odd = _persona(1, province="Limpopo")  # nobody in the pool is from Limpopo
    pool, quality = hh.match_pool(_pool(), odd)
    assert quality != "prov_geo_race_sex_age"
    assert len(pool) >= hh.MIN_POOL


# ── Sanity ───────────────────────────────────────────────────────────────────

def test_sanity_catches_a_young_grandparent_and_a_childless_guardian():
    young = _persona(1, age=25)
    rows = [{"field": "ghs_role", "value": "gogo_guardian"},
            {"field": "learners_in_household", "value": "0"}]
    problems = hh._sanity([young], [rows])
    assert any("grandparent guardian at 25" in p for p in problems)
    assert any("guardian with no learners" in p for p in problems)


# ── Readers see it, and measured still wins ──────────────────────────────────

def _load_mcs():
    path = os.path.join(HERE, "..", "app", "services", "mechanism_card_service.py")
    spec = importlib.util.spec_from_file_location("mcs_household_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cards_read_an_imputed_parent():
    mcs = _load_mcs()
    persona = {"age": 35, "circumstances": [
        {"field": "ghs_role", "value": "guardian_parent", "source": hh.SOURCE},
        {"field": "learners_in_household", "value": "2", "source": hh.SOURCE}]}
    card = {"applies_when": [{"ghs_role": ["guardian_parent"]}]}
    assert mcs.situation_match_strength(card, mcs.situation_facts(persona)) > 0


def test_a_measured_value_beats_an_imputed_row():
    mcs = _load_mcs()
    persona = {"ghs_role": "gogo_guardian", "circumstances": [
        {"field": "ghs_role", "value": "guardian_parent", "source": hh.SOURCE}]}
    assert mcs.situation_facts(persona)["ghs_role"] == "gogo_guardian"


# ── The shared fact reader: measured first, imputed as fallback ──────────────
# Registering these four as circumstance fields once made fact_value read ONLY the
# rows, so the 31 measured guardians lost their fee bands in the room picker, and an
# imputed band came back as a string that list() split into letters.

def test_fact_value_prefers_the_measured_answer():
    from app.models.persona import fact_value
    persona = {"learner_fee_bands": ["R1–R100 per year"], "medical_aid": False,
               "circumstances": [
                   {"field": "learner_fee_bands", "value": "No fees", "source": hh.SOURCE},
                   {"field": "medical_aid", "value": "True", "source": hh.SOURCE}]}
    assert fact_value(persona, "learner_fee_bands") == ["R1–R100 per year"]
    assert fact_value(persona, "medical_aid") is False


def test_fact_value_falls_back_to_the_imputed_row():
    from app.models.persona import fact_value
    persona = {"circumstances": [
        {"field": "ghs_role", "value": "guardian_parent", "source": hh.SOURCE}]}
    assert fact_value(persona, "ghs_role") == "guardian_parent"


def test_the_picker_reads_an_imputed_fee_band_whole():
    from app.services import panel_service as ps
    persona = {"circumstances": [
        {"field": "learner_fee_bands", "value": "R20 001–R40 000 per year", "source": hh.SOURCE}]}
    assert ps._fee_bands(persona) == ["R20 001–R40 000 per year"]
    assert ps._fee_tier(persona) == "high_fee"
    assert ps._pays_school_fees(persona)


def test_the_picker_still_reads_a_measured_guardians_bands():
    from app.services import panel_service as ps
    persona = {"learner_fee_bands": ["No fees", "R201–R300 per year"]}
    assert ps._fee_bands(persona) == ["No fees", "R201–R300 per year"]
    assert ps._fee_tier(persona) == "low_fee"


# ── The room picker's parent groups ──────────────────────────────────────────
# "Parents & guardians" used to mean actor_archetype == guardian_parent, a label only
# the 31 people built as guardians carry. It now means anyone known to raise a
# learner, measured or filled, and a room seats the most certain first.

def _row(field, value, grade):
    return {"field": field, "value": value, "source": hh.SOURCE, "grade": grade}


def _parents():
    measured = {"id": "m", "actor_archetype": "guardian_parent",
                "learner_fee_bands": ["R20 001–R40 000 per year"]}
    strong = {"id": "s", "actor_archetype": "urban_professional", "circumstances": [
        _row("ghs_role", "guardian_parent", "strong"),
        _row("learner_fee_bands", "R40 001–R80 000 per year", "strong")]}
    weak = {"id": "w", "actor_archetype": "civic_moderate", "circumstances": [
        _row("ghs_role", "guardian_parent", "weak"),
        _row("learner_fee_bands", "R8 001–R12 000 per year", "weak")]}
    gogo = {"id": "g", "actor_archetype": "grant_dependent_survivor", "circumstances": [
        _row("ghs_role", "gogo_guardian", "strong")]}
    nobody = {"id": "n", "actor_archetype": "unemployed_youth", "circumstances": [
        _row("learners_in_household", "0", "weak")]}
    return measured, strong, weak, gogo, nobody


def test_certainty_reads_measured_then_filled():
    from app.services import panel_service as ps
    measured, strong, weak, gogo, nobody = _parents()
    assert ps.guardian_certainty(measured) == "measured"
    assert ps.guardian_certainty({"ghs_role": "gogo_guardian"}) == "measured"
    assert ps.guardian_certainty(strong) == "strong"
    assert ps.guardian_certainty(weak) == "weak"
    assert ps.guardian_certainty(nobody) is None
    # A filled row with no grade is not trusted as strong.
    assert ps.guardian_certainty({"circumstances": [
        {"field": "ghs_role", "value": "guardian_parent"}]}) == "weak"


def test_the_gogo_group_takes_grandparents_only():
    from app.services import panel_service as ps
    measured, strong, weak, gogo, nobody = _parents()
    group = ps.SEGMENTS["gogo_guardians"]["predicate"]
    assert [p["id"] for p in (measured, strong, weak, gogo, nobody) if group(p)] == ["g"]


def test_parents_group_now_holds_filled_parents():
    from app.services import panel_service as ps
    group = ps.SEGMENTS["guardians"]["predicate"]
    assert [p["id"] for p in _parents() if group(p)] == ["m", "s", "w", "g"]


def test_high_fee_parents_include_a_filled_fee_payer():
    from app.services import panel_service as ps
    group = ps.SEGMENTS["guardians_high_fee"]["predicate"]
    assert {p["id"] for p in _parents() if group(p)} == {"m", "s", "w"}


def test_most_certain_are_seated_first():
    from app.services import panel_service as ps
    measured, strong, weak, gogo, nobody = _parents()
    library = ps._FilteredLibrary([weak, strong, measured])
    for seed in range(5):
        cast, _ = ps._mixed_cast(["guardians"], 2, seed, None, library)
        assert [p["id"] for p in cast] == ["m", "s"]


def test_a_group_without_a_certainty_rule_draws_exactly_as_before():
    from app.services import panel_service as ps
    pool = [{"id": i} for i in range(10)]
    assert ps._most_certain_first(pool, ps.SEGMENTS["unemployed"]) is pool


def test_a_room_reports_how_sure_its_parents_are():
    from app.services import panel_service as ps
    assert ps.parent_certainty_counts(list(_parents())) == {
        "measured": 1, "strong": 2, "weak": 1}
    assert ps.parent_certainty_counts([_parents()[4]]) == {}



# ── Hardship and work pick the household, not whether there is a learner ────
# School fees follow income, and most personas carry none. Matching the DONOR on
# food hardship and employment cut high-fee draws into below-median-income homes
# from 42% to 36% on the validation (real: 18%), with the share living with a
# learner unchanged, because that is still decided on demographics alone.

def test_ghs_hunger_answers_become_two_levels():
    assert hh.ghs_hardship(1) == "never"
    assert {hh.ghs_hardship(c) for c in (2, 3, 4, 5)} == {"some"}
    assert hh.ghs_hardship(6) is None and hh.ghs_hardship(9) is None


def test_lived_poverty_crosses_to_the_same_two_levels():
    assert hh.persona_hardship({"lived_poverty": "none"}) == "never"
    for band in ("low", "moderate", "high"):
        assert hh.persona_hardship({"lived_poverty": band}) == "some"
    assert hh.persona_hardship({"circumstances": [
        {"field": "lived_poverty", "value": "none"}]}) == "never"
    assert hh.persona_hardship({}) is None


def _split_pool():
    """Parents in two kinds of household: comfortable earners paying high fees, and
    unemployed households that go short of food and pay none. Plus non-parents."""
    rows = []
    for i in range(40):
        rows.append(_person(f"rich{i}", 30 + i % 11, "parent", learners="1",
                            fee="R20 001–R40 000 per year", med=True,
                            employment="Employed", hardship="never"))
    for i in range(40):
        rows.append(_person(f"poor{i}", 30 + i % 11, "parent", learners="2",
                            fee="No fees", med=False,
                            employment="Unemployed", hardship="some"))
    for i in range(40):
        rows.append(_person(f"none{i}", 30 + i % 11, "none", employment="Employed",
                            hardship="never"))
    return pd.DataFrame(rows)


def _parent_donors(**facts):
    people = [_persona(i, **facts) for i in range(12)]
    donors = [r["donor"] for r in hh.assign(people, _split_pool())
              if r["donor"]["learner_relation"] == "parent"]
    assert donors, "the pool is two-thirds parents, so some seats must be parents"
    return donors


def test_a_comfortable_earner_draws_a_comfortable_household():
    for donor in _parent_donors(employment_status="Employed", lived_poverty="none"):
        assert donor["uqnr"].startswith("rich")
        assert donor["fee_band"] == "R20 001–R40 000 per year"


def test_a_hungry_jobseeker_draws_a_household_like_theirs():
    for donor in _parent_donors(employment_status="Unemployed", lived_poverty="high"):
        assert donor["uqnr"].startswith("poor")
        assert donor["fee_band"] == "No fees"


def test_hardship_does_not_move_the_share_living_with_a_learner():
    # Same demographics, opposite hardship: the parent seats are the same.
    rich = [_persona(i, employment_status="Employed", lived_poverty="none") for i in range(15)]
    poor = [_persona(i, employment_status="Unemployed", lived_poverty="high") for i in range(15)]
    count = lambda people: sum(r["donor"]["learner_relation"] == "parent"
                               for r in hh.assign(people, _split_pool()))
    assert count(rich) == count(poor)


def test_a_persona_without_the_fact_skips_the_rungs_that_need_it():
    pool, quality = hh.match_pool(_split_pool(), _persona(1), hh._DONOR_RUNGS)
    assert "hard" not in quality and "emp" not in quality


# ── Filled facts reach the persona's prompt ──────────────────────────────────
# The four fields had no prompt wording as circumstance rows, so persona_facts
# skipped them: they steered cards and the room picker, and the persona itself
# never heard them. Medical aid reached 147 of 375 prompts on a clinic pitch
# (only the measured ones); now 363.

def _facts(persona, pitch):
    from app.services import persona_facts
    return {f["field"]: f["line"] for f in persona_facts.picked_facts(
        {"source_entity_type": "library_persona", **persona}, pitch)}


def test_filled_facts_are_said_to_the_persona():
    persona = {"circumstances": [
        _row("learners_in_household", "2", "weak"),
        _row("ghs_role", "guardian_parent", "weak"),
        _row("learner_fee_bands", "R20 001–R40 000 per year", "weak"),
        _row("medical_aid", "True", "strong")]}
    school = _facts(persona, "An app for parents about their child's school fees.")
    assert school["learners_in_household"] == "Learners at school in your household: 2."
    assert school["ghs_role"] == "You are a parent with children at school."
    assert "R20 001–R40 000 per year" in school["learner_fee_bands"]
    health = _facts(persona, "A clinic nurse visit, no medical aid needed.")
    assert health["medical_aid"] == "You have medical aid."


def test_no_children_is_said_too_so_none_are_invented():
    facts = _facts({"circumstances": [_row("learners_in_household", "0", "weak")]},
                   "A new phone contract.")
    assert facts["learners_in_household"] == "Learners at school in your household: 0."


def test_a_measured_answer_is_said_instead_of_the_filled_one():
    from app.services import persona_facts
    persona = {"source_entity_type": "library_persona", "medical_aid": False,
               "circumstances": [_row("medical_aid", "True", "strong")]}
    lines = [f["line"] for f in persona_facts.picked_facts(persona, "A clinic visit, no medical aid needed.")]
    assert "You have no medical aid." in lines
    assert "You have medical aid." not in lines


# ── Household facts for the topics no card covered ──────────────────────────
# audit_card_gaps.py: power, water, safety, housing, transport and environment had no
# research card for anyone. GHS records what each household has and does on all six;
# these are said to the persona as facts about their life.

def test_water_cuts_read_as_three_levels():
    assert hh.water_interruptions(2, 8) == "none"
    assert hh.water_interruptions(1, 1) == "often"      # every week
    assert hh.water_interruptions(1, 2) == "often"      # a couple of times a month
    assert hh.water_interruptions(1, 4) == "sometimes"  # a couple of times a year
    assert hh.water_interruptions(8, 8) is None         # not asked of this household


def test_water_backup_names_the_bigger_step_first():
    assert hh.water_backup(1, 1) == "borehole"
    assert hh.water_backup(2, 1) == "tank"
    assert hh.water_backup(2, 2) == "none"
    assert hh.water_backup(9, 2) is None


def test_the_first_ranked_reason_not_to_recycle_is_kept():
    row = {"SWR_NOTSEPWASTE_SPACE": 2, "SWR_NOTSEPWASTE_COST": 1, "SWR_NOTSEPWASTE_DIRTY": 3}
    assert hh.not_recycling_reason(row) == "cost"
    assert hh.not_recycling_reason({"SWR_NOTSEPWASTE_SPACE": 8}) is None


def test_tenure_and_the_way_to_work_decode():
    assert hh._TENURE[3] == "bond" and hh._TENURE[5] == "own" and hh._TENURE[1] == "rent"
    assert hh._TRANSPORT[5] == "taxi" and hh._TRANSPORT[9] == "own_car"
    assert 88 not in hh._TRANSPORT


def _own_household_frame():
    rows = []
    for i in range(40):
        rows.append({**_person(f"u{i}", 30 + i % 11, "none"), "personnr": "01",
                     "solar_panels": "False", "home_security": "False",
                     "water_interruptions": "none", "water_backup": "none",
                     "housing_tenure": "rent", "recycles": "False",
                     "not_recycling_reason": "no_space", "transport_to_work": "taxi"})
    rows.append({**_person("mine", 44, "parent", learners="2", med=True), "personnr": "03",
                 "solar_panels": "True", "home_security": "True",
                 "water_interruptions": "often", "water_backup": "borehole",
                 "housing_tenure": "bond", "recycles": "True",
                 "not_recycling_reason": None, "transport_to_work": "own_car"})
    return pd.DataFrame(rows)


def test_a_persona_built_from_ghs_reads_its_own_household():
    frame = _own_household_frame()
    persona = _persona(1, age=44, ghs_person_rows=["mine:3"], employment_status="Employed")
    result = hh.assign([persona], frame)[0]
    assert result["measured"] and result["donor"]["uqnr"] == "mine"
    facts = {r["field"]: r for r in hh.rows_for(persona, result)}
    assert facts["solar_panels"]["value"] == "True"
    assert facts["housing_tenure"]["value"] == "bond"
    assert facts["transport_to_work"]["value"] == "own_car"
    assert facts["learners_in_household"]["value"] == "2"
    assert {r["grade"] for r in facts.values()} == {"measured"}


def test_a_matched_persona_gets_the_donors_whole_household():
    frame = _own_household_frame()
    persona = _persona(1, age=35, employment_status="Employed")
    result = hh.assign([persona], frame)[0]
    assert not result.get("measured")
    facts = {r["field"]: r["value"] for r in hh.rows_for(persona, result)}
    donor = result["donor"]
    for field in hh.HOUSEHOLD_FACTS:
        if donor.get(field) is not None:
            assert facts[field] == donor[field]


def test_the_way_to_work_is_only_said_of_people_who_work():
    frame = _own_household_frame()
    for status, said in (("Employed", True), ("Unemployed", False),
                         ("Other not economically active", False)):
        persona = _persona(1, age=44, ghs_person_rows=["mine:3"], employment_status=status)
        fields = {r["field"] for r in hh.rows_for(persona, hh.assign([persona], frame)[0])}
        assert ("transport_to_work" in fields) is said, status


def test_each_household_fact_reaches_the_pitch_it_is_about():
    persona = {"circumstances": [
        _row("solar_panels", "True", "measured"), _row("home_security", "True", "measured"),
        _row("water_interruptions", "often", "measured"), _row("housing_tenure", "bond", "measured"),
        _row("recycles", "False", "measured"), _row("not_recycling_reason", "no_space", "measured"),
        _row("transport_to_work", "taxi", "measured")]}
    power = _facts(persona, "A solar and battery kit that keeps the lights on when the power is out.")
    assert power["solar_panels"] == "Your household has solar panels."
    assert power["water_interruptions"] == "Your water supply is cut at least a couple of times a month."
    safety = _facts(persona, "A neighbourhood patrol with a panic button app.")
    assert safety["home_security"] == "Your household has a home security service."
    housing = _facts(persona, "An app that matches backyard rooms with tenants, with a written lease.")
    assert housing["housing_tenure"] == "Your household is still paying off its home."
    waste = _facts(persona, "A company collects your sorted recycling each week.")
    assert waste["not_recycling_reason"].endswith("there is no space for it.")
    commute = _facts(persona, "A shared ride to the taxi rank each morning.")
    assert commute["transport_to_work"] == "You take a minibus taxi to work."


def test_household_facts_stay_out_of_pitches_they_are_not_about():
    persona = {"circumstances": [_row("solar_panels", "True", "measured"),
                                 _row("home_security", "True", "measured"),
                                 _row("housing_tenure", "bond", "measured")]}
    school = _facts(persona, "An after-school maths programme for Grade 9s.")
    assert not {"solar_panels", "home_security", "housing_tenure"} & set(school)
