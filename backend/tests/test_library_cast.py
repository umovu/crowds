"""Unit tests for the simulation library cast flow (LLM off).

The simulation prepare path no longer generates personas from graph entities —
it draws a cast from the curated, survey-grounded persona library, optionally
mixed with the user's custom agents. These tests pin the LLM-free contract:

  * cast size is DEFAULT_MAIN_CAST_SIZE, capped at MAX_CAST_SIZE
  * library personas carry source_entity_type="library_persona"
  * the leak guard refuses research/graph-authored identities sneaking in
  * custom agents override library personas by name and survive the merge
  * merge_profiles returns plain dicts so the result is JSON-serializable
  * select_for_query returns n library personas with a spread of archetypes
  * the simulation_manager's cast path exposes the right pieces and stamps
    deterministic economic fields (in product mode)

These run with the LLM switched OFF — they are the primary safety net for the
library-cast refactor and must stay assertable without a model. We load the
dependency-light modules directly (mirrors test_mode_detector.py) to avoid
the heavy app.services __init__ which requires agentsociety2's env vars.
"""

import importlib.util
import json
import os
import sys
import types
from typing import Any, Dict, List

HERE = os.path.dirname(__file__)
APP = os.path.normpath(os.path.join(HERE, "..", "app"))
SERVICES = os.path.join(APP, "services")


def _load(modname, filename, package=None):
    # If a previous import already registered this module (e.g. custom_parser
    # doing `from .agent_profile_generator import X` triggers it), reuse that
    # instance — otherwise we end up with two copies of the same class and
    # isinstance() checks fail.
    if modname in sys.modules:
        return sys.modules[modname]
    spec = importlib.util.spec_from_file_location(modname, os.path.join(SERVICES, filename))
    mod = importlib.util.module_from_spec(spec)
    if package:
        mod.__package__ = package
    sys.modules[modname] = mod
    # Register as an attribute on the parent package so sibling relative
    # imports (`from .x import Y`) find THIS module object, not a fresh copy.
    if package and package in sys.modules:
        setattr(sys.modules[package], modname.rsplit(".", 1)[-1], mod)
    spec.loader.exec_module(mod)
    return mod


def _load_app(modname, filename):
    """Load an app.models / app.config module that uses relative imports
    (we register it under its real dotted name so those imports resolve)."""
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


# Stand up `app`, `app.services`, `app.config`, `app.models` skeletons so
# relative imports inside the loaded modules resolve without dragging in
# the heavy __init__ chains that need LLM env vars.
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

# Stub GraphStorage in app.storage so custom_agent_parser can import
# agent_profile_generator → entity_reader without booting the real storage
# stack (Neo4j / Ladybug / embeddings). The cast path never touches it.
class _GraphStorage:  # placeholder; LLM-off tests don't construct one
    pass
storage_stub = sys.modules["app.storage"]
storage_stub.GraphStorage = _GraphStorage

# Order matters: dependencies must land in sys.modules before dependents.
# agent_profile_generator → custom_agent_parser (the parser does a relative
# import of AgentProfile). Pre-register the class on the parent package
# so isinstance() checks against AgentProfile see the same class object.
_load_app("app.config", "config")
_load("app.services.income_seeder", "income_seeder.py", package="app.services")
_load("app.services.mode_specs", "mode_specs.py", package="app.services")
_load("app.services.persona_library", "persona_library.py", package="app.services")
_load("app.services.persona_retrieval", "persona_retrieval.py", package="app.services")
profile_gen = _load("app.services.agent_profile_generator", "agent_profile_generator.py", package="app.services")
custom_parser = _load("app.services.custom_agent_parser", "custom_agent_parser.py", package="app.services")
panel = _load("app.services.panel_service", "panel_service.py", package="app.services")


# ── constants ─────────────────────────────────────────────────────────────

