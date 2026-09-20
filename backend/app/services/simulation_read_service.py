"""Reading a simulation back: history, cost, and live progress.

The rules behind the read-only simulation screens. Three jobs:

  * `history` — the saved-run list the home screen shows, with the project name,
    round counts and the report each run produced folded in.
  * `cost_breakdown` — what a run spent, in dollars and rand. The token counts come
    from the repository; turning them into money is the rule that lives here.
  * `profiles_progress` / `config_progress` — what the live progress screens poll
    while a run is still being prepared. They answer "is it still working, and how
    far has it got", derived from the state file rather than guessed.

No Flask. The caller passes the user id, since only a request knows who is asking.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..config import Config
from ..repositories import project_repository, report_repository
from ..repositories import simulation_repository as repo
from ..utils.logger import get_logger
from .simulation_manager import SimulationManager
from .simulation_runner import SimulationRunner

logger = get_logger("fub.simulation_read")

#: Stamped on every history row so the UI can tell old saved runs from new ones.
HISTORY_VERSION = "v1.0.2"

#: Rand per dollar. A display convenience on top of the real USD figure, not a
#: live rate — the USD number is the one the provider actually bills.
ZAR_PER_USD = 18.5

#: Fallback prices per million tokens, used only when the config names none.
DEFAULT_PRICE_PROMPT = 0.14
DEFAULT_PRICE_COMPLETION = 0.28


# ── history ─────────────────────────────────────────────────────────────────────
def _recommended_rounds(config: Optional[Dict[str, Any]]) -> int:
    """Rounds implied by the configured clock, used when a run set no total."""
    time_config = (config or {}).get("time_config", {})
    return int(time_config.get("total_simulation_hours", 0) * 60
               / max(time_config.get("minutes_per_round", 60), 1))


def _run_progress(simulation_id: str, recommended: int) -> Dict[str, Any]:
    """Where the run got to, from run_state.json. Idle when it never started."""
    state = SimulationRunner.get_run_state(simulation_id)
    if not state:
        return {"current_round": 0, "runner_status": "idle", "total_rounds": recommended}
    return {
        "current_round": state.current_round,
        "runner_status": state.runner_status.value,
        # A user-set total wins; otherwise fall back to what the clock implies.
        "total_rounds": state.total_rounds if state.total_rounds > 0 else recommended,
    }


def history(limit: int = 20, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Saved runs, newest first, with everything the home screen lists."""
    manager = SimulationManager()
    rows = []
    for sim in manager.list_simulations(user_id=user_id)[:limit]:
        row = sim.to_dict()

        config = manager.get_simulation_config(sim.simulation_id)
        row["simulation_requirement"] = (config or {}).get("simulation_requirement", "")
        row["total_simulation_hours"] = \
            (config or {}).get("time_config", {}).get("total_simulation_hours", 0)
        row.update(_run_progress(sim.simulation_id, _recommended_rounds(config)))

        # Up to three of the project's source documents, for the card's subtitle.
        project = project_repository.get(sim.project_id)
        files = getattr(project, "files", None) if project else None
        row["files"] = [{"filename": f.get("filename", "Unknown file")}
                        for f in (files or [])[:3]]

        row["report_id"] = report_repository.latest_id_for_simulation(sim.simulation_id)
        row["version"] = HISTORY_VERSION
        row["created_date"] = (row.get("created_at") or "")[:10]
        rows.append(row)
    return rows


# ── cost ────────────────────────────────────────────────────────────────────────
def cost_breakdown(state: Any, simulation_id: str) -> Dict[str, Any]:
    """What this run cost: the prepare phase, the run itself, and the total.

    Prepare cost is recorded on the run's state as it happens. The run's own cost is
    summed from the action log the subprocess appends to.
    """
    totals = repo.action_totals(simulation_id)
    sim_cost = totals["cost_usd"]
    total_usd = round(state.prepare_cost_usd + sim_cost, 6)

    return {
        "prepare": {
            "prompt_tokens": state.prepare_prompt_tokens,
            "completion_tokens": state.prepare_completion_tokens,
            "cost_usd": state.prepare_cost_usd,
            "cost_zar": round(state.prepare_cost_usd * ZAR_PER_USD, 4),
        },
        "simulation": {
            "prompt_tokens": int(totals["prompt_tokens"]),
            "completion_tokens": int(totals["completion_tokens"]),
            "cost_usd": round(sim_cost, 6),
            "cost_zar": round(sim_cost * ZAR_PER_USD, 4),
        },
        "total_cost_usd": total_usd,
        "total_cost_zar": round(total_usd * ZAR_PER_USD, 4),
        "pricing_used": {
            "input_per_1m": float(Config.LLM_PRICE_PROMPT_PER_1M or DEFAULT_PRICE_PROMPT),
            "output_per_1m": float(Config.LLM_PRICE_COMPLETION_PER_1M
                                   or DEFAULT_PRICE_COMPLETION),
        },
    }


# ── live progress ───────────────────────────────────────────────────────────────
#: What a run reports before it has ever been started.
IDLE = "idle"


