"""LLM-off tests for the sim-start + credits fix.

Covers local-plans/SIM_START_AND_CREDITS_FIX.md with the LLM switched off:

  * Task 1 — SimulationRunner.RUN_STATE_DIR resolves under Config.DATA_ROOT (the
    mounted volume in prod), not a source-relative path that diverges on hosts
    where DATA_ROOT=/data and made /start 400 on every hosted run.
  * Task 2 — the /start preset path applies the quick/balanced/deep pack to a
    config file on disk (time_config + convergence params + max_rounds), and
    `json` is bound at module import so the old `name 'json' is not defined`
    NameError cannot recur.
  * Task 3 — the sim credit is charged on first start only, never at create:
    create-then-abandon charges 0, create→start charges 1, start→stop→start
    charges 1 (the persisted `credit_charged` guard survives), and starting with
    the trial exhausted returns 402.

The credit rules live in `app.services.simulation_run_service`, so that is what is
tested, directly, with no Flask request involved. AgentSociety2 (which demands
AGENTSOCIETY_LLM_API_KEY) is never imported — the
heavy `interview_service` module is stubbed. Real `SimulationManager` /
`SimulationRunner` / `config` are loaded so path + persistence behaviour is the
real code, with the network subprocess start stubbed out.
"""

import importlib.util
import json as _json
import os
import sys
import tempfile
import types
from flask import Flask

HERE = os.path.dirname(__file__)
APP = os.path.normpath(os.path.join(HERE, "..", "app"))
SERVICES = os.path.join(APP, "services")

# A fresh DATA_ROOT (temp dir) BEFORE config is imported, so the real Config and
# every class-level path derived from it resolve into our temp root. If another
# test module already registered app.config with the default root, force a reload.
_DATA_ROOT = tempfile.mkdtemp(prefix="fub_simfix_")
os.environ["DATA_ROOT"] = _DATA_ROOT
if "app.config" in sys.modules:
    del sys.modules["app.config"]


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


# Package skeletons so relative imports resolve without running the heavy
# app.services.__init__ (which requires agentsociety2's env vars).
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

# GraphStorage is never constructed here; stub so the real services import.
sys.modules["app.storage"].GraphStorage = type("GraphStorage", (), {})
# Real modules under test.
config = _load_app("app.config", "config")
Config = config.Config
_load("app.services.sim_presets", "sim_presets.py", package="app.services")
from app.services.sim_presets import SIM_PRESETS, apply_preset  # noqa: E402

_load("app.services.simulation_manager", "simulation_manager.py", package="app.services")
from app.services.simulation_manager import SimulationManager  # noqa: E402

_load("app.services.simulation_runner", "simulation_runner.py", package="app.services")
from app.services.simulation_runner import SimulationRunner  # noqa: E402

_load_app("app.models.project", "models/project")

# Stub billing (no Supabase hits) with an in-process sim_used counter. The routes now
# read the caller from app.auth, ask app.controllers.gates for the 402, and count usage
# through app.services.billing_service, so all three are stubbed. `bill._sim_used` stays
# the counter these tests assert on.
bill = types.ModuleType("app.services.billing_service")
bill._sim_used = 0


def _get_entitlement(uid):
    return {"plan": "free", "sim_used": bill._sim_used}


def _increment_sim_used(uid):
    bill._sim_used += 1


def _check_sim_quota(uid):
    """Same answer as the real check: allowed, or a refusal with the upgrade code."""
    ent = _get_entitlement(uid)
    if ent.get("plan") != "paid" and int(ent.get("sim_used", 0) or 0) >= 2:
        return types.SimpleNamespace(allowed=False, message="used up",
                                     code="upgrade_required")
    return types.SimpleNamespace(allowed=True, message="", code="upgrade_required")


bill.get_entitlement = staticmethod(_get_entitlement)
bill.increment_sim_used = staticmethod(_increment_sim_used)
bill.check_sim_quota = staticmethod(_check_sim_quota)
sys.modules["app.services.billing_service"] = bill
sys.modules["app.services"].billing_service = bill

# Stub the agentsociety2-bound service so importing the routes never boots it.
_iv_stub = types.ModuleType("app.services.interview_service")
_iv_stub.InterviewService = type("InterviewService", (), {})
sys.modules["app.services.interview_service"] = _iv_stub
sys.modules["app.services"].mode_detector = types.ModuleType("app.services.mode_detector")

