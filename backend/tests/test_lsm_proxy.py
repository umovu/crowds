"""Audit tests for the LSM proxy scorer (LLM off).

Two jobs:

  * pin the rubric — the points, the poverty brake, the band cutoffs
  * catch drift — if the library or the rubric changes, band counts move and
    these fail loudly instead of quietly reshaping every client's audience

Runs with the LLM switched OFF, by design: the whole scorer must be assertable
without a model (CLAUDE.md, product-mode economy rules). We load the modules
directly rather than via app.services, whose __init__ needs LLM env vars
(mirrors test_library_cast.py).

Band counts below are the live library on 2026-08-24. A tolerance of +/-15 is
wide enough for a normal library rebuild and narrow enough to notice a rubric
change. If a rebuild moves a band further than that, look before you widen it.
"""

import importlib.util
import json
import os
import sys
import types

HERE = os.path.dirname(__file__)
APP = os.path.normpath(os.path.join(HERE, "..", "app"))
SERVICES = os.path.join(APP, "services")
LIBRARY_JSON = os.path.join(APP, "data", "persona_library", "personas.json")


def _load(modname, filename, package=None):
    if modname in sys.modules:
        return sys.modules[modname]
    spec = importlib.util.spec_from_file_location(modname, os.path.join(SERVICES, filename))
    mod = importlib.util.module_from_spec(spec)
    if package:
        mod.__package__ = package
    sys.modules[modname] = mod
    if package and package in sys.modules:
        setattr(sys.modules[package], modname.rsplit(".", 1)[-1], mod)
    spec.loader.exec_module(mod)
    return mod


for pkg_name, pkg_path in [
    ("app", APP),
    ("app.services", SERVICES),
    ("app.utils", os.path.join(APP, "utils")),
]:
    if pkg_name not in sys.modules:
        m = types.ModuleType(pkg_name)
        m.__path__ = [pkg_path]
        sys.modules[pkg_name] = m

lsm = _load("app.services.lsm_proxy", "lsm_proxy.py", package="app.services")


# Updated 2026-08-28 for the 297 -> 375 library (78 GHS affluent personas added
# so the attitude/affordability filter had a pool to draw from; see
# ghs_adapter.sample_affluent_skeletons). The rubric did NOT change — the library
# grew, and it grew at the top, which is why Band 4 moved most.
EXPECTED_COUNTS = {
    "Band 1 — Going without": 73,
    "Band 2 — Getting by": 109,
    "Band 3 — Steady": 99,
    "Band 4 — Comfortable": 94,
}
TOLERANCE = 15


