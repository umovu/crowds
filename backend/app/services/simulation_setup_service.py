"""Setting a run up: declared agents, and refreshing its research.

Two jobs that happen around a simulation rather than during it:

  * `parse_custom_agents` — read an uploaded document into agent profiles. The file
    is a temporary: it exists only long enough to be parsed, then it goes.
  * `rerun_research` — redo the deep web research for whatever archetypes the run's
    graph actually contains, and overwrite its enrichment.

No Flask. The upload's bytes arrive through a `write` callback so the web framework's
file object stays in the controller.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..config import Config
from ..repositories import project_repository
from ..repositories import simulation_repository as repo
from ..utils.logger import get_logger
from .simulation_manager import SimulationManager, SimulationStatus

logger = get_logger("fub.simulation_setup")

#: Where an upload waits while it is being parsed. Nothing else uses this directory.
TEMP_UPLOAD_DIR = "temp"

#: Used when the run's project has no seed text of its own.
DEFAULT_RESEARCH_QUERY = "current socio-economic conditions South Africa 2025"


#: A run counts as prepared in any of these states, provided its config was
#: generated. Deliberately broad: a run that is already running, finished, stopped or
#: even failed has still been prepared, and narrowing this list has broken /start
#: before. Do not tighten it.
PREPARED_STATUSES = ("ready", "preparing", "running", "completed", "stopped",
                     "failed", "paused")

#: The files a prepared run must have on disk.
REQUIRED_FILES = ("state.json", "simulation_config.json",
                  "agentsociety_profiles.json")

#: How the prepare stages map onto a single 0-100 progress bar.
STAGE_WEIGHTS = {
    "reading": (0, 20),
    "generating_profiles": (20, 70),
    "generating_config": (70, 90),
    "copying_scripts": (90, 100),
}

STAGE_NAMES = {
    "reading": "Read knowledge graph entities",
    "generating_profiles": "GenerateAgentpersona",
    "generating_config": "Generate simulation configuration",
    "copying_scripts": "Prepare simulation scripts",
}


class RunNotFound(LookupError):
    """No such simulation."""


class ProjectNotFound(LookupError):
    """The run's project is gone, so there is nothing to prepare from."""


class MissingRequirement(ValueError):
    """The project has no seed text to prepare from."""


class NoCustomAgents(ValueError):
    """Custom-only was asked for, but no usable custom agent was supplied."""


class TaskNotFound(LookupError):
    """No such preparation task."""


class NeedTaskOrSimulation(ValueError):
    """Neither a task id nor a simulation id was given."""


class NoEntityTypes(ValueError):
    """The run's graph holds nothing that could be researched."""


class ResearchEmpty(RuntimeError):
    """The research pipeline came back with nothing."""


def parse_custom_agents(write: Callable[[str], None], filename: str,
                        simulation_requirement: str = "") -> List[Dict[str, Any]]:
    """Parse an uploaded document into agent profiles.

    Takes JSON arrays of profiles directly, and unstructured text (PDF, MD, TXT) via
    the LLM. `write` is handed the destination path.

    `secure_filename` is applied HERE, next to the path join, rather than left to the
    caller: it is what stops an uploaded name from escaping the temp directory, and
    keeping the two together means a future caller cannot forget it.
    """
    from werkzeug.utils import secure_filename

    from .custom_agent_parser import CustomAgentParser

    upload_dir = os.path.join(Config.UPLOAD_FOLDER, TEMP_UPLOAD_DIR)
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, secure_filename(filename))
    write(file_path)

    try:
        profiles = CustomAgentParser().parse_doc(file_path, simulation_requirement)
        return [p.to_agentsociety_format() for p in profiles]
    finally:
        # The temp file has served its purpose either way. A failure to remove it
        # must not mask a parse error or fail a good parse.
        try:
            os.remove(file_path)
        except OSError:
            pass