# Stub the project lookup used by /create(+)/start to return a fixed project.
# Project storage moved to app.repositories.project_repository, so that is what the
# routes call now.
_projects = types.ModuleType("app.repositories.project_repository")
_projects.get = staticmethod(
    lambda pid: types.SimpleNamespace(graph_id="graph_test", project_id=pid or "proj_test")
)
_repos = sys.modules.get("app.repositories") or types.ModuleType("app.repositories")
_repos.__path__ = [os.path.join(APP, "repositories")]
_repos.project_repository = _projects
sys.modules["app.repositories"] = _repos
sys.modules["app.repositories.project_repository"] = _projects

# The service under test, and the readiness check it relies on.
_load("app.services.simulation_setup_service", "simulation_setup_service.py", package="app.services")
run = _load("app.services.simulation_run_service", "simulation_run_service.py", package="app.services")

# Never launch a real simulation subprocess in tests.
SimulationRunner.start_simulation = staticmethod(
    lambda simulation_id=None, **kw: types.SimpleNamespace(
        to_dict=lambda: {"simulation_id": simulation_id, "runer_status": "running"}
    )
)
SimulationRunner.get_run_state = staticmethod(lambda sid: None)
SimulationRunner.stop_simulation = staticmethod(lambda sid: None)
SimulationRunner.cleanup_simulation_logs = staticmethod(lambda sid: {"success": True})

def _sim_dir(sid):
    return os.path.join(Config.OASIS_SIMULATION_DATA_DIR, sid)


def _make_prepared(sid):
    """Write the files /start's prepared-check + preset block need."""
    d = _sim_dir(sid)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "state.json"), "w", encoding="utf-8") as f:
        _json.dump({"status": "ready", "config_generated": True}, f)
    with open(os.path.join(d, "simulation_config.json"), "w", encoding="utf-8") as f:
        _json.dump({"simulation_requirement": "test", "time_config": {"total_simulation_hours": 1, "minutes_per_round": 60}}, f)
    with open(os.path.join(d, "agentsociety_profiles.json"), "w", encoding="utf-8") as f:
        _json.dump([], f)


def _create_sim(sim_used=0):
    """Create a sim through the real service, returning its id."""
    bill._sim_used = sim_used
    return run.create("proj_test", "graph_test", "user_test")["simulation_id"]


def _start(sid, preset="balanced", force=False):
    body = {"simulation_id": sid, "platform": "opinion_space", "preset": preset}
    if force:
        body["force"] = True
    return run.start(body, "user_test")


# ── Task 1: SimulationRunner writes run state under DATA_ROOT ───────────────

def test_run_state_dir_lives_under_data_root():
    assert SimulationRunner.RUN_STATE_DIR == Config.OASIS_SIMULATION_DATA_DIR
    assert SimulationRunner.RUN_STATE_DIR == os.path.join(Config.DATA_ROOT, "uploads", "simulations")
    assert os.path.normpath(SimulationRunner.RUN_STATE_DIR).startswith(
        os.path.normpath(_DATA_ROOT)
    )


def test_scripts_dir_stays_source_relative():
    # SCRIPTS_DIR ships with the code, not the volume — it must NOT move to DATA_ROOT.
    assert os.path.abspath(SimulationRunner.SCRIPTS_DIR) != SimulationRunner.RUN_STATE_DIR
    assert "backend" in SimulationRunner.SCRIPTS_DIR.replace("\\", "/")


# ── Task 2: preset block writes time_config to disk; json is bound ─────────

def test_start_writes_the_preset_to_disk_and_holds_free_tier_to_quick():
    # The preset block used to crash with `name 'json' is not defined`. It now lives
    # in the service and writes through the repository; this proves the write lands,
    # and that a free-tier run is held to the smallest preset whatever it asked for.
    sid = _create_sim(sim_used=0)
    _make_prepared(sid)
    out = _start(sid, preset="deep")
    with open(os.path.join(_sim_dir(sid), "simulation_config.json"), encoding="utf-8") as f:
        cfg = _json.load(f)
    quick = SIM_PRESETS["quick"]
    assert cfg["time_config"]["total_simulation_hours"] == quick["time_config"]["total_simulation_hours"]
    assert cfg["max_agents_per_round"] == quick["max_agents_per_round"]
    assert out["max_rounds_applied"] == quick["max_rounds"]


