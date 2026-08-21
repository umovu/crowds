"""LLM-off tests for the pointers layer (backend/app/services/pointers.py).

Pointers are pure dict + string logic — no network, no model, no Flask app.
The only service touched is `panel_service` (for `SEGMENTS` and
`suggest_segments`), which we load dependency-light exactly like
test_library_cast.py does, so AgentSociety2 (which demands
AGENTSOCIETY_LLM_API_KEY) never gets imported.

Pin the contracts the plan cares about:
  * `land` assembly includes the extra lines only when filled, and NEVER lets
    `worry` into the seed.
  * `fit` assembly includes the price line only when given.
  * `missing_required` flags blank requireds and passes filled ones.
  * `route_segments` routes `fit` to FIT_SEGMENTS regardless, auto-routes
    `land` from seed keywords, falls back to ["everyone"], and never raises.
  * every FIT_SEGMENTS key exists in panel_service.SEGMENTS (no silent empty
    cast from a typo).
  * unknown pointer ids are a no-op everywhere, never an exception.
"""

import importlib.util
import json
import os
import sys
import types

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
    spec = importlib.util.spec_from_file_location(modname, os.path.join(APP, *filename.split(".")) + ".py")
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


storage_stub = sys.modules["app.storage"]
storage_stub.GraphStorage = _GraphStorage

_load_app("app.config", "config")
_load("app.services.income_seeder", "income_seeder.py", package="app.services")
_load("app.services.mode_specs", "mode_specs.py", package="app.services")
_load("app.services.persona_library", "persona_library.py", package="app.services")
_load("app.services.persona_retrieval", "persona_retrieval.py", package="app.services")
panel = _load("app.services.panel_service", "panel_service.py", package="app.services")
pointers = _load("app.services.pointers", "pointers.py", package="app.services")


# ── assemble_seed: land ────────────────────────────────────────────────────

def test_land_seed_all_slots_filled():
    seed = pointers.assemble_seed("land", {
        "announcement": "We're moving to R99/month.",
        "audience": "working South Africans",
        "change": "existing users pay the new rate",
        "worry": "people cancel",
    })
    assert "We're moving to R99/month." in seed
    assert "It is aimed at working South Africans." in seed
    assert "For them, this means existing users pay the new rate." in seed


def test_land_seed_only_required_slot():
    seed = pointers.assemble_seed("land", {"announcement": "Just the announcement."})
    assert seed.strip() == "Just the announcement."


def test_land_seed_empty_input_returns_empty():
    assert pointers.assemble_seed("land", {}) == ""
    assert pointers.assemble_seed("land", {"announcement": ""}) == ""


def test_land_seed_never_contains_worry():
    seed = pointers.assemble_seed("land", {
        "announcement": "We're moving to R99/month.",
        "worry": "people cancel",
    })
    assert "cancel" not in seed
    assert "worry" not in seed.lower()


# ── assemble_seed: fit ─────────────────────────────────────────────────────

def test_fit_seed_includes_price_when_given():
    seed = pointers.assemble_seed("fit", {"offer": "Solar kits", "price": "R499 once off"})
    assert "Solar kits" in seed
    assert "It costs R499 once off." in seed


def test_fit_seed_omits_price_line_when_absent():
    seed = pointers.assemble_seed("fit", {"offer": "Solar kits"})
    assert "Solar kits" in seed
    assert "costs" not in seed.lower()


# ── match_single_required / missing_required ───────────────────────────────

def test_missing_required_catches_blank_required():
    missing = pointers.missing_required("land", {"announcement": "  "})
    assert "announcement" in missing


def test_missing_required_passes_filled():
    assert pointers.missing_required("land", {"announcement": "x"}) == []
    assert pointers.missing_required("breaks", {
        "announcement": "x", "worry": "y"}) == []