def test_default_main_cast_size_is_24():
    assert panel.MAX_CAST_SIZE == 50
    # DEFAULT_MAIN_CAST_SIZE lives on the manager; we can only assert it once
    # the manager is importable. Here we sanity-check the panel max which is
    # what constrains the main-sim cast's n.
    from app.services.simulation_manager import DEFAULT_MAIN_CAST_SIZE
    assert DEFAULT_MAIN_CAST_SIZE == 24
    assert DEFAULT_MAIN_CAST_SIZE <= panel.MAX_CAST_SIZE


# ── assert_library_cast (leak guard) ───────────────────────────────────────

def test_clean_library_cast_accepted():
    panel.assert_library_cast([
        {"name": "A", "source_entity_type": panel.LIBRARY_PROVENANCE},
        {"name": "B", "source_entity_type": None},  # unset is treated as library
    ])


def test_non_library_identity_refused():
    raised = False
    try:
        panel.assert_library_cast([
            {"name": "Thandeka", "source_entity_type": panel.LIBRARY_PROVENANCE},
            {"name": "Thuto.io", "source_entity_type": "Organization"},
        ])
    except ValueError as e:
        raised = "non-library" in str(e)
    assert raised, "expected the leak guard to refuse research/graph identities"


def test_empty_cast_does_not_raise():
    # Nothing to leak in; trivially clean.
    panel.assert_library_cast([])


def test_custom_provenance_refused_by_guard():
    # The guard's contract is library-ONLY. Customs carry their own
    # provenance (e.g. "custom_manual"), which the guard refuses by design —
    # customs are merged in AFTER the guard runs (on the library portion),
    # so a customs list never goes through it.
    raised = False
    try:
        panel.assert_library_cast([
            {"name": "Custom Brand Voice", "source_entity_type": "custom_manual"},
        ])
    except ValueError as e:
        raised = "non-library" in str(e)
    assert raised, "guard must refuse non-library provenance (customs are checked elsewhere)"


# ── _build_profile: provenance + product economics ────────────────────────

def test_build_profile_stamps_library_provenance():
    p = panel._build_profile(
        {"id": "x1", "name": "Test"}, agent_id=0, mode="policy",
    )
    assert p["source_entity_type"] == panel.LIBRARY_PROVENANCE
    assert p["library_id"] == "x1"
    assert p["id"] == 0
    assert p["stance"] == "neutral"
    assert p["is_institutional"] is False


def test_build_profile_policy_mode_no_budget_fields():
    p = panel._build_profile({"id": "x1", "name": "Test"}, 0, "policy")
    # Policy mode must NOT add budget_tier — that's a product-mode lens
    assert "budget_tier" not in p


def test_build_profile_product_mode_has_budget_tier():
    p = panel._build_profile(
        {"id": "x1", "name": "Test", "actor_archetype": "budget_holder"},
        0, "product",
    )
    # budget_tier is computed from real persona data only, never the LLM
    assert p["budget_tier"] in ("tight", "moderate", "loose")


def test_build_profile_product_mode_respects_household_income_override():
    # Real GHS household income beats archetype inference (rules in mode_specs.budget_tier)
    p_loose = panel._build_profile(
        {"id": "x1", "name": "Rich Early Adopter",
         "actor_archetype": "early_adopter", "monthly_household_income_rand": 2000},
        0, "product",
    )
    assert p_loose["budget_tier"] == "tight"


def test_build_profile_does_not_mutate_input():
    src = {"id": "orig", "name": "Keep", "actor_archetype": "civic_moderate"}
    snapshot = dict(src)
    panel._build_profile(src, 5, "policy")
    assert src == snapshot


# ── select_for_query: size, spread, determinism ───────────────────────────

def test_select_for_query_returns_n_personas():
    from app.services.persona_retrieval import select_for_query
    library = panel.get_library()
    assert not library.is_empty(), "library must be populated for this test"
    cast = select_for_query(12, "a community grant program", library=library, seed=7)
    assert len(cast) == 12


def test_select_for_query_is_deterministic_for_seed():
    from app.services.persona_retrieval import select_for_query
    library = panel.get_library()
    a = select_for_query(8, "transport subsidy in Gauteng", library=library, seed=42)
    b = select_for_query(8, "transport subsidy in Gauteng", library=library, seed=42)
    assert [p.get("id") for p in a] == [p.get("id") for p in b]


