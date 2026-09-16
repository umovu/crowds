"""Projects, ontology, graph builds and task status.

  GET    /api/graph/project/<id>          one project
  GET    /api/graph/project/list          every project
  DELETE /api/graph/project/<id>          delete a project and its files
  POST   /api/graph/project/<id>/reset    put it back to rebuildable
  POST   /api/graph/ontology/generate     upload documents, generate the ontology
  POST   /api/graph/build                 start a graph build (background)
  GET    /api/graph/task/<task_id>        build progress
  GET    /api/graph/tasks                 every task
  GET    /api/graph/data/<graph_id>       nodes and edges
  DELETE /api/graph/delete/<graph_id>     delete a graph

The work lives in graph_service. This file reads the request, hands the service what
it cannot fetch for itself — the graph storage and the upload writers, both tied to
the request — and turns the answer into JSON.
"""

import threading
import traceback

from flask import current_app, jsonify, request

from . import graph_bp
from ..config import Config
from ..models.project import ProjectStatus
from ..models.task import TaskManager
from ..repositories import project_repository
from ..services import graph_service
from ..utils.logger import get_logger

logger = get_logger("fub.controller.graph")


def _storage():
    """The GraphStorage on the app. Fetched here: a background thread cannot."""
    storage = current_app.extensions.get("graph_storage")
    if not storage:
        raise ValueError("GraphStorage not initialized")
    return storage


def allowed_file(filename: str) -> bool:
    import os
    if not filename or "." not in filename:
        return False
    return os.path.splitext(filename)[1].lower().lstrip(".") in Config.ALLOWED_EXTENSIONS


def _failed(e: Exception, status: int = 500):
    return jsonify({"success": False, "error": str(e),
                    "traceback": traceback.format_exc()}), status


# ── projects ────────────────────────────────────────────────────────────────
@graph_bp.route('/project/<project_id>', methods=['GET'])
def get_project(project_id: str):
    project = project_repository.get(project_id)
    if not project:
        return jsonify({"success": False,
                        "error": f"Project does not exist: {project_id}"}), 404
    return jsonify({"success": True, "data": project.to_dict()})


@graph_bp.route('/project/list', methods=['GET'])
def list_projects():
    projects = project_repository.list_projects(limit=request.args.get('limit', 50, type=int))
    return jsonify({"success": True, "data": [p.to_dict() for p in projects],
                    "count": len(projects)})


@graph_bp.route('/project/<project_id>', methods=['DELETE'])
def delete_project(project_id: str):
    if not project_repository.delete(project_id):
        return jsonify({"success": False,
                        "error": f"Project does not exist or deletion failed: {project_id}"}), 404
    return jsonify({"success": True, "message": f"Project deleted: {project_id}"})


@graph_bp.route('/project/<project_id>/reset', methods=['POST'])
def reset_project(project_id: str):
    project = project_repository.get(project_id)
    if not project:
        return jsonify({"success": False,
                        "error": f"Project does not exist: {project_id}"}), 404
    project = graph_service.reset_project(project)
    return jsonify({"success": True, "message": f"Project reset: {project_id}",
                    "data": project.to_dict()})


# ── ontology ────────────────────────────────────────────────────────────────
@graph_bp.route('/ontology/generate', methods=['POST'])
def generate_ontology():
    """Upload documents (multipart/form-data) and generate an ontology from them.

    Files are optional when `simulation_requirement` is substantial — a
    web-research briefing can serve as the document on its own.
    """
    try:
        simulation_requirement = request.form.get('simulation_requirement', '')
        if not simulation_requirement:
            return jsonify({"success": False,
                            "error": "Please provide simulation requirement description "
                                     "(simulation_requirement)"}), 400

        uploads = [(f.filename, f.save) for f in request.files.getlist('files')
                   if f and f.filename and allowed_file(f.filename)]
        if not uploads and len(simulation_requirement.strip()) < 100:
            return jsonify({"success": False, "error": (
                "Provide at least one document file OR a substantial "
                "simulation_requirement (100+ characters) describing your scenario."
            )}), 400

        project = project_repository.create(name=request.form.get('project_name',
                                                                  'Unnamed Project'))
        project.simulation_requirement = simulation_requirement
        enrichment = request.form.get('enrichment_data', '')
        if enrichment:
            try:
                import json
                project.enrichment_data = json.loads(enrichment)
            except Exception as e:  # noqa: BLE001 - bad enrichment must not fail the upload
                logger.warning("Failed to parse enrichment data: %s", e)

        try:
            project = graph_service.build_ontology(
                project, uploads, simulation_requirement,
                request.form.get('additional_context', ''))
        except graph_service.NoDocuments as e:
            project_repository.delete(project.project_id)
            return jsonify({"success": False, "error": str(e)}), 400

        return jsonify({"success": True, "data": {
            "project_id": project.project_id,
            "project_name": project.name,
            "ontology": project.ontology,
            "analysis_summary": project.analysis_summary,
            "files": project.files,
            "total_text_length": project.total_text_length,
            "custom_agents": project.custom_agents,
            "custom_agents_count": len(project.custom_agents),
        }})
    except Exception as e:  # noqa: BLE001
        return _failed(e)