def check_prepared(simulation_id: str) -> Tuple[bool, Dict[str, Any]]:
    """Is this run prepared? Returns (prepared, info) and never raises.

    Reads the run's files directly rather than going through the manager, which is
    what lets it answer for a run the manager has never loaded.

    It also REPAIRS one state: a run whose files are all present but whose status is
    still `preparing` is rewritten to `ready`. That is a deliberate side effect of
    asking — prepare can finish without anything updating the status, and without
    this a finished run would never start.
    """
    if not repo.exists(simulation_id):
        return False, {"reason": "Simulation directory does not exist"}

    existing, missing = [], []
    for name in REQUIRED_FILES:
        (existing if os.path.exists(repo.path(simulation_id, name)) else missing
         ).append(name)
    if missing:
        return False, {"reason": "Missing required files",
                       "missing_files": missing, "existing_files": existing}

    try:
        state_data = repo.read_state(simulation_id)
        if state_data is None:
            return False, {"reason": "Failed to read state file: state.json unreadable"}

        status = state_data.get("status", "")
        config_generated = state_data.get("config_generated", False)
        logger.debug("Detect simulation preparation status: %s, status=%s, "
                     "config_generated=%s", simulation_id, status, config_generated)

        if not (status in PREPARED_STATUSES and config_generated):
            logger.warning("Simulation %s Detection result: Has notPreparation complete "
                           "(status=%s, config_generated=%s)",
                           simulation_id, status, config_generated)
            return False, {
                "reason": f"Status not in prepared list or config_generated is false: "
                          f"status={status}, config_generated={config_generated}",
                "status": status,
                "config_generated": config_generated,
            }

        profiles_count = len(repo.read_profiles(simulation_id))

        if status == "preparing":
            try:
                state_data["status"] = "ready"
                state_data["updated_at"] = datetime.now().isoformat()
                repo.write_state(simulation_id, state_data)
                logger.info("Auto update simulation status: %s preparing -> ready",
                            simulation_id)
                status = "ready"
            except Exception as e:  # noqa: BLE001 - the answer still stands
                logger.warning(f"Failed to auto update status: {e}")

        logger.info("Simulation %s Detection result: HasPreparation complete "
                    "(status=%s, config_generated=%s)",
                    simulation_id, status, config_generated)
        return True, {
            "status": status,
            "entities_count": state_data.get("entities_count", 0),
            "profiles_count": profiles_count,
            "entity_types": state_data.get("entity_types", []),
            "config_generated": config_generated,
            "created_at": state_data.get("created_at"),
            "updated_at": state_data.get("updated_at"),
            "existing_files": existing,
        }
    except Exception as e:  # noqa: BLE001 - "cannot tell" is a legitimate answer
        return False, {"reason": f"Failed to read state file: {str(e)}"}


def _progress_reporter(task_manager: Any, task_id: str):
    """Fold per-stage progress into one 0-100 bar, with a readable message."""
    stage_details: Dict[str, Any] = {}

    def report(stage, progress, message, **kwargs):
        start, end = STAGE_WEIGHTS.get(stage, (0, 100))
        overall = int(start + (end - start) * progress / 100)
        index = (list(STAGE_WEIGHTS).index(stage) + 1
                 if stage in STAGE_WEIGHTS else 1)
        total_stages = len(STAGE_WEIGHTS)

        stage_details[stage] = {
            "stage_name": STAGE_NAMES.get(stage, stage),
            "stage_progress": progress,
            "current": kwargs.get("current", 0),
            "total": kwargs.get("total", 0),
            "item_name": kwargs.get("item_name", ""),
        }
        detail = stage_details[stage]
        label = STAGE_NAMES.get(stage, stage)
        detailed = (f"[{index}/{total_stages}] {label}: "
                    f"{detail['current']}/{detail['total']} - {message}"
                    if detail["total"] > 0
                    else f"[{index}/{total_stages}] {label}: {message}")

        task_manager.update_task(task_id, progress=overall, message=detailed,
                                 progress_detail={
                                     "current_stage": stage,
                                     "current_stage_name": label,
                                     "stage_index": index,
                                     "total_stages": total_stages,
                                     "stage_progress": progress,
                                     "current_item": detail["current"],
                                     "total_items": detail["total"],
                                     "item_description": message,
                                 })
    return report