def test_select_for_query_has_anti_echo_chamber_spread():
    from app.services.persona_retrieval import select_for_query
    library = panel.get_library()
    cast = select_for_query(15, "general policy announcement", library=library, seed=1)
    distinct_archetypes = {p.get("actor_archetype") for p in cast}
    # persona_retrieval enforces a MIN_DISTINCT_ARCHETYPES floor
    assert len(distinct_archetypes) >= 4


# ── merge_profiles: custom override, dict output, JSON-safe ───────────────

def _agent_profile(name, **kw):
    """Build a minimal AgentProfile (dataclass) for the parser tests."""
    return profile_gen.AgentProfile(
        id=0,  # will be reassigned by merge
        name=name,
        persona=f"a {name}",
        background_story="",
        source_entity_type="custom_manual",
        stance=kw.get("stance"),
        actor_archetype=kw.get("actor_archetype"),
        is_core_focus=kw.get("is_core_focus", False),
    )


def test_merge_profiles_empty_customs_returns_auto_dicts():
    autos = [{"id": 0, "name": "LibA"}, {"id": 1, "name": "LibB"}]
    out = custom_parser.CustomAgentParser.merge_profiles(autos, [])
    assert isinstance(out, list)
    assert all(isinstance(p, dict) for p in out)
    assert [p["name"] for p in out] == ["LibA", "LibB"]


def test_merge_profiles_custom_overrides_auto_by_name():
    auto = [{"id": 0, "name": "Thandi", "stance": "neutral"}]
    custom = [_agent_profile("Thandi", stance="oppose", actor_archetype="skeptic")]
    out = custom_parser.CustomAgentParser.merge_profiles(auto, custom)
    assert len(out) == 1
    assert out[0]["name"] == "Thandi"
    # Custom data must win
    assert out[0]["stance"] == "oppose"
    assert out[0]["actor_archetype"] == "skeptic"
    assert out[0]["source_entity_type"] == "custom_manual"


def test_merge_profiles_appends_unique_customs():
    auto = [{"id": 0, "name": "LibA"}]
    custom = [_agent_profile("Custom1"), _agent_profile("Custom2")]
    out = custom_parser.CustomAgentParser.merge_profiles(auto, custom)
    names = [p["name"] for p in out]
    assert names == ["LibA", "Custom1", "Custom2"]
    # IDs reassigned 0..N-1
    assert [p["id"] for p in out] == [0, 1, 2]


def test_merge_profiles_renumbers_ids_sequentially():
    auto = [{"id": 7, "name": "X"}, {"id": 9, "name": "Y"}]
    custom = [_agent_profile("Z")]
    out = custom_parser.CustomAgentParser.merge_profiles(auto, custom)
    assert [p["id"] for p in out] == [0, 1, 2]


def test_merge_profiles_output_is_json_serializable():
    # The simulation_manager json.dumps the result. If merge returned any
    # AgentProfile dataclass instances, the write would crash with
    # `TypeError: Object of type AgentProfile is not JSON serializable`.
    auto = [{"id": 0, "name": "LibA"}]
    custom = [_agent_profile("Custom1", is_core_focus=True)]
    out = custom_parser.CustomAgentParser.merge_profiles(auto, custom)
    s = json.dumps(out, default=str)  # default=str catches anything weird
    parsed = json.loads(s)
    assert parsed[0]["name"] == "LibA"
    assert parsed[1]["is_core_focus"] is True


def test_merge_profiles_handles_dict_customs():
    # Defensive: callers may already pass dicts on the custom side.
    auto = [{"id": 0, "name": "LibA"}]
    custom = [{"id": 99, "name": "Custom1", "source_entity_type": "custom_manual"}]
    out = custom_parser.CustomAgentParser.merge_profiles(auto, custom)
    assert out[0]["name"] == "LibA"
    assert out[1]["name"] == "Custom1"


