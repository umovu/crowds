"""
Simulation-related API routes
Step2: Entity reading and filtering, OASIS simulation preparation and execution (fully automated)
"""

import os
import traceback
import asyncio
from typing import Dict, Any, List, Optional
from flask import request, jsonify, send_file, current_app

from . import simulation_bp
from ..config import Config
from ..services.entity_reader import EntityReader
from ..services.agent_profile_generator import AgentProfileGenerator
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner, RunnerStatus
from ..services.topic_extractor import TopicExtractor
from ..services.interview_service import InterviewService
from ..services.custom_agent_parser import CustomAgentParser
from ..services.agent_enricher import AgentContextEnricher
from ..services.deep_research_service import research_archetypes as _deep_research_archetypes
from ..utils.logger import get_logger
from ..models.project import ProjectManager

logger = get_logger('fub.api.simulation')


# Interview prompt optimization prefix
# Adding this prefix can prevent agents from calling tools and reply directly with text
INTERVIEW_PROMPT_PREFIX = """You are being interviewed about a specific South African policy. Follow these rules STRICTLY:

SPEAKING STYLE:
- Speak as a real South African with lived experience in your community
- Use natural language - you may include SA slang, vernacular, or code-switching where appropriate
- Express yourself as a person with authentic perspective, not as a policy analyst

VOICE:
- If your persona represents a community or collective, use 'we' and 'our community' to express shared views
- If your persona is an individual, use 'I' and 'my' perspective
- Ground your response in how this policy or question affects YOUR LIVELIHOOD, FAMILY, or COMMUNITY

TOPIC FOCUS:
- Stay STRICTLY on the policy or question being asked
- Keep responses concrete and specific about the policy's direct impacts
- Do not volunteer information about sports, entertainment, unrelated political issues, or personal matters unconnected to the topic

RESPONSE FORMAT:
- Reply directly with text only - do not call any tools
- Be concise but substantive - 2-4 sentences minimum for structured questions"""


def optimize_interview_prompt(prompt: str) -> str:
    """
    Optimize Interview questions, add prefix to avoid agent calling tools
    
    Args:
        prompt: Original question
        
    Returns:
        Optimized question
    """
    if not prompt:
        return prompt
    # Avoid adding prefix repeatedly
    if prompt.startswith(INTERVIEW_PROMPT_PREFIX):
        return prompt
    return f"{INTERVIEW_PROMPT_PREFIX}{prompt}"


# ============== Entity reading interface ==============