def run_status(simulation_id: str) -> Dict[str, Any]:
    """Where the run is right now, for the screen that polls while it runs.

    A run that was never started answers with zeros rather than 404: the screen opens
    before the run does, and an error there would read as a broken simulation.
    """
    state = SimulationRunner.get_run_state(simulation_id)
    if not state:
        return {
            "simulation_id": simulation_id,
            "runner_status": IDLE,
            "current_round": 0,
            "total_rounds": 0,
            "progress_percent": 0,
            "simulation_actions_count": 0,
            "total_actions_count": 0,
        }

    data = state.to_dict()
    # How many agents have spoken so far comes from the subprocess's own status file,
    # not the run state, so it has to be merged in.
    env = SimulationRunner.get_env_status_detail(simulation_id)
    data["agents_expressed_count"] = env.get("agents_expressed_count", 0)
    data["agents_expressed"] = env.get("agents_expressed", [])
    data["total_agents"] = env.get("total_agents", 0)
    return data


def run_status_detail(simulation_id: str,
                      platform: Optional[str] = None) -> Dict[str, Any]:
    """The run's status plus every action, and the current round's separately."""
    state = SimulationRunner.get_run_state(simulation_id)
    if not state:
        return {"simulation_id": simulation_id, "runner_status": IDLE, "all_actions": []}

    all_actions = SimulationRunner.get_all_actions(
        simulation_id=simulation_id, platform=platform)
    # "Recent" means this round. Before round 1 there is nothing recent to show.
    recent = SimulationRunner.get_all_actions(
        simulation_id=simulation_id, platform=platform,
        round_num=state.current_round) if state.current_round > 0 else []

    result = state.to_dict()
    result["all_actions"] = [a.to_dict() for a in all_actions]
    result["rounds_count"] = len(state.rounds)
    result["recent_actions"] = [a.to_dict() for a in recent]
    return result


def agents(simulation_id: str) -> List[Dict[str, Any]]:
    """The run's cast with its policy-relevant state. Raises FileNotFoundError."""
    from .interview_service import InterviewService
    return InterviewService(simulation_id).list_agents()


# ── export ──────────────────────────────────────────────────────────────────────
def parse_rounds(rounds_arg: str) -> Optional[List[int]]:
    """"all" means every round (None); otherwise the numbers named, junk dropped."""
    if rounds_arg == "all":
        return None
    return [int(r.strip()) for r in rounds_arg.split(",") if r.strip().isdigit()]


def export_states(simulation_id: str,
                  rounds: Optional[List[int]] = None) -> Dict[str, Any]:
    """Stance, radicalism and mobilisation per agent per round."""
    from .data_exporter import SimulationDataExporter
    return SimulationDataExporter(simulation_id).export_agent_states(rounds=rounds)


def export_impact(simulation_id: str) -> Dict[str, Any]:
    """The aggregate read from the latest impact interviews."""
    from .data_exporter import SimulationDataExporter
    return SimulationDataExporter(simulation_id).export_impact_summary()


# ── live progress ───────────────────────────────────────────────────────────────
def profiles_progress(simulation_id: str, platform: str) -> Dict[str, Any]:
    """The cast as it is being written, for the screen that watches it fill up."""
    snap = repo.snapshot(simulation_id, repo.PROFILES_FILE)
    profiles = snap.data if isinstance(snap.data, list) else []
    state = repo.read_state(simulation_id) or {}
    return {
        "simulation_id": simulation_id,
        "platform": platform,
        "count": len(profiles),
        "total_expected": state.get("entities_count"),
        "is_generating": state.get("status", "") == "preparing",
        "file_exists": snap.present,
        "file_modified_at": snap.modified_at,
        "profiles": profiles,
    }


def _stage(status: str, is_generating: bool, state: Dict[str, Any]) -> Optional[str]:
    """Which step of prepare the run is on, in the order the UI draws them."""
    if is_generating:
        return "generating_config" if state.get("profiles_generated", False) \
            else "generating_profiles"
    if status == "ready":
        return "completed"
    if status == "failed":
        return "failed"
    return None


def config_progress(simulation_id: str) -> Dict[str, Any]:
    """The generated config as it is being written, plus how far prepare has got.

    Returns partial information on purpose: the screen polls this during generation,
    so a missing or half-written config is a normal answer, not an error.
    """
    snap = repo.snapshot(simulation_id, repo.CONFIG_FILE)
    config = snap.data if isinstance(snap.data, dict) else None
    state = repo.read_state(simulation_id) or {}
    status = state.get("status", "")
    is_generating = status == "preparing"

    out = {
        "simulation_id": simulation_id,
        "file_exists": snap.present,
        "file_modified_at": snap.modified_at,
        "is_generating": is_generating,
        "generation_stage": _stage(status, is_generating, state),
        "config_generated": state.get("config_generated", False),
        "status": status,
        "error": state.get("error"),
        "failed": status == "failed",
        "config": config,
    }
    if config:
        out["summary"] = {
            "total_agents": len(config.get("agent_configs", [])),
            "simulation_hours": config.get("time_config", {}).get("total_simulation_hours"),
            "initial_posts_count":
                len(config.get("event_config", {}).get("initial_posts", [])),
            "hot_topics_count":
                len(config.get("event_config", {}).get("hot_topics", [])),
            "has_opinion_space_config": True,
            "generated_at": config.get("generated_at"),
            "llm_model": config.get("llm_model"),
        }
    return out
