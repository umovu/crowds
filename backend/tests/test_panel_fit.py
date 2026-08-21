"""LLM-off tests for the segment fit card (panel_service.rank_by_segment).

The fit card is the "which room is this for" answer. Its three readings come
from three different places on purpose, and this file pins that separation:

  * `stance_split`   — what people SAID (LLM output)
  * `budget_tiers`   — what their real income supports (computed, never LLM)
  * `top_objections` — the wall the room kept hitting (deterministic classifier)

If any future change collapses these into one number, that number is a purchase
probability by another name, which CLAUDE.md bans outright. The tests below
should fail loudly if that happens.

Dependency-light loading (same shape as test_pointers.py) so AgentSociety2 —
which demands AGENTSOCIETY_LLM_API_KEY — is never imported.
"""

import importlib.util
import json
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
    if "." in modname:
        parent_name, _, child = modname.rpartition(".")
        if parent_name in sys.modules:
            setattr(sys.modules[parent_name], child, mod)
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


# ── fixture: a two-segment room written straight to disk ───────────────────

SESSION_ID = "fit-test-session"

# Three traders, three professionals. Archetype drives the segment predicate;
# budget_tier is a real computed field we set here so the affordability reading
# is assertable without touching income_seeder.
PROFILES = [
    {"id": 1, "name": "Nomsa", "actor_archetype": "informal_trader", "budget_tier": "tight"},
    {"id": 2, "name": "Sipho", "actor_archetype": "informal_trader", "budget_tier": "tight"},
    {"id": 3, "name": "Thabo", "actor_archetype": "informal_trader", "budget_tier": "comfortable"},
    {"id": 4, "name": "Pieter", "actor_archetype": "urban_professional", "budget_tier": "comfortable"},
    {"id": 5, "name": "Ayanda", "actor_archetype": "urban_professional", "budget_tier": "comfortable"},
    {"id": 6, "name": "Riaan", "actor_archetype": "urban_professional", "budget_tier": "comfortable"},
]

# Traders win the room; professionals push back. Both rooms mention "branch"
# (no_human_support) so the objection reading has something real to count.
RESULTS = [
    {"agent_id": 1, "agent_name": "Nomsa", "stance_after": "support",
     "response": "Cheap enough for me. But if it breaks, is there a branch?"},
    {"agent_id": 2, "agent_name": "Sipho", "stance_after": "support",
     "response": "I would use this. I just want someone to talk to."},
    {"agent_id": 3, "agent_name": "Thabo", "stance_after": "concerned",
     "response": "The monthly fee is what worries me."},
    {"agent_id": 4, "agent_name": "Pieter", "stance_after": "oppose",
     "response": "I can pay. I will not share my line."},
    {"agent_id": 5, "agent_name": "Ayanda", "stance_after": "oppose",
     "response": "No. And there is no branch to sort it out."},
    {"agent_id": 6, "agent_name": "Riaan", "stance_after": "neutral",
     "response": "Waiting to see if it is reliable."},
]

META = {"segments": ["informal_traders", "professionals"]}


@pytest.fixture(autouse=True)
def _restore_session_dir():
    """`panel_service` is a module-level singleton shared with the other test
    files in this suite. These tests repoint its session dir at a tmp path, so
    put it back afterwards — otherwise test_pointers reads OUR fixture sessions
    and fails only when the full suite runs.
    """
    original = panel.Config.PANEL_SESSION_DATA_DIR
    yield
    panel.Config.PANEL_SESSION_DATA_DIR = original


def _write_session(tmp_path, profiles=PROFILES):
    """Lay a session down on disk and point panel_service's base dir at it."""
    base = str(tmp_path)
    panel.Config.PANEL_SESSION_DATA_DIR = base
    sdir = os.path.join(base, SESSION_ID)
    os.makedirs(sdir, exist_ok=True)
    with open(os.path.join(sdir, panel.PROFILES_FILE), "w", encoding="utf-8") as fh:
        json.dump(profiles, fh)
    return base


def _rank(tmp_path, results=RESULTS, meta=META, profiles=PROFILES):
    _write_session(tmp_path, profiles)
    return panel.rank_by_segment(SESSION_ID, meta, results)


# ── ranking ────────────────────────────────────────────────────────────────

def test_ranks_the_room_that_leaned_in_first(tmp_path):
    ranked = _rank(tmp_path)
    assert [r["segment_id"] for r in ranked] == ["informal_traders", "professionals"]


def test_needs_two_concrete_segments(tmp_path):
    assert _rank(tmp_path, meta={"segments": ["informal_traders"]}) == []
    assert _rank(tmp_path, meta={"segments": ["everyone"]}) == []


def test_no_results_means_no_ranking(tmp_path):
    assert _rank(tmp_path, results=[]) == []


# ── the three readings stay three readings ─────────────────────────────────

def test_stance_split_counts_what_people_said(tmp_path):
    traders = _rank(tmp_path)[0]
    assert traders["stance_split"] == {"support": 2, "concerned": 1}


def test_budget_tiers_come_from_real_fields(tmp_path):
    traders = _rank(tmp_path)[0]
    assert traders["budget_tiers"] == {"tight": 2, "comfortable": 1}


def test_top_objections_are_counted_not_scored(tmp_path):
    traders = _rank(tmp_path)[0]
    top = {o["id"]: o["count"] for o in traders["top_objections"]}
    assert top["no_human_support"] == 2  # Nomsa and Sipho, not Thabo
    assert all(isinstance(o["count"], int) for o in traders["top_objections"])
    assert all(o["label"] for o in traders["top_objections"])