# ── graph build ─────────────────────────────────────────────────────────────
@graph_bp.route('/build', methods=['POST'])
def build_graph():
    """Start a graph build on a background thread; poll /task/<task_id> for progress."""
    try:
        data = request.get_json() or {}
        project_id = data.get('project_id')
        if not project_id:
            return jsonify({"success": False, "error": "Please provide project_id"}), 400

        project = project_repository.get(project_id)
        if not project:
            return jsonify({"success": False,
                            "error": f"Project does not exist: {project_id}"}), 404

        force = data.get('force', False)
        refusal = graph_service.check_buildable(project, force)
        if refusal:
            body = {"success": False, "error": refusal}
            if project.graph_build_task_id:
                body["task_id"] = project.graph_build_task_id
            return jsonify(body), 400
        if force:
            project = graph_service.reset_project(project)

        text = project_repository.get_extracted_text(project_id)
        if not text:
            return jsonify({"success": False, "error": "Extracted text not found"}), 400
        if not project.ontology:
            return jsonify({"success": False, "error": "Ontology definition not found"}), 400

        graph_name = data.get('graph_name', project.name or 'Fub Simulation Graph')
        project.chunk_size = data.get('chunk_size', project.chunk_size or Config.DEFAULT_CHUNK_SIZE)
        project.chunk_overlap = data.get('chunk_overlap',
                                         project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP)

        # Fetched in the request: the background thread has no app context.
        storage = _storage()
        task_manager = TaskManager()
        task_id = task_manager.create_task(f"Build graph: {graph_name}")
        logger.info("Graph build task created: task_id=%s, project_id=%s", task_id, project_id)

        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        project_repository.save(project)

        threading.Thread(target=graph_service.build_graph, daemon=True, kwargs={
            "project": project, "storage": storage, "task_id": task_id,
            "task_manager": task_manager, "text": text, "ontology": project.ontology,
            "graph_name": graph_name, "chunk_size": project.chunk_size,
            "chunk_overlap": project.chunk_overlap,
        }).start()

        return jsonify({"success": True, "data": {
            "project_id": project_id, "task_id": task_id,
            "message": "Graph build task started. Query progress via /task/{task_id}",
        }})
    except Exception as e:  # noqa: BLE001
        # Logged as well as returned: this used to surface as a bare 500 with no cause.
        logger.error("build_graph failed (synchronous phase): %s", e)
        logger.error(traceback.format_exc())
        return _failed(e)


# ── tasks ───────────────────────────────────────────────────────────────────
@graph_bp.route('/task/<task_id>', methods=['GET'])
def get_task(task_id: str):
    task = TaskManager().get_task(task_id)
    if not task:
        return jsonify({"success": False, "error": f"Task does not exist: {task_id}"}), 404
    return jsonify({"success": True, "data": task.to_dict()})


@graph_bp.route('/tasks', methods=['GET'])
def list_tasks():
    tasks = TaskManager().list_tasks()
    return jsonify({"success": True, "data": tasks, "count": len(tasks)})


# ── graph data ──────────────────────────────────────────────────────────────
@graph_bp.route('/data/<graph_id>', methods=['GET'])
def get_graph_data(graph_id: str):
    try:
        return jsonify({"success": True,
                        "data": graph_service.graph_data(_storage(), graph_id)})
    except Exception as e:  # noqa: BLE001
        return _failed(e)


@graph_bp.route('/delete/<graph_id>', methods=['DELETE'])
def delete_graph(graph_id: str):
    try:
        graph_service.delete_graph(_storage(), graph_id)
        return jsonify({"success": True, "message": f"Graph deleted: {graph_id}"})
    except Exception as e:  # noqa: BLE001
        return _failed(e)
