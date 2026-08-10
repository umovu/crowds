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

AgenSociety2 (which demands AGENTSOCIETY_LLM_API_KEY) is never imported — the
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
    ("app.api", os.path.join(APP, "api")),
    ("app.services", SERVICES),
    ("app.models", os.path.join(APP, "models")),
    ("app.utils", os.path.join(APP, "utils")),
    ("app.storage", os.path.join(APP, "storage")),
]:
    if pkg_name not in sys.modules:
        m = types.ModuleType(pkg_name)
        m.__path__ = [pkg_path]
        sys.modules[pkg_name] = m

# GraphStorage is never constructed here; stub so the real services import.
sys.modules["app.storage"].GraphStorage = type("GraphStorage", (), {})
# The route's decorator target.
sys.modules["app.api"].simulation_bp = types.SimpleNamespace(route=lambda *a, **k: (lambda f: f))

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

# Stub billing (no Supabase hits) with an in-process sim_used counter.
bill = types.ModuleType("app.billing")
bill._sim_used = 0


def _get_entitlement(uid):
    return {"plan": "free", "sim_used": bill._sim_used}


def _check_sim_quota():
    if _get_entitlement(None).get("plan") == "paid":
        return None
    if int(_get_entitlement(None).get("sim_used", 0) or 0) >= 2:
        return ({"success": False, "error": "used up", "code": "upgrade_required"}, 402)
    return None


def _increment_sim_used(uid):
    bill._sim_used += 1


bill.current_user_id = staticmethod(lambda: "user_test")
bill.get_entitlement = staticmethod(_get_entitlement)
bill.check_sim_quota = staticmethod(_check_sim_quota)
bill.increment_sim_used = staticmethod(_increment_sim_used)
sys.modules["app.billing"] = bill

# Stub the agentsociety2-bound service so importing the routes never boots it.
_iv_stub = types.ModuleType("app.services.interview_service")
_iv_stub.InterviewService = type("InterviewService", (), {})
sys.modules["app.services.interview_service"] = _iv_stub
sys.modules["app.services"].mode_detector = types.ModuleType("app.services.mode_detector")

# Stub the ProjectManager used by /create(+)/start to return a fixed project.
pm = sys.modules["app.models.project"]
pm.ProjectManager.get_project = staticmethod(
    lambda pid: types.SimpleNamespace(graph_id="graph_test", project_id=pid or "proj_test")
)

# Import the routes under test.
sim = _load_app("app.api.simulation", "api/simulation")
SimulationStatus = sim.SimulationStatus

# Never launch a real simulation subprocess in tests.
SimulationRunner.start_simulation = staticmethod(
    lambda simulation_id=None, **kw: types.SimpleNamespace(
        to_dict=lambda: {"simulation_id": simulation_id, "runer_status": "running"}
    )
)
SimulationRunner.get_run_state = staticmethod(lambda sid: None)
SimulationRunner.stop_simulation = staticmethod(lambda sid: None)
SimulationRunner.cleanup_simulation_logs = staticmethod(lambda sid: {"success": True})

# Capture route JSON payloads instead of hitting Flask's render pipeline.
class _Resp:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code


sim.jsonify = lambda payload, status_code=200: _Resp(payload, status_code)


def _fake_request(payload):
    return types.SimpleNamespace(get_json=lambda: payload)


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
    """Drive the real /create route, returning (simulation_id, status_code)."""
    bill._sim_used = sim_used
    sim.request = _fake_request({"project_id": "proj_test", "graph_id": "graph_test"})
    resp = sim.create_simulation()
    data = resp.payload["data"]
    return data["simulation_id"], resp.status_code


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

def test_module_level_json_import_is_bound():
    # Regression guard: the /start preset block previously raised
    # `name 'json' is not defined` because there was no module-level import.
    assert sim.json is not None
    assert callable(sim.json.dumps)


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
    _, status = _create_sim(sim_used=0)
    assert status == 200
    assert bill._sim_used == 0


def test_create_then_start_charges_one():
    sid, _ = _create_sim(sim_used=0)
    _make_prepared(sid)
    sim.request = _fake_request({"simulation_id": sid, "platform": "opinion_space", "preset": "balanced"})
    resp = sim.start_simulation()
    assert resp.status_code == 200
    assert bill._sim_used == 1
    state = SimulationManager().get_simulation(sid)
    assert state.credit_charged is True


def test_start_stop_start_charges_one_total():
    sid, _ = _create_sim(sim_used=0)
    _make_prepared(sid)
    sim.request = _fake_request({"simulation_id": sid, "platform": "opinion_space", "preset": "balanced"})
    assert sim.start_simulation().status_code == 200
    assert bill._sim_used == 1

    # Simulated restart (force=true): the persisted credit_charged guard must
    # stop a second charge.
    sim.request = _fake_request({"simulation_id": sid, "platform": "opinion_space", "preset": "balanced", "force": True})
    assert sim.start_simulation().status_code == 200
    assert bill._sim_used == 1


def test_start_after_quota_exhausted_returns_402():
    sid, _ = _create_sim(sim_used=1)
    _make_prepared(sid)
    bill._sim_used = 2  # trial exhausted
    sim.request = _fake_request({"simulation_id": sid, "platform": "opinion_space", "preset": "quick"})
    resp = sim.start_simulation()
    assert isinstance(resp, tuple) and resp[1] == 402


def test_restart_after_quota_exhausted_still_allowed():
    # A sim already charged keeps running through a restart even when the trial
    # shows exhausted — the guard checks charge state, not the quota.
    sid, _ = _create_sim(sim_used=1)
    _make_prepared(sid)
    sim.request = _fake_request({"simulation_id": sid, "platform": "opinion_space", "preset": "balanced"})
    assert sim.start_simulation().status_code == 200
    bill._sim_used = 2
    sim.request = _fake_request({"simulation_id": sid, "platform": "opinion_space", "preset": "balanced", "force": True})
    resp = sim.start_simulation()
    assert not isinstance(resp, tuple)  # no 402
    assert resp.status_code == 200
    assert bill._sim_used == 2