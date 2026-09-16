"""Turning uploaded documents into a knowledge graph.

Two jobs, both of them rules rather than request handling:

  * `build_ontology` — read the uploaded documents, pull out any custom agents the
    author declared, and ask the LLM for an ontology. Saves the project as it goes.
  * `build_graph` — chunk the extracted text, create the graph, set the ontology and
    add the text in batches, reporting progress to a task.

Neither function touches Flask. `storage` is passed in, because the graph build runs
on a background thread that cannot reach `current_app`, and the upload writer is
passed in for the same reason: the web framework's file object stays in the
controller.
"""

from __future__ import annotations

import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..models.project import Project, ProjectStatus
from ..models.task import TaskStatus
from ..repositories import project_repository
from ..utils.file_parser import FileParser
from ..utils.logger import get_logger
from .custom_agent_parser import CustomAgentParser
from .graph_builder import GraphBuilderService
from .ontology_generator import OntologyGenerator
from .text_processor import TextProcessor

logger = get_logger("fub.graph_service")

#: Marker filename used when a substantial seed message stands in for a document.
SEED_FILENAME = "seed_briefing.md"


class NoDocuments(ValueError):
    """Raised when nothing usable was uploaded and there is no seed to fall back on."""


def store_uploads(project: Project,
                  uploads: List[Tuple[str, Callable[[str], None]]]) -> Tuple[List[str], str]:
    """Save each upload; return the extracted texts and the combined document.

    `uploads` is (original_filename, write) pairs — `write` is handed the destination
    path. The project's own `files` list is updated as a side effect. The combined
    string is built here, in the same loop as the extraction, rather than re-derived
    later by slicing `project.files`.
    """
    texts: List[str] = []
    combined = ""
    for filename, write in uploads:
        info = project_repository.save_upload(project.project_id, write, filename)
        project.files.append({"filename": info["original_filename"], "size": info["size"]})
        text = TextProcessor.preprocess_text(FileParser.extract_text(info["path"]))
        texts.append(text)
        combined += f"\n\n=== {info['original_filename']} ===\n{text}"
    return texts, combined


def build_ontology(project: Project,
                   uploads: List[Tuple[str, Callable[[str], None]]],
                   simulation_requirement: str,
                   additional_context: str = "") -> Project:
    """Store the uploads, find declared agents, and generate the ontology.

    Raises NoDocuments when there is nothing to work from, so the caller can delete
    the half-made project and answer 400.
    """
    document_texts, all_text = store_uploads(project, uploads)

    # No files, but a substantial seed message (e.g. a web-research briefing) can
    # serve as the document on its own.
    if not document_texts and len((simulation_requirement or "").strip()) >= 100:
        seed = TextProcessor.preprocess_text(simulation_requirement)
        document_texts.append(seed)
        all_text = f"\n\n=== {SEED_FILENAME} ===\n{seed}"
        project.files.append({"filename": SEED_FILENAME, "size": len(seed), "synthetic": True})
        logger.info("Using simulation_requirement as a synthetic document (%d chars)", len(seed))

    if not document_texts:
        raise NoDocuments("No documents successfully processed. Please check file format")

    project.total_text_length = len(all_text)
    project_repository.save_extracted_text(project.project_id, all_text)
    logger.info("Text extraction completed, %d characters", len(all_text))

    project.custom_agents = _declared_agents(all_text, simulation_requirement)
    project.custom_agents_enabled = bool(project.custom_agents)

    logger.info("Calling the LLM for an ontology definition...")
    ontology = OntologyGenerator().generate(
        document_texts=document_texts,
        simulation_requirement=simulation_requirement,
        additional_context=additional_context or None,
    )
    project.ontology = {
        "entity_types": ontology.get("entity_types", []),
        "edge_types": ontology.get("edge_types", []),
    }
    project.analysis_summary = ontology.get("analysis_summary", "")
    project.status = ProjectStatus.ONTOLOGY_GENERATED
    project_repository.save(project)
    logger.info("Ontology generated for %s: %d entity types, %d relation types",
                project.project_id, len(project.ontology["entity_types"]),
                len(project.ontology["edge_types"]))
    return project