def _library():
    with open(LIBRARY_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("personas", []) if isinstance(data, dict) else list(data)


def _circ(**fields):
    return [
        {"field": k, "value": v, "match_quality": "exact"} for k, v in fields.items()
    ]


# ── rubric ────────────────────────────────────────────────────────────────

def test_band_cutoffs():
    assert lsm.band_for_score(4) == lsm.BAND_1
    assert lsm.band_for_score(5) == lsm.BAND_2
    assert lsm.band_for_score(8) == lsm.BAND_2
    assert lsm.band_for_score(9) == lsm.BAND_3
    assert lsm.band_for_score(12) == lsm.BAND_3
    assert lsm.band_for_score(13) == lsm.BAND_4


def test_band_names_are_ours_not_lsms():
    """Band 1-4 with a plain-word name. No borrowed acronym in client-facing copy."""
    assert lsm.BANDS == (
        "Band 1 — Going without",
        "Band 2 — Getting by",
        "Band 3 — Steady",
        "Band 4 — Comfortable",
    )
    for band in lsm.BANDS:
        assert "LSM" not in lsm.BAND_MEANING[band]
        assert "SEM" not in lsm.BAND_MEANING[band]


def test_asset_points():
    def score(**fields):
        return lsm.score_persona({"circumstances": _circ(**fields)})["score"]

    assert score(owns_vehicle="own") == 4
    assert score(owns_vehicle="household") == 2
    assert score(owns_computer="own") == 3
    assert score(owns_computer="household") == 2
    assert score(owns_bank_account="own") == 2
    assert score(owns_bank_account="household") == 2
    assert score(owns_television="own") == 1
    assert score(internet_use="daily") == 2
    assert score(internet_use="weekly") == 1
    assert score(electricity_reliability="always") == 1
    assert score(electricity_reliability="most") == 1


def test_urban_is_top_level_not_a_circumstance():
    """geotype lives on the persona itself; the assets live in circumstances."""
    assert lsm.score_persona({"geotype": "Urban"})["score"] == 1
    assert lsm.score_persona({"geotype": "Traditional"})["score"] == 0
    assert lsm.score_persona({"geotype": "Farms"})["score"] == 0


def test_poverty_brake():
    def score(level):
        return lsm.score_persona({"circumstances": _circ(lived_poverty=level)})["score"]

    assert score("none") == 3
    assert score("low") == 1
    assert score("moderate") == -1
    assert score("high") == -3


def test_maximums():
    """Assets cap at 14; the poverty brake takes the absolute ceiling to 17."""
    everything = {
        "geotype": "Urban",
        "circumstances": _circ(
            owns_vehicle="own",
            owns_computer="own",
            owns_bank_account="own",
            owns_television="own",
            internet_use="daily",
            electricity_reliability="always",
        ),
    }
    assert lsm.score_persona(everything)["score"] == 14
    everything["circumstances"] += _circ(lived_poverty="none")
    assert lsm.score_persona(everything)["score"] == 17


def test_missing_and_unknown_values_score_zero_never_guessed():
    assert lsm.score_persona({})["score"] == 0
    junk = {"circumstances": _circ(owns_vehicle="spaceship", internet_use="sometimes")}
    assert lsm.score_persona(junk)["score"] == 0


def test_no_grant_cap():
    """Version 3 dropped the clamp: a grant survivor may reach Comfortable."""
    rich_survivor = {
        "actor_archetype": "grant_dependent_survivor",
        "geotype": "Urban",
        "circumstances": _circ(
            owns_vehicle="own",
            owns_computer="own",
            owns_bank_account="own",
            owns_television="own",
            internet_use="daily",
            electricity_reliability="always",
            lived_poverty="none",
        ),
    }
    assert lsm.score_persona(rich_survivor)["band"] == lsm.BAND_4


def test_confidence_tracks_match_quality_and_never_moves_the_band():
    fields = dict(
        lived_poverty="low",
        owns_vehicle="own",
        owns_computer="own",
        owns_bank_account="own",
        owns_television="own",
        internet_use="daily",
        electricity_reliability="most",
    )
    exact = {"circumstances": _circ(**fields)}
    assert lsm.score_persona(exact)["confidence"] == "high"

    loose = {
        "circumstances": [
            dict(r, match_quality="race_only") for r in _circ(**fields)
        ]
    }
    assert lsm.score_persona(loose)["confidence"] == "low"
    assert lsm.score_persona(loose)["score"] == lsm.score_persona(exact)["score"]
    assert lsm.score_persona(loose)["band"] == lsm.score_persona(exact)["band"]


def test_every_band_has_a_client_facing_meaning():
    for band in lsm.BANDS:
        assert lsm.BAND_MEANING[band].strip()


# ── drift against the live library ────────────────────────────────────────

def test_band_counts_have_not_drifted():
    counts = lsm.band_counts(_library())
    for band, expected in EXPECTED_COUNTS.items():
        assert abs(counts[band] - expected) <= TOLERANCE, (
            f"{band} moved from {expected} to {counts[band]}. Either the library "
            f"was rebuilt or the rubric changed — check which before widening this."
        )


def test_every_persona_scores():
    personas = _library()
    assert len(personas) > 0
    for persona in personas:
        result = lsm.score_persona(persona)
        assert result["band"] in lsm.BANDS
        assert result["confidence"] in ("high", "medium", "low")


def test_urban_professionals_land_high():
    personas = [
        p for p in _library() if p.get("actor_archetype") == "urban_professional"
    ]
    assert personas, "no urban_professional personas — did the archetype key change?"
    high = sum(
        1
        for p in personas
        if lsm.score_persona(p)["band"] in (lsm.BAND_4, lsm.BAND_3)
    )
    assert high > len(personas) / 2


def test_worked_example_still_scores_five():
    """The hand-checked example from the plan doc. If this moves, the doc lies."""
    match = [p for p in _library() if p.get("name") == "Nokuthula Xaba"]
    assert match, "worked-example persona missing from the library"
    result = lsm.score_persona(match[0])
    assert result["score"] == 5
    assert result["band"] == lsm.BAND_2
