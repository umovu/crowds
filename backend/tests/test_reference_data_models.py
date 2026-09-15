"""Data files we maintain by hand fit their models in app/data/model. LLM-off.

These files feed money (grant amounts become known income and budget tiers), the
shared world every agent sees (costs, scheduled events) and how answers are read
(complaint and pitch word lists). A typo in one changes results without any error.
"""

import copy
import glob
import importlib.util
import json
import os
import re

import pytest

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

_spec = importlib.util.spec_from_file_location(
    "data_model_for_reference_tests", os.path.join(BACKEND, "app", "services", "data_model.py"))
dm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dm)

FILES = {
    "grant_schedule": "data/sa_grant_amounts.json",
    "world_facts": "app/data/sa_world_facts.json",
    "event_rules": "app/config/event_rules.json",
    "b2b_sectors": "app/data/persona_library/b2b_sectors.json",
    "b2b_functions": "app/data/persona_library/b2b_functions.json",
    "objection_vocab": "app/data/objection_vocab.json",
    "pitch_parts": "app/data/pitch_parts.json",
}


def _load(name):
    with open(os.path.join(BACKEND, *FILES[name].split("/")), encoding="utf-8") as fh:
        return json.load(fh)


def _source(rel):
    with open(os.path.join(BACKEND, *rel.split("/")), encoding="utf-8") as fh:
        return fh.read()


@pytest.mark.parametrize("name", sorted(FILES))
def test_each_reference_file_fits_its_model(name):
    assert dm.model_problems(name, _load(name)) == []
    assert dm.load(name)["stored_in"] == f"backend/{FILES[name]}"


# ── grants: real money ─────────────────────────────────────────────────────

def test_the_fallback_grant_exists():
    assert "generic" in _load("grant_schedule")["grants"]


def test_every_grant_the_detector_can_return_is_in_the_schedule():
    from app.services.income_seeder import _match_grant_type, detect_grant
    grants = set(_load("grant_schedule")["grants"])
    for spec in _load("grant_schedule")["grants"].values():
        for word in spec["keywords"]:
            assert _match_grant_type(word) in grants
    assert detect_grant(actor_archetype="grant_dependent_survivor")[1] in grants


def test_grant_types_saved_on_room_seats_are_real_grants():
    grants = set(_load("grant_schedule")["grants"])
    files = glob.glob(os.path.join(BACKEND, "uploads", "panel_sessions", "*", "agentsociety_profiles.json"))
    if not files:
        pytest.skip("no saved rooms")
    seen = set()
    for path in files:
        with open(path, encoding="utf-8") as fh:
            seen |= {s["grant_type"] for s in json.load(fh) if s.get("grant_type")}
    assert seen <= grants


# ── world facts ────────────────────────────────────────────────────────────

def test_each_world_fact_item_appears_once():
    items = [f["item"] for f in _load("world_facts")["facts"]]
    assert len(items) == len(set(items))


def test_promoting_a_fact_keeps_the_file_on_model(tmp_path):
    from app.services import world_facts
    path = tmp_path / "facts.json"
    path.write_text(json.dumps(_load("world_facts")), encoding="utf-8")
    world_facts.promote_fact("bread_loaf", 18.5, "R/loaf", source="Stats SA", as_of="2026-06", path=str(path))
    assert dm.model_problems("world_facts", json.loads(path.read_text(encoding="utf-8"))) == []


# ── event rules ────────────────────────────────────────────────────────────

def test_rule_ids_are_unique():
    ids = [r["id"] for r in _load("event_rules")["rules"]]
    assert len(ids) == len(set(ids))


def test_trigger_types_are_exactly_what_the_engine_evaluates():
    handled = set(re.findall(r'trigger_type == "(\w+)"', _source("app/services/event_rule_engine.py")))
    assert set(dm.load("event_rules")["fields"]["rules"]["items"]["fields"]["trigger"]["fields"]["type"]["allowed"]) == handled


def test_the_engine_loads_every_policy_rule():
    from app.services.event_rule_engine import EventRuleEngine
    rules = _load("event_rules")["rules"]
    policy = [r for r in rules if "policy" in (r.get("applies_to_modes") or ["policy"])]
    assert len(EventRuleEngine(mode="policy").rules) == len(policy)


# ── b2b and word lists ─────────────────────────────────────────────────────

def test_b2b_sectors_name_real_jobs_survey_industries():
    industries = set(dm.load("persona")["fields"]["industry"]["allowed"])
    unknown = {s["qlfs_industry"] for s in _load("b2b_sectors")["sectors"].values()} - industries
    assert not unknown


def test_objection_module_tables_match_the_file():
    from app.services import objections
    vocab = _load("objection_vocab")
    assert set(objections.READING_WALL_TYPES) == set(vocab["walls"])
    assert set(objections.PULL_TYPES) == set(vocab["pulls"])


# ── the checker catches the mistakes it exists for ────────────────────────

def _flags(name, data, text):
    return any(text in p for p in dm.model_problems(name, data))


def test_a_zero_grant_amount_is_caught():
    data = copy.deepcopy(_load("grant_schedule"))
    data["grants"]["child_support"]["monthly_amount"] = 0
    assert _flags("grant_schedule", data, "below 1")


def test_a_fact_with_an_unknown_provenance_is_caught():
    data = copy.deepcopy(_load("world_facts"))
    data["facts"][0]["provenance"] = "guess"
    assert _flags("world_facts", data, "'guess'")


def test_a_trigger_the_engine_cannot_evaluate_is_caught():
    data = copy.deepcopy(_load("event_rules"))
    data["rules"][0]["trigger"]["type"] = "vibes"
    assert _flags("event_rules", data, "'vibes'")


def test_a_capitalised_pitch_word_is_caught():
    data = copy.deepcopy(_load("pitch_parts"))
    data["parts"]["health"]["words"].append("Clinic")
    assert _flags("pitch_parts", data, "does not look right")


# ── the app says so ───────────────────────────────────────────────────────

def test_the_event_engine_warns_about_an_off_model_rules_file(tmp_path, monkeypatch):
    from app.services import event_rule_engine as ere
    data = copy.deepcopy(_load("event_rules"))
    data["rules"][0]["event"]["severity"] = "extreme"
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    warnings = []
    monkeypatch.setattr(ere.logger, "warning", lambda msg, *a: warnings.append(msg % a if a else msg))
    engine = ere.EventRuleEngine(rules_path=str(path), mode="policy")
    assert engine.rules
    assert any("'extreme'" in w for w in warnings)


def test_world_facts_warn_about_an_off_model_file(tmp_path, monkeypatch):
    from app.services import world_facts
    data = copy.deepcopy(_load("world_facts"))
    data["facts"][0]["provenance"] = "guess"
    path = tmp_path / "facts.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    warnings = []
    monkeypatch.setattr(world_facts.logger, "warning", lambda msg, *a: warnings.append(msg % a if a else msg))
    world_facts.load_facts(str(path))
    assert any("'guess'" in w for w in warnings)
