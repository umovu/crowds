"""Generating, reading and chatting about simulation reports.

  POST   /api/report/generate                     start a report (background)
  POST   /api/report/generate/status              progress of that task
  GET    /api/report/<report_id>                  one report
  GET    /api/report/by-simulation/<sim_id>       the report for a simulation
  GET    /api/report/list                         every report
  GET    /api/report/<report_id>/download         the assembled markdown
  DELETE /api/report/<report_id>                  delete a report
  POST   /api/report/chat                         ask the report agent a question
  GET    /api/report/<report_id>/progress         generation progress
  GET    /api/report/<report_id>/sections         sections written so far
  GET    /api/report/<report_id>/section/<index>  one section
  GET    /api/report/check/<simulation_id>        is a report ready
  GET    /api/report/<report_id>/agent-log        structured agent log
  GET    /api/report/<report_id>/agent-log/stream the whole agent log
  GET    /api/report/<report_id>/console-log      console log
  GET    /api/report/<report_id>/console-log/stream  the whole console log
  POST   /api/report/tools/search                 graph search (debugging)
  POST   /api/report/tools/statistics             graph stats (debugging)

Reports are written section by section, so the progress and section routes exist to
let the UI show a report as it is built.

`storage` and the graph tools are built here, inside the request: report generation
runs on a background thread that cannot reach `current_app`.
"""

import threading
import traceback
import uuid

from flask import current_app, jsonify, request, send_file

from . import report_bp
from ..models.task import TaskStatus, TaskManager
from ..repositories import project_repository
from ..services.graph_tools import GraphToolsService
from ..services.report_agent import ReportAgent, ReportManager, ReportStatus
from ..services.simulation_manager import SimulationManager
from ..utils.logger import get_logger

logger = get_logger("fub.controller.report")


def _failed(what: str, e: Exception, status: int = 500):
    logger.error("%s: %s", what, e)
    return jsonify({"success": False, "error": str(e),
                    "traceback": traceback.format_exc()}), status


def _graph_tools():
    """Graph tools for this request. Raises when Neo4j is not connected."""
    storage = current_app.extensions.get("graph_storage")
    if not storage:
        raise ValueError("GraphStorage not initialized — check Neo4j connection")
    return GraphToolsService(storage=storage)


def _simulation_context(simulation_id: str):
    """(graph_id, simulation_requirement) for a simulation, or an error response."""
    state = SimulationManager().get_simulation(simulation_id)
    if not state:
        return None, jsonify({"success": False,
                              "error": f"Simulation does not exist: {simulation_id}"}), 404
    project = project_repository.get(state.project_id)
    if not project:
        return None, jsonify({"success": False,
                              "error": f"Project does not exist: {state.project_id}"}), 404
    graph_id = state.graph_id or project.graph_id
    if not graph_id:
        return None, jsonify({"success": False,
                              "error": "Missing graph ID, please ensure graph is built"}), 400
    return (graph_id, project.simulation_requirement), None, None


