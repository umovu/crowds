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
            province="Gauteng", geo="Urban", race="African/Black", wgt=100.0):
    return {"uqnr": uqnr, "age": age, "person_wgt": wgt, "province": province,
            "gender": gender, "race": race, "geo": geo, "learner_relation": relation,
            "learners": learners, "fee_band": fee, "medical_aid": med}


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