def test_merge_profiles_rejects_unknown_type():
    auto = []
    custom = ["not-a-profile"]  # str
    try:
        custom_parser.CustomAgentParser.merge_profiles(auto, custom)
    except TypeError:
        return
    raise AssertionError("expected TypeError for unknown profile type")


# ── panel cast shape (the path the manager imports) ───────────────────────

def test_panel_cast_is_all_library_sourced():
    # A panel cast goes through the same _build_profile + assert_library_cast
    # the manager uses; it must be 100% library by construction.
    meta = panel.create_session(pitch="a new policy", mode="policy", n=8, seed=3)
    assert meta["cast_size"] == 8
    sess_dir = panel.session_dir(meta["session_id"])
    profiles_path = os.path.join(sess_dir, panel.PROFILES_FILE)
    with open(profiles_path, "r", encoding="utf-8") as f:
        profiles = json.load(f)
    # Every member is library-provenanced
    for p in profiles:
        assert p.get("library_id"), f"cast member missing library_id: {p.get('name')}"
    panel.delete_session(meta["session_id"])


# ── simulation_manager surface (source-level checks) ─────────────────────
# We don't import the manager (its module pulls the heavy app.services
# __init__ which needs a live LLM env). The contract is structural — these
# checks pin the prepare flow's source to the right symbols/calls so a
# future refactor can't silently break the cast pipeline.

def _read_manager_source() -> str:
    with open(os.path.join(SERVICES, "simulation_manager.py"), "r", encoding="utf-8") as f:
        return f.read()


def test_simulation_manager_defines_required_symbols():
    src = _read_manager_source()
    assert "DEFAULT_MAIN_CAST_SIZE = 24" in src, "DEFAULT_MAIN_CAST_SIZE = 24 missing"
    assert "class SimulationManager" in src
    assert "def prepare_simulation" in src


def test_simulation_manager_imports_panel_helpers():
    # The manager imports the panel helpers — make sure the link is in place.
    # LIBRARY_PROVENANCE is stamped by panel_service._build_profile, so the
    # manager doesn't reference the constant directly.
    src = _read_manager_source()
    assert "_build_profile" in src
    assert "assert_library_cast" in src
    assert "MAX_CAST_SIZE" in src
    assert "select_for_query" in src
    assert "get_library" in src


def test_simulation_manager_calls_assert_library_guard():
    # The leak guard must run on the LIBRARY portion only, before any
    # custom merge — customs legitimately carry non-library provenance.
    src = _read_manager_source()
    guard_idx = src.find("assert_library_cast(library_profiles)")
    merge_idx = src.find("CustomAgentParser.merge_profiles(library_profiles, custom_profiles)")
    assert guard_idx > 0, "assert_library_cast(library_profiles) call missing"
    assert merge_idx > 0, "merge_profiles(library_profiles, custom_profiles) call missing"
    assert guard_idx < merge_idx, "leak guard must run BEFORE the custom merge"


def test_simulation_manager_passes_empty_entities_to_config():
    # The cast is library personas, not graph entities — config gen gets [].
    src = _read_manager_source()
    assert "entities=[]" in src, "config gen should be called with entities=[]"


def test_simulation_manager_sets_entities_count_to_cast_size():
    # The status endpoint's "expected count" must converge to the cast size,
    # not the (now meaningless) graph entity count.
    src = _read_manager_source()
    assert "state.entities_count = len(profiles)" in src


def test_simulation_manager_zero_entities_does_not_hard_fail():
    # The graph is now CONTEXT only. An empty graph must NOT abort prepare
    # — the library cast still gives the sim a full room.
    src = _read_manager_source()
    assert "filtered.filtered_count == 0" in src
    # Find the block; make sure the warn+continue path is the only branch
    block_start = src.find("if filtered.filtered_count == 0:")
    assert block_start > 0
    # Walk to the next blank-line-separated paragraph
    block_end = src.find("\n\n", block_start)
    block = src[block_start:block_end]
    assert "raise" not in block, "zero-entity path must NOT raise — it should warn + continue"
