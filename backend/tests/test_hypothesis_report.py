"""LLM-off tests for the hypothesis report (hypothesis_report.py).

The report has two halves and they must not blur. The facts half — who was in
the room, where they landed, who moved, the wall they hit, what their income
supports — is computed from persisted round JSON, so every assertion here runs
with no model configured. The guesses half is one LLM pass; these tests pin
that it degrades to an empty list rather than faking one, and that a guess
carrying a figure is dropped (a hypothesis with a percentage in it is the
banned "% who would buy" wearing a sentence).

Dependency-light loading, same shape as test_panel_fit.py, so AgentSociety2 is
never imported.
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
hyp = _load("app.services.hypothesis_report", "hypothesis_report.py", package="app.services")


SESSION_ID = "hypothesis-test-session"

PROFILES = [
    {"id": 1, "name": "Nomsa", "actor_archetype": "informal_trader", "budget_tier": "tight"},
    {"id": 2, "name": "Sipho", "actor_archetype": "informal_trader", "budget_tier": "tight"},
    {"id": 3, "name": "Pieter", "actor_archetype": "urban_professional",
     "budget_tier": "comfortable"},
]

# Nomsa flips toward support, Pieter hardens away from it, Sipho holds. One
# reaction is phrased as a condition so the "what would change their mind"
# block has something real to quote.
RESULTS = [
    {"agent_id": 1, "agent_name": "Nomsa", "stance_before": "oppose",
     "stance_after": "support", "stance_changed": True,
     "response": "I would use it, as long as there is a branch when it breaks."},
    {"agent_id": 2, "agent_name": "Sipho", "stance_before": "neutral",
     "stance_after": "neutral", "stance_changed": False,
     "response": "The monthly fee is what worries me."},
    {"agent_id": 3, "agent_name": "Pieter", "stance_before": "neutral",
     "stance_after": "oppose", "stance_changed": True,
     "response": "No branch, no deal. I do not trust it."},
]

META = {
    "pitch": "A clinic that packs your chronic medication for collection.",
    "mode": "product",
    "segments": ["informal_traders", "professionals"],
    "segment_label": "Informal traders + Professionals",
    "created_at": "2026-09-01T09:00:00",
}


@pytest.fixture(autouse=True)
def _restore_session_dir():
    """panel_service is a module-level singleton shared across this suite —
    put its session dir back so other files don't read our fixtures."""
    original = panel.Config.PANEL_SESSION_DATA_DIR
    yield
    panel.Config.PANEL_SESSION_DATA_DIR = original


@pytest.fixture(autouse=True)
def _llm_off(monkeypatch):
    """Every assertion in this file must hold with no model reachable."""
    for var in ("SIM_LLM_API_KEY", "SIM_LLM_BASE_URL", "SIM_LLM_MODEL",
                "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_NAME"):
        monkeypatch.delenv(var, raising=False)


def _write_session(tmp_path, results=RESULTS, meta=META, profiles=PROFILES):
    """Lay a one-round session on disk and point panel_service at it."""
    panel.Config.PANEL_SESSION_DATA_DIR = str(tmp_path)
    sdir = os.path.join(str(tmp_path), SESSION_ID)
    os.makedirs(os.path.join(sdir, panel.ROUNDS_DIR), exist_ok=True)
    with open(os.path.join(sdir, panel.PROFILES_FILE), "w", encoding="utf-8") as fh:
        json.dump(profiles, fh)
    with open(os.path.join(sdir, panel.META_FILE), "w", encoding="utf-8") as fh:
        json.dump(meta, fh)
    with open(os.path.join(sdir, panel.ROUNDS_DIR, "round_001.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"round": 1, "pitch": meta.get("pitch"),
                   "result": {"results": results,
                              "summary_narrative": "The room wants a person to call."}}, fh)
    return SESSION_ID


# ── the facts half: no model, real numbers ─────────────────────────────────

def test_movement_counts_who_actually_changed(tmp_path):
    report = hyp.facts(_write_session(tmp_path))
    mv = report["movement"]
    assert mv["moved_count"] == 2
    assert mv["warmer"] == 1
    assert mv["cooler"] == 1
    assert mv["answers_considered"] == 3


def test_movement_names_the_direction_each_person_went(tmp_path):
    moves = {p["name"]: p["direction"]
             for p in hyp.facts(_write_session(tmp_path))["movement"]["people"]}
    assert moves == {"Nomsa": "warmer", "Pieter": "cooler"}