# ── generation ──────────────────────────────────────────────────────────────
@report_bp.route('/generate', methods=['POST'])
def generate_report():
    try:
        data = request.get_json() or {}
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({"success": False, "error": "Please provide simulation_id"}), 400

        if not data.get('force_regenerate', False):
            existing = ReportManager.get_report_by_simulation(simulation_id)
            if existing and existing.status == ReportStatus.COMPLETED:
                return jsonify({"success": True, "data": {
                    "simulation_id": simulation_id, "report_id": existing.report_id,
                    "status": "completed", "message": "Report already exists",
                    "already_generated": True}})

        context, error, status = _simulation_context(simulation_id)
        if error is not None:
            return error, status
        graph_id, simulation_requirement = context
        if not simulation_requirement:
            return jsonify({"success": False,
                            "error": "Missing simulation requirement description"}), 400

        report_id = f"report_{uuid.uuid4().hex[:12]}"
        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="report_generate",
            metadata={"simulation_id": simulation_id, "graph_id": graph_id,
                      "report_id": report_id})

        # Built in the request: the background thread has no app context.
        graph_tools = _graph_tools()

        def run_generate():
            try:
                task_manager.update_task(task_id, status=TaskStatus.PROCESSING, progress=0,
                                         message="Initializing Report Agent...")
                agent = ReportAgent(graph_id=graph_id, simulation_id=simulation_id,
                                    simulation_requirement=simulation_requirement,
                                    graph_tools=graph_tools)

                def on_progress(stage, progress, message):
                    task_manager.update_task(task_id, progress=progress,
                                             message=f"[{stage}] {message}")

                report = agent.generate_report(progress_callback=on_progress,
                                               report_id=report_id)
                ReportManager.save_report(report)
                if report.status == ReportStatus.COMPLETED:
                    task_manager.complete_task(task_id, result={
                        "report_id": report.report_id, "simulation_id": simulation_id,
                        "status": "completed"})
                else:
                    task_manager.fail_task(task_id, report.error or "Report generation failed")
            except Exception as e:  # noqa: BLE001 - reported on the task, never raised
                logger.error("Report generation failed: %s", e)
                task_manager.fail_task(task_id, str(e))

        threading.Thread(target=run_generate, daemon=True).start()

        return jsonify({"success": True, "data": {
            "simulation_id": simulation_id, "report_id": report_id, "task_id": task_id,
            "status": "generating", "already_generated": False,
            "message": "Report generation task started. "
                       "Query progress via /api/report/generate/status"}})
    except Exception as e:  # noqa: BLE001
        return _failed("Failed to start report generation task", e)


@report_bp.route('/generate/status', methods=['POST'])
def get_generate_status():
    try:
        data = request.get_json() or {}
        task_id = data.get('task_id')
        simulation_id = data.get('simulation_id')
        # A finished report wins over task progress, even when both ids are sent:
        # the UI polls this while generating and must stop as soon as one exists.
        if simulation_id:
            existing = ReportManager.get_report_by_simulation(simulation_id)
            if existing and existing.status == ReportStatus.COMPLETED:
                return jsonify({"success": True, "data": {
                    "simulation_id": simulation_id,
                    "report_id": existing.report_id,
                    "status": "completed",
                    "progress": 100,
                    "message": "Report generated",
                    "already_completed": True,
                }})

        if not task_id:
            return jsonify({"success": False,
                            "error": "Please provide task_id or simulation_id"}), 400

        task = TaskManager().get_task(task_id)
        if not task:
            return jsonify({"success": False,
                            "error": f"Task does not exist: {task_id}"}), 404
        return jsonify({"success": True, "data": task.to_dict()})
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to query task status: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


# ── reading ─────────────────────────────────────────────────────────────────
@report_bp.route('/<report_id>', methods=['GET'])
def get_report(report_id: str):
    try:
        report = ReportManager.get_report(report_id)
        if not report:
            return jsonify({"success": False,
                            "error": f"Report does not exist: {report_id}"}), 404
        return jsonify({"success": True, "data": report.to_dict()})
    except Exception as e:  # noqa: BLE001
        return _failed("Failed to get report", e)


@report_bp.route('/by-simulation/<simulation_id>', methods=['GET'])
def get_report_by_simulation(simulation_id: str):
    try:
        report = ReportManager.get_report_by_simulation(simulation_id)
        if not report:
            return jsonify({"success": False, "has_report": False,
                            "error": f"No report available for this simulation: "
                                     f"{simulation_id}"}), 404
        return jsonify({"success": True, "data": report.to_dict()})
    except Exception as e:  # noqa: BLE001
        return _failed("Failed to get report", e)