def _declared_agents(all_text: str, simulation_requirement: str) -> List[Dict[str, Any]]:
    """Custom agents the author declared in an '# Agents' section, or []."""
    try:
        profiles = CustomAgentParser.extract_agents_from_text(
            all_text, simulation_requirement=simulation_requirement, use_llm=True)
    except Exception as e:  # noqa: BLE001 - a missing section must not fail the upload
        logger.warning("Custom agent extraction from the seed document failed: %s", e)
        return []
    if not profiles:
        logger.info("No '# Agents' section found in the document")
        return []
    agents = [p.to_agentsociety_format() for p in profiles]
    logger.info("Extracted %d custom agents from the '# Agents' section", len(agents))
    return agents


def build_graph(project: Project, *, storage: Any, task_id: str, task_manager: Any,
                text: str, ontology: Dict[str, Any], graph_name: str,
                chunk_size: int, chunk_overlap: int) -> None:
    """Build the graph, reporting progress to `task_id`. Never raises.

    `storage` and `task_manager` are passed in: this runs on a background thread with
    no Flask context, and the project object comes with it so nothing is re-fetched
    mid-build.
    """
    build_logger = get_logger("fub.build")
    try:
        build_logger.info("[%s] Starting graph build...", task_id)
        task_manager.update_task(task_id, status=TaskStatus.PROCESSING,
                                 message="Initializing graph build service...")
        builder = GraphBuilderService(storage=storage)

        task_manager.update_task(task_id, message="Chunking text...", progress=5)
        chunks = TextProcessor.split_text(text, chunk_size=chunk_size, overlap=chunk_overlap)

        task_manager.update_task(task_id, message="Creating Neo graph...", progress=10)
        graph_id = builder.create_graph(name=graph_name)
        project.graph_id = graph_id
        project_repository.save(project)

        task_manager.update_task(task_id, message="Setting ontology definition...", progress=15)
        builder.set_ontology(graph_id, ontology)

        def on_progress(msg, ratio):
            task_manager.update_task(task_id, message=msg, progress=15 + int(ratio * 40))

        task_manager.update_task(task_id, progress=15,
                                 message=f"Starting to add {len(chunks)} text chunks...")
        builder.add_text_batches(graph_id, chunks, batch_size=3, progress_callback=on_progress)

        task_manager.update_task(task_id, progress=90,
                                 message="Text processing completed, generating graph data...")
        task_manager.update_task(task_id, message="Retrieving graph data...", progress=95)
        graph_data = builder.get_graph_data(graph_id)

        project.status = ProjectStatus.GRAPH_COMPLETED
        project_repository.save(project)

        nodes = graph_data.get("node_count", 0)
        edges = graph_data.get("edge_count", 0)
        build_logger.info("[%s] Graph build completed: graph_id=%s, nodes=%d, edges=%d",
                          task_id, graph_id, nodes, edges)
        task_manager.update_task(
            task_id, status=TaskStatus.COMPLETED, message="Graph build completed", progress=100,
            result={"project_id": project.project_id, "graph_id": graph_id,
                    "node_count": nodes, "edge_count": edges, "chunk_count": len(chunks)})
    except Exception as e:  # noqa: BLE001 - a build failure is reported, never raised
        build_logger.error("[%s] Graph build failed: %s", task_id, e)
        build_logger.debug(traceback.format_exc())
        project.status = ProjectStatus.FAILED
        project.error = str(e)
        project_repository.save(project)
        task_manager.update_task(task_id, status=TaskStatus.FAILED,
                                 message=f"Build failed: {e}", error=traceback.format_exc())


def graph_data(storage: Any, graph_id: str) -> Dict[str, Any]:
    return GraphBuilderService(storage=storage).get_graph_data(graph_id)


def delete_graph(storage: Any, graph_id: str) -> None:
    GraphBuilderService(storage=storage).delete_graph(graph_id)


def reset_project(project: Project) -> Project:
    """Put a project back to where it can be rebuilt from."""
    project.status = (ProjectStatus.ONTOLOGY_GENERATED if project.ontology
                      else ProjectStatus.CREATED)
    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    project_repository.save(project)
    return project


def check_buildable(project: Project, force: bool) -> Optional[str]:
    """Why this project cannot be built right now, or None when it can be."""
    if project.status == ProjectStatus.CREATED:
        return "Project has not generated ontology yet. Please call /ontology/generate first"
    if project.status == ProjectStatus.GRAPH_BUILDING and not force:
        return ("Graph is being built. Do not submit repeatedly. "
                "To force rebuild, add force: true")
    return None
