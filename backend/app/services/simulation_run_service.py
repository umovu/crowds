"""Creating and starting a simulation — the money path.

Simulations are paid, with a free trial. Three rules keep that honest:

  * **The quota is checked at create, but nothing is charged there.** A user is told
    up front they are out of runs; a sim that is created and never started costs
    nothing.
  * **The credit is charged once, at start.** The persisted `credit_charged` flag makes
    start -> stop -> start cost one credit, and lets an already-charged sim restart
    even after the trial has run out. The flag is saved with the state, so it survives
    a server restart.
  * **The free tier runs the smallest preset** ('quick'), whatever was asked for, to
    bound token spend on a trial sim.

No Flask. A refused quota comes back as `QuotaExceeded` carrying the billing `Gate`;
the controller turns that into the 402 the frontend's upgrade modal listens for.
`tests/test_sim_start_and_credits.py` pins these rules with the LLM off.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..repositories import project_repository
from ..repositories import simulation_repository as repo
from ..utils.logger import get_logger
from . import billing_service, simulation_setup_service
from .sim_presets import SIM_PRESETS, apply_preset
from .simulation_manager import SimulationManager, SimulationStatus
from .simulation_runner import SimulationRunner

logger = get_logger("fub.simulation_run")

#: The only platform the simulation runs on.
PLATFORMS = ("opinion_space",)

#: The preset a free-tier run is held to.
FREE_TIER_PRESET = "quick"


class QuotaExceeded(RuntimeError):
    """The caller's plan does not allow another simulation. Carries the Gate."""

    def __init__(self, gate: Any):
        self.gate = gate
        super().__init__(gate.message)


class ProjectNotFound(LookupError):
    """No such project."""


class RunNotFound(LookupError):
    """No such simulation."""


class NeedsPrepare(RuntimeError):
    """The run is not (or no longer) prepared, so it cannot start."""


class BadRequest(ValueError):
    """Something in the request cannot be used."""


def create(project_id: str, graph_id: Optional[str],
           user_id: Optional[str]) -> Dict[str, Any]:
    """Create a simulation for a project. Charges nothing.

    The quota check happens before this is called; see the module note.
    """
    project = project_repository.get(project_id)
    if not project:
        raise ProjectNotFound(f"Project does not exist: {project_id}")

    graph_id = graph_id or project.graph_id
    if not graph_id:
        raise BadRequest("Project has not built knowledge graph yet, "
                         "please call /api/graph/build first")

    state = SimulationManager().create_simulation(
        project_id=project_id, graph_id=graph_id, user_id=user_id)
    return state.to_dict()


def _max_rounds(value: Any) -> Optional[int]:
    """The requested round cap, validated. None when none was asked for."""
    if value is None:
        return None
    try:
        rounds = int(value)
    except (ValueError, TypeError):
        raise BadRequest("max_rounds Must be valid integer")
    if rounds <= 0:
        raise BadRequest("max_rounds Must be positive integer")
    return rounds


def _ensure_prepared(manager: SimulationManager, state: Any, simulation_id: str,
                     force: bool) -> bool:
    """Confirm the run's files are really there. Returns whether it was force-restarted.

    A READY status is a claim about the files, and it is verified rather than trusted:
    a wiped or partly-restored run directory used to leave a READY run that failed on
    every start with an internal message naming an endpoint the user cannot call. It is
    demoted instead, so the next attempt re-prepares.
    """
    if state.status == SimulationStatus.READY:
        is_prepared, info = simulation_setup_service.check_prepared(simulation_id)
        if not is_prepared:
            logger.warning("Simulation %s claims READY but is not on disk (%s) — "
                           "demoting to CREATED", simulation_id, info.get("reason"))
            state.status = SimulationStatus.CREATED
            state.config_generated = False
            manager.save(state)
            raise NeedsPrepare("This simulation's setup is missing, so it can't start. "
                               "Build it again — nothing was charged.")
        return False

    is_prepared, _ = simulation_setup_service.check_prepared(simulation_id)
    if not is_prepared:
        raise NeedsPrepare("This simulation hasn't finished being set up yet, so "
                           "it can't start. Build it again — nothing was charged.")

    if state.status == SimulationStatus.RUNNING:
        run_state = SimulationRunner.get_run_state(simulation_id)
        if run_state and run_state.runner_status.value == "running":
            if not force:
                raise BadRequest("Simulation is running. Please call /stop first "
                                 "or use force=true to force restart.")
            logger.info(f"Force mode：Stop runningSimulation {simulation_id}")
            try:
                SimulationRunner.stop_simulation(simulation_id)
            except Exception as e:  # noqa: BLE001 - restart goes ahead regardless
                logger.warning(f"Warning when stopping simulation: {str(e)}")

    restarted = False
    if force:
        logger.info(f"Force mode: cleaning simulation runtime files for {simulation_id}")
        cleanup = SimulationRunner.cleanup_simulation_logs(simulation_id)
        if not cleanup.get("success"):
            logger.warning(f"Warning when cleaning logs: {cleanup.get('errors')}")
        restarted = True

    logger.info(f"Simulation {simulation_id} preparation complete, resetting status "
                f"to ready (previous status: {state.status.value})")
    state.status = SimulationStatus.READY
    manager.save(state)
    return restarted


