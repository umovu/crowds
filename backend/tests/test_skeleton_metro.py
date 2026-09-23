"""A persona sampled today knows its own metro, because the survey recorded it.

The library's first 375 carry a metro DRAWN from the GHS spread for people like
them (scripts/add_ghs_geography.py) — honest at the group level, a guess at the
individual one. Anyone sampled from QLFS after this does better: the survey row
itself says which metro the household was in, so the value is measured, not
placed. These tests keep that true, and keep the two sources spelling the same
place the same way — the cast picker matches these labels exactly, so "GP - Non
Metro" and "GP - Non-metro" would be two different cities to it.

No model, no network.
"""
import importlib.util
import json
import os
import sys

import pytest

from app.models.persona import CIRCUMSTANCES

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(_BACKEND, "scripts")
LIBRARY = os.path.join(_BACKEND, "app", "data", "persona_library", "personas.json")


def _load(name):
    """Import a build script by path — they are scripts, not an installed package."""
    sys.path.insert(0, SCRIPTS)
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ps = _load("persona_sampler")

MODEL_METROS = set(CIRCUMSTANCES["metro"]["values"])


@pytest.fixture(scope="module")
def skeletons():
    if not os.path.exists(ps._DEFAULT_DTA):
        pytest.skip("QLFS microdata not in this checkout")
    return ps.sample_skeletons(300, seed=42)


def test_every_sampled_skeleton_carries_a_metro(skeletons):
    assert all(s.get("metro") for s in skeletons)


def test_sampled_metros_are_in_the_model_vocabulary(skeletons):
    seen = {s["metro"] for s in skeletons}
    assert seen <= MODEL_METROS, seen - MODEL_METROS


def test_a_metro_never_contradicts_its_own_province(skeletons):
    prefix = {"Western Cape": "WC", "Eastern Cape": "EC", "Northern Cape": "NC",
              "Free State": "FS", "KwaZulu-Natal": "KZN", "North West": "NW",
              "Gauteng": "GP", "Mpumalanga": "MP", "Limpopo": "LP"}
    for s in skeletons:
        assert s["metro"].split(" - ")[0] == prefix[s["province"]], s


def test_qlfs_spells_a_metro_the_way_ghs_does(skeletons):
    """QLFS writes "Non Metro", GHS "Non-metro", and QLFS pads "WC  -". Left
    alone, the same place arrives under two names and each room sees half of it."""
    assert ps._metro_label("WC -  City of Cape Town") == "WC - City of Cape Town"
    assert ps._metro_label("GP - Non Metro") == "GP - Non-metro"
    assert ps._metro_label("KZN – eThekwini") == "KZN - eThekwini"
    assert ps._metro_label(None) is None
    assert ps._metro_label(float("nan")) is None

    if os.path.exists(LIBRARY):
        with open(LIBRARY, encoding="utf-8") as fh:
            people = json.load(fh)["personas"]
        placed = {r["value"] for p in people for r in p.get("circumstances") or []
                  if r.get("field") == "metro"}
        if placed:
            assert {s["metro"] for s in skeletons} <= placed | MODEL_METROS


def test_sampling_is_still_deterministic():
    if not os.path.exists(ps._DEFAULT_DTA):
        pytest.skip("QLFS microdata not in this checkout")
    a = ps.sample_skeletons(50, seed=7)
    b = ps.sample_skeletons(50, seed=7)
    assert [s["metro"] for s in a] == [s["metro"] for s in b]


def test_the_build_moves_metro_onto_the_persona_as_a_measured_row():
    """A top-level "metro" key would fail the persona model, which forbids
    unknown fields. The build turns it into a circumstance row instead, marked
    as coming from QLFS so it stays distinguishable from a drawn placement."""
    source = open(os.path.join(SCRIPTS, "build_library.py"), encoding="utf-8").read()
    assert 'sk.pop("metro"' in source
    assert '"source": "qlfs_2026_q1"' in source
    assert '"match_quality": "exact"' in source
    assert "qlfs_2026_q1" in CIRCUMSTANCES["metro"]["source"]["survey"]