def test_a_stance_flag_without_a_real_change_is_not_movement(tmp_path):
    results = [dict(RESULTS[1], stance_changed=True)]  # neutral -> neutral
    assert hyp.facts(_write_session(tmp_path, results=results))["movement"]["moved_count"] == 0


def test_unknown_stance_labels_do_not_break_the_report(tmp_path):
    results = [dict(RESULTS[0], stance_before="furious", stance_after="delighted")]
    people = hyp.facts(_write_session(tmp_path, results=results))["movement"]["people"]
    assert people[0]["direction"] == "sideways"


def test_stance_split_counts_where_they_landed(tmp_path):
    split = hyp.facts(_write_session(tmp_path))["stance_split"]
    assert split == {"support": 1, "neutral": 1, "oppose": 1}


def test_walls_come_from_the_deterministic_classifier(tmp_path):
    walls = hyp.facts(_write_session(tmp_path))["walls"]
    assert "no_human_support" in [w["id"] for w in walls]


def test_conditions_quote_the_persona_verbatim(tmp_path):
    conditions = hyp.facts(_write_session(tmp_path))["conditions"]
    assert conditions
    assert conditions[0]["name"] == "Nomsa"
    assert conditions[0]["quote"] == RESULTS[0]["response"]


def test_budget_tiers_come_from_real_persona_fields(tmp_path):
    room = hyp.facts(_write_session(tmp_path))["room"]
    assert room["budget_tiers"] == {"tight": 2, "comfortable": 1}
    assert room["seats"] == 3 and room["heard"] == 3


def test_heard_is_smaller_than_seats_when_an_interview_failed(tmp_path):
    results = RESULTS[:2] + [dict(RESULTS[2], error="timeout")]
    room = hyp.facts(_write_session(tmp_path, results=results))["room"]
    assert room["seats"] == 3 and room["heard"] == 2


# ── the guesses half: absent, never faked ──────────────────────────────────

def test_build_returns_no_hypotheses_with_the_model_off(tmp_path):
    report = hyp.build(_write_session(tmp_path))
    assert report["hypotheses"] == []
    assert report["movement"]["moved_count"] == 2  # the facts still stand


def test_a_hypothesis_carrying_a_figure_is_dropped():
    kept = hyp._clean_hypotheses([
        {"claim": "Trust is the blocker", "test": "Ask a room that already pays you"},
        {"claim": "About 40% would switch", "test": "Re-pitch with the fee named"},
        {"claim": "Price is the blocker", "test": "Drop it to R50 and re-ask"},
    ])
    assert [h["claim"] for h in kept] == ["Trust is the blocker"]


def test_malformed_hypotheses_are_dropped_not_guessed_at():
    assert hyp._clean_hypotheses("not a list") == []
    assert hyp._clean_hypotheses([{"claim": "No test given"}]) == []


def test_missing_session_is_a_not_found(tmp_path):
    panel.Config.PANEL_SESSION_DATA_DIR = str(tmp_path)
    with pytest.raises(FileNotFoundError):
        hyp.build("no-such-session")


# ── caching ────────────────────────────────────────────────────────────────

def test_the_report_is_cached_beside_the_session(tmp_path):
    session_id = _write_session(tmp_path)
    hyp.build(session_id)
    cached = os.path.join(panel.session_dir(session_id), hyp.REPORT_FILE)
    assert os.path.exists(cached)


def test_a_new_round_invalidates_the_cache(tmp_path):
    session_id = _write_session(tmp_path)
    assert hyp.build(session_id)["rounds"] == 1
    with open(os.path.join(panel.session_dir(session_id), panel.ROUNDS_DIR,
                           "round_002.json"), "w", encoding="utf-8") as fh:
        json.dump({"round": 2, "result": {"results": []}}, fh)
    assert hyp.build(session_id)["rounds"] == 2


# ── rendering ──────────────────────────────────────────────────────────────

def test_markdown_states_who_moved(tmp_path):
    md = hyp.render_markdown(hyp.build(_write_session(tmp_path)))
    assert "Who changed their mind" in md
    assert "Nomsa" in md and "warmer" in md


def test_markdown_says_so_plainly_when_nobody_moved(tmp_path):
    results = [dict(r, stance_changed=False, stance_after=r["stance_before"])
               for r in RESULTS]
    md = hyp.render_markdown(hyp.build(_write_session(tmp_path, results=results)))
    assert "Nobody moved" in md


def test_markdown_never_promises_a_purchase_rate(tmp_path):
    md = hyp.render_markdown(hyp.build(_write_session(tmp_path))).lower()
    for banned in ("would buy", "conversion", "likelihood to buy", "validation score"):
        assert banned not in md