def test_breaks_worry_is_inferred_not_required():
    # The redesigned flow reads the worry from the sentence (study_reader) —
    # the slot carries it for the summary contract but never forces a typed box.
    assert "worry" not in pointers.missing_required("breaks", {"announcement": "x"})


# ── route_segments ─────────────────────────────────────────────────────────

def test_fit_routes_to_fit_segments_regardless_of_seed():
    assert pointers.route_segments("fit", "anything at all") == pointers.FIT_SEGMENTS
    assert pointers.route_segments("fit", "") == pointers.FIT_SEGMENTS


def test_land_auto_routes_farming_pitch_to_farmers():
    segs = pointers.route_segments("land", "An agri platform for livestock farmers")
    assert "farmers" in segs


def test_land_falls_back_to_everyone_on_generic_text():
    assert pointers.route_segments("land", "a completely generic sentence") == ["everyone"]


# ── vocabulary guard ───────────────────────────────────────────────────────

def test_fit_segments_all_exist_in_panel_segments():
    assert all(s in panel.SEGMENTS for s in pointers.FIT_SEGMENTS)


# ── unknown pointer is always a no-op ──────────────────────────────────────

def test_unknown_pointer_is_a_noop():
    assert pointers.assemble_seed("nope", {"a": "b"}) == ""
    assert pointers.summary_contract("nope") == ""
    assert pointers.route_segments("nope", "text") == []
    assert pointers.missing_required("nope", {}) == []


def test_known_pointers_have_required_slots_and_contracts():
    for pid in pointers.POINTERS:
        assert pointers.POINTERS[pid]["slots"]
        assert pointers.summary_contract(pid)
        assert any(s["required"] for s in pointers.POINTERS[pid]["slots"])


# ── summary_contract worry / guess / decision lines ────────────────────────

def test_land_contract_appends_worry_line_only_when_filled():
    assert "cancel" not in pointers.summary_contract("land")
    c = pointers.summary_contract("land", {"announcement": "x", "worry": "people cancel"})
    assert "people cancel" in c


def test_fit_contract_appends_guess_line():
    c = pointers.summary_contract("fit", {"offer": "x", "guess": "parents"})
    assert "parents" in c


# ── rank_by_segment (the `fit` deliverable, LLM off) ───────────────────────

def _write_session_profiles(session_id, personas):
    sdir = panel.session_dir(session_id)
    os.makedirs(os.path.join(sdir, panel.ROUNDS_DIR), exist_ok=True)
    with open(os.path.join(sdir, panel.PROFILES_FILE), "w") as fh:
        json.dump(personas, fh)
    return sdir


def test_rank_by_segment_groups_by_first_matching_segment():
    sid = "panel_testfit_rank"
    _write_session_profiles(sid, [
        {"id": 0, "name": "A", "actor_archetype": "urban_professional", "age": 40,
         "employment_status": "Employed"},
        {"id": 1, "name": "B", "actor_archetype": "informal_trader", "age": 31,
         "employment_status": "Informal worker"},
        {"id": 2, "name": "C", "actor_archetype": "small_business_owner", "age": 45,
         "employment_status": "Employed"},
    ])
    meta = {"segments": ["professionals", "informal_traders", "small_business"]}
    results = [
        {"agent_id": 0, "agent_name": "A", "stance_after": "for",
         "response": "Good fit"},
        {"agent_id": 1, "agent_name": "B", "stance_after": "against",
         "response": "Too pricey"},
        {"agent_id": 2, "agent_name": "C", "stance_after": "neutral",
         "response": "Maybe"},
    ]
    out = panel.rank_by_segment(sid, meta, results)
    assert len(out) == 3
    by_id = {b["segment_id"]: b for b in out}
    assert by_id["professionals"]["members"][0]["agent_id"] == 0
    assert by_id["informal_traders"]["stance_split"] == {"against": 1}
    assert by_id["small_business"]["members"][0]["response"] == "Maybe"