@report_bp.route('/list', methods=['GET'])
def list_reports():
    try:
        reports = ReportManager.list_reports(
            simulation_id=request.args.get('simulation_id'),
            limit=request.args.get('limit', 50, type=int))
        return jsonify({"success": True, "data": [r.to_dict() for r in reports],
                        "count": len(reports)})
    except Exception as e:  # noqa: BLE001
        return _failed("Failed to list reports", e)


@report_bp.route('/<report_id>/download', methods=['GET'])
def download_report(report_id: str):
    try:
        report = ReportManager.get_report(report_id)
        if not report:
            return jsonify({"success": False,
                            "error": f"Report does not exist: {report_id}"}), 404
        path = ReportManager.markdown_path(report_id)
        if path:
            return send_file(path, as_attachment=True, download_name=f"{report_id}.md")
        # Never assembled on disk: send what the metadata holds.
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False,
                                         encoding='utf-8') as fh:
            fh.write(report.markdown_content)
            temp_path = fh.name
        return send_file(temp_path, as_attachment=True, download_name=f"{report_id}.md")
    except Exception as e:  # noqa: BLE001
        return _failed("Failed to download report", e)


@report_bp.route('/<report_id>', methods=['DELETE'])
def delete_report(report_id: str):
    try:
        if not ReportManager.delete_report(report_id):
            return jsonify({"success": False,
                            "error": f"Report does not exist: {report_id}"}), 404
        return jsonify({"success": True, "message": f"Report deleted: {report_id}"})
    except Exception as e:  # noqa: BLE001
        return _failed("Failed to delete report", e)


# ── chat ────────────────────────────────────────────────────────────────────
@report_bp.route('/chat', methods=['POST'])
def chat_with_report_agent():
    import signal

    class Timeout(Exception):
        pass

    def on_alarm(signum, frame):
        raise Timeout("Request timed out after 60 seconds")

    try:
        data = request.get_json() or {}
        simulation_id = data.get('simulation_id')
        message = data.get('message')
        if not simulation_id:
            return jsonify({"success": False, "error": "Please provide simulation_id"}), 400
        if not message:
            return jsonify({"success": False, "error": "Please provide message"}), 400

        context, error, status = _simulation_context(simulation_id)
        if error is not None:
            return error, status
        graph_id, simulation_requirement = context

        agent = ReportAgent(graph_id=graph_id, simulation_id=simulation_id,
                            simulation_requirement=simulation_requirement or "",
                            graph_tools=_graph_tools())

        # SIGALRM only exists on unix; on Windows the call simply runs unbounded.
        if hasattr(signal, 'SIGALRM'):
            signal.signal(signal.SIGALRM, on_alarm)
            signal.alarm(60)
        try:
            answer = agent.chat(message=message, chat_history=data.get('chat_history', []))
        finally:
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)

        return jsonify({"success": True, "data": {"response": answer,
                                                  "simulation_id": simulation_id}})
    except Timeout as e:
        logger.error("Chat timed out: %s", e)
        return jsonify({"success": False, "timeout": True,
                        "error": "Request timed out. Please try again."}), 504
    except Exception as e:  # noqa: BLE001
        return _failed("Chat failed", e)


# ── progress and sections ───────────────────────────────────────────────────
@report_bp.route('/<report_id>/progress', methods=['GET'])
def get_report_progress(report_id: str):
    try:
        progress = ReportManager.get_progress(report_id)
        if not progress:
            return jsonify({"success": False,
                            "error": f"Report does not exist or progress info "
                                     f"unavailable: {report_id}"}), 404
        return jsonify({"success": True, "data": progress})
    except Exception as e:  # noqa: BLE001
        return _failed("Failed to get report progress", e)


@report_bp.route('/<report_id>/sections', methods=['GET'])
def get_report_sections(report_id: str):
    try:
        sections = ReportManager.get_generated_sections(report_id)
        report = ReportManager.get_report(report_id)
        return jsonify({"success": True, "data": {
            "report_id": report_id, "sections": sections, "total": len(sections),
            "is_complete": report is not None and report.status == ReportStatus.COMPLETED}})
    except Exception as e:  # noqa: BLE001
        return _failed("Failed to get section list", e)


