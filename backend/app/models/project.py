"""
Project Context Management
Persists project state on server to avoid frontend passing large data between interfaces
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from enum import Enum
from dataclasses import dataclass, field, asdict
from ..utils.logger import get_logger

logger = get_logger("fub.project")


def warn_if_off_model(data: Dict[str, Any]) -> None:
    """Log (never raise) when a project no longer fits app/data/model/project.json.

    Public because the project repository calls it on the way to disk: the check is a
    model concern, the writing is not.
    """
    try:
        from ..services import data_model
        problems = data_model.model_problems("project", data, data.get("project_id"))
    except Exception as e:  # noqa: BLE001 — a check must never lose a user's project
        logger.warning(f"Could not check project against its data model: {e}")
        return
    if problems:
        logger.warning(f"Project {data.get('project_id')} does not match its data model: "
                       f"{len(problems)} problem(s). First: {'; '.join(problems[:3])}")


class CustomAgentSource(str, Enum):
    """Source of custom agent definitions"""
    SEED_DOCUMENT = "seed_document"
    AGENT_DOCUMENT = "agent_document"
    MANUAL = "manual"


class ProjectStatus(str, Enum):
    """Project status"""
    CREATED = "created"              # Just created, files uploaded
    ONTOLOGY_GENERATED = "ontology_generated"  # Ontology generated
    GRAPH_BUILDING = "graph_building"    # Graph building in progress
    GRAPH_COMPLETED = "graph_completed"  # Graph build completed
    FAILED = "failed"                # Failed


@dataclass
class Project:
    """Project data model"""
    project_id: str
    name: str
    status: ProjectStatus
    created_at: str
    updated_at: str

    # File information
    files: List[Dict[str, str]] = field(default_factory=list)  # [{filename, path, size}]
    total_text_length: int = 0

    # Ontology information (populated after interface 1 generates)
    ontology: Optional[Dict[str, Any]] = None
    analysis_summary: Optional[str] = None

    # Graph information (populated after interface 2 completes)
    graph_id: Optional[str] = None
    graph_build_task_id: Optional[str] = None

    # Custom agents extracted from seed document or added manually
    custom_agents: List[Dict[str, Any]] = field(default_factory=list)
    custom_agents_enabled: bool = False

    # Web enrichment data (archetype → research text)
    enrichment_data: Dict[str, str] = field(default_factory=dict)

    # Literature papers saved to this project (used as agent-grounding context).
    # Each entry: {id, title, authors, year, source, abstract, url}
    saved_papers: List[Dict[str, Any]] = field(default_factory=list)

    # Configuration
    simulation_requirement: Optional[str] = None
    chunk_size: int = 500
    chunk_overlap: int = 50

    # Error information
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "project_id": self.project_id,
            "name": self.name,
            "status": self.status.value if isinstance(self.status, ProjectStatus) else self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "files": self.files,
            "total_text_length": self.total_text_length,
            "ontology": self.ontology,
            "analysis_summary": self.analysis_summary,
            "graph_id": self.graph_id,
            "graph_build_task_id": self.graph_build_task_id,
            "custom_agents": self.custom_agents,
            "custom_agents_enabled": self.custom_agents_enabled,
            "enrichment_data": self.enrichment_data,
            "saved_papers": self.saved_papers,
            "simulation_requirement": self.simulation_requirement,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "error": self.error
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Project':
        """Create from dictionary"""
        status = data.get('status', 'created')
        if isinstance(status, str):
            status = ProjectStatus(status)
        
        return cls(
            project_id=data['project_id'],
            name=data.get('name', 'Unnamed Project'),
            status=status,
            created_at=data.get('created_at', ''),
            updated_at=data.get('updated_at', ''),
            files=data.get('files', []),
            total_text_length=data.get('total_text_length', 0),
            ontology=data.get('ontology'),
            analysis_summary=data.get('analysis_summary'),
            graph_id=data.get('graph_id'),
            graph_build_task_id=data.get('graph_build_task_id'),
            custom_agents=data.get('custom_agents', []),
            custom_agents_enabled=data.get('custom_agents_enabled', False),
            enrichment_data=data.get('enrichment_data', {}),
            saved_papers=data.get('saved_papers', []),
            simulation_requirement=data.get('simulation_requirement'),
            chunk_size=data.get('chunk_size', 500),
            chunk_overlap=data.get('chunk_overlap', 50),
            error=data.get('error')
        )