def test_rank_by_segment_empty_for_single_segment():
    meta = {"segments": ["everyone"]}
    assert panel.rank_by_segment("panel_testfit_rank", meta, [{"agent_id": 0}]) == []
    assert panel.rank_by_segment("panel_testfit_rank", {"segments": ["professionals"]},
                                 [{"agent_id": 0}]) == []


def test_rank_by_segment_reports_empty_segments_explicitly():
    # A group that drew no matching member must not vanish: it shows as an
    # explicit empty row so the UI can say "no one from this group was
    # available" instead of the ranking silently missing a segment.
    sid = "panel_testfit_unmatched"
    _write_session_profiles(sid, [{"id": 0, "name": "A", "actor_archetype": "civic_moderate",
                                   "age": 40, "employment_status": "Employed"}])
    meta = {"segments": ["professionals", "informal_traders"]}
    out = panel.rank_by_segment(sid, meta, [{"agent_id": 0, "agent_name": "A",
                                             "stance_after": "for", "response": "hi"}])
    assert len(out) == 2
    assert all(b["members"] == [] and b["stance_split"] == {} for b in out)


def test_rank_by_segment_orders_most_won_over_first():
    # The ordering IS the `fit` answer: most-won-over first, deterministically,
    # tie-broken by label. Never a model in the loop.
    sid = "panel_testfit_order"
    _write_session_profiles(sid, [
        {"id": 0, "name": "A", "actor_archetype": "urban_professional", "age": 40,
         "employment_status": "Employed"},
        {"id": 1, "name": "B", "actor_archetype": "urban_professional", "age": 41,
         "employment_status": "Employed"},
        {"id": 2, "name": "C", "actor_archetype": "informal_trader", "age": 31,
         "employment_status": "Informal worker"},
        {"id": 3, "name": "D", "actor_archetype": "informal_trader", "age": 32,
         "employment_status": "Informal worker"},
    ])
    meta = {"segments": ["professionals", "informal_traders"]}
    results = [
        {"agent_id": 0, "stance_after": "support", "response": "yes"},
        {"agent_id": 1, "stance_after": "support", "response": "yes"},
        {"agent_id": 2, "stance_after": "oppose", "response": "no"},
        {"agent_id": 3, "stance_after": "concerned", "response": "maybe"},
    ]
    out = panel.rank_by_segment(sid, meta, results)
    assert [o["segment_id"] for o in out] == ["professionals", "informal_traders"]
    assert out[0]["stance_split"] == {"support": 2}


def test_rank_by_segment_fit_shaped_with_too_few_seats_keeps_all_segments():
    # `fit` pins the cast to 12 but a below-12 session (or a small library)
    # leaves some of the six groups empty. Every requested segment must still
    # appear exactly once, empty rows ranking last — the group never vanishes.
    sid = "panel_testfit_shortcast"
    _write_session_profiles(sid, [
        {"id": 0, "name": "A", "actor_archetype": "urban_professional", "age": 40,
         "employment_status": "Employed"},
        {"id": 1, "name": "B", "actor_archetype": "small_business_owner", "age": 45,
         "employment_status": "Employed"},
    ])
    meta = {"segments": pointers.FIT_SEGMENTS}
    results = [
        {"agent_id": 0, "agent_name": "A", "stance_after": "support", "response": "yes"},
        {"agent_id": 1, "agent_name": "B", "stance_after": "oppose", "response": "too dear"},
    ]
    out = panel.rank_by_segment(sid, meta, results)
    assert len(out) == len(pointers.FIT_SEGMENTS)
    assert {o["segment_id"] for o in out} == set(pointers.FIT_SEGMENTS)
    ids = [o["segment_id"] for o in out]
    assert ids[-1] in ("guardians", "informal_traders", "youth", "unemployed")
    empty = [o for o in out if o["members"] == []]
    assert len(empty) == len(pointers.FIT_SEGMENTS) - 2