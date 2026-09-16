"""Controlling a run: stop, pause, resume, close, fork.

The verbs that change what a simulation is doing, as opposed to reading it back.

The actual work belongs to `SimulationRunner`, which owns the subprocess and talks to
it over the IPC channel. What lives here is the part either side of that call: which
status the run should be left in afterwards, and how a fork's agent modifications are
read off a JSON body.

Two behaviours are preserved deliberately rather than tidied:

  * **`stop` leaves the run PAUSED, not STOPPED**, even though both exist in the enum.
    Stopping is recoverable in this app, and the UI treats paused as "can be resumed".
  * **Status is set through the manager, never by writing the file.** The manager's
    save stamps `updated_at`, runs the off-model check, and updates its in-memory
    cache. Writing through the repository would skip all three and leave a stale
    cached state behind.

No Flask.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..utils.logger import get_logger
from .simulation_manager import SimulationManager, SimulationStatus
from .simulation_runner import SimulationRunner

logger = get_logger("fub.simulation_control")


def stop(simulation_id: str) -> Dict[str, Any]:
    """Stop the run and leave it paused, so it can be started again."""
    run_state = SimulationRunner.stop_simulation(simulation_id)
    SimulationManager().set_status(simulation_id, SimulationStatus.PAUSED)
    return run_state.to_dict()


def pause(simulation_id: str) -> Dict[str, Any]:
    """Pause between rounds. The current round finishes first.

    While paused the agents can still be interviewed and intervened with, which is
    the whole point of pausing rather than stopping.
    """
    return SimulationRunner.pause_simulation(simulation_id)


def resume(simulation_id: str) -> Dict[str, Any]:
    """Resume a paused run."""
    return SimulationRunner.resume_simulation(simulation_id)


def close_env(simulation_id: str, timeout: float = 30) -> Dict[str, Any]:
    """Ask the run to shut its environment down gracefully and mark it completed.

    Different from `stop`: this lets the simulation exit on its own terms rather than
    terminating it, so the run is finished rather than parked.
    """
    result = SimulationRunner.close_simulation_env(
        simulation_id=simulation_id, timeout=timeout)
    SimulationManager().set_status(simulation_id, SimulationStatus.COMPLETED)
    return result


def env_status(simulation_id: str) -> Dict[str, Any]:
    """Whether the environment is up and able to answer interview requests."""
    alive = SimulationRunner.check_env_alive(simulation_id)
    detail = SimulationRunner.get_env_status_detail(simulation_id)
    return {
        "simulation_id": simulation_id,
        "env_alive": alive,
        "twitter_available": detail.get("twitter_available", False),
        "reddit_available": detail.get("reddit_available", False),
        "message": ("Environment running, ready to receive interview requests"
                    if alive else "Environment not running or closed"),
    }


def agent_modifications(raw: Optional[Dict[str, Any]]) -> Dict[int, Any]:
    """Read a fork's agent edits off a JSON body.

    JSON object keys are always strings, so they are converted to the int agent ids
    the fork expects. A key that is not a number is skipped rather than failing the
    fork, matching the original.
    """
    out: Dict[int, Any] = {}
    for key, value in (raw or {}).items():
        try:
            out[int(key)] = value
        except (TypeError, ValueError):
            continue
    return out


def fork(simulation_id: str, new_simulation_id: str,
         raw_modifications: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Copy a run under a new id, optionally changing some agents' states.

    `InterviewService.fork_simulation` is synchronous and hands back the new
    directory, so there is no event loop involved here.
    """
    from .interview_service import InterviewService

    modifications = agent_modifications(raw_modifications)
    new_dir = InterviewService(simulation_id).fork_simulation(
        new_simulation_id, modifications)
    return {
        "original_simulation_id": simulation_id,
        "new_simulation_id": new_simulation_id,
        "new_simulation_dir": new_dir,
        "modified_agents": len(modifications),
    }