def _custom_profiles(raw: Any, project: Any) -> list:
    """Parse custom agents from the request, else from the project. [] if neither.

    A parse failure is logged and treated as "none supplied": a malformed block must
    not abort a prepare that can still run on the library cast. When the caller asked
    for custom-only, `start_prepare` refuses instead.
    """
    from .custom_agent_parser import CustomAgentParser

    if raw:
        try:
            parsed = CustomAgentParser().parse_raw(raw)
            logger.info("Received %d raw custom agents from request, parsed %d valid "
                        "profiles", len(raw), len(parsed))
            return parsed
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to parse custom agents from request: {e}")
            return []
    if project.custom_agents:
        try:
            parsed = CustomAgentParser().parse_raw(project.custom_agents)
            logger.info("Loaded %d custom agents from project, parsed %d valid "
                        "profiles", len(project.custom_agents), len(parsed))
            return parsed
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to parse custom agents from project: {e}")
    return []


def start_prepare(data: Dict[str, Any], *, storage: Any, task_manager: Any,
                  user_id: Optional[str] = None) -> Dict[str, Any]:
    """Start preparing a run, on a background thread. Returns the immediate answer.

    No paywall here: a sim is gated at create and its credit is charged at /start, so
    preparing an already-created sim must always be allowed for its owner.

    Raises RunNotFound / ProjectNotFound (404), MissingRequirement / NoCustomAgents
    (400), and ValueError for missing storage — which the caller answers 404, as the
    original route did.
    """
    import threading

    from ..models.task import TaskStatus
    from .simulation_manager import DEFAULT_MAIN_CAST_SIZE
    from . import mode_detector

    simulation_id = data.get("simulation_id")
    manager = SimulationManager()
    state = manager.get_simulation(simulation_id)
    if not state:
        raise RunNotFound(f"Simulation does not exist: {simulation_id}")

    force_regenerate = data.get("force_regenerate", False)
    logger.info("Start processing /prepare Request: simulation_id=%s, "
                "force_regenerate=%s", simulation_id, force_regenerate)

    if not force_regenerate:
        is_prepared, prepare_info = check_prepared(simulation_id)
        if is_prepared:
            logger.info("Simulation %s has preparation complete, no need to "
                        "regenerate", simulation_id)
            return {
                "simulation_id": simulation_id,
                "status": "ready",
                "message": "Preparation already completed，No need to repeatGenerate",
                "already_prepared": True,
                "prepare_info": prepare_info,
            }
        logger.info("Simulation %s has no preparation complete, preparing now",
                    simulation_id)

    project = project_repository.get(state.project_id)
    if not project:
        raise ProjectNotFound(f"Project does not exist: {state.project_id}")

    simulation_requirement = project.simulation_requirement or ""
    if not simulation_requirement:
        raise MissingRequirement("Project missing simulation requirement "
                                 "description (simulation_requirement)")

    document_text = project_repository.get_extracted_text(state.project_id) or ""
    entity_types_list = data.get("entity_types")
    parallel_profile_count = data.get("parallel_profile_count", 5)
    custom_only = bool(data.get("custom_agents_only", False))

    # An explicit mode choice is pinned; otherwise it is detected from the seed, so a
    # user never silently gets the wrong one. Keyword detection runs here so the
    # response can echo the banner immediately; the optional LLM tiebreak happens
    # inside prepare_simulation, where the LLM client already exists.
    manual_mode = (data.get("mode") or "").strip().lower()
    if manual_mode not in ("policy", "product"):
        manual_mode = ""
    mode_is_manual = bool(data.get("mode_is_manual")) and bool(manual_mode)
    detection = mode_detector.detect(simulation_requirement, document_text,
                                     llm_client=None)
    mode = manual_mode if mode_is_manual else detection["mode"]
    if mode not in ("policy", "product"):
        mode = "policy"

    custom_profiles = _custom_profiles(data.get("custom_agents", []), project)
    # Asked for custom-only with nothing usable: fail loudly rather than quietly
    # running a full auto-generated population the user did not want.
    if custom_only and not custom_profiles:
        raise NoCustomAgents(
            "Custom-agents-only mode is on, but no usable custom agents were "
            "provided. Add at least one custom agent, or turn off custom-only mode.")

    if not storage:
        raise ValueError("GraphStorage not initialized — check Neo4j connection")

    # Read the graph synchronously so the response can carry the expected counts.
    try:
        logger.info("Synchronously get entity count: graph_id=%s", state.graph_id)
        from .entity_reader import EntityReader
        preview = EntityReader(storage).filter_defined_entities(
            graph_id=state.graph_id, defined_entity_types=entity_types_list,
            enrich_with_edges=False)
        # The cast comes from the persona library, NOT these graph entities, so the
        # expected count is the library cast size rather than filtered_count. The
        # entity types are still read, for display and context.
        state.entities_count = DEFAULT_MAIN_CAST_SIZE
        state.entity_types = list(preview.entity_types)
        logger.info("Graph entities (context only): %d, types: %s",
                    preview.filtered_count, preview.entity_types)
    except Exception as e:  # noqa: BLE001 - the background task retries this
        logger.warning("Synchronously get entity countFailed（Will retry in "
                       "background task）: %s", e)

    task_id = task_manager.create_task(
        task_type="simulation_prepare",
        metadata={"simulation_id": simulation_id, "project_id": state.project_id})

    state.status = SimulationStatus.PREPARING
    # `save`, not `set_status`: entities_count and entity_types were just set on this
    # object and set_status would reload over them.
    manager.save(state)

    def run_prepare():
        try:
            task_manager.update_task(task_id, status=TaskStatus.PROCESSING,
                                     progress=0,
                                     message="Start preparing simulation environment...")
            # Fail-open: an unreachable operator context costs flavour, not the run.
            # Imported here, not at module level: app/api/simulation.py imports this
            # service, and the money guard path-loads that file without stubbing the
            # Supabase-backed repositories. Keeping this lazy keeps that import light.
            try:
                from ..repositories import operator_context_repository as oc_repo
                uid = state.user_id or user_id
                operator_context = oc_repo.get(uid) if uid else ""
            except Exception:  # noqa: BLE001
                operator_context = ""

            result_state = manager.prepare_simulation(
                simulation_id=simulation_id,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                defined_entity_types=entity_types_list,
                progress_callback=_progress_reporter(task_manager, task_id),
                parallel_profile_count=parallel_profile_count,
                storage=storage,
                custom_profiles=custom_profiles,
                custom_only=custom_only,
                mode=mode,
                detection=detection,
                mode_is_manual=mode_is_manual,
                operator_context=operator_context,
            )
            # prepare_simulation answers with a FAILED state rather than raising for
            # known problems, so surface that as a failed task or the UI polls forever.
            if getattr(result_state, "status", None) == SimulationStatus.FAILED:
                task_manager.fail_task(task_id,
                                       result_state.error or "Preparation failed")
            else:
                task_manager.complete_task(task_id,
                                           result=result_state.to_simple_dict())
        except Exception as e:  # noqa: BLE001 - reported on the task, never raised
            logger.error(f"Failed to prepare simulation: {str(e)}")
            task_manager.fail_task(task_id, str(e))
            failed = manager.get_simulation(simulation_id)
            if failed:
                failed.status = SimulationStatus.FAILED
                failed.error = str(e)
                manager.save(failed)

    threading.Thread(target=run_prepare, daemon=True).start()

    return {
        "simulation_id": simulation_id,
        "task_id": task_id,
        "status": "preparing",
        "message": "Preparation task started，Please via "
                   "/api/simulation/prepare/status Query progress",
        "already_prepared": False,
        "expected_entities_count": state.entities_count,
        "entity_types": state.entity_types,
        # The frontend renders its detection banner from these. The keyword decision
        # is echoed here; an LLM tiebreak may still refine the persisted mode.
        "mode": mode,
        "mode_is_manual": mode_is_manual,
        "converged": detection["converged"],
        "secondary_lens": detection["secondary_lens"],
        "mode_detection": {
            "decided_mode": detection["mode"],
            "confidence": detection["confidence"],
            "scores": detection["scores"],
        },
    }