@report_bp.route('/<report_id>/section/<int:section_index>', methods=['GET'])
def get_single_section(report_id: str, section_index: int):
    try:
        section = ReportManager.get_section(report_id, section_index)
        if not section:
            return jsonify({"success": False,
                            "error": f"Section does not exist: "
                                     f"section_{section_index:02d}.md"}), 404
        return jsonify({"success": True, "data": section})
    except Exception as e:  # noqa: BLE001
        return _failed("Failed to get section content", e)


@report_bp.route('/check/<simulation_id>', methods=['GET'])
def check_report_status(simulation_id: str):
    try:
        report = ReportManager.get_report_by_simulation(simulation_id)
        status = None
        if report is not None:
            status = report.status.value if hasattr(report.status, 'value') else report.status
        return jsonify({"success": True, "data": {
            "simulation_id": simulation_id,
            "has_report": report is not None,
            "report_id": report.report_id if report else None,
            "report_status": status,
            # The post-run interview opens once a report exists.
            "interview_unlocked": report is not None
                                  and report.status == ReportStatus.COMPLETED}})
    except Exception as e:  # noqa: BLE001
        return _failed("Failed to check report status", e)


# ── logs ────────────────────────────────────────────────────────────────────
@report_bp.route('/<report_id>/agent-log', methods=['GET'])
def get_agent_log(report_id: str):
    try:
        return jsonify({"success": True, "data": ReportManager.get_agent_log(
            report_id, from_line=request.args.get('from_line', 0, type=int))})
    except Exception as e:  # noqa: BLE001
        return _failed("Failed to get agent log", e)


@report_bp.route('/<report_id>/agent-log/stream', methods=['GET'])
def stream_agent_log(report_id: str):
    try:
        logs = ReportManager.get_agent_log_stream(report_id)
        return jsonify({"success": True, "data": {"logs": logs, "count": len(logs)}})
    except Exception as e:  # noqa: BLE001
        return _failed("Failed to get agent log", e)


@report_bp.route('/<report_id>/console-log', methods=['GET'])
def get_console_log(report_id: str):
    try:
        return jsonify({"success": True, "data": ReportManager.get_console_log(
            report_id, from_line=request.args.get('from_line', 0, type=int))})
    except Exception as e:  # noqa: BLE001
        return _failed("Failed to get console log", e)


@report_bp.route('/<report_id>/console-log/stream', methods=['GET'])
def stream_console_log(report_id: str):
    try:
        logs = ReportManager.get_console_log_stream(report_id)
        return jsonify({"success": True, "data": {"logs": logs, "count": len(logs)}})
    except Exception as e:  # noqa: BLE001
        return _failed("Failed to get console log", e)


# ── graph tools (debugging) ─────────────────────────────────────────────────
@report_bp.route('/tools/search', methods=['POST'])
def search_graph_tool():
    try:
        data = request.get_json() or {}
        graph_id, query = data.get('graph_id'), data.get('query')
        if not graph_id or not query:
            return jsonify({"success": False,
                            "error": "Please provide graph_id and query"}), 400
        result = _graph_tools().search_graph(graph_id=graph_id, query=query,
                                            limit=data.get('limit', 10))
        return jsonify({"success": True, "data": result.to_dict()})
    except Exception as e:  # noqa: BLE001
        return _failed("Graph search failed", e)


@report_bp.route('/tools/statistics', methods=['POST'])
def get_graph_statistics_tool():
    try:
        graph_id = (request.get_json() or {}).get('graph_id')
        if not graph_id:
            return jsonify({"success": False, "error": "Please provide graph_id"}), 400
        return jsonify({"success": True,
                        "data": _graph_tools().get_graph_statistics(graph_id)})
    except Exception as e:  # noqa: BLE001
        return _failed("Failed to get graph statistics", e)
