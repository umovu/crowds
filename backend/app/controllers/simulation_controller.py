"""Reading simulations back: the graph's entities, saved runs, config and cost.

  GET /api/simulation/entities/<graph_id>                    filtered graph entities
  GET /api/simulation/entities/<graph_id>/<entity_uuid>      one entity in context
  GET /api/simulation/entities/<graph_id>/by-type/<type>     entities of one type
  GET /api/simulation/<simulation_id>                        a run's status
  GET /api/simulation/list                                   every run
  GET /api/simulation/history                                runs, with project detail
  GET /api/simulation/<simulation_id>/profiles               the cast
  GET /api/simulation/<simulation_id>/profiles/realtime      the cast, while it fills
  GET /api/simulation/<simulation_id>/enrichment             deep-research findings
  GET /api/simulation/<simulation_id>/cost                   tokens and money spent
  GET /api/simulation/<simulation_id>/config                 the generated config
  GET /api/simulation/<simulation_id>/config/realtime        config, while it writes
  GET /api/simulation/<simulation_id>/config/download        the config as a file
  GET /api/simulation/script/<script_name>/download          the run script

Every route here only reads. Creating, preparing, starting and stopping a run stay in
app/api/simulation.py, together with the credit charge, so the test that guarantees a
user is billed once is untouched by this split.

These register on their own blueprint at the same /api/simulation prefix, so the URLs
are unchanged. Nothing calls `url_for('simulation.*')`, so the endpoint names moving to
`simulation_read.*` breaks no link.
"""

import csv
import io
import traceback

from flask import current_app, jsonify, request, send_file

from . import simulation_read_bp
from ..auth import current_user_id
from ..repositories import simulation_repository as repo
from ..services import simulation_interview_service, simulation_read_service
from ..services.entity_reader import EntityReader
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner
from ..utils.logger import get_logger

logger = get_logger('fub.controller.simulation')

#: Only these ship with the code and may be downloaded.
ALLOWED_SCRIPTS = ("run_simulation_as.py", "action_logger.py")


def _failed(e: Exception, status: int = 500):
    """The historical error shape for these routes: message plus traceback."""
    return jsonify({"success": False, "error": str(e),
                    "traceback": traceback.format_exc()}), status


def _reader() -> EntityReader:
    """A reader over the app's graph storage. Fetched here: a service cannot."""
    storage = current_app.extensions.get('graph_storage')
    if not storage:
        raise ValueError("GraphStorage not initialized")
    return EntityReader(storage)


def _missing(simulation_id: str):
    return jsonify({"success": False,
                    "error": f"Simulation does not exist: {simulation_id}"}), 404


# ── graph entities ──────────────────────────────────────────────────────────────
@simulation_read_bp.route('/entities/<graph_id>', methods=['GET'])
def get_graph_entities(graph_id: str):
    """Entities from the knowledge graph, keeping only defined types.

    Query: entity_types (comma separated, optional further filter), enrich (default
    true, fetches the related edges too).
    """
    try:
        types_arg = request.args.get('entity_types', '')
        entity_types = [t.strip() for t in types_arg.split(',') if t.strip()] or None
        enrich = request.args.get('enrich', 'true').lower() == 'true'
        logger.info(f"Get knowledge graph entities: graph_id={graph_id}, "
                    f"entity_types={entity_types}, enrich={enrich}")
        result = _reader().filter_defined_entities(
            graph_id=graph_id, defined_entity_types=entity_types,
            enrich_with_edges=enrich)
        return jsonify({"success": True, "data": result.to_dict()})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to get knowledge graph entities: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/entities/<graph_id>/<entity_uuid>', methods=['GET'])
def get_entity_detail(graph_id: str, entity_uuid: str):
    """Get detailed information of a single entity"""
    try:
        entity = _reader().get_entity_with_context(graph_id, entity_uuid)
        if not entity:
            return jsonify({"success": False,
                            "error": f"Entity does not exist: {entity_uuid}"}), 404
        return jsonify({"success": True, "data": entity.to_dict()})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to get entity details: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/entities/<graph_id>/by-type/<entity_type>', methods=['GET'])