def prepare_status(task_id: Optional[str] = None,
                   simulation_id: Optional[str] = None) -> Dict[str, Any]:
    """Progress of a preparation, by task id or by simulation id.

    A simulation id is answered from the files on disk, so a finished preparation is
    reported even when its task is long gone (after a restart, say).

    Raises NeedTaskOrSimulation (400) and TaskNotFound (404).
    """
    from ..models.task import TaskManager

    if simulation_id:
        is_prepared, prepare_info = check_prepared(simulation_id)
        if is_prepared:
            return {
                "simulation_id": simulation_id,
                "status": "ready",
                "progress": 100,
                "message": "Preparation already completed",
                "already_prepared": True,
                "prepare_info": prepare_info,
            }

    if not task_id:
        if simulation_id:
            return {
                "simulation_id": simulation_id,
                "status": "not_started",
                "progress": 0,
                "message": "Preparation not started yet, please call "
                           "/api/simulation/prepare",
                "already_prepared": False,
            }
        raise NeedTaskOrSimulation("Please provide task_id Or simulation_id")

    task = TaskManager().get_task(task_id)
    if not task:
        # The task is gone, but the work may still have finished on disk.
        if simulation_id:
            is_prepared, prepare_info = check_prepared(simulation_id)
            if is_prepared:
                return {
                    "simulation_id": simulation_id,
                    "task_id": task_id,
                    "status": "ready",
                    "progress": 100,
                    "message": "Task complete（PrepareWork already exists）",
                    "already_prepared": True,
                    "prepare_info": prepare_info,
                }
        raise TaskNotFound(f"Task does not exist: {task_id}")

    out = task.to_dict()
    out["already_prepared"] = False
    return out