def test_row_carries_no_single_fit_score(tmp_path):
    """The banned shape: one number standing in for all three readings."""
    row = _rank(tmp_path)[0]
    banned = {"fit_score", "score", "buy_probability", "purchase_probability",
              "would_buy", "conversion", "likelihood"}
    assert not banned & set(row)


# ── seats vs heard ─────────────────────────────────────────────────────────

def test_seats_and_heard_match_on_a_clean_round(tmp_path):
    for row in _rank(tmp_path):
        assert row["seats"] == 3
        assert row["heard_count"] == 3


def test_a_silent_persona_lowers_heard_but_not_seats(tmp_path):
    # Riaan's interview failed — he keeps his seat and his budget tier.
    partial = [r for r in RESULTS if r["agent_id"] != 6]
    pros = [r for r in _rank(tmp_path, results=partial)
            if r["segment_id"] == "professionals"][0]
    assert pros["seats"] == 3
    assert pros["heard_count"] == 2
    assert sum(pros["budget_tiers"].values()) == 3


def test_empty_segment_is_an_explicit_row_with_its_seats(tmp_path):
    # A segment nobody in the room matches: the row must survive, saying zero.
    meta = {"segments": ["informal_traders", "professionals", "learners"]}
    ranked = _rank(tmp_path, meta=meta)
    learners = [r for r in ranked if r["segment_id"] == "learners"][0]
    assert learners is ranked[-1]  # empty rows sink
    assert learners["heard_count"] == 0
    assert learners["seats"] == 0
    assert learners["top_objections"] == []


def test_ranking_is_deterministic(tmp_path):
    assert _rank(tmp_path) == _rank(tmp_path)


# ── coverage: the scope is stated, not implied ─────────────────────────────

def test_coverage_reports_compared_out_of_available():
    cov = panel.coverage_summary(META)
    assert cov["segments_compared"] == 2
    assert cov["segments_available"] > 2


def test_coverage_excludes_everyone_from_both_sides():
    cov = panel.coverage_summary({"segments": ["everyone", "professionals"]})
    assert cov["segments_compared"] == 1
    assert cov["segments_available"] == len(
        [s for s in panel.SEGMENTS if s != "everyone"])


# ── latest_results: the strip compares rooms, not rounds ───────────────────

def _save_round(base, results, num):
    rdir = os.path.join(base, SESSION_ID, "rounds")
    os.makedirs(rdir, exist_ok=True)
    with open(os.path.join(rdir, f"round_{num:03d}.json"), "w", encoding="utf-8") as fh:
        json.dump({"round": num, "result": {"results": results}}, fh)


def test_latest_results_unions_across_rounds(tmp_path):
    base = _write_session(tmp_path)
    _save_round(base, RESULTS[:3], 1)   # traders answered in round 1
    _save_round(base, RESULTS[3:], 2)   # professionals answered in round 2
    got = panel.latest_results(SESSION_ID)
    assert sorted(r["agent_id"] for r in got) == [1, 2, 3, 4, 5, 6]


def test_latest_results_lets_the_newest_answer_win(tmp_path):
    base = _write_session(tmp_path)
    _save_round(base, [{"agent_id": 1, "stance_after": "oppose", "response": "no"}], 1)
    _save_round(base, [{"agent_id": 1, "stance_after": "support", "response": "yes"}], 2)
    got = panel.latest_results(SESSION_ID)
    assert len(got) == 1
    assert got[0]["stance_after"] == "support"


def test_latest_results_on_a_fresh_session_is_empty(tmp_path):
    _write_session(tmp_path)
    assert panel.latest_results(SESSION_ID) == []


# ── carry_probe: the wall becomes a question ───────────────────────────────

def test_carry_probe_asks_about_the_previous_wall():
    probe = panel.carry_probe("no_human_support")
    assert probe and "?" in probe


def test_carry_probe_ignores_a_bad_id():
    assert panel.carry_probe("not_a_real_objection") is None
    assert panel.carry_probe(None) is None
    assert panel.carry_probe("") is None


# ── coverage log ───────────────────────────────────────────────────────────

def test_coverage_gap_appends_one_line_per_call(tmp_path):
    base = _write_session(tmp_path)
    meta = dict(META, pitch="a shared data bundle", user_id="u1")
    panel.log_coverage_gap(SESSION_ID, meta, chosen="guardians",
                           abandoned=["professionals"], note="rural nurses")
    panel.log_coverage_gap(SESSION_ID, meta, note="second")
    with open(os.path.join(base, panel.COVERAGE_LOG), encoding="utf-8") as fh:
        lines = [json.loads(l) for l in fh if l.strip()]
    assert len(lines) == 2
    assert lines[0]["segment_chosen"] == "guardians"
    assert lines[0]["segments_abandoned"] == ["professionals"]
    assert lines[0]["note"] == "rural nurses"
    assert lines[0]["user_id"] == "u1"
    assert lines[0]["segments_offered"] == ["informal_traders", "professionals"]


def test_coverage_gap_never_raises_on_a_bad_path(tmp_path):
    """It's a roadmap log, not a round. It must never break the user's flow."""
    panel.Config.PANEL_SESSION_DATA_DIR = os.path.join(str(tmp_path), "f.txt")
    with open(panel.Config.PANEL_SESSION_DATA_DIR, "w") as fh:
        fh.write("not a directory")
    panel.log_coverage_gap(SESSION_ID, {"pitch": "x"}, note="should not raise")