def get_entities_by_type(graph_id: str, entity_type: str):
    """Get all entities of specified type"""
    try:
        enrich = request.args.get('enrich', 'true').lower() == 'true'
        entities = _reader().get_entities_by_type(
            graph_id=graph_id, entity_type=entity_type, enrich_with_edges=enrich)
        return jsonify({"success": True, "data": {
            "entity_type": entity_type,
            "count": len(entities),
            "entities": [e.to_dict() for e in entities],
        }})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to get entities: {str(e)}")
        return _failed(e)


# ── saved runs ──────────────────────────────────────────────────────────────────
@simulation_read_bp.route('/<simulation_id>', methods=['GET'])
def get_simulation(simulation_id: str):
    """Get simulation status"""
    try:
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if not state:
            return _missing(simulation_id)

        result = state.to_dict()
        # A prepared run also carries the instructions for running it.
        if state.status == SimulationStatus.READY:
            result["run_instructions"] = manager.get_run_instructions(simulation_id)
        return jsonify({"success": True, "data": result})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to get simulation status: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/list', methods=['GET'])
def list_simulations():
    """List all simulations. Query: project_id to filter (optional)."""
    try:
        simulations = SimulationManager().list_simulations(
            project_id=request.args.get('project_id'), user_id=current_user_id())
        return jsonify({"success": True,
                        "data": [s.to_dict() for s in simulations],
                        "count": len(simulations)})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to list simulations: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/history', methods=['GET'])
def get_simulation_history():
    """Saved runs with project detail, for the home screen. Query: limit (default 20)."""
    try:
        rows = simulation_read_service.history(
            limit=request.args.get('limit', 20, type=int), user_id=current_user_id())
        return jsonify({"success": True, "data": rows, "count": len(rows)})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to get historical simulations: {str(e)}")
        return _failed(e)


