"""Re-matching broken personas (scripts/rematch_broken_personas.py). LLM-off.

A persona's matched survey facts must not contradict its own: the kind of area it lives
in, its own phone answers, and the recorded survey person. The re-match keeps age before
area where it can, and never touches identity.
"""

import json
import os
import sys

import pytest

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(BACKEND, "scripts"))

import attitude_fuser as af  # noqa: E402
import rematch_broken_personas as rb  # noqa: E402

LIBRARY = os.path.join(BACKEND, "app", "data", "persona_library", "personas.json")


def _persona(**extra):
    p = {"id": "p1", "name": "Test", "age": 40, "gender": "Male", "province": "Eastern Cape",
         "education": "Secondary not completed", "employment_status": "Unemployed",
         "race": "African/Black", "geotype": "Traditional",
         "circumstances": [{"field": "internet_use", "value": "never", "source": "afrobarometer_r9_sa",
                            "match_quality": "exact"}]}
    p.update(extra)
    return p


def _donor(respondent, age, geotype, **circ):
    view = af._skeleton_join_view(_persona())
    return {**view, "age_band": rb.band2(age), "_age": age, "geotype": geotype, "respondent": respondent,
            "weight": 1.0, "attitudes": {}, "circumstances": {"internet_use": "never", **circ}}


def test_age_bands_split_the_oldest_group():
    assert rb.band2(74) == "60-74"
    assert rb.band2(75) == "75+"
    assert rb.band2(98) == "75+"
    assert rb.band2(30) == rb.ada.age_to_band(30)


def test_broken_reasons_name_each_problem():
    person = _persona()
    assert rb.broken_reasons(person, _donor("SAF1", 40, "Rural")) == []
    assert "wrong area" in rb.broken_reasons(person, _donor("SAF1", 40, "Urban"))
    assert "facts not from recorded survey person" in rb.broken_reasons(
        person, dict(_donor("SAF1", 40, "Rural"), circumstances={"internet_use": "daily"}))
    assert "75+ matched to someone younger" in rb.broken_reasons(_persona(age=80), _donor("SAF1", 62, "Rural"))
    smartphone = {"own": True, "smart": True}
    phone_person = _persona(circumstances=[{"field": "owns_phone", "value": "own", "source": "x", "match_quality": "exact"},
                                           {"field": "phone_internet", "value": "no", "source": "x", "match_quality": "exact"}])
    donor = _donor("SAF1", 40, "Rural", owns_phone="own", phone_internet="no")
    assert "phone contradiction" in rb.broken_reasons(phone_person, donor, smartphone)


def test_rematch_needs_the_same_area_and_agreeing_phones():
    pool = [_donor("SAF1", 41, "Urban", owns_phone="own", phone_internet="yes"),
            _donor("SAF2", 42, "Rural", owns_phone="own", phone_internet="no"),
            _donor("SAF3", 43, "Rural", owns_phone="own", phone_internet="yes")]
    donor, _label = rb.rematch(_persona(), pool, {"own": True, "smart": True})
    assert donor["respondent"] == "SAF3"


def test_rematch_tries_someone_near_in_age_before_dropping_age():
    # No exact age band; one respondent within 10 years, one 30 years older.
    pool = [_donor("OLD", 70, "Rural"), _donor("NEAR", 48, "Rural")]
    donor, label = rb.rematch(_persona(age=40), pool)
    assert donor["respondent"] == "NEAR"
    assert label == "age_backoff"


def test_when_age_must_go_the_nearest_ages_are_used():
    # A 70-year-old grandmother with nobody within 10 years: the 48-year-old is used,
    # never the 20-year-old. (Once matched a gogo to a 20-year-old's views.)
    pool = [_donor("YOUNG", 20, "Rural"), _donor("NEARER", 48, "Rural")]
    for _ in range(5):
        donor, _label = rb.rematch(_persona(age=70), pool)
        assert donor["respondent"] == "NEARER"


def test_phone_gives_way_before_a_big_age_gap():
    # A 63-year-old grandmother with no phone. The only respondent who agrees on phones is
    # 20; a 66-year-old from the same area shares a household phone's opposite answer.
    # Phones must not cost 43 years: the 66-year-old is used.
    young = _donor("YOUNG", 20, "Rural", owns_phone="household")
    older = _donor("OLDER", 66, "Rural", owns_phone="own", phone_internet="no")
    donor, _label = rb.rematch(_persona(age=63), [young, older], {"own": False, "smart": False})
    assert donor["respondent"] == "OLDER"


def test_area_rule_gives_way_before_a_race_only_match():
    # The only same-area respondent shares nothing but race; a different-area one shares
    # gender, job status and race. A race-only match is not allowed, so area gives way.
    near = _donor("OTHER_AREA", 41, "Urban")
    race_only = dict(_donor("SAME_AREA", 41, "Rural"), gender="Female", province="Gauteng",
                     education_band="tertiary", employment_status="Employed")
    donor, label = rb.rematch(_persona(), [near, race_only])
    assert label != "race_only"
    assert donor["respondent"] == "OTHER_AREA"


def test_the_library_is_consistent_after_the_rematch():
    if not os.path.exists(LIBRARY) or not os.path.exists(rb.ada._AFROBAROMETER_PATH):
        pytest.skip("library or Afrobarometer file not in this checkout")
    with open(LIBRARY, encoding="utf-8") as fh:
        people = json.load(fh)["personas"]
    by_resp = {d["respondent"]: d for d in rb.donors_with_age()}
    reasons = [(p["name"], rb.broken_reasons(p, by_resp.get(p.get("survey_respondent") or ""))) for p in people]
    not_from_person = [n for n, why in reasons if "facts not from recorded survey person" in why]
    wrong_area = [n for n, why in reasons if "wrong area" in why]
    if len(wrong_area) > 50:
        pytest.skip("library not re-matched yet (scripts/rematch_broken_personas.py --apply)")
    assert not not_from_person, not_from_person[:5]
    # Only where keeping the area would have meant a race-only match.
    assert len(wrong_area) <= 3, wrong_area
    assert not [p["name"] for p in people if p.get("attitude_match_quality") == "race_only"]
