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
from typing import Any, Callable, Dict, List, Optional

from ..config import Config
from ..repositories import project_repository
from ..repositories import simulation_repository as repo
from ..utils.logger import get_logger
from .simulation_manager import SimulationManager

logger = get_logger("fub.simulation_setup")

#: Where an upload waits while it is being parsed. Nothing else uses this directory.
TEMP_UPLOAD_DIR = "temp"

#: Used when the run's project has no seed text of its own.
DEFAULT_RESEARCH_QUERY = "current socio-economic conditions South Africa 2025"


class RunNotFound(LookupError):
    """No such simulation."""


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
