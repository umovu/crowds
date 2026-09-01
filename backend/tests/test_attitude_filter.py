"""LLM-off tests for the attitude lens (Step 3).

The lens lets a user build a room out of people who ALREADY hold a measured
view — "can afford it, but has never thought about pollution" — instead of
writing what a persona thinks. That distinction is the whole safety argument for
the feature, so these tests pin the mechanics that keep it true:

  * matching reads the library's LIST-shaped attitudes (a dict-shaped read
    silently returns nothing — that exact bug once dropped the survey-grounded
    layer out of the sim prompt)
  * a persona MISSING the dimension never matches — absence is not evidence
  * every dimension asked for must be satisfied (AND, not OR)
  * nothing is written: the lens filters and never assigns a stance

Dependency-light loading (same shape as test_panel_fit.py) so AgentSociety2 —
which demands AGENTSOCIETY_LLM_API_KEY — is never imported.
"""

import importlib.util
import os
import sys
import types

import pytest

HERE = os.path.dirname(__file__)
APP = os.path.normpath(os.path.join(HERE, "..", "app"))
SERVICES = os.path.join(APP, "services")


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


def _load_app(modname, filename):
    if modname in sys.modules:
        return sys.modules[modname]
    spec = importlib.util.spec_from_file_location(
        modname, os.path.join(APP, *filename.split(".")) + ".py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


for pkg_name, pkg_path in [
    ("app", APP),
    ("app.services", SERVICES),
    ("app.models", os.path.join(APP, "models")),
    ("app.utils", os.path.join(APP, "utils")),
    ("app.storage", os.path.join(APP, "storage")),
]:
    if pkg_name not in sys.modules:
        m = types.ModuleType(pkg_name)
        m.__path__ = [pkg_path]
        sys.modules[pkg_name] = m


class _GraphStorage:
    pass


sys.modules["app.storage"].GraphStorage = _GraphStorage

_load_app("app.config", "config")
_load("app.services.income_seeder", "income_seeder.py", package="app.services")
_load("app.services.mode_specs", "mode_specs.py", package="app.services")
_load("app.services.objections", "objections.py", package="app.services")
_load("app.services.persona_library", "persona_library.py", package="app.services")
_load("app.services.persona_retrieval", "persona_retrieval.py", package="app.services")
panel = _load("app.services.panel_service", "panel_service.py", package="app.services")


DIM = "environment_priority"


def _persona(name, stances):
    """A library-shaped persona: attitudes are a LIST of rows, not a dict."""
    return {
        "id": name,
        "name": name,
        "attitudes": [
            {"topic": dim, "stance": stance,
             "source": "afrobarometer_r9_sa", "match_quality": "exact"}
            for dim, stance in stances.items()
        ],
    }


# ── reading a stance ────────────────────────────────────────────────────────

def test_reads_the_list_shape_the_library_actually_ships():
    p = _persona("A", {DIM: "low", "gov_trust": "high"})
    assert panel.persona_attitude(p, DIM) == "low"
    assert panel.persona_attitude(p, "gov_trust") == "high"


def test_missing_dimension_reads_as_none_not_an_error():
    assert panel.persona_attitude(_persona("A", {"gov_trust": "low"}), DIM) is None
    assert panel.persona_attitude({"name": "no attitudes at all"}, DIM) is None


# ── matching ────────────────────────────────────────────────────────────────

def test_matches_only_the_wanted_stance():
    wanted = {DIM: {"low"}}
    assert panel._persona_matches_attitudes(_persona("A", {DIM: "low"}), wanted)
    assert not panel._persona_matches_attitudes(_persona("B", {DIM: "high"}), wanted)
    assert not panel._persona_matches_attitudes(_persona("C", {DIM: "mid"}), wanted)


def test_a_persona_without_the_dimension_never_matches():
    """Absence is not evidence. Counting the unmeasured in would pad the room
    with people whose view was never recorded."""
    wanted = {DIM: {"low"}}
    assert not panel._persona_matches_attitudes(_persona("A", {"gov_trust": "low"}), wanted)
    assert not panel._persona_matches_attitudes({"name": "bare"}, wanted)


def test_several_stances_are_an_or_within_one_dimension():
    wanted = {DIM: {"low", "mid"}}
    assert panel._persona_matches_attitudes(_persona("A", {DIM: "mid"}), wanted)
    assert not panel._persona_matches_attitudes(_persona("B", {DIM: "high"}), wanted)


def test_several_dimensions_are_an_and():
    wanted = {DIM: {"low"}, "gov_trust": {"high"}}
    assert panel._persona_matches_attitudes(
        _persona("both", {DIM: "low", "gov_trust": "high"}), wanted)
    assert not panel._persona_matches_attitudes(
        _persona("half", {DIM: "low", "gov_trust": "low"}), wanted)


def test_the_lens_filters_and_never_assigns():
    """The safety property: matching must not write a stance onto anyone."""
    p = _persona("A", {"gov_trust": "high"})
    before = [dict(r) for r in p["attitudes"]]
    panel._persona_matches_attitudes(p, {DIM: {"low"}})
    assert p["attitudes"] == before
    assert panel.persona_attitude(p, DIM) is None


# ── the dimension is actually on the library ────────────────────────────────

def test_library_carries_the_environment_dimension():
    """Guards the data, not just the code: if a rebuild drops the fusion pass,
    the filter silently matches nobody and the feature dies quietly."""
    library = panel.get_library()
    if library.is_empty():
        pytest.skip("persona library not built in this environment")
    stances = [panel.persona_attitude(p, DIM) for p in library.all()]
    present = [s for s in stances if s]
    assert len(present) > 0.9 * len(stances), (
        f"only {len(present)}/{len(stances)} personas carry {DIM} — "
        "re-run backend/scripts/add_environment_attitude.py")
    assert set(present) <= {"low", "mid", "high"}
    # All three bands must exist, or there is nothing to contrast.
    assert set(present) == {"low", "mid", "high"}