def _apply_overrides(simulation_id: str, root: str, preset: Optional[str],
                     overrides: Dict[str, Any]) -> Optional[int]:
    """Write the preset and tuning overrides into the run's config.

    Returns the preset's round cap, if a preset was applied. A config that cannot be
    read or written is logged and skipped: the run still starts on its own config.
    """
    if not (preset or any(v is not None for v in overrides.values())):
        return None
    config = repo.read_config(simulation_id, root)
    if config is None:
        return None

    rounds = None
    try:
        if preset in SIM_PRESETS:
            rounds, time_overrides = apply_preset(config, preset)
            logger.info(f"Applied preset '{preset}' to config: {simulation_id}, "
                        f"time_config={time_overrides}")
        casts = {"convergence_threshold": float, "convergence_window": int,
                 "max_agents_per_round": int, "min_agents_per_round": int}
        for key, cast in casts.items():
            if overrides.get(key) is not None:
                config[key] = cast(overrides[key])
        repo.write_config(simulation_id, config, root)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Failed to update config with preset params: {e}")
    return rounds


def start(data: Dict[str, Any], user_id: Optional[str]) -> Dict[str, Any]:
    """Start a prepared simulation, charging the credit once. Returns the run state.

    Raises BadRequest (400), RunNotFound (404), QuotaExceeded (402) and
    NeedsPrepare (409). The runner's own ValueError is a 400 as well.
    """
    simulation_id = data.get("simulation_id")
    platform = data.get("platform", "opinion_space")
    enable_graph_memory_update = data.get("enable_graph_memory_update", False)
    force = data.get("force", False)
    max_rounds = _max_rounds(data.get("max_rounds"))

    preset = data.get("preset")
    if billing_service.get_entitlement(user_id).get("plan") != "paid":
        preset = FREE_TIER_PRESET

    if platform not in PLATFORMS:
        raise BadRequest(f"Invalid platform type: {platform}. "
                         "Only 'opinion_space' is supported.")

    manager = SimulationManager()
    state = manager.get_simulation(simulation_id)
    if not state:
        raise RunNotFound(f"Simulation does not exist: {simulation_id}")

    # Only an uncharged run is gated: a restart of a paid-for run is never refused.
    if not state.credit_charged:
        gate = billing_service.check_sim_quota(user_id)
        if not gate.allowed:
            raise QuotaExceeded(gate)

    force_restarted = _ensure_prepared(manager, state, simulation_id, force)

    graph_id = None
    if enable_graph_memory_update:
        graph_id = state.graph_id
        if not graph_id:
            project = project_repository.get(state.project_id)
            graph_id = project.graph_id if project else None
        if not graph_id:
            raise BadRequest("Enable knowledge graph memory update requires valid "
                             "graph_id，Please ensure project graph built")
        logger.info(f"Enable knowledge graph memory update: "
                    f"simulation_id={simulation_id}, graph_id={graph_id}")

    preset_rounds = _apply_overrides(simulation_id, manager.SIMULATION_DATA_DIR, preset, {
        "convergence_threshold": data.get("convergence_threshold"),
        "convergence_window": data.get("convergence_window"),
        "max_agents_per_round": data.get("max_agents_per_round"),
        "min_agents_per_round": data.get("min_agents_per_round"),
    })
    if max_rounds is None and preset_rounds is not None:
        max_rounds = preset_rounds
        logger.info(f"Using max_rounds={max_rounds} from preset")

    run_state = SimulationRunner.start_simulation(
        simulation_id=simulation_id, platform=platform, max_rounds=max_rounds,
        enable_graph_memory_update=enable_graph_memory_update, graph_id=graph_id)

    # Charged only once the run has actually started, and only once ever.
    if not state.credit_charged:
        billing_service.increment_sim_used(user_id)
        state.credit_charged = True

    state.status = SimulationStatus.RUNNING
    manager.save(state)

    out = run_state.to_dict()
    if max_rounds:
        out["max_rounds_applied"] = max_rounds
    out["graph_memory_update_enabled"] = enable_graph_memory_update
    out["force_restarted"] = force_restarted
    if enable_graph_memory_update:
        out["graph_id"] = graph_id
    return out