@simulation_bp.route('/entities/<graph_id>', methods=['GET'])
def get_graph_entities(graph_id: str):
    """
    Get all entities from the knowledge graph (filtered)
    
    Only return nodes that match predefined entity types (nodes whose Labels are not just Entity)
    
    Query parameters:
        entity_types: comma-separated list of entity types (optional, for further filtering)
        enrich: whether to get related edge information (default true)
    """
    try:
        entity_types_str = request.args.get('entity_types', '')
        entity_types = [t.strip() for t in entity_types_str.split(',') if t.strip()] if entity_types_str else None
        enrich = request.args.get('enrich', 'true').lower() == 'true'
        
        logger.info(f"Get knowledge graph entities: graph_id={graph_id}, entity_types={entity_types}, enrich={enrich}")
        
        storage = current_app.extensions.get('graph_storage')
        if not storage:
            raise ValueError("GraphStorage not initialized")
        reader = EntityReader(storage)
        result = reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=enrich
        )
        
        return jsonify({
            "success": True,
            "data": result.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Failed to get knowledge graph entities: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/entities/<graph_id>/<entity_uuid>', methods=['GET'])
def get_entity_detail(graph_id: str, entity_uuid: str):
    """Get detailed information of a single entity"""
    try:
        storage = current_app.extensions.get('graph_storage')
        if not storage:
            raise ValueError("GraphStorage not initialized")
        reader = EntityReader(storage)
        entity = reader.get_entity_with_context(graph_id, entity_uuid)
        
        if not entity:
            return jsonify({
                "success": False,
                "error": f"Entity does not exist: {entity_uuid}"
            }), 404
        
        return jsonify({
            "success": True,
            "data": entity.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Failed to get entity details: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/entities/<graph_id>/by-type/<entity_type>', methods=['GET'])
def get_entities_by_type(graph_id: str, entity_type: str):
    """Get all entities of specified type"""
    try:
        enrich = request.args.get('enrich', 'true').lower() == 'true'
        
        storage = current_app.extensions.get('graph_storage')
        if not storage:
            raise ValueError("GraphStorage not initialized")
        reader = EntityReader(storage)
        entities = reader.get_entities_by_type(
            graph_id=graph_id,
            entity_type=entity_type,
            enrich_with_edges=enrich
        )
        
        return jsonify({
            "success": True,
            "data": {
                "entity_type": entity_type,
                "count": len(entities),
                "entities": [e.to_dict() for e in entities]
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get entities: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Custom Agent Parsing ==============

@simulation_bp.route('/custom-agents/parse', methods=['POST'])
def parse_custom_agent_document():
    """
    Parse a custom agent definition document.

    Supports JSON files (direct AgentProfile-compatible arrays)
    and unstructured text (PDF, MD, TXT) via LLM extraction.

    Request: multipart/form-data with 'file' field

    Returns:
        {
            "success": true,
            "data": [ {agent_profile}, ... ]
        }
    """
    try:
        from werkzeug.utils import secure_filename

        if 'file' not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"success": False, "error": "Empty filename"}), 400

        # Save uploaded file temporarily
        upload_dir = os.path.join(os.path.dirname(__file__), '../../uploads/temp')
        os.makedirs(upload_dir, exist_ok=True)
        filename = secure_filename(file.filename)
        file_path = os.path.join(upload_dir, filename)
        file.save(file_path)

        # Get optional simulation context
        simulation_requirement = request.form.get('simulation_requirement', '')

        parser = CustomAgentParser()
        profiles = parser.parse_doc(file_path, simulation_requirement)

        # Clean up temp file
        try:
            os.remove(file_path)
        except Exception:
            pass

        # Serialize profiles for response
        data = [p.to_agentsociety_format() for p in profiles]

        return jsonify({
            "success": True,
            "data": data,
            "count": len(data)
        })

    except Exception as e:
        logger.error(f"Failed to parse custom agent document: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Simulation management interface ==============

@simulation_bp.route('/create', methods=['POST'])
def create_simulation():
    """
    Create new simulation
    
    Note: parameters like max_rounds are intelligently generated by LLM, no manual setting needed
    
    Request (JSON):
        {
            "project_id": "proj_xxxx",  // Required
            "graph_id": "fub_xxxx"      // Optional, if not provided, get from project
        }

    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "project_id": "proj_xxxx",
                "graph_id": "fub_xxxx",
                "status": "created",
                "created_at": "2025-12-01T10:00:00"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        project_id = data.get('project_id')
        if not project_id:
            return jsonify({
                "success": False,
                "error": "Please provide project_id"
            }), 400
        
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Project does not exist: {project_id}"
            }), 404
        
        graph_id = data.get('graph_id') or project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "Project has not built knowledge graph yet, please call /api/graph/build first"
            }), 400
        
        manager = SimulationManager()
        state = manager.create_simulation(
            project_id=project_id,
            graph_id=graph_id,
        )
        
        return jsonify({
            "success": True,
            "data": state.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Failed to create simulation: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


def _check_simulation_prepared(simulation_id: str) -> tuple:
    """
    Check if simulation is ready
    
    Check conditions:
    1. state.json exists and status is "ready"
    2. Required files exist: reddit_profiles.json, twitter_profiles.csv, simulation_config.json
    
    Note: run scripts (run_*.py) remain in backend/scripts/ directory, no longer copied to simulation directory
    
    Args:
        simulation_id: Simulation ID
        
    Returns:
        (is_prepared: bool, info: dict)
    """
    import os
    from ..config import Config
    
    simulation_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
    
    # Check if directory exists
    if not os.path.exists(simulation_dir):
        return False, {"reason": "Simulation directory does not exist"}
    
    required_files = [
        "state.json",
        "simulation_config.json",
        "agentsociety_profiles.json",
    ]
    
    # Check if files exist
    existing_files = []
    missing_files = []
    for f in required_files:
        file_path = os.path.join(simulation_dir, f)
        if os.path.exists(file_path):
            existing_files.append(f)
        else:
            missing_files.append(f)
    
    if missing_files:
        return False, {
            "reason": "Missing required files",
            "missing_files": missing_files,
            "existing_files": existing_files
        }
    
    # Check status in state.json
    state_file = os.path.join(simulation_dir, "state.json")
    try:
        import json
        with open(state_file, 'r', encoding='utf-8') as f:
            state_data = json.load(f)
        
        status = state_data.get("status", "")
        config_generated = state_data.get("config_generated", False)
        
        # Detailed logs
        logger.debug(f"Detect simulation preparation status: {simulation_id}, status={status}, config_generated={config_generated}")
        
        # If config_generated=True and files exist, consider preparation complete
        # The following statuses indicate preparation is complete：
        # - ready: Preparation complete, can run
        # - preparing: If config_generated=True, description shows completed
        # - running: Running, preparation already completed
        # - completed: Execution complete, preparation already completed
        # - stopped: Stopped, preparation already completed
        # - failed: Execution failed (but preparation is not completed)
        prepared_statuses = ["ready", "preparing", "running", "completed", "stopped", "failed", "paused"]
        if status in prepared_statuses and config_generated:
            # Get file statistics
            profiles_file = os.path.join(simulation_dir, "agentsociety_profiles.json")
            config_file = os.path.join(simulation_dir, "simulation_config.json")
            
            profiles_count = 0
            if os.path.exists(profiles_file):
                with open(profiles_file, 'r', encoding='utf-8') as f:
                    profiles_data = json.load(f)
                    profiles_count = len(profiles_data) if isinstance(profiles_data, list) else 0
            
            # If status is "preparing" but files are completed, update status to "ready"
            if status == "preparing":
                try:
                    state_data["status"] = "ready"
                    from datetime import datetime
                    state_data["updated_at"] = datetime.now().isoformat()
                    with open(state_file, 'w', encoding='utf-8') as f:
                        json.dump(state_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"Auto update simulation status: {simulation_id} preparing -> ready")
                    status = "ready"
                except Exception as e:
                    logger.warning(f"Failed to auto update status: {e}")
            
            logger.info(f"Simulation {simulation_id} Detection result: HasPreparation complete (status={status}, config_generated={config_generated})")
            return True, {
                "status": status,
                "entities_count": state_data.get("entities_count", 0),
                "profiles_count": profiles_count,
                "entity_types": state_data.get("entity_types", []),
                "config_generated": config_generated,
                "created_at": state_data.get("created_at"),
                "updated_at": state_data.get("updated_at"),
                "existing_files": existing_files
            }
        else:
            logger.warning(f"Simulation {simulation_id} Detection result: Has notPreparation complete (status={status}, config_generated={config_generated})")
            return False, {
                "reason": f"Status not in prepared list or config_generated is false: status={status}, config_generated={config_generated}",
                "status": status,
                "config_generated": config_generated
            }
            
    except Exception as e:
        return False, {"reason": f"Failed to read state file: {str(e)}"}


@simulation_bp.route('/prepare', methods=['POST'])
def prepare_simulation():
    """
    Prepare simulation environment (async task with LLM intelligent configuration generation).

    This is a time-consuming operation. The interface returns immediately with a task_id.
    Use GET /api/simulation/prepare/status to query progress.

    Features:
    - Automatically detect completed preparations to avoid duplicate generation
    - If already prepared, return existing results directly
    - Support forced regeneration (force_regenerate=true)

    Steps:
    1. Check if preparation is already complete
    2. Read and filter entities from knowledge graph
    3. Generate OASIS Agent Profile for each entity (with retry mechanism)
    4. LLM intelligently generates simulation configuration (with retry mechanism)
    5. Save configuration files and preset scripts
    
    Request (JSON):
        {
            "simulation_id": "sim_xxxx",                   // Required，Simulation ID
            "entity_types": ["Student", "PublicFigure"],  // Optional，Specified entity type
            "use_llm_for_profiles": true,                 // Optional，IsOtherwise useLLMGeneratepersona
            "parallel_profile_count": 5,                  // Optional, number of personas to generate in parallel, default 5
            "force_regenerate": false                     // Optional，ForceGenerate，Defaultfalse
        }
    
    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "task_id": "task_xxxx",           // Return for new tasks
                "status": "preparing|ready",
                "message": "Preparation task started|Preparation already completed",
                "already_prepared": true|false    // Is preparation complete
            }
        }
    """
    import threading
    import os
    from ..models.task import TaskManager, TaskStatus
    from ..config import Config
    
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id"
            }), 400
        
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        
        if not state:
            return jsonify({
                "success": False,
                "error": f"Simulation does not exist: {simulation_id}"
            }), 404
        
        # Check if forced regeneration
        force_regenerate = data.get('force_regenerate', False)
        logger.info(f"Start processing /prepare Request: simulation_id={simulation_id}, force_regenerate={force_regenerate}")
        
        # Check if already prepared（Avoid duplicatesGenerate）
        if not force_regenerate:
            logger.debug(f"Check simulation {simulation_id} Is preparation complete...")
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
            logger.debug(f"Check result: is_prepared={is_prepared}, prepare_info={prepare_info}")
            if is_prepared:
                logger.info(f"Simulation {simulation_id} has preparation complete, no need to regenerate")
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "ready",
                        "message": "Preparation already completed，No need to repeatGenerate",
                        "already_prepared": True,
                        "prepare_info": prepare_info
                    }
                })
            else:
                logger.info(f"Simulation {simulation_id} has no preparation complete, preparing now")
        
        # Get necessary information from project
        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Project does not exist: {state.project_id}"
            }), 404
        
        # Get simulation requirements
        simulation_requirement = project.simulation_requirement or ""
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": "Project missing simulation requirement description (simulation_requirement)"
            }), 400
        
        # Get document text
        document_text = ProjectManager.get_extracted_text(state.project_id) or ""
        
        entity_types_list = data.get('entity_types')
        use_llm_for_profiles = data.get('use_llm_for_profiles', True)
        parallel_profile_count = data.get('parallel_profile_count', 5)
        custom_agents_raw = data.get('custom_agents', [])

        # Parse custom agents if provided in request, else load from project
        custom_profiles = []
        if custom_agents_raw and len(custom_agents_raw) > 0:
            try:
                parser = CustomAgentParser()
                custom_profiles = parser.parse_raw(custom_agents_raw)
                logger.info(f"Received {len(custom_agents_raw)} raw custom agents from request, parsed {len(custom_profiles)} valid profiles")
            except Exception as e:
                logger.warning(f"Failed to parse custom agents from request: {e}")
        elif project.custom_agents and len(project.custom_agents) > 0:
            try:
                parser = CustomAgentParser()
                custom_profiles = parser.parse_raw(project.custom_agents)
                logger.info(f"Loaded {len(project.custom_agents)} custom agents from project, parsed {len(custom_profiles)} valid profiles")
            except Exception as e:
                logger.warning(f"Failed to parse custom agents from project: {e}")

        # ========== Get GraphStorage（Capture reference before background task starts） ==========
        storage = current_app.extensions.get('graph_storage')
        if not storage:
            raise ValueError("GraphStorage not initialized — check Neo4j connection")

        # ========== Synchronously get entity count（Before background task starts） ==========
        # This way frontend when callingprepareCan immediately getExpected total agents
        try:
            logger.info(f"Synchronously get entity count: graph_id={state.graph_id}")
            reader = EntityReader(storage)
            # Quickly read entities (no edge information, only statistics required)
            filtered_preview = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=entity_types_list,
                enrich_with_edges=False  # No edge information，Speed up
            )
            # Save entity count to status（For frontend to get immediately）
            state.entities_count = filtered_preview.filtered_count
            state.entity_types = list(filtered_preview.entity_types)
            logger.info(f"Expected entity count: {filtered_preview.filtered_count}, [type][model]: {filtered_preview.entity_types}")
        except Exception as e:
            logger.warning(f"Synchronously get entity countFailed（Will retry in background task）: {e}")
            # Failure does not affect subsequent process，Background task will retry
        
        # Create async task
        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="simulation_prepare",
            metadata={
                "simulation_id": simulation_id,
                "project_id": state.project_id
            }
        )
        
        # Update simulation status（Include pre-fetched entity count）
        state.status = SimulationStatus.PREPARING
        manager._save_simulation_state(state)
        
        # Define background task
        def run_prepare():
            try:
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=0,
                    message="Start preparing simulation environment..."
                )
                
                # PrepareSimulation（With progress callback）
                # Store stage progress details
                stage_details = {}
                
                def progress_callback(stage, progress, message, **kwargs):
                    # Calculate total progress
                    stage_weights = {
                        "reading": (0, 20),           # 0-20%
                        "generating_profiles": (20, 70),  # 20-70%
                        "generating_config": (70, 90),    # 70-90%
                        "copying_scripts": (90, 100)       # 90-100%
                    }
                    
                    start, end = stage_weights.get(stage, (0, 100))
                    current_progress = int(start + (end - start) * progress / 100)
                    
                    # Build detailed progress information
                    stage_names = {
                        "reading": "Read knowledge graph entities",
                        "generating_profiles": "GenerateAgentpersona",
                        "generating_config": "Generate simulation configuration",
                        "copying_scripts": "Prepare simulation scripts"
                    }
                    
                    stage_index = list(stage_weights.keys()).index(stage) + 1 if stage in stage_weights else 1
                    total_stages = len(stage_weights)
                    
                    # Update stage details
                    stage_details[stage] = {
                        "stage_name": stage_names.get(stage, stage),
                        "stage_progress": progress,
                        "current": kwargs.get("current", 0),
                        "total": kwargs.get("total", 0),
                        "item_name": kwargs.get("item_name", "")
                    }
                    
                    # Build detailed progress information
                    detail = stage_details[stage]
                    progress_detail_data = {
                        "current_stage": stage,
                        "current_stage_name": stage_names.get(stage, stage),
                        "stage_index": stage_index,
                        "total_stages": total_stages,
                        "stage_progress": progress,
                        "current_item": detail["current"],
                        "total_items": detail["total"],
                        "item_description": message
                    }
                    
                    # Build concise message
                    if detail["total"] > 0:
                        detailed_message = (
                            f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: "
                            f"{detail['current']}/{detail['total']} - {message}"
                        )
                    else:
                        detailed_message = f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: {message}"
                    
                    task_manager.update_task(
                        task_id,
                        progress=current_progress,
                        message=detailed_message,
                        progress_detail=progress_detail_data
                    )
                
                result_state = manager.prepare_simulation(
                    simulation_id=simulation_id,
                    simulation_requirement=simulation_requirement,
                    document_text=document_text,
                    defined_entity_types=entity_types_list,
                    use_llm_for_profiles=use_llm_for_profiles,
                    progress_callback=progress_callback,
                    parallel_profile_count=parallel_profile_count,
                    storage=storage,
                    custom_profiles=custom_profiles,
                )

                # prepare_simulation returns a FAILED state (instead of raising)
                # for known issues like 0 matching entities. Surface that as a
                # failed task so the frontend stops polling and shows the error.
                if getattr(result_state, "status", None) == SimulationStatus.FAILED:
                    task_manager.fail_task(
                        task_id,
                        result_state.error or "Preparation failed"
                    )
                else:
                    task_manager.complete_task(
                        task_id,
                        result=result_state.to_simple_dict()
                    )
                
            except Exception as e:
                logger.error(f"Failed to prepare simulation: {str(e)}")
                task_manager.fail_task(task_id, str(e))
                
                # Update simulation status to failed
                state = manager.get_simulation(simulation_id)
                if state:
                    state.status = SimulationStatus.FAILED
                    state.error = str(e)
                    manager._save_simulation_state(state)
        
        # Start background thread
        thread = threading.Thread(target=run_prepare, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "task_id": task_id,
                "status": "preparing",
                "message": "Preparation task started，Please via /api/simulation/prepare/status Query progress",
                "already_prepared": False,
                "expected_entities_count": state.entities_count,  # Expected number of entities to process
                "entity_types": state.entity_types  # Entity type list
            }
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404
        
    except Exception as e:
        logger.error(f"Failed to start preparation task: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/prepare/status', methods=['POST'])
def get_prepare_status():
    """
    Query preparation task progress
    
    Support two query methods:
    1. Query via task_id to check ongoing task progress
    2. Check via simulation_id to verify if preparation is already completed
    
    Request (JSON):
        {
            "task_id": "task_xxxx",          // Optional, from previous /prepare call
            "simulation_id": "sim_xxxx"      // Optional，Simulation ID（For checking completedPrepare）
        }
    
    Returns:
        {
            "success": true,
            "data": {
                "task_id": "task_xxxx",
                "status": "processing|completed|ready",
                "progress": 45,
                "message": "...",
                "already_prepared": true|false,  // Is there completed preparation
                "prepare_info": {...}            // Detailed information when preparation complete
            }
        }
    """
    from ..models.task import TaskManager
    
    try:
        data = request.get_json() or {}
        
        task_id = data.get('task_id')
        simulation_id = data.get('simulation_id')
        
        # If simulation_id is provided, check if preparation is complete
        if simulation_id:
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
            if is_prepared:
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "ready",
                        "progress": 100,
                        "message": "Preparation already completed",
                        "already_prepared": True,
                        "prepare_info": prepare_info
                    }
                })
        
        # If no task_id，ReturnError
        if not task_id:
            if simulation_id:
                # Have simulation_idBut notPreparation complete
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "not_started",
                        "progress": 0,
                        "message": "Preparation not started yet, please call /api/simulation/prepare",
                        "already_prepared": False
                    }
                })
            return jsonify({
                "success": False,
                "error": "Please provide task_id Or simulation_id"
            }), 400
        
        task_manager = TaskManager()
        task = task_manager.get_task(task_id)
        
        if not task:
            # Task does not exist, but if simulation_id is provided, check if preparation is complete
            if simulation_id:
                is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
                if is_prepared:
                    return jsonify({
                        "success": True,
                        "data": {
                            "simulation_id": simulation_id,
                            "task_id": task_id,
                            "status": "ready",
                            "progress": 100,
                            "message": "Task complete（PrepareWork already exists）",
                            "already_prepared": True,
                            "prepare_info": prepare_info
                        }
                    })
            
            return jsonify({
                "success": False,
                "error": f"Task does not exist: {task_id}"
            }), 404
        
        task_dict = task.to_dict()
        task_dict["already_prepared"] = False
        
        return jsonify({
            "success": True,
            "data": task_dict
        })
        
    except Exception as e:
        logger.error(f"Failed to query task status: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/<simulation_id>', methods=['GET'])
def get_simulation(simulation_id: str):
    """Get simulation status"""
    try:
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        
        if not state:
            return jsonify({
                "success": False,
                "error": f"Simulation does not exist: {simulation_id}"
            }), 404
        
        result = state.to_dict()
        
        # If simulation is ready，Additional runtime instructions
        if state.status == SimulationStatus.READY:
            result["run_instructions"] = manager.get_run_instructions(simulation_id)
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"Failed to get simulation status: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/list', methods=['GET'])
def list_simulations():
    """
    List all simulations
    
    Query parameters:
        project_id: By projectIDFilter（Optional）
    """
    try:
        project_id = request.args.get('project_id')
        
        manager = SimulationManager()
        simulations = manager.list_simulations(project_id=project_id)
        
        return jsonify({
            "success": True,
            "data": [s.to_dict() for s in simulations],
            "count": len(simulations)
        })
        
    except Exception as e:
        logger.error(f"Failed to list simulations: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


def _get_report_id_for_simulation(simulation_id: str) -> str:
    """
    Get simulation Corresponding latest report_id
    
    Traverse reports directory and find the report matching the simulation_id.
    If multiple exist, return the latest one (by created_at timestamp).
    
    Args:
        simulation_id: Simulation ID
        
    Returns:
        report_id Or None
    """
    import json
    from datetime import datetime
    
    # reports Directory path：backend/uploads/reports
    # __file__ Is app/api/simulation.py，Need to go up two levels to backend/
    reports_dir = os.path.join(os.path.dirname(__file__), '../../uploads/reports')
    if not os.path.exists(reports_dir):
        return None
    
    matching_reports = []
    
    try:
        for report_folder in os.listdir(reports_dir):
            report_path = os.path.join(reports_dir, report_folder)
            if not os.path.isdir(report_path):
                continue
            
            meta_file = os.path.join(report_path, "meta.json")
            if not os.path.exists(meta_file):
                continue
            
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                
                if meta.get("simulation_id") == simulation_id:
                    matching_reports.append({
                        "report_id": meta.get("report_id"),
                        "created_at": meta.get("created_at", ""),
                        "status": meta.get("status", "")
                    })
            except Exception:
                continue
        
        if not matching_reports:
            return None
        
        # Sort by creation time descending，ReturnLatest
        matching_reports.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return matching_reports[0].get("report_id")
        
    except Exception as e:
        logger.warning(f"Failed to find report for simulation {simulation_id}: {e}")
        return None


@simulation_bp.route('/history', methods=['GET'])
def get_simulation_history():
    """
    Get historical simulation list（With project details）
    
    For homepage historical project display. Returns project name and other information about the simulation.
    
    Query parameters:
        limit: Return count limit（Default20）
    
    Returns:
        {
            "success": true,
            "data": [
                {
                    "simulation_id": "sim_xxxx",
                    "project_id": "proj_xxxx",
                    "project_name": "WDU Opinion Analysis",
                    "simulation_requirement": "If Wuhan University publishes...",
                    "status": "completed",
                    "entities_count": 68,
                    "profiles_count": 68,
                    "entity_types": ["Student", "Professor", ...],
                    "created_at": "2024-12-10",
                    "updated_at": "2024-12-10",
                    "total_rounds": 120,
                    "current_round": 120,
                    "report_id": "report_xxxx",
                    "version": "v1.0.2"
                },
                ...
            ],
            "count": 7
        }
    """
    try:
        limit = request.args.get('limit', 20, type=int)
        
        manager = SimulationManager()
        simulations = manager.list_simulations()[:limit]
        
        # Enhance simulation data，Only from Simulation FileRead
        enriched_simulations = []
        for sim in simulations:
            sim_dict = sim.to_dict()
            
            # Get simulation configuration information（From simulation_config.json Read simulation_requirement）
            config = manager.get_simulation_config(sim.simulation_id)
            if config:
                sim_dict["simulation_requirement"] = config.get("simulation_requirement", "")
                time_config = config.get("time_config", {})
                sim_dict["total_simulation_hours"] = time_config.get("total_simulation_hours", 0)
                # Recommended rounds（Fallback value）
                recommended_rounds = int(
                    time_config.get("total_simulation_hours", 0) * 60 / 
                    max(time_config.get("minutes_per_round", 60), 1)
                )
            else:
                sim_dict["simulation_requirement"] = ""
                sim_dict["total_simulation_hours"] = 0
                recommended_rounds = 0
            
            # Get running status (from run_state.json)
            run_state = SimulationRunner.get_run_state(sim.simulation_id)
            if run_state:
                sim_dict["current_round"] = run_state.current_round
                sim_dict["runner_status"] = run_state.runner_status.value
                # Use user-set total_rounds，If not, thenUseRecommended rounds
                sim_dict["total_rounds"] = run_state.total_rounds if run_state.total_rounds > 0 else recommended_rounds
            else:
                sim_dict["current_round"] = 0
                sim_dict["runner_status"] = "idle"
                sim_dict["total_rounds"] = recommended_rounds
            
            # Get associated project file list（At most3items）
            project = ProjectManager.get_project(sim.project_id)
            if project and hasattr(project, 'files') and project.files:
                sim_dict["files"] = [
                    {"filename": f.get("filename", "Unknown file")} 
                    for f in project.files[:3]
                ]
            else:
                sim_dict["files"] = []
            
            # Get associated report_id（FindThis simulation Latest report）
            sim_dict["report_id"] = _get_report_id_for_simulation(sim.simulation_id)
            
            # Add version number
            sim_dict["version"] = "v1.0.2"
            
            # Format date
            try:
                created_date = sim_dict.get("created_at", "")[:10]
                sim_dict["created_date"] = created_date
            except:
                sim_dict["created_date"] = ""
            
            enriched_simulations.append(sim_dict)
        
        return jsonify({
            "success": True,
            "data": enriched_simulations,
            "count": len(enriched_simulations)
        })
        
    except Exception as e:
        logger.error(f"Failed to get historical simulations: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/profiles', methods=['GET'])
def get_simulation_profiles(simulation_id: str):
    """
    Get simulation'sAgent Profile
    
    Query parameters:
        platform: Platform type（reddit/twitter，Defaultreddit）
    """
    try:
        platform = request.args.get('platform', 'opinion_space')

        manager = SimulationManager()
        profiles = manager.get_profiles(simulation_id, platform=platform)
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "count": len(profiles),
                "profiles": profiles
            }
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404
        
    except Exception as e:
        logger.error(f"GetProfileFailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/enrichment', methods=['GET'])
def get_simulation_enrichment(simulation_id: str):
    """Return raw deep-research findings per archetype (empty dict if not available)."""
    try:
        manager = SimulationManager()
        sim_dir = manager._get_simulation_dir(simulation_id)
        enrichment_path = os.path.join(sim_dir, 'enrichment.json')
        if not os.path.exists(enrichment_path):
            return jsonify({"success": True, "data": {}})
        with open(enrichment_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.warning(f"Failed to load enrichment for {simulation_id}: {e}")
        return jsonify({"success": True, "data": {}})


@simulation_bp.route('/<simulation_id>/research/rerun', methods=['POST'])
def rerun_simulation_research(simulation_id: str):
    """Re-run deep web research for this simulation's archetypes.

    Reads entity types from the graph that this simulation is built on,
    runs the deep research pipeline, overwrites enrichment.json.
    """
    try:
        import re as _re
        from ..services.entity_reader import EntityReader
        from ..services.agent_enricher import AgentContextEnricher
        from ..services.deep_research_service import research_archetypes as _research

        manager = SimulationManager()
        state = manager._load_simulation_state(simulation_id)
        if not state:
            return jsonify({"success": False, "error": "Simulation not found"}), 404

        from ..storage import get_storage
        storage = get_storage()
        reader = EntityReader(storage)
        filtered = reader.filter_defined_entities(graph_id=state.graph_id, defined_entity_types=None, enrich_with_edges=False)

        def _norm(t):
            s = _re.sub(r'([A-Z])', r'_\1', t).lower().lstrip('_')
            return _re.sub(r'[\s\-]+', '_', s.strip())

        entity_types = list({_norm(e.type) for e in filtered.entities if e.type})
        if not entity_types:
            return jsonify({"success": False, "error": "No entity types found in graph"}), 400

        project = ProjectManager().get_project(state.project_id) if state.project_id else None
        seed = (project.simulation_requirement if project else "") or ""

        raw_research = _research(
            archetypes=entity_types,
            query=seed or "current socio-economic conditions South Africa 2025",
            document_text=seed,
        )

        if not raw_research:
            return jsonify({
                "success": False,
                "error": "Research returned no results. Check FIRECRAWL_API_KEY and Firecrawl quota."
            }), 500

        enrichment = AgentContextEnricher.enrich_from_miroflow(raw_research, entity_types)
        sim_dir = manager._get_simulation_dir(simulation_id)
        enrichment_file = os.path.join(sim_dir, "enrichment.json")
        with open(enrichment_file, 'w', encoding='utf-8') as f:
            json.dump(raw_research, f, ensure_ascii=False, indent=2)

        return jsonify({
            "success": True,
            "data": {
                "archetypes": entity_types,
                "enriched_count": len(enrichment),
                "enrichment": raw_research,
            }
        })
    except Exception as e:
        logger.error(f"Re-run research failed for {simulation_id}: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@simulation_bp.route('/<simulation_id>/cost', methods=['GET'])
def get_simulation_cost(simulation_id: str):
    """Return token usage and estimated USD/ZAR cost for prepare + simulation phases."""
    try:
        manager = SimulationManager()
        state = manager._load_simulation_state(simulation_id)
        if not state:
            return jsonify({"success": False, "error": "Simulation not found"}), 404

        sim_dir = manager._get_simulation_dir(simulation_id)
        actions_path = os.path.join(sim_dir, 'opinion_space', 'actions.jsonl')
        sim_tokens_in = sim_tokens_out = sim_cost = 0.0
        if os.path.exists(actions_path):
            with open(actions_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        a = json.loads(line)
                        sim_tokens_in += a.get("prompt_tokens", 0)
                        sim_tokens_out += a.get("completion_tokens", 0)
                        sim_cost += a.get("estimated_cost_usd", 0)
                    except Exception:
                        pass

        price_in = float(Config.LLM_PRICE_PROMPT_PER_1M or 0.14)
        price_out = float(Config.LLM_PRICE_COMPLETION_PER_1M or 0.28)
        total_usd = round(state.prepare_cost_usd + sim_cost, 6)
        zar_rate = 18.5

        return jsonify({
            "success": True,
            "data": {
                "prepare": {
                    "prompt_tokens": state.prepare_prompt_tokens,
                    "completion_tokens": state.prepare_completion_tokens,
                    "cost_usd": state.prepare_cost_usd,
                    "cost_zar": round(state.prepare_cost_usd * zar_rate, 4),
                },
                "simulation": {
                    "prompt_tokens": int(sim_tokens_in),
                    "completion_tokens": int(sim_tokens_out),
                    "cost_usd": round(sim_cost, 6),
                    "cost_zar": round(sim_cost * zar_rate, 4),
                },
                "total_cost_usd": total_usd,
                "total_cost_zar": round(total_usd * zar_rate, 4),
                "pricing_used": {
                    "input_per_1m": price_in,
                    "output_per_1m": price_out,
                },
            }
        })
    except Exception as e:
        logger.warning(f"Cost endpoint error for {simulation_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@simulation_bp.route('/<simulation_id>/profiles/realtime', methods=['GET'])
def get_simulation_profiles_realtime(simulation_id: str):
    """
    Real-time get simulation's Agent Profile (for viewing during generation).

    Difference from /profiles endpoint:
    - Reads file directly, bypasses SimulationManager
    - For real-time viewing during generation
    - Returns additional metadata (such as file modification time, whether generation is in progress, etc.)
    
    Query parameters:
        platform: Platform type（reddit/twitter，Defaultreddit）
    
    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "platform": "reddit",
                "count": 15,
                "total_expected": 93,  // Expected total（IfHas）
                "is_generating": true,  // Is generating
                "file_exists": true,
                "file_modified_at": "2025-12-04T18:20:00",
                "profiles": [...]
            }
        }
    """
    import json
    import csv
    from datetime import datetime
    
    try:
        # Get platform from query parameters
        platform = request.args.get('platform', 'reddit')

        # Get simulation directory
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)

        if not os.path.exists(sim_dir):
            return jsonify({
                "success": False,
                "error": f"Simulation does not exist: {simulation_id}"
            }), 404

        profiles_file = os.path.join(sim_dir, "agentsociety_profiles.json")

        # Check if files exist
        file_exists = os.path.exists(profiles_file)
        profiles = []
        file_modified_at = None

        if file_exists:
            file_stat = os.stat(profiles_file)
            file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()

            try:
                with open(profiles_file, 'r', encoding='utf-8') as f:
                    profiles = json.load(f)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Failed to read profiles file: {e}")
                profiles = []
        
        # Check if generation is in progress (through state.json status field)
        is_generating = False
        total_expected = None
        
        state_file = os.path.join(sim_dir, "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                    status = state_data.get("status", "")
                    is_generating = status == "preparing"
                    total_expected = state_data.get("entities_count")
            except Exception:
                pass
        
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "platform": platform,
                "count": len(profiles),
                "total_expected": total_expected,
                "is_generating": is_generating,
                "file_exists": file_exists,
                "file_modified_at": file_modified_at,
                "profiles": profiles
            }
        })
        
    except Exception as e:
        logger.error(f"Real-time getProfileFailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/config/realtime', methods=['GET'])
def get_simulation_config_realtime(simulation_id: str):
    """
    Real-time get simulation configuration (for viewing during generation).

    Difference from /config endpoint:
    - Reads file directly, bypasses SimulationManager
    - For real-time viewing during generation
    - Returns additional metadata (such as file modification time, whether generation is in progress, etc.)
    - Returns partial information even if config not fully generated
    
    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "file_exists": true,
                "file_modified_at": "2025-12-04T18:20:00",
                "is_generating": true,  // Is generating
                "generation_stage": "generating_config",  // Current generation stage
                "config": {...}  // Configuration content（IfExists）
            }
        }
    """
    import json
    from datetime import datetime
    
    try:
        # Get simulation directory
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
        
        if not os.path.exists(sim_dir):
            return jsonify({
                "success": False,
                "error": f"Simulation does not exist: {simulation_id}"
            }), 404
        
        # Config file path
        config_file = os.path.join(sim_dir, "simulation_config.json")
        
        # Check if files exist
        file_exists = os.path.exists(config_file)
        config = None
        file_modified_at = None
        
        if file_exists:
            # Get file modification time
            file_stat = os.stat(config_file)
            file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Failed to read config file: {e}")
                config = None
        
        # Check if generation is in progress (through state.json status field)
        is_generating = False
        generation_stage = None
        config_generated = False
        
        status = ""
        error_msg = None
        state_file = os.path.join(sim_dir, "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                    status = state_data.get("status", "")
                    error_msg = state_data.get("error")
                    is_generating = status == "preparing"
                    config_generated = state_data.get("config_generated", False)

                    # Judge current stage
                    if is_generating:
                        if state_data.get("profiles_generated", False):
                            generation_stage = "generating_config"
                        else:
                            generation_stage = "generating_profiles"
                    elif status == "ready":
                        generation_stage = "completed"
                    elif status == "failed":
                        generation_stage = "failed"
            except Exception:
                pass

        # Build return data
        response_data = {
            "simulation_id": simulation_id,
            "file_exists": file_exists,
            "file_modified_at": file_modified_at,
            "is_generating": is_generating,
            "generation_stage": generation_stage,
            "config_generated": config_generated,
            "status": status,
            "error": error_msg,
            "failed": status == "failed",
            "config": config
        }
        
        # If configuration exists，Extract key statistics
        if config:
            response_data["summary"] = {
                "total_agents": len(config.get("agent_configs", [])),
                "simulation_hours": config.get("time_config", {}).get("total_simulation_hours"),
                "initial_posts_count": len(config.get("event_config", {}).get("initial_posts", [])),
                "hot_topics_count": len(config.get("event_config", {}).get("hot_topics", [])),
                "has_opinion_space_config": True,
                "generated_at": config.get("generated_at"),
                "llm_model": config.get("llm_model")
            }
        
        return jsonify({
            "success": True,
            "data": response_data
        })
        
    except Exception as e:
        logger.error(f"Real-time getConfigFailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/config', methods=['GET'])
def get_simulation_config(simulation_id: str):
    """
    Get simulation configuration (generated with LLM intelligence).

    Returns:
        - time_config: Time configuration (simulation duration, start time, end time, etc.)
        - agent_configs: Activity configuration for each agent (behavior patterns, interaction styles, etc.)
        - event_config: Event configuration (initial posts, event sequences, etc.)
        - platform_configs: Platform configuration
        - generation_reasoning: LLM configuration reasoning explanation
    """
    try:
        manager = SimulationManager()
        config = manager.get_simulation_config(simulation_id)
        
        if not config:
            return jsonify({
                "success": False,
                "error": f"Simulation configuration does not exist. Please call /prepare first"
            }), 404
        
        return jsonify({
            "success": True,
            "data": config
        })
        
    except Exception as e:
        logger.error(f"Failed to get configuration: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/config/download', methods=['GET'])
def download_simulation_config(simulation_id: str):
    """Download simulation configuration file"""
    try:
        manager = SimulationManager()
        sim_dir = manager._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        
        if not os.path.exists(config_path):
            return jsonify({
                "success": False,
                "error": "Configuration file does not exist. Please call /prepare first"
            }), 404
        
        return send_file(
            config_path,
            as_attachment=True,
            download_name="simulation_config.json"
        )
        
    except Exception as e:
        logger.error(f"Failed to download configuration: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/script/<script_name>/download', methods=['GET'])
def download_simulation_script(script_name: str):
    """
    Download simulation run script file (from backend/scripts/)

    script_name options:
        - run_simulation_as.py
        - action_logger.py
    """
    try:
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts'))

        allowed_scripts = [
            "run_simulation_as.py",
            "action_logger.py"
        ]

        if script_name not in allowed_scripts:
            return jsonify({
                "success": False,
                "error": f"Unknown script: {script_name}. Options: {allowed_scripts}"
            }), 400
        
        script_path = os.path.join(scripts_dir, script_name)
        
        if not os.path.exists(script_path):
            return jsonify({
                "success": False,
                "error": f"Script file does not exist: {script_name}"
            }), 404
        
        return send_file(
            script_path,
            as_attachment=True,
            download_name=script_name
        )
        
    except Exception as e:
        logger.error(f"Failed to download script: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== ProfileGeneration interface（StandaloneUse） ==============

@simulation_bp.route('/generate-profiles', methods=['POST'])
def generate_profiles():
    """
    Generate agent profiles directly from the knowledge graph (no simulation created).

    Request (JSON):
        {
            "graph_id": "fub_xxxx",          // Required
            "entity_types": ["Student"],     // Optional — filter entity types
            "use_llm": true,                 // Optional — use LLM for generation
            "seed_message": "..."            // Optional — policy/event text; used to
                                             //   ground web research queries per entity type
        }

    Web enrichment runs automatically when SERPER_API_KEY is set in .env.
    Each entity type is researched in parallel (Serper search + LLM synthesis),
    and the findings are injected into persona prompts before generation.
    """
    try:
        data = request.get_json() or {}
        
        graph_id = data.get('graph_id')
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "Please provide graph_id"
            }), 400
        
        entity_types = data.get('entity_types')
        use_llm = data.get('use_llm', True)
        storage = current_app.extensions.get('graph_storage')
        if not storage:
            raise ValueError("GraphStorage not initialized")
        reader = EntityReader(storage)
        filtered = reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=True
        )

        if filtered.filtered_count == 0:
            return jsonify({
                "success": False,
                "error": "No matching entities found"
            }), 400

        # --- Web research enrichment ---
        # Runs automatically when FIRECRAWL_API_KEY is set (deep-research-python).
        # Falls back gracefully if the library is not installed or keys are missing.
        enrichment_data = {}
        seed_message = data.get('seed_message') or data.get('document_text', '')
        try:
            entity_types = list({e.type.lower() for e in filtered.entities if e.type})
            if entity_types:
                logger.info(f"Running deep-research enrichment for entity types: {entity_types}")
                query = seed_message or "current socio-economic conditions South Africa 2025"
                raw_content = _deep_research_archetypes(
                    archetypes=entity_types,
                    query=query,
                    document_text=seed_message,
                    max_workers=3,
                )
                enrichment_data = AgentContextEnricher.enrich_from_miroflow(raw_content, entity_types)
                logger.info(f"Web enrichment complete: {len(enrichment_data)} archetypes enriched")
        except Exception as enrich_err:
            logger.warning(f"Web enrichment failed (continuing without it): {enrich_err}")

        generator = AgentProfileGenerator(enrichment_data=enrichment_data)
        profiles = generator.generate_profiles_from_entities(
            entities=filtered.entities,
            use_llm=use_llm
        )
        profiles_data = [p.to_agentsociety_format() for p in profiles]

        return jsonify({
            "success": True,
            "data": {
                "platform": "opinion_space",
                "entity_types": list(filtered.entity_types),
                "count": len(profiles_data),
                "profiles": profiles_data
            }
        })
        
    except Exception as e:
        logger.error(f"GenerateProfileFailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Simulation execution control interface ==============

@simulation_bp.route('/start', methods=['POST'])
def start_simulation():
    """
    Start running simulation

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",          // Required，Simulation ID
            "platform": "parallel",                // Optional: twitter / reddit / parallel (Default)
            "max_rounds": 100,                     // Optional: Maximum simulation rounds, default unlimited
            "enable_graph_memory_update": false,   // Optional: Whether to enable knowledge graph memory updates for agents
            "force": false                         // Optional: Force restart (stop running simulation and clean runtime files)
        }

    About force Parameters:
        - After enabling, if simulation is running or completed, clean runtime logs
        - Cleanup includes：run_state.json, actions.jsonl, simulation.log And so on
        - Will not clean configuration files（simulation_config.json）And profile File
        - For scenarios that need to rerun simulation

    About enable_graph_memory_update:
        - After enabling, all agents in the simulation will update the knowledge graph with their actions (posts, comments, follows, etc.)
        - This allows the knowledge graph to "remember" the simulation, improving context understanding and AI decision-making
        - Requires associated project to have valid graph_id
        - Uses batch update mechanism to reduce API overhead

    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "process_pid": 12345,
                "twitter_running": true,
                "reddit_running": true,
                "started_at": "2025-12-01T10:00:00",
                "graph_memory_update_enabled": true,  // Whether knowledge graph memory update enabled
                "force_restarted": true               // Whether is forced restart
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id"
            }), 400

        platform = data.get('platform', 'opinion_space')
        max_rounds = data.get('max_rounds')  # Optional: Maximum simulation rounds
        enable_graph_memory_update = data.get('enable_graph_memory_update', False)  # Optional：IsFalseEnable knowledge graph memory update
        force = data.get('force', False)  # Optional：Force restart

        # New: Preset and simulation params
        preset = data.get('preset')  # 'quick', 'balanced', 'deep'
        convergence_threshold = data.get('convergence_threshold')
        convergence_window = data.get('convergence_window')
        max_agents_per_round = data.get('max_agents_per_round')
        min_agents_per_round = data.get('min_agents_per_round')

        # Verify max_rounds Parameters
        if max_rounds is not None:
            try:
                max_rounds = int(max_rounds)
                if max_rounds <= 0:
                    return jsonify({
                        "success": False,
                        "error": "max_rounds Must be positive integer"
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    "success": False,
                    "error": "max_rounds Must be valid integer"
                }), 400

        if platform not in ['opinion_space']:
            return jsonify({
                "success": False,
                "error": f"Invalid platform type: {platform}. Only 'opinion_space' is supported."
            }), 400

        # Check if simulation is ready
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return jsonify({
                "success": False,
                "error": f"Simulation does not exist: {simulation_id}"
            }), 404

        force_restarted = False
        
        # Intelligently handle status: if preparation work is complete, reset status to ready
        if state.status != SimulationStatus.READY:
            # Check if preparation is complete
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)

            if is_prepared:
                # Preparation work complete, verify if simulation is not already running
                if state.status == SimulationStatus.RUNNING:
                    # Check if simulation process is really running
                    run_state = SimulationRunner.get_run_state(simulation_id)
                    if run_state and run_state.runner_status.value == "running":
                        # Process is indeed running
                        if force:
                            # Force mode：Stop runningSimulation
                            logger.info(f"Force mode：Stop runningSimulation {simulation_id}")
                            try:
                                SimulationRunner.stop_simulation(simulation_id)
                            except Exception as e:
                                logger.warning(f"Warning when stopping simulation: {str(e)}")
                        else:
                            return jsonify({
                                "success": False,
                                "error": f"Simulation is running. Please call /stop first or use force=true to force restart."
                            }), 400

                # If force mode，Clean runtime logs
                if force:
                    logger.info(f"Force mode: cleaning simulation runtime files for {simulation_id}")
                    cleanup_result = SimulationRunner.cleanup_simulation_logs(simulation_id)
                    if not cleanup_result.get("success"):
                        logger.warning(f"Warning when cleaning logs: {cleanup_result.get('errors')}")
                    force_restarted = True

                # Process does not exist or has ended，Reset status to ready
                logger.info(f"Simulation {simulation_id} preparation complete, resetting status to ready (previous status: {state.status.value})")
                state.status = SimulationStatus.READY
                manager._save_simulation_state(state)
            else:
                # Preparation not complete
                return jsonify({
                    "success": False,
                    "error": f"Simulation not ready. Current status: {state.status.value}. Please call /prepare first"
                }), 400
        
        # Get knowledge graphID（For knowledge graph memory update）
        graph_id = None
        if enable_graph_memory_update:
            # Get from simulation status or project graph_id
            graph_id = state.graph_id
            if not graph_id:
                # Try to get from project
                project = ProjectManager.get_project(state.project_id)
                if project:
                    graph_id = project.graph_id
            
            if not graph_id:
                return jsonify({
                    "success": False,
                    "error": "Enable knowledge graph memory update requires valid graph_id，Please ensure project graph built"
                }), 400
            
            logger.info(f"Enable knowledge graph memory update: simulation_id={simulation_id}, graph_id={graph_id}")
        
        # Load and update simulation config with preset params
        config_updated = False
        max_rounds_from_preset = None
        
        if preset or convergence_threshold or convergence_window or max_agents_per_round or min_agents_per_round:
            sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
            config_path = os.path.join(sim_dir, "simulation_config.json")

            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)

                    # Apply preset
                    if preset in ['quick', 'balanced', 'deep']:
                        presets = {
                            'quick':    {'convergence_threshold': 0.08, 'convergence_window': 3, 'max_agents_per_round': 10, 'min_agents_per_round': 2},
                            'balanced': {'convergence_threshold': 0.05, 'convergence_window': 3, 'max_agents_per_round': 15, 'min_agents_per_round': 3},
                            'deep':     {'convergence_threshold': 0.03, 'convergence_window': 5, 'max_agents_per_round': 30, 'min_agents_per_round': 5},
                        }
                        config.update(presets[preset])
                        # Also set max_rounds explicitly from preset
                        preset_rounds = {'quick': 6, 'balanced': 12, 'deep': 24}
                        max_rounds_from_preset = preset_rounds[preset]
                        
                        # Apply preset time_config to control total rounds
                        # Aligned with run_simulation_as.py presets
                        time_overrides = {
                            'quick':    {'total_simulation_hours': 6, 'minutes_per_round': 60},   # 6 rounds
                            'balanced': {'total_simulation_hours': 12, 'minutes_per_round': 60},  # 12 rounds
                            'deep':     {'total_simulation_hours': 24, 'minutes_per_round': 60},  # 24 rounds
                        }
                        if 'time_config' not in config:
                            config['time_config'] = {}
                        config['time_config'].update(time_overrides[preset])
                        
                        logger.info(f"Applied preset '{preset}' to config: {simulation_id}, time_config={time_overrides[preset]}")

                    # Apply individual overrides
                    if convergence_threshold is not None:
                        config['convergence_threshold'] = float(convergence_threshold)
                    if convergence_window is not None:
                        config['convergence_window'] = int(convergence_window)
                    if max_agents_per_round is not None:
                        config['max_agents_per_round'] = int(max_agents_per_round)
                    if min_agents_per_round is not None:
                        config['min_agents_per_round'] = int(min_agents_per_round)

                    with open(config_path, 'w', encoding='utf-8') as f:
                        json.dump(config, f, ensure_ascii=False, indent=2)
                    config_updated = True
                except Exception as e:
                    logger.warning(f"Failed to update config with preset params: {e}")

        # Use max_rounds from preset if not explicitly set
        if max_rounds is None and max_rounds_from_preset is not None:
            max_rounds = max_rounds_from_preset
            logger.info(f"Using max_rounds={max_rounds} from preset")

        # Start simulation
        run_state = SimulationRunner.start_simulation(
            simulation_id=simulation_id,
            platform=platform,
            max_rounds=max_rounds,
            enable_graph_memory_update=enable_graph_memory_update,
            graph_id=graph_id
        )
        
        # Update simulation status
        state.status = SimulationStatus.RUNNING
        manager._save_simulation_state(state)
        
        response_data = run_state.to_dict()
        if max_rounds:
            response_data['max_rounds_applied'] = max_rounds
        response_data['graph_memory_update_enabled'] = enable_graph_memory_update
        response_data['force_restarted'] = force_restarted
        if enable_graph_memory_update:
            response_data['graph_id'] = graph_id
        
        return jsonify({
            "success": True,
            "data": response_data
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Failed to start simulation: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/stop', methods=['POST'])
def stop_simulation():
    """
    Stop simulation
    
    Request (JSON):
        {
            "simulation_id": "sim_xxxx"  // Required，Simulation ID
        }
    
    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "stopped",
                "completed_at": "2025-12-01T12:00:00"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id"
            }), 400
        
        run_state = SimulationRunner.stop_simulation(simulation_id)
        
        # Update simulation status
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.PAUSED
            manager._save_simulation_state(state)
        
        return jsonify({
            "success": True,
            "data": run_state.to_dict()
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Failed to stop simulation: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Real-time status monitoring interface ==============

@simulation_bp.route('/<simulation_id>/run-status', methods=['GET'])
def get_run_status(simulation_id: str):
    """
    Get simulation real-time running status（For frontend polling）
    
    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "current_round": 5,
                "total_rounds": 144,
                "progress_percent": 3.5,
                "simulated_hours": 2,
                "total_simulation_hours": 72,
                "twitter_running": true,
                "reddit_running": true,
                "twitter_actions_count": 150,
                "reddit_actions_count": 200,
                "total_actions_count": 350,
                "started_at": "2025-12-01T10:00:00",
                "updated_at": "2025-12-01T10:30:00"
            }
        }
    """
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)
        
        if not run_state:
            return jsonify({
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "runner_status": "idle",
                    "current_round": 0,
                    "total_rounds": 0,
                    "progress_percent": 0,
                    "simulation_actions_count": 0,
                    "total_actions_count": 0,
                }
            })
        
        data = run_state.to_dict()

        # Merge live agent-expressed count from subprocess env_status.json
        env_status = SimulationRunner.get_env_status_detail(simulation_id)
        data["agents_expressed_count"] = env_status.get("agents_expressed_count", 0)
        data["agents_expressed"]       = env_status.get("agents_expressed", [])
        data["total_agents"]           = env_status.get("total_agents", 0)

        return jsonify({
            "success": True,
            "data": data,
        })

    except Exception as e:
        logger.error(f"Failed to get running status: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/run-status/detail', methods=['GET'])
def get_run_status_detail(simulation_id: str):
    """
    Get simulation detailed running status（Include all actions）
    
    For frontend to display real-time dynamics
    
    Query parameters:
        platform: Filter platform（twitter/reddit，Optional）
    
    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "current_round": 5,
                ...
                "all_actions": [
                    {
                        "round_num": 5,
                        "timestamp": "2025-12-01T10:30:00",
                        "platform": "twitter",
                        "agent_id": 3,
                        "agent_name": "Agent Name",
                        "action_type": "CREATE_POST",
                        "action_args": {"content": "..."},
                        "result": null,
                        "success": true
                    },
                    ...
                ],
                "twitter_actions": [...],  # Twitter All actions of platform
                "reddit_actions": [...]    # Reddit All actions of platform
            }
        }
    """
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)
        platform_filter = request.args.get('platform')
        
        if not run_state:
            return jsonify({
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "runner_status": "idle",
                    "all_actions": [],
                }
            })

        all_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform=platform_filter,
        )

        current_round = run_state.current_round
        recent_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform=platform_filter,
            round_num=current_round,
        ) if current_round > 0 else []

        result = run_state.to_dict()
        result["all_actions"] = [a.to_dict() for a in all_actions]
        result["rounds_count"] = len(run_state.rounds)
        result["recent_actions"] = [a.to_dict() for a in recent_actions]
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"Failed to get detailed status: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/actions', methods=['GET'])
def get_simulation_actions(simulation_id: str):
    """
    Get from simulationAgentAction history
    
    Query parameters:
        limit: Return count（Default100）
        offset: Offset（Default0）
        platform: Filter platform（twitter/reddit）
        agent_id: FilterAgent ID
        round_num: Filter round
    
    Returns:
        {
            "success": true,
            "data": {
                "count": 100,
                "actions": [...]
            }
        }
    """
    try:
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        platform = request.args.get('platform')
        agent_id = request.args.get('agent_id', type=int)
        round_num = request.args.get('round_num', type=int)
        
        actions = SimulationRunner.get_actions(
            simulation_id=simulation_id,
            limit=limit,
            offset=offset,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num
        )
        
        return jsonify({
            "success": True,
            "data": {
                "count": len(actions),
                "actions": [a.to_dict() for a in actions]
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get action history: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/timeline', methods=['GET'])
def get_simulation_timeline(simulation_id: str):
    """
    Get simulation timeline（Summarized by round）
    
    For frontend to display progress bar and timeline view
    
    Query parameters:
        start_round: Start round（Default0）
        end_round: End round（Default all）
    
    Return summary information per round
    """
    try:
        start_round = request.args.get('start_round', 0, type=int)
        end_round = request.args.get('end_round', type=int)
        
        timeline = SimulationRunner.get_timeline(
            simulation_id=simulation_id,
            start_round=start_round,
            end_round=end_round
        )
        
        return jsonify({
            "success": True,
            "data": {
                "rounds_count": len(timeline),
                "timeline": timeline
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get timeline: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/agent-stats', methods=['GET'])
def get_agent_stats(simulation_id: str):
    """
    Get eachAgentStatistics
    
    For frontend display of agent activity ranking and statistics.
    """
    try:
        stats = SimulationRunner.get_agent_stats(simulation_id)
        
        return jsonify({
            "success": True,
            "data": {
                "agents_count": len(stats),
                "stats": stats
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get agent statistics: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Database query interface ==============

@simulation_bp.route('/<simulation_id>/posts', methods=['GET'])
def get_simulation_posts(simulation_id: str):
    """
    Get posts in simulation
    
    Query parameters:
        platform: Platform type（twitter/reddit）
        limit: Return count（Default50）
        offset: Offset
    
    Return post list (read from SQLite database)
    """
    try:
        platform = request.args.get('platform', 'reddit')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        sim_dir = os.path.join(
            os.path.dirname(__file__),
            f'../../uploads/simulations/{simulation_id}'
        )
        
        db_file = f"{platform}_simulation.db"
        db_path = os.path.join(sim_dir, db_file)
        
        if not os.path.exists(db_path):
            return jsonify({
                "success": True,
                "data": {
                    "platform": platform,
                    "count": 0,
                    "posts": [],
                    "message": "Database does not exist，SimulationMay not have run yet"
                }
            })
        
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT * FROM post 
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            """, (limit, offset))
            
            posts = [dict(row) for row in cursor.fetchall()]
            
            cursor.execute("SELECT COUNT(*) FROM post")
            total = cursor.fetchone()[0]
            
        except sqlite3.OperationalError:
            posts = []
            total = 0
        
        conn.close()
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "total": total,
                "count": len(posts),
                "posts": posts
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get posts: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/comments', methods=['GET'])
def get_simulation_comments(simulation_id: str):
    """
    Get comments in simulation（OnlyReddit）
    
    Query parameters:
        post_id: Filter postsID（Optional）
        limit: Return count
        offset: Offset
    """
    try:
        post_id = request.args.get('post_id')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        sim_dir = os.path.join(
            os.path.dirname(__file__),
            f'../../uploads/simulations/{simulation_id}'
        )
        
        db_path = os.path.join(sim_dir, "reddit_simulation.db")
        
        if not os.path.exists(db_path):
            return jsonify({
                "success": True,
                "data": {
                    "count": 0,
                    "comments": []
                }
            })
        
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            if post_id:
                cursor.execute("""
                    SELECT * FROM comment 
                    WHERE post_id = ?
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """, (post_id, limit, offset))
            else:
                cursor.execute("""
                    SELECT * FROM comment 
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """, (limit, offset))
            
            comments = [dict(row) for row in cursor.fetchall()]
            
        except sqlite3.OperationalError:
            comments = []
        
        conn.close()
        
        return jsonify({
            "success": True,
            "data": {
                "count": len(comments),
                "comments": comments
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get comments: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interview Interview interface ==============

@simulation_bp.route('/interview', methods=['POST'])
def interview_agent():
    """
    Interview individualAgent

    Note: This feature requires simulation to be in a running or completed state (run the simulation and wait for it to progress).

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",       // Required，Simulation ID
            "agent_id": 0,                     // Required，Agent ID
            "prompt": "What do you think about this？",  // Required，Interview question
            "platform": "twitter",             // Optional，Specified platform（twitter/reddit）
                                               // When not specified: Both platforms in dual-platform simulations
            "timeout": 60                      // Optional, timeout in seconds, default 60
        }

    Return (when platform not specified, returns results from both platforms):
        {
            "success": true,
            "data": {
                "agent_id": 0,
                "prompt": "What do you think about this？",
                "result": {
                    "agent_id": 0,
                    "prompt": "...",
                    "platforms": {
                        "twitter": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit": {"agent_id": 0, "response": "...", "platform": "reddit"}
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }

    Return（Specifiedplatform）：
        {
            "success": true,
            "data": {
                "agent_id": 0,
                "prompt": "What do you think about this？",
                "result": {
                    "agent_id": 0,
                    "response": "I think...",
                    "platform": "twitter",
                    "timestamp": "2025-12-08T10:00:00"
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        agent_id = data.get('agent_id')
        prompt = data.get('prompt')
        platform = data.get('platform')  # Optional：twitter/reddit/None
        timeout = data.get('timeout', 60)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id"
            }), 400
        
        if agent_id is None:
            return jsonify({
                "success": False,
                "error": "Please provide agent_id"
            }), 400
        
        if not prompt:
            return jsonify({
                "success": False,
                "error": "Please provide prompt（Interview question）"
            }), 400
        
        # VerifyplatformParameters
        if platform and platform not in ("opinion_space",):
            return jsonify({
                "success": False,
                "error": "platform must be opinion_space (was: 'twitter' Or 'reddit'"
            }), 400
        
        # Check environment status
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "Simulation environment not running or closed. Please ensure simulation is started and wait for it to progress."
            }), 400
        
        # Optimizeprompt，Add prefix to avoidAgent call tools
        optimized_prompt = optimize_interview_prompt(prompt)
        
        # Extract query context for context-aware responses
        storage = current_app.extensions.get('graph_storage')
        
        # Get graph_id from simulation
        manager = SimulationManager()
        sim_state = manager.get_simulation(simulation_id)
        graph_id = sim_state.graph_id if sim_state else None
        
        query_context = None
        if storage and graph_id:
            try:
                extractor = TopicExtractor()
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                query_context = loop.run_until_complete(
                    extractor.extract_query_context(prompt, storage, graph_id)
                )
                loop.close()
            except Exception as e:
                logger.warning(f"Failed to extract query context: {e}")
        
        result = SimulationRunner.interview_agent(
            simulation_id=simulation_id,
            agent_id=agent_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout,
            query_context=query_context
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"WaitInterviewResponse timeout: {str(e)}"
        }), 504
        
    except Exception as e:
        logger.error(f"InterviewFailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/interview/batch', methods=['POST'])
def interview_agents_batch():
    """
    Batch interview multipleAgent

    Note: This feature requires simulation to be in a running or completed state.

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",       // Required，Simulation ID
            "interviews": [                    // Required，Interview list
                {
                    "agent_id": 0,
                    "prompt": "Your opinion onAWhat do you think？",
                    "platform": "twitter"      // Optional, interview this agent on specified platform
                },
                {
                    "agent_id": 1,
                    "prompt": "Your opinion onBWhat do you think？"  // Not specifiedplatform[then]UseDefaultValue
                }
            ],
            "platform": "reddit",              // Optional, Default platform (overridden by each item's platform)
                                               // When not specified: Both platforms in dual-platform simulations, single platform in single-platform simulations
            "timeout": 120                     // Optional, timeout in seconds, default 120
        }

    Returns:
        {
            "success": true,
            "data": {
                "interviews_count": 2,
                "result": {
                    "interviews_count": 4,
                    "results": {
                        "twitter_0": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit_0": {"agent_id": 0, "response": "...", "platform": "reddit"},
                        "twitter_1": {"agent_id": 1, "response": "...", "platform": "twitter"},
                        "reddit_1": {"agent_id": 1, "response": "...", "platform": "reddit"}
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        interviews = data.get('interviews')
        platform = data.get('platform')  # Optional：twitter/reddit/None
        timeout = data.get('timeout', 120)

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id"
            }), 400

        if not interviews or not isinstance(interviews, list):
            return jsonify({
                "success": False,
                "error": "Please provide interviews (Interview list)"
            }), 400

        # Verify platform parameter - opinion_space only
        if platform and platform not in ("opinion_space",):
            return jsonify({
                "success": False,
                "error": "platform must be 'opinion_space'"
            }), 400

        # Verify each interview item
        for i, interview in enumerate(interviews):
            if 'agent_id' not in interview:
                return jsonify({
                    "success": False,
                    "error": f"Interview list item {i+1} missing agent_id"
                }), 400
            if 'prompt' not in interview:
                return jsonify({
                    "success": False,
                    "error": f"Interview list item {i+1} missing prompt"
                }), 400
            # Verify each item's platform (if provided) - opinion_space only
            item_platform = interview.get('platform')
            if item_platform and item_platform not in ("opinion_space",):
                return jsonify({
                    "success": False,
                    "error": f"Interview list item {i+1}: platform must be 'opinion_space'"
                }), 400

        # Check environment status
        # Check environment status
        try:
            env_alive = SimulationRunner.check_env_alive(simulation_id)
            logger.info(f"Interview check: simulation={simulation_id}, env_alive={env_alive}")
        except Exception as e:
            logger.error(f"check_env_alive failed: {e}")
            env_alive = False

        if not env_alive:
            return jsonify({
                "success": False,
                "error": "Simulation environment not running or closed. Please ensure simulation is started and wait for it to progress."
            }), 400

        # OptimizeEachInterview itemprompt，Add prefix to avoidAgent call tools
        optimized_interviews = []
        for interview in interviews:
            optimized_interview = interview.copy()
            optimized_interview['prompt'] = optimize_interview_prompt(interview.get('prompt', ''))
            optimized_interviews.append(optimized_interview)

        result = SimulationRunner.interview_agents_batch(
            simulation_id=simulation_id,
            interviews=optimized_interviews,
            platform=platform,
            timeout=timeout
        )

        # Check if we got actual results - if not, fall back to post-simulation interview
        if not result.get("result", {}).get("results"):
            logger.warning(f"Interview returned no results, falling back to post-simulation interview")
            result = _post_simulation_interview_fallback(
                simulation_id=simulation_id,
                profiles=SimulationManager().get_profiles(simulation_id, 'opinion_space') or [],
                prompt=", ".join([iv.get("prompt", "") for iv in optimized_interviews]),
                platform=platform or 'opinion_space'
            )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"Wait for batchInterviewResponse timeout: {str(e)}"
        }), 504

    except Exception as e:
        logger.error(f"BatchInterviewFailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/interview/post-simulation', methods=['POST'])
def interview_agents_post_simulation():
    """
    Post-simulation interview - Interview agents after simulation completes.

    This endpoint allows interviewing ANY agent (including those who didn't speak)
    after the simulation has completed. It reads agent profiles from disk.

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",       // Required, Simulation ID
            "prompt": "What do you think about...?", // Required, Interview question
            "agent_id": 0,                      // Optional, Specific agent ID (if empty, interviews all)
            "platform": "opinion_space",         // Optional, Must be opinion_space
            "timeout": 180                    // Optional, Timeout in seconds, default 180
        }

    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "interviews_count": 1,
                "result": {
                    "results": {
                        "opinion_space_0": {"agent_id": 0, "response": "...", "platform": "opinion_space"}
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    import sqlite3
    import os
    import json

    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        prompt = data.get('prompt')
        agent_id = data.get('agent_id')
        platform = data.get('platform', 'opinion_space')
        timeout = data.get('timeout', 180)

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id"
            }), 400

        if not prompt:
            return jsonify({
                "success": False,
                "error": "Please provide prompt (interview question)"
            }), 400

        # Validate platform
        if platform and platform not in ("opinion_space",):
            return jsonify({
                "success": False,
                "error": "platform must be 'opinion_space'"
            }), 400

        # Load agent profiles directly from file (bypass SimulationManager validation)
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
        profiles_file = os.path.join(sim_dir, "agentsociety_profiles.json")
        
        try:
            if not os.path.exists(profiles_file):
                raise FileNotFoundError(f"Profiles file not found: {profiles_file}")
            with open(profiles_file, 'r', encoding='utf-8') as f:
                profiles = json.load(f)
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Cannot load profiles: {str(e)}"
            }), 400

        if not profiles:
            return jsonify({
                "success": False,
                "error": f"No agents found for simulation {simulation_id}"
            }), 404

        # Determine which agents to interview
        if agent_id is not None:
            # Filter to specific agent
            target_profiles = [p for p in profiles if p.get('id') == agent_id]
            if not target_profiles:
                return jsonify({
                    "success": False,
                    "error": f"Agent {agent_id} not found in simulation"
                }), 404
        else:
            # No agent_id specified - interview all agents
            target_profiles = profiles

        # Optimize prompt to prevent agent from calling tools
        optimized_prompt = optimize_interview_prompt(prompt)

        # Build interview list
        interviews = []
        for agent in target_profiles:
            agent_idx = agent.get('id', agent.get('agent_id'))
            if agent_idx is not None:
                interviews.append({
                    "agent_id": agent_idx,
                    "prompt": optimized_prompt
                })

        # Check if simulation environment is still running
        from app.services.simulation_runner import SimulationRunner
        env_alive = SimulationRunner.check_env_alive(simulation_id)

        if env_alive:
            # Simulation is still running - use live interview API
            result = SimulationRunner.interview_agents_batch(
                simulation_id=simulation_id,
                interviews=interviews,
                platform=platform,
                timeout=float(timeout)
            )
        else:
            # Simulation completed - need to restart environment briefly for interview
            # or use stored profiles for a simulated response
            result = _post_simulation_interview_fallback(
                simulation_id=simulation_id,
                profiles=target_profiles,
                prompt=optimized_prompt,
                platform=platform)

        return jsonify({
            "success": result.get("success", False),
            "data": {
                "simulation_id": simulation_id,
                "interviews_count": len(interviews),
                "result": result
            }
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"Interview timeout: {str(e)}"
        }), 504

    except Exception as e:
        logger.error(f"Post-simulation interview failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


def _post_simulation_interview_fallback(
    simulation_id: str,
    profiles: List[Dict],
    prompt: str,
    platform: str = "opinion_space"
) -> Dict[str, Any]:
    """
    Fallback interview method when simulation environment is not running.
    Loads agent profiles and simulates interview responses using LLM.
    """
    from app.utils.llm_client import LLMClient
    from datetime import datetime

    llm = LLMClient()
    results = {}

    max_agents = min(10, len(profiles))  # Limit to avoid long processing
    for agent in profiles[:max_agents]:
        agent_id = agent.get('id', agent.get('agent_id'))
        if agent_id is None:
            continue

        agent_name = agent.get('username') or agent.get('name') or f"Agent {agent_id}"
        agent_bio = agent.get('bio', '') or agent.get('persona', '') or agent.get('background_story', '')
        agent_role = agent.get('profession') or agent.get('occupation', 'Citizen')

        # Build prompt with agent context
        context_prompt = f"""You are {agent_name}, a {agent_role} in South Africa.

Your background: {agent_bio[:500]}

Please answer the following question in YOUR OWN VOICE, as yourself:

{prompt}

Remember:
1. Answer directly as your character
2. Do not call any tools
3. Do not use JSON or markdown formatting
4. Provide a genuine, personal response"""

        try:
            response = llm.chat(
                messages=[{"role": "user", "content": context_prompt}],
                temperature=0.7
            )

            results[f"{platform}_{agent_id}"] = {
                "agent_id": agent_id,
                "response": response,
                "platform": platform
            }
        except Exception as e:
            results[f"{platform}_{agent_id}"] = {
                "agent_id": agent_id,
                "response": f"Sorry, I couldn't process this interview: {str(e)}",
                "platform": platform
            }

    return {
        "success": True,
        "interviews_count": len(results),
        "results": results,
        "timestamp": datetime.now().isoformat()
    }


@simulation_bp.route('/interview/all', methods=['POST'])
def interview_all_agents():
    """
    Global interview - Interview all agents with the same question

    Note: This feature requires simulation to be in a running or completed state.

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",            // Required, Simulation ID
            "prompt": "What is your overall view on this?",  // Required, interview question (avoid enabling agent to use tools)
            "platform": "opinion_space",            // Optional, Must be opinion_space
            "timeout": 180                          // Optional, timeout in seconds, default 180
        }

    Returns:
        {
            "success": true,
            "data": {
                "interviews_count": 50,
                "result": {
                    "interviews_count": 100,
                    "results": {
                        "twitter_0": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit_0": {"agent_id": 0, "response": "...", "platform": "reddit"},
                        ...
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        prompt = data.get('prompt')
        platform = data.get('platform')  # Optional：twitter/reddit/None
        timeout = data.get('timeout', 180)

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id"
            }), 400

        if not prompt:
            return jsonify({
                "success": False,
                "error": "Please provide prompt（Interview question）"
            }), 400

        # VerifyplatformParameters
        if platform and platform not in ("opinion_space",):
            return jsonify({
                "success": False,
                "error": "platform must be opinion_space (was: 'twitter' Or 'reddit'"
            }), 400

        # Check environment status
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "Simulation environment not running or closed. Please ensure simulation is started and wait for it to progress."
            }), 400

        # Optimizeprompt，Add prefix to avoidAgent call tools
        optimized_prompt = optimize_interview_prompt(prompt)

        result = SimulationRunner.interview_all_agents(
            simulation_id=simulation_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"Wait for globalInterviewResponse timeout: {str(e)}"
        }), 504

    except Exception as e:
        logger.error(f"GlobalInterviewFailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/interview/history', methods=['POST'])
def get_interview_history():
    """
    GetInterviewHistorical records

    Read all from simulation databaseInterviewRecord

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",  // Required，Simulation ID
            "platform": "reddit",          // Optional，Platform type（reddit/twitter）
                                           // If not specified, return all history of both platforms
            "agent_id": 0,                 // Optional, Get interview history for only this agent
            "limit": 100                   // Optional，Return count，Default100
        }

    Returns:
        {
            "success": true,
            "data": {
                "count": 10,
                "history": [
                    {
                        "agent_id": 0,
                        "response": "I think...",
                        "prompt": "What do you think about this？",
                        "timestamp": "2025-12-08T10:00:00",
                        "platform": "reddit"
                    },
                    ...
                ]
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        platform = data.get('platform')  # If not specified, return history of both platforms
        agent_id = data.get('agent_id')
        limit = data.get('limit', 100)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id"
            }), 400

        history = SimulationRunner.get_interview_history(
            simulation_id=simulation_id,
            platform=platform,
            agent_id=agent_id,
            limit=limit
        )

        return jsonify({
            "success": True,
            "data": {
                "count": len(history),
                "history": history
            }
        })

    except Exception as e:
        logger.error(f"Failed to get interview history: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/env-status', methods=['POST'])
def get_env_status():
    """
    Get simulation environment status

    Check if simulation environment is alive (can receive interview requests).

    Request (JSON):
        {
            "simulation_id": "sim_xxxx"  // Required，Simulation ID
        }

    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "env_alive": true,
                "twitter_available": true,
                "reddit_available": true,
                "message": "Environment running, ready to receive interview requests"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id"
            }), 400

        env_alive = SimulationRunner.check_env_alive(simulation_id)
        
        # Get more detailed status information
        env_status = SimulationRunner.get_env_status_detail(simulation_id)

        if env_alive:
            message = "Environment running, ready to receive interview requests"
        else:
            message = "Environment not running or closed"

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "env_alive": env_alive,
                "twitter_available": env_status.get("twitter_available", False),
                "reddit_available": env_status.get("reddit_available", False),
                "message": message
            }
        })

    except Exception as e:
        logger.error(f"Failed to get environment status: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/close-env', methods=['POST'])
def close_simulation_env():
    """
    Close simulation environment
    
    Send close environment command to simulation to gracefully exit and wait for completion.

    Note: This is different from /stop. /stop terminates the simulation abruptly.
    This interface lets the simulation gracefully close the environment and exit.
    
    Request (JSON):
        {
            "simulation_id": "sim_xxxx",  // Required，Simulation ID
            "timeout": 30                  // Optional, timeout in seconds, default 30
        }
    
    Returns:
        {
            "success": true,
            "data": {
                "message": "Environment close command sent",
                "result": {...},
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        timeout = data.get('timeout', 30)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id"
            }), 400
        
        result = SimulationRunner.close_simulation_env(
            simulation_id=simulation_id,
            timeout=timeout
        )
        
        # Update simulation status
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.COMPLETED
            manager._save_simulation_state(state)
        
        return jsonify({
            "success": result.get("success", False),
            "data": result
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Failed to close environment: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# =============================================================================
# Policy Wind Tunnel — Interview & Intervention APIs
# =============================================================================

@simulation_bp.route('/<simulation_id>/agents', methods=['GET'])
def list_simulation_agents(simulation_id: str):
    """
    List all agents in a simulation with their policy-relevant state.

    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "agent_count": 50,
                "agents": [
                    {
                        "id": 0,
                        "name": "Official Body",
                        "occupation": "Government Agency",
                        "actor_archetype": "institutional_loyalist",
                        "group_affiliation": null,
                        "is_institutional": true,
                        "stance": "neutral",
                        "base_radicalism": 1,
                        "interested_topics": ["Policy Implementation", "Public Safety", ...]
                    },
                    ...
                ]
            }
        }
    """
    try:
        service = InterviewService(simulation_id)
        agents = service.list_agents()
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "agent_count": len(agents),
                "agents": agents,
            }
        })
    except FileNotFoundError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404
    except Exception as e:
        logger.error(f"Failed to list agents: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/agents/<int:agent_id>/interview', methods=['POST'])
def interview_single_agent(simulation_id: str, agent_id: int):
    """
    Interview a single agent (post-hoc, no running simulation required).

    Request (JSON):
        {
            "question": "What is your biggest concern?",  // Required if question_type not set
            "question_type": "biggest_concern",           // Optional: structured question type
            "policy_context": "Fuel levy increase of 75c/L"  // Optional: for structured questions
        }

    Supported question_type values:
        - "biggest_concern": What is your biggest concern?
        - "what_would_change": What would change your position?
        - "willing_to_negotiate": Are you willing to negotiate?
        - "mobilization_intent": Are you planning to take action?
        - "message_to_government": What message for policy makers?

    Returns:
        {
            "success": true,
            "data": {
                "agent_id": 5,
                "agent_name": "Taxi Association Chair",
                "response": "Our biggest concern is...",
                "stance_before": "oppose",
                "stance_after": "concerned",
                "stance_changed": true,
                "actor_archetype": "community_protector",
                "timestamp": "2026-05-05T10:00:00"
            }
        }
    """
    try:
        data = request.get_json() or {}
        question = data.get('question', '')
        question_type = data.get('question_type')
        policy_context = data.get('policy_context')

        if not question and not question_type:
            return jsonify({
                "success": False,
                "error": "Provide 'question' or 'question_type'"
            }), 400

        service = InterviewService(simulation_id)

        # Run async interview in sync Flask context
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(service.interview_agent(
                agent_id=agent_id,
                question=question,
                question_type=question_type,
                policy_context=policy_context,
            ))
        finally:
            loop.close()

        return jsonify({
            "success": True,
            "data": result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404
    except Exception as e:
        logger.error(f"Interview failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/agents/batch-interview', methods=['POST'])
def batch_interview_agents(simulation_id: str):
    """
    Interview multiple agents with the same question.

    Request (JSON):
        {
            "question": "What is your biggest concern?",
            "question_type": "biggest_concern",        // Optional
            "policy_context": "Fuel levy increase...", // Optional
            "agent_ids": [5, 12, 23]                   // Optional (default: all agents)
        }

    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "total_interviewed": 50,
                "successful": 48,
                "failed": 2,
                "stance_distribution": {"oppose": 20, "concerned": 15, ...},
                "results": [...]
            }
        }
    """
    try:
        data = request.get_json() or {}
        question = data.get('question', '')
        question_type = data.get('question_type')
        policy_context = data.get('policy_context')
        agent_ids = data.get('agent_ids')

        if not question and not question_type:
            return jsonify({
                "success": False,
                "error": "Provide 'question' or 'question_type'"
            }), 400

        service = InterviewService(simulation_id)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(service.batch_interview(
                question=question,
                agent_ids=agent_ids,
                question_type=question_type,
                policy_context=policy_context,
            ))
        finally:
            loop.close()

        return jsonify({
            "success": True,
            "data": result
        })

    except Exception as e:
        logger.error(f"Batch interview failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/agents/<int:agent_id>/intervene', methods=['POST'])
def intervene_with_agent(simulation_id: str, agent_id: int):
    """
    Apply a policy-maker intervention to an agent.

    Request (JSON):
        {
            "intervention_text": "We will offer a R500/month taxi operator subsidy"
        }

    Returns:
        {
            "success": true,
            "data": {
                "agent_id": 5,
                "agent_name": "Taxi Association Chair",
                "response": "That changes things...",
                "stance_before": "oppose",
                "stance_after": "concerned",
                "radicalism_before": 4,
                "radicalism_after": 2,
                "mobilization_before": 2,
                "mobilization_after": 1,
                "stance_changed": true,
                "timestamp": "2026-05-05T10:00:00"
            }
        }
    """
    try:
        data = request.get_json() or {}
        intervention_text = data.get('intervention_text')

        if not intervention_text:
            return jsonify({
                "success": False,
                "error": "Provide 'intervention_text'"
            }), 400

        service = InterviewService(simulation_id)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(service.intervene_with_agent(
                agent_id=agent_id,
                intervention_text=intervention_text,
            ))
        finally:
            loop.close()

        return jsonify({
            "success": True,
            "data": result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404
    except Exception as e:
        logger.error(f"Intervention failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/fork', methods=['POST'])
def fork_simulation(simulation_id: str):
    """
    Fork a simulation, optionally modifying agent states.

    Request (JSON):
        {
            "new_simulation_id": "sim_xxxx_fork1",
            "agent_modifications": {
                "5": {"stance": "support", "current_radicalism": 2},
                "12": {"stance": "neutral", "current_radicalism": 1}
            }
        }

    Returns:
        {
            "success": true,
            "data": {
                "original_simulation_id": "sim_xxxx",
                "new_simulation_id": "sim_xxxx_fork1",
                "new_simulation_dir": "/path/to/sim",
                "modified_agents": 2
            }
        }
    """
    try:
        data = request.get_json() or {}
        new_simulation_id = data.get('new_simulation_id')
        agent_modifications_raw = data.get('agent_modifications', {})

        if not new_simulation_id:
            return jsonify({
                "success": False,
                "error": "Provide 'new_simulation_id'"
            }), 400

        # Convert string keys to int keys (JSON keys are strings)
        agent_modifications = {}
        for k, v in agent_modifications_raw.items():
            try:
                agent_modifications[int(k)] = v
            except ValueError:
                continue

        service = InterviewService(simulation_id)
        new_dir = service.fork_simulation(new_simulation_id, agent_modifications)

        return jsonify({
            "success": True,
            "data": {
                "original_simulation_id": simulation_id,
                "new_simulation_id": new_simulation_id,
                "new_simulation_dir": new_dir,
                "modified_agents": len(agent_modifications),
            }
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
    except Exception as e:
        logger.error(f"Fork failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# =============================================================================
# In-Simulation Pause & Intervention APIs
# =============================================================================

@simulation_bp.route('/<simulation_id>/pause', methods=['POST'])
def pause_simulation(simulation_id: str):
    """
    Pause a running simulation between rounds.

    The simulation will complete the current round, then pause before
    starting the next round. While paused, you can interview agents
    and apply interventions.

    Returns:
        {
            "success": true,
            "data": {
                "paused": true,
                "message": "Simulation paused"
            }
        }
    """
    try:
        result = SimulationRunner.pause_simulation(simulation_id)
        return jsonify({
            "success": result.get("success", False),
            "data": result
        })
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
    except Exception as e:
        logger.error(f"Pause failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/resume', methods=['POST'])
def resume_simulation(simulation_id: str):
    """
    Resume a paused simulation.

    Returns:
        {
            "success": true,
            "data": {
                "paused": false,
                "message": "Simulation resumed"
            }
        }
    """
    try:
        result = SimulationRunner.resume_simulation(simulation_id)
        return jsonify({
            "success": result.get("success", False),
            "data": result
        })
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
    except Exception as e:
        logger.error(f"Resume failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/agents/<int:agent_id>/intervene-live', methods=['POST'])
def intervene_live(simulation_id: str, agent_id: int):
    """
    Apply an intervention to an agent during a running (paused) simulation.

    Request (JSON):
        {
            "intervention_text": "We will offer a R500/month taxi operator subsidy"
        }

    Returns:
        {
            "success": true,
            "data": {
                "agent_id": 5,
                "response": "That changes things...",
                "stance_before": "oppose",
                "stance_after": "concerned",
                "radicalism_before": 4,
                "radicalism_after": 2,
                "mobilization_before": 2,
                "mobilization_after": 1,
                "propagation_count": 3,
                "stance_changed": true
            }
        }
    """
    try:
        data = request.get_json() or {}
        intervention_text = data.get('intervention_text')

        if not intervention_text:
            return jsonify({
                "success": False,
                "error": "Provide 'intervention_text'"
            }), 400

        result = SimulationRunner.apply_intervention_during_sim(
            simulation_id=simulation_id,
            agent_id=agent_id,
            intervention_text=intervention_text,
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result.get("result") or result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
    except Exception as e:
        logger.error(f"Live intervention failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Impact-Extraction Interview API ==============

@simulation_bp.route('/interview/impact', methods=['POST'])
def impact_interview():
    """
    Batch impact-extraction interview with auto-reframing per agent.

    The system analyzes the user's generic question, reframes it per agent persona,
    interviews all agents, and returns structured impact metadata.

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",   // Required
            "question": "What if the policy changes after 12 months?",  // Required
            "agent_ids": [1, 4, 7]         // Optional, default all agents
        }

    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "original_question": "What if the policy changes after 12 months?",
                "question_archetype": "counterfactual",
                "total_interviewed": 8,
                "impact_dashboard": {
                    "emotional_temperature": {"fear": 5, "anger": 2, "sadness": 1},
                    "stance_distribution": {"support": 3, "concerned": 4, "oppose": 1},
                    "mobilization_risk": {"low": 5, "medium": 2, "high": 1},
                    "predicted_actions": [...]
                },
                "results": [
                    {
                        "agent_id": 1,
                        "agent_name": "Agent Name",
                        "response": "The changes will affect my community...",
                        "reframed_question": "The policy change happens next month...",
                        "impact_metadata": {
                            "granularity": "micro",
                            "affected_entity": "Family",
                            "emotional_tone": "fear",
                            "predicted_action": "keep son indoors"
                        },
                        "internal_state": {
                            "emotion": {"fear": 9, "anger": 2, ...},
                            "needs": {"safety_physical": 95, ...},
                            "stance": "support"
                        }
                    }
                ]
            }
        }
    """
    try:
        data = request.get_json() or {}
        simulation_id = data.get("simulation_id")
        question = data.get("question", "")
        agent_ids = data.get("agent_ids")

        if not simulation_id:
            return jsonify({"success": False, "error": "simulation_id is required"}), 400
        if not question:
            return jsonify({"success": False, "error": "question is required"}), 400

        service = InterviewService(simulation_id)

        # Run batch impact interview (async)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                service.batch_impact_interview(
                    question=question,
                    agent_ids=agent_ids,
                )
            )
        finally:
            loop.close()

        return jsonify({
            "success": True,
            "data": result
        })

    except Exception as e:
        logger.error(f"Impact interview failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Structured Data Export API ==============

@simulation_bp.route('/<simulation_id>/export/states', methods=['GET'])
def export_agent_states(simulation_id: str):
    """
    Export time-series agent state data for external analysis.

    Query parameters:
        format: "json" or "csv" (default json)
        rounds: comma-separated round numbers, or "all"

    Returns:
        Time-series of stance, radicalism, emotion, mobilization per agent per round.
    """
    try:
        from ..services.data_exporter import SimulationDataExporter

        fmt = request.args.get("format", "json")
        rounds_str = request.args.get("rounds", "all")
        rounds = None
        if rounds_str != "all":
            rounds = [int(r.strip()) for r in rounds_str.split(",") if r.strip().isdigit()]

        exporter = SimulationDataExporter(simulation_id)
        data = exporter.export_agent_states(rounds=rounds)

        if fmt == "csv":
            import csv
            import io
            output = io.StringIO()
            if data and data.get("records"):
                writer = csv.DictWriter(output, fieldnames=data["records"][0].keys())
                writer.writeheader()
                writer.writerows(data["records"])
            return send_file(
                io.BytesIO(output.getvalue().encode()),
                mimetype="text/csv",
                as_attachment=True,
                download_name=f"{simulation_id}_agent_states.csv"
            )

        return jsonify({
            "success": True,
            "data": data
        })

    except Exception as e:
        logger.error(f"Export agent states failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/export/impact', methods=['GET'])
def export_impact_summary(simulation_id: str):
    """
    Export aggregate impact summary from latest impact interviews.

    Query parameters:
        format: "json" or "csv" (default json)

    Returns:
        Aggregate emotional temperature, stance distribution, mobilization risk,
        predicted actions, and affected entities.
    """
    try:
        from ..services.data_exporter import SimulationDataExporter

        fmt = request.args.get("format", "json")

        exporter = SimulationDataExporter(simulation_id)
        data = exporter.export_impact_summary()

        if fmt == "csv":
            import csv
            import io
            output = io.StringIO()
            if data and data.get("predicted_actions"):
                writer = csv.DictWriter(output, fieldnames=data["predicted_actions"][0].keys())
                writer.writeheader()
                writer.writerows(data["predicted_actions"])
            return send_file(
                io.BytesIO(output.getvalue().encode()),
                mimetype="text/csv",
                as_attachment=True,
                download_name=f"{simulation_id}_impact_summary.csv"
            )

        return jsonify({
            "success": True,
            "data": data
        })

    except Exception as e:
        logger.error(f"Export impact summary failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