def test_apply_preset_writes_time_config_to_disk(tmp_path):
    sid = "sim_preset_test"
    config_path = os.path.join(tmp_path, "simulation_config.json")
    file_root = os.path.join(tmp_path, sid)
    os.makedirs(file_root, exist_ok=True)

    # Stand in for the route's preset block, which reads config, applies the
    # preset, and writes it back under Config.OASIS_SIMULATION_DATA_DIR.
    with open(config_path, "w", encoding="utf-8") as f:
        _json.dump({"time_config": {"total_simulation_hours": 1, "minutes_per_round": 60}}, f)
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = _json.load(f)
    max_rounds, time_ov = apply_preset(cfg, "deep")
    assert max_rounds == 24
    assert time_ov == {"total_simulation_hours": 24, "minutes_per_round": 60}
    with open(config_path, "w", encoding="utf-8") as f:
        _json.dump(cfg, f)

    on_disk = _json.load(open(config_path, encoding="utf-8"))
    assert on_disk["time_config"]["total_simulation_hours"] == 24
    assert on_disk["time_config"]["minutes_per_round"] == 60
    assert on_disk["convergence_threshold"] == SIM_PRESETS["deep"]["convergence_threshold"]
    assert on_disk["max_agents_per_round"] == SIM_PRESETS["deep"]["max_agents_per_round"]


def test_apply_preset_matches_table_for_all_presets():
    for name, pack in SIM_PRESETS.items():
        cfg = {"time_config": {"total_simulation_hours": 0, "minutes_per_round": 0}}
        max_rounds, _ = apply_preset(cfg, name)
        assert max_rounds == pack["max_rounds"]
        assert cfg["time_config"]["total_simulation_hours"] == pack["time_config"]["total_simulation_hours"]
        assert cfg["time_config"]["minutes_per_round"] == pack["time_config"]["minutes_per_round"]
        assert cfg["convergence_threshold"] == pack["convergence_threshold"]
        assert cfg["convergence_window"] == pack["convergence_window"]
        assert cfg["max_agents_per_round"] == pack["max_agents_per_round"]
        assert cfg["min_agents_per_round"] == pack["min_agents_per_round"]


def test_apply_preset_unknown_is_noop():
    cfg = {"time_config": {}}
    max_rounds, time_ov = apply_preset(cfg, "bogus")
    assert max_rounds is None
    assert time_ov == {}
    assert cfg["time_config"] == {}


# ── Task 3: credit charged at /start, once, never at /create ───────────────

def test_create_then_abandon_charges_zero():
    _create_sim(sim_used=0)
    assert bill._sim_used == 0


def test_create_then_start_charges_one():
    sid = _create_sim(sim_used=0)
    _make_prepared(sid)
    _start(sid)
    assert bill._sim_used == 1
    state = SimulationManager().get_simulation(sid)
    assert state.credit_charged is True


def test_start_stop_start_charges_one_total():
    sid = _create_sim(sim_used=0)
    _make_prepared(sid)
    _start(sid)
    assert bill._sim_used == 1

    # Simulated restart (force=true): the persisted credit_charged guard must
    # stop a second charge.
    _start(sid, force=True)
    assert bill._sim_used == 1


def test_start_after_quota_exhausted_is_refused():
    sid = _create_sim(sim_used=1)
    _make_prepared(sid)
    bill._sim_used = 2  # trial exhausted
    try:
        _start(sid, preset="quick")
    except run.QuotaExceeded as e:
        # The controller answers this with a 402 carrying the upgrade code.
        assert e.gate.code == "upgrade_required"
    else:
        raise AssertionError("expected the exhausted trial to refuse the start")
    assert bill._sim_used == 2  # nothing charged for a refused start


def test_restart_after_quota_exhausted_still_allowed():
    # A sim already charged keeps running through a restart even when the trial
    # shows exhausted — the guard checks charge state, not the quota.
    sid = _create_sim(sim_used=1)
    _make_prepared(sid)
    _start(sid)
    bill._sim_used = 2
    _start(sid, force=True)  # no QuotaExceeded
    assert bill._sim_used == 2