def _archetype(entity_type: str) -> str:
    """Turn a graph entity type into an archetype key: `PublicFigure` -> `public_figure`."""
    spaced = re.sub(r"([A-Z])", r"_\1", entity_type).lower().lstrip("_")
    return re.sub(r"[\s\-]+", "_", spaced.strip())


def rerun_research(simulation_id: str,
                   agent_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Research the run's archetypes again and overwrite its enrichment.

    The archetypes come from the graph the run was built on, not from a list someone
    typed, so the research matches what the simulation actually contains.

    Raises RunNotFound, NoEntityTypes, or ResearchEmpty.
    """
    from ..storage import get_storage
    from .agent_enricher import AgentContextEnricher
    from .deep_research_service import research_archetypes
    from .entity_reader import EntityReader

    state = SimulationManager().get_simulation(simulation_id)
    if not state:
        raise RunNotFound("Simulation not found")

    # A fresh storage handle on purpose: this is the same instance the original route
    # built, rather than the one hanging off the app.
    filtered = EntityReader(get_storage()).filter_defined_entities(
        graph_id=state.graph_id, defined_entity_types=None, enrich_with_edges=False)
    entity_types = list({_archetype(e.type) for e in filtered.entities if e.type})
    if not entity_types:
        raise NoEntityTypes("No entity types found in graph")

    project = project_repository.get(state.project_id) if state.project_id else None
    seed = (project.simulation_requirement if project else "") or ""

    raw_research = research_archetypes(
        archetypes=entity_types,
        query=seed or DEFAULT_RESEARCH_QUERY,
        document_text=seed,
        agent_context=agent_context or {},
    )
    if not raw_research:
        raise ResearchEmpty("Research returned no results. "
                            "Check FIRECRAWL_API_KEY and Firecrawl quota.")

    enrichment = AgentContextEnricher.enrich_from_web_research(
        raw_research, entity_types)
    repo.write_enrichment(simulation_id, raw_research)

    return {
        "archetypes": entity_types,
        "enriched_count": len(enrichment),
        "enrichment": raw_research,
        "agent_context": agent_context or {},
    }
