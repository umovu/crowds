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

import traceback

from flask import current_app, jsonify, request, send_file

from . import simulation_read_bp
from ..auth import current_user_id
from ..repositories import simulation_repository as repo
from ..services import simulation_read_service
from ..services.entity_reader import EntityReader
from ..services.simulation_manager import SimulationManager, SimulationStatus
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