# ── the cast ────────────────────────────────────────────────────────────────────
@simulation_read_bp.route('/<simulation_id>/profiles', methods=['GET'])
def get_simulation_profiles(simulation_id: str):
    """The run's cast. Query: platform (default opinion_space)."""
    try:
        platform = request.args.get('platform', 'opinion_space')
        profiles = SimulationManager().get_profiles(simulation_id, platform=platform)
        return jsonify({"success": True, "data": {
            "platform": platform, "count": len(profiles), "profiles": profiles,
        }})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:  # noqa: BLE001
        logger.error(f"GetProfileFailed: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/<simulation_id>/profiles/realtime', methods=['GET'])
def get_simulation_profiles_realtime(simulation_id: str):
    """The cast while it is still being written, for the live progress screen.

    Reads the file directly rather than going through the manager, and reports on the
    file itself (whether it exists, when it changed) so the screen can show progress.
    """
    try:
        if not repo.exists(simulation_id):
            return _missing(simulation_id)
        return jsonify({"success": True, "data": simulation_read_service.profiles_progress(
            simulation_id, request.args.get('platform', 'reddit'))})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Real-time getProfileFailed: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/<simulation_id>/enrichment', methods=['GET'])
def get_simulation_enrichment(simulation_id: str):
    """Raw deep-research findings per archetype, or {} when the run has none.

    Answers 200 with {} even on failure: the screen treats "no findings" as a normal
    state, and a missing file must not read as a broken run.
    """
    try:
        return jsonify({"success": True,
                        "data": repo.read_enrichment(simulation_id)})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Failed to load enrichment for {simulation_id}: {e}")
        return jsonify({"success": True, "data": {}})


# ── cost ────────────────────────────────────────────────────────────────────────
@simulation_read_bp.route('/<simulation_id>/cost', methods=['GET'])
def get_simulation_cost(simulation_id: str):
    """Token usage and estimated USD/ZAR cost for the prepare and run phases."""
    try:
        state = SimulationManager().get_simulation(simulation_id)
        if not state:
            return jsonify({"success": False, "error": "Simulation not found"}), 404
        return jsonify({"success": True, "data":
                        simulation_read_service.cost_breakdown(state, simulation_id)})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Cost endpoint error for {simulation_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ── config ──────────────────────────────────────────────────────────────────────
@simulation_read_bp.route('/<simulation_id>/config', methods=['GET'])
def get_simulation_config(simulation_id: str):
    """The generated simulation config: clock, per-agent activity, events, platforms."""
    try:
        config = SimulationManager().get_simulation_config(simulation_id)
        if not config:
            return jsonify({
                "success": False,
                "error": "Simulation configuration does not exist. Please call /prepare first",
            }), 404
        return jsonify({"success": True, "data": config})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to get configuration: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/<simulation_id>/config/realtime', methods=['GET'])
def get_simulation_config_realtime(simulation_id: str):
    """The config while it is being generated, plus which stage prepare is on."""
    try:
        if not repo.exists(simulation_id):
            return _missing(simulation_id)
        return jsonify({"success": True,
                        "data": simulation_read_service.config_progress(simulation_id)})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Real-time getConfigFailed: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/<simulation_id>/config/download', methods=['GET'])
def download_simulation_config(simulation_id: str):
    """Download simulation configuration file"""
    try:
        config_path = repo.path(simulation_id, repo.CONFIG_FILE)
        if not __import__('os').path.exists(config_path):
            return jsonify({
                "success": False,
                "error": "Configuration file does not exist. Please call /prepare first",
            }), 404
        return send_file(config_path, as_attachment=True,
                         download_name=repo.CONFIG_FILE)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to download configuration: {str(e)}")
        return _failed(e)


# ── interviews ──────────────────────────────────────────────────────────────────
#: The only platform the simulation runs on. Kept as a check because callers still
#: send the retired 'twitter' / 'reddit' values.
PLATFORMS = ("opinion_space",)


def _bad(message: str):
    return jsonify({"success": False, "error": message}), 400


def _timed_out(e: Exception, message: str):
    return jsonify({"success": False, "error": f"{message}: {str(e)}"}), 504


@simulation_read_bp.route('/interview', methods=['POST'])
def interview_agent():
    """Interview one agent. Needs the simulation running or recently completed."""
    try:
        data = request.get_json() or {}
        simulation_id = data.get('simulation_id')
        agent_id = data.get('agent_id')
        prompt = data.get('prompt')
        platform = data.get('platform')

        if not simulation_id:
            return _bad("Please provide simulation_id")
        if agent_id is None:
            return _bad("Please provide agent_id")
        if not prompt:
            return _bad("Please provide prompt（Interview question）")
        if platform and platform not in PLATFORMS:
            return _bad("platform must be opinion_space (was: 'twitter' Or 'reddit'")

        result = simulation_interview_service.interview_one(
            simulation_id=simulation_id, agent_id=agent_id, prompt=prompt,
            platform=platform, timeout=data.get('timeout', 60),
            # Only a request can reach the graph storage, so it is passed in.
            storage=current_app.extensions.get('graph_storage'))
        return jsonify({"success": result.get("success", False), "data": result})

    except simulation_interview_service.EnvironmentNotRunning as e:
        return _bad(str(e))
    except ValueError as e:
        return _bad(str(e))
    except TimeoutError as e:
        return _timed_out(e, "WaitInterviewResponse timeout")
    except Exception as e:  # noqa: BLE001
        logger.error(f"InterviewFailed: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/interview/batch', methods=['POST'])
def interview_agents_batch():
    """Interview several agents, each with their own question."""
    try:
        data = request.get_json() or {}
        simulation_id = data.get('simulation_id')
        interviews = data.get('interviews')
        platform = data.get('platform')

        if not simulation_id:
            return _bad("Please provide simulation_id")
        if not interviews or not isinstance(interviews, list):
            return _bad("Please provide interviews (Interview list)")
        if platform and platform not in PLATFORMS:
            return _bad("platform must be 'opinion_space'")
        for i, interview in enumerate(interviews):
            if 'agent_id' not in interview:
                return _bad(f"Interview list item {i+1} missing agent_id")
            if 'prompt' not in interview:
                return _bad(f"Interview list item {i+1} missing prompt")
            item_platform = interview.get('platform')
            if item_platform and item_platform not in PLATFORMS:
                return _bad(f"Interview list item {i+1}: platform must be 'opinion_space'")

        result = simulation_interview_service.interview_batch(
            simulation_id=simulation_id, interviews=interviews,
            platform=platform, timeout=data.get('timeout', 120))
        return jsonify({"success": result.get("success", False), "data": result})

    except simulation_interview_service.EnvironmentNotRunning as e:
        return _bad(str(e))
    except ValueError as e:
        return _bad(str(e))
    except TimeoutError as e:
        return _timed_out(e, "Wait for batchInterviewResponse timeout")
    except Exception as e:  # noqa: BLE001
        logger.error(f"BatchInterviewFailed: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/interview/post-simulation', methods=['POST'])
def interview_agents_post_simulation():
    """Interview agents after the run finished, including ones that never spoke.

    Works from the saved profiles, so it does not need a running environment.
    """
    try:
        data = request.get_json() or {}
        simulation_id = data.get('simulation_id')
        prompt = data.get('prompt')
        platform = data.get('platform', 'opinion_space')

        if not simulation_id:
            return _bad("Please provide simulation_id")
        if not prompt:
            return _bad("Please provide prompt (interview question)")
        if platform and platform not in PLATFORMS:
            return _bad("platform must be 'opinion_space'")

        out = simulation_interview_service.post_simulation(
            simulation_id=simulation_id, prompt=prompt,
            agent_id=data.get('agent_id'), platform=platform,
            timeout=data.get('timeout', 180))
        return jsonify({"success": out["result"].get("success", False), "data": {
            "simulation_id": simulation_id,
            "interviews_count": out["interviews_count"],
            "result": out["result"],
        }})

    except simulation_interview_service.ProfilesUnavailable as e:
        return _bad(f"Cannot load profiles: {str(e)}")
    except simulation_interview_service.NoAgents as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except simulation_interview_service.AgentNotFound as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except ValueError as e:
        return _bad(str(e))
    except TimeoutError as e:
        return _timed_out(e, "Interview timeout")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Post-simulation interview failed: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/interview/all', methods=['POST'])
def interview_all_agents():
    """Ask every agent the same question. Needs the simulation running."""
    try:
        data = request.get_json() or {}
        simulation_id = data.get('simulation_id')
        prompt = data.get('prompt')
        platform = data.get('platform')

        if not simulation_id:
            return _bad("Please provide simulation_id")
        if not prompt:
            return _bad("Please provide prompt（Interview question）")
        if platform and platform not in PLATFORMS:
            return _bad("platform must be opinion_space (was: 'twitter' Or 'reddit'")

        result = simulation_interview_service.interview_all(
            simulation_id=simulation_id, prompt=prompt, platform=platform,
            timeout=data.get('timeout', 180))
        return jsonify({"success": result.get("success", False), "data": result})

    except simulation_interview_service.EnvironmentNotRunning as e:
        return _bad(str(e))
    except ValueError as e:
        return _bad(str(e))
    except TimeoutError as e:
        return _timed_out(e, "Wait for globalInterviewResponse timeout")
    except Exception as e:  # noqa: BLE001
        logger.error(f"GlobalInterviewFailed: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/interview/history', methods=['POST'])
def get_interview_history():
    """Every interview recorded for a run. Query body: platform, agent_id, limit."""
    try:
        data = request.get_json() or {}
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return _bad("Please provide simulation_id")

        history = SimulationRunner.get_interview_history(
            simulation_id=simulation_id,
            platform=data.get('platform'),
            agent_id=data.get('agent_id'),
            limit=data.get('limit', 100))
        return jsonify({"success": True,
                        "data": {"count": len(history), "history": history}})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to get interview history: {str(e)}")
        return _failed(e)


# ── per-agent interviews and interventions ─────────────────────────────────────
def _live_payload(result):
    """The runner wraps its answer; older clients expect the inner object."""
    return result.get("result") or result


@simulation_read_bp.route('/<simulation_id>/agents/<int:agent_id>/interview',
                          methods=['POST'])
def interview_single_agent(simulation_id: str, agent_id: int):
    """Interview one agent after the fact. No running simulation required.

    Body: `question`, or a `question_type` (first_reaction, what_would_work,
    what_puts_you_off, need_to_know, who_you_would_tell) with optional
    `policy_context`.
    """
    try:
        data = request.get_json() or {}
        question = data.get('question', '')
        question_type = data.get('question_type')
        if not question and not question_type:
            return _bad("Provide 'question' or 'question_type'")

        result = simulation_interview_service.interview_one_agent(
            simulation_id=simulation_id, agent_id=agent_id, question=question,
            question_type=question_type, policy_context=data.get('policy_context'))
        return jsonify({"success": True, "data": result})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:  # noqa: BLE001
        logger.error(f"Interview failed: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/<simulation_id>/agents/batch-interview', methods=['POST'])
def batch_interview_agents(simulation_id: str):
    """Ask several agents the same question. Body: question or question_type,
    optional policy_context and agent_ids (default: everyone)."""
    try:
        data = request.get_json() or {}
        question = data.get('question', '')
        question_type = data.get('question_type')
        if not question and not question_type:
            return _bad("Provide 'question' or 'question_type'")

        result = simulation_interview_service.batch_interview(
            simulation_id=simulation_id, question=question,
            agent_ids=data.get('agent_ids'), question_type=question_type,
            policy_context=data.get('policy_context'))
        return jsonify({"success": True, "data": result})

    except Exception as e:  # noqa: BLE001
        logger.error(f"Batch interview failed: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/<simulation_id>/agents/<int:agent_id>/intervene',
                          methods=['POST'])
def intervene_with_agent(simulation_id: str, agent_id: int):
    """Put a policy-maker's offer to one agent. Body: intervention_text."""
    try:
        intervention_text = (request.get_json() or {}).get('intervention_text')
        if not intervention_text:
            return _bad("Provide 'intervention_text'")

        result = simulation_interview_service.intervene(
            simulation_id=simulation_id, agent_id=agent_id,
            intervention_text=intervention_text)
        return jsonify({"success": True, "data": result})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:  # noqa: BLE001
        logger.error(f"Intervention failed: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/<simulation_id>/agents/<int:agent_id>/intervene-live',
                          methods=['POST'])
def intervene_live(simulation_id: str, agent_id: int):
    """Poke one agent during a running (paused) simulation. Body: intervention_text."""
    try:
        intervention_text = (request.get_json() or {}).get('intervention_text')
        if not intervention_text:
            return _bad("Provide 'intervention_text'")

        result = simulation_interview_service.intervene_during_run(
            simulation_id=simulation_id, agent_id=agent_id,
            intervention_text=intervention_text)
        return jsonify({"success": result.get("success", False),
                        "data": _live_payload(result)})

    except ValueError as e:
        return _bad(str(e))
    except Exception as e:  # noqa: BLE001
        logger.error(f"Live intervention failed: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/<simulation_id>/broadcast-intervention', methods=['POST'])
def broadcast_intervention(simulation_id: str):
    """Announce something to the whole room during a running (paused) simulation.

    The message posts to the feed and the entire active room reacts next round,
    unlike intervene-live which targets one agent.
    """
    try:
        data = request.get_json() or {}
        intervention_text = data.get('intervention_text')
        if not intervention_text:
            return _bad("Provide 'intervention_text'")

        result = simulation_interview_service.broadcast_during_run(
            simulation_id=simulation_id, intervention_text=intervention_text,
            founder_name=data.get('founder_name') or "")
        return jsonify({"success": result.get("success", False),
                        "data": _live_payload(result)})

    except ValueError as e:
        return _bad(str(e))
    except Exception as e:  # noqa: BLE001
        logger.error(f"Broadcast intervention failed: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/interview/impact', methods=['POST'])
def impact_interview():
    """Batch impact interview: the question is reframed per persona before asking,
    and the answers come back with structured impact metadata."""
    try:
        data = request.get_json() or {}
        simulation_id = data.get("simulation_id")
        question = data.get("question", "")
        if not simulation_id:
            return _bad("simulation_id is required")
        if not question:
            return _bad("question is required")

        result = simulation_interview_service.impact_interview(
            simulation_id=simulation_id, question=question,
            agent_ids=data.get("agent_ids"))
        return jsonify({"success": True, "data": result})

    except Exception as e:  # noqa: BLE001
        logger.error(f"Impact interview failed: {str(e)}")
        return _failed(e)


# ── live status while a run executes ────────────────────────────────────────────
@simulation_read_bp.route('/<simulation_id>/run-status', methods=['GET'])
def get_run_status(simulation_id: str):
    """The run's status, for the frontend to poll."""
    try:
        return jsonify({"success": True,
                        "data": simulation_read_service.run_status(simulation_id)})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to get running status: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/<simulation_id>/run-status/detail', methods=['GET'])
def get_run_status_detail(simulation_id: str):
    """The run's status with every action. Query: platform to filter (optional)."""
    try:
        return jsonify({"success": True, "data": simulation_read_service.run_status_detail(
            simulation_id, request.args.get('platform'))})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to get detailed status: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/<simulation_id>/actions', methods=['GET'])
def get_simulation_actions(simulation_id: str):
    """Agent action history. Query: limit, offset, platform, agent_id, round_num."""
    try:
        actions = SimulationRunner.get_actions(
            simulation_id=simulation_id,
            limit=request.args.get('limit', 100, type=int),
            offset=request.args.get('offset', 0, type=int),
            platform=request.args.get('platform'),
            agent_id=request.args.get('agent_id', type=int),
            round_num=request.args.get('round_num', type=int))
        return jsonify({"success": True, "data": {
            "count": len(actions), "actions": [a.to_dict() for a in actions],
        }})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to get action history: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/<simulation_id>/timeline', methods=['GET'])
def get_simulation_timeline(simulation_id: str):
    """One summary per round, for the progress bar. Query: start_round, end_round."""
    try:
        timeline = SimulationRunner.get_timeline(
            simulation_id=simulation_id,
            start_round=request.args.get('start_round', 0, type=int),
            end_round=request.args.get('end_round', type=int))
        return jsonify({"success": True, "data": {
            "rounds_count": len(timeline), "timeline": timeline,
        }})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to get timeline: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/<simulation_id>/agent-stats', methods=['GET'])
def get_agent_stats(simulation_id: str):
    """Per-agent activity statistics, for the ranking view."""
    try:
        stats = SimulationRunner.get_agent_stats(simulation_id)
        return jsonify({"success": True, "data": {
            "agents_count": len(stats), "stats": stats,
        }})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to get agent statistics: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/<simulation_id>/agents', methods=['GET'])
def list_simulation_agents(simulation_id: str):
    """The cast with its policy-relevant state: stance, archetype, topics."""
    try:
        found = simulation_read_service.agents(simulation_id)
        return jsonify({"success": True, "data": {
            "simulation_id": simulation_id,
            "agent_count": len(found),
            "agents": found,
        }})
    except FileNotFoundError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to list agents: {str(e)}")
        return _failed(e)


# ── what the run produced ───────────────────────────────────────────────────────
@simulation_read_bp.route('/<simulation_id>/posts', methods=['GET'])
def get_simulation_posts(simulation_id: str):
    """Posts the run produced. Query: platform, limit, offset.

    A missing database means the run has not executed yet, which is said out loud
    rather than returned as an error or as an empty result.
    """
    try:
        platform = request.args.get('platform', 'reddit')
        page = repo.read_posts(
            simulation_id, platform,
            limit=request.args.get('limit', 50, type=int),
            offset=request.args.get('offset', 0, type=int))
        if page is None:
            return jsonify({"success": True, "data": {
                "platform": platform, "count": 0, "posts": [],
                "message": "Database does not exist，SimulationMay not have run yet",
            }})
        return jsonify({"success": True, "data": {
            "platform": platform, "total": page["total"],
            "count": len(page["rows"]), "posts": page["rows"],
        }})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to get posts: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/<simulation_id>/comments', methods=['GET'])
def get_simulation_comments(simulation_id: str):
    """Comments the run produced (Reddit only). Query: post_id, limit, offset."""
    try:
        rows = repo.read_comments(
            simulation_id,
            post_id=request.args.get('post_id'),
            limit=request.args.get('limit', 50, type=int),
            offset=request.args.get('offset', 0, type=int))
        rows = rows or []
        return jsonify({"success": True,
                        "data": {"count": len(rows), "comments": rows}})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to get comments: {str(e)}")
        return _failed(e)


# ── structured export ───────────────────────────────────────────────────────────
def _csv_download(records, filename: str):
    """Render records as a CSV attachment. Empty input still returns a file."""
    output = io.StringIO()
    if records:
        writer = csv.DictWriter(output, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
    return send_file(io.BytesIO(output.getvalue().encode()), mimetype="text/csv",
                     as_attachment=True, download_name=filename)


@simulation_read_bp.route('/<simulation_id>/export/states', methods=['GET'])
def export_agent_states(simulation_id: str):
    """Time-series agent state for external analysis. Query: format (json/csv), rounds."""
    try:
        data = simulation_read_service.export_states(
            simulation_id,
            simulation_read_service.parse_rounds(request.args.get("rounds", "all")))
        if request.args.get("format", "json") == "csv":
            return _csv_download((data or {}).get("records"),
                                 f"{simulation_id}_agent_states.csv")
        return jsonify({"success": True, "data": data})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Export agent states failed: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/<simulation_id>/export/impact', methods=['GET'])
def export_impact_summary(simulation_id: str):
    """Aggregate impact summary from the latest impact interviews. Query: format."""
    try:
        data = simulation_read_service.export_impact(simulation_id)
        if request.args.get("format", "json") == "csv":
            return _csv_download((data or {}).get("predicted_actions"),
                                 f"{simulation_id}_impact_summary.csv")
        return jsonify({"success": True, "data": data})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Export impact summary failed: {str(e)}")
        return _failed(e)


@simulation_read_bp.route('/script/<script_name>/download', methods=['GET'])
def download_simulation_script(script_name: str):
    """Download a simulation run script. Only ALLOWED_SCRIPTS may be fetched."""
    import os
    try:
        if script_name not in ALLOWED_SCRIPTS:
            return jsonify({
                "success": False,
                "error": f"Unknown script: {script_name}. Options: {list(ALLOWED_SCRIPTS)}",
            }), 400
        scripts_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
        script_path = os.path.join(scripts_dir, script_name)
        if not os.path.exists(script_path):
            return jsonify({"success": False,
                            "error": f"Script file does not exist: {script_name}"}), 404
        return send_file(script_path, as_attachment=True, download_name=script_name)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to download script: {str(e)}")
        return _failed(e)
