"""
Simulation Manager
Manages AgentSociety opinion-space simulations.
Uses preset scripts + LLM intelligent generation of config parameters.
"""

import os
import re
import json
import shutil
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.logger import get_logger
from .entity_reader import EntityReader, FilteredEntities
from .simulation_config_generator import SimulationConfigGenerator, SimulationParameters
from .document_context_engine import DocumentContextEngine
from . import mode_detector
from .custom_agent_parser import CustomAgentParser
from .deep_research_service import research_archetypes as _deep_research_archetypes
from .agent_enricher import AgentContextEnricher
from .persona_library import get_library
from .persona_retrieval import select_for_query
from .panel_service import _build_profile, assert_library_cast, MAX_CAST_SIZE

logger = get_logger('fub.simulation')

# Main-simulation cast size. Larger than the panel default (12) — a full sim feed
# wants a fuller room. The cast is drawn from the persona library, never from seed
# entities, so brands/products can't leak in as agents.
DEFAULT_MAIN_CAST_SIZE = 24


class SimulationStatus(str, Enum):
    """Simulation status"""
    CREATED = "created"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"      # Simulation manually stopped
    COMPLETED = "completed"  # Simulation completed naturally
    FAILED = "failed"


@dataclass
class SimulationState:
    """Simulation status"""
    simulation_id: str
    project_id: str
    graph_id: str

    # Status
    status: SimulationStatus = SimulationStatus.CREATED

    # Preparation phase data
    entities_count: int = 0
    profiles_count: int = 0
    entity_types: List[str] = field(default_factory=list)

    # Config generation information
    config_generated: bool = False
    config_reasoning: str = ""

    # Runtime data
    current_round: int = 0

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # Error message
    error: Optional[str] = None

    # Cost tracking
    prepare_prompt_tokens: int = 0
    prepare_completion_tokens: int = 0
    prepare_cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Complete status dict (internal use)"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "config_generated": self.config_generated,
            "config_reasoning": self.config_reasoning,
            "current_round": self.current_round,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
            "prepare_prompt_tokens": self.prepare_prompt_tokens,
            "prepare_completion_tokens": self.prepare_completion_tokens,
            "prepare_cost_usd": self.prepare_cost_usd,
        }
    
    def to_simple_dict(self) -> Dict[str, Any]:
        """Simplified status dict (API return use)"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "config_generated": self.config_generated,
            "error": self.error,
        }


class SimulationManager:
    """
    Simulation Manager
    
    Core Functions:
    1. Read entities from graph and filter
    2. Generate OASIS Agent Profile
    3. Use LLM intelligent generation of simulation config parameters
    4. Prepare all files required by preset scripts
    """
    
    # Simulation data storage directory
    # Use the configured data root (DATA_ROOT/uploads/simulations) so saved sim
    # state lives on the mounted volume in prod — not the ephemeral container
    # filesystem, which is wiped on every redeploy. Matches the path the rest of
    # the code (Config.OASIS_SIMULATION_DATA_DIR, API routes, exporter) uses.
    SIMULATION_DATA_DIR = Config.OASIS_SIMULATION_DATA_DIR
    
    def __init__(self):
        # Ensure directory exists
        os.makedirs(self.SIMULATION_DATA_DIR, exist_ok=True)
        
        # In-memory simulation state cache
        self._simulations: Dict[str, SimulationState] = {}
    
    def _get_simulation_dir(self, simulation_id: str) -> str:
        """Get simulation data directory"""
        sim_dir = os.path.join(self.SIMULATION_DATA_DIR, simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        return sim_dir
    
    def _save_simulation_state(self, state: SimulationState):
        """Save simulation state to file"""
        sim_dir = self._get_simulation_dir(state.simulation_id)
        state_file = os.path.join(sim_dir, "state.json")
        
        state.updated_at = datetime.now().isoformat()
        
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)
        
        self._simulations[state.simulation_id] = state
    
    def _load_simulation_state(self, simulation_id: str) -> Optional[SimulationState]:
        """Load simulation state from file"""
        if simulation_id in self._simulations:
            return self._simulations[simulation_id]
        
        sim_dir = self._get_simulation_dir(simulation_id)
        state_file = os.path.join(sim_dir, "state.json")
        
        if not os.path.exists(state_file):
            return None
        
        with open(state_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        state = SimulationState(
            simulation_id=simulation_id,
            project_id=data.get("project_id", ""),
            graph_id=data.get("graph_id", ""),
            status=SimulationStatus(data.get("status", "created")),
            entities_count=data.get("entities_count", 0),
            profiles_count=data.get("profiles_count", 0),
            entity_types=data.get("entity_types", []),
            config_generated=data.get("config_generated", False),
            config_reasoning=data.get("config_reasoning", ""),
            current_round=data.get("current_round", 0),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            error=data.get("error"),
            prepare_prompt_tokens=data.get("prepare_prompt_tokens", 0),
            prepare_completion_tokens=data.get("prepare_completion_tokens", 0),
            prepare_cost_usd=data.get("prepare_cost_usd", 0.0),
        )

        self._simulations[simulation_id] = state
        return state
    
    def create_simulation(
        self,
        project_id: str,
        graph_id: str,
    ) -> SimulationState:
        """
        Create new simulation.

        Args:
            project_id: Project ID
            graph_id: Graph ID

        Returns:
            SimulationState
        """
        import uuid
        simulation_id = f"sim_{uuid.uuid4().hex[:12]}"

        state = SimulationState(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            status=SimulationStatus.CREATED,
        )
        
        self._save_simulation_state(state)
        logger.info(f"Create simulation: {simulation_id}, project={project_id}, graph={graph_id}")
        
        return state
    
    def prepare_simulation(
        self,
        simulation_id: str,
        simulation_requirement: str,
        document_text: str,
        defined_entity_types: Optional[List[str]] = None,
        progress_callback: Optional[callable] = None,
        parallel_profile_count: int = 3,
        storage: 'GraphStorage' = None,
        custom_profiles: Optional[List] = None,
        custom_only: bool = False,
        mode: str = 'policy',
        detection: Optional[Dict[str, Any]] = None,
        mode_is_manual: bool = False,
    ) -> SimulationState:
        """
        Prepare simulation environment (fully automated)
        
        Steps:
        1. Read and filter entities from graph
        2. Generate OASIS Agent Profile for each entity (optional LLM enhancement, parallel support)
        3. Use LLM intelligent generation of simulation config parameters (time, activity, speaking frequency, etc.)
        4. Save config files and Profile files
        5. Copy preset scripts to simulation directory
        
        Args:
            simulation_id: Simulation ID
            simulation_requirement: Simulation requirement description (for LLM config generation)
            document_text: Original document content (for LLM background understanding)
            defined_entity_types: Predefined entity types (optional)
            progress_callback: Progress callback function (stage, progress, message)
            parallel_profile_count: Number of parallel profile generations, default 3
            
        Returns:
            SimulationState
        """
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"Simulation does not exist: {simulation_id}")
        
        try:
            state.status = SimulationStatus.PREPARING
            self._save_simulation_state(state)
            
            sim_dir = self._get_simulation_dir(simulation_id)

            # Load enrichment data if it exists (from deep web research)
            enrichment_data = {}
            enrichment_file = os.path.join(sim_dir, "enrichment.json")
            if os.path.exists(enrichment_file):
                try:
                    with open(enrichment_file, 'r', encoding='utf-8') as f:
                        enrichment_data = json.load(f)
                    logger.info(f"Loaded enrichment data from simulation dir for {len(enrichment_data)} archetypes")
                except Exception as e:
                    logger.warning(f"Failed to load enrichment data from simulation dir: {e}")

            # Also check project for enrichment data (saved during project creation)
            project_for_papers = None
            if not enrichment_data and state.project_id:
                try:
                    from ..models.project import ProjectManager
                    project_for_papers = ProjectManager.get_project(state.project_id)
                    if project_for_papers and project_for_papers.enrichment_data:
                        enrichment_data = project_for_papers.enrichment_data
                        logger.info(f"Loaded enrichment data from project for {len(enrichment_data)} archetypes")
                except Exception as e:
                    logger.warning(f"Failed to load enrichment data from project: {e}")
            elif state.project_id:
                try:
                    from ..models.project import ProjectManager
                    project_for_papers = ProjectManager.get_project(state.project_id)
                except Exception:
                    pass

            # Merge in saved literature papers as a shared grounding block.
            # The block is appended to every archetype's existing enrichment so
            # personas reference the academic context alongside other research.
            try:
                saved_papers = list(getattr(project_for_papers, "saved_papers", []) or []) if project_for_papers else []
            except Exception:
                saved_papers = []
            if saved_papers:
                lit_lines = ["ACADEMIC LITERATURE (saved to this project):"]
                for p in saved_papers[:15]:
                    title = (p.get("title") or "").strip()
                    year  = p.get("year") or ""
                    src   = p.get("source") or ""
                    authors_list = p.get("authors") or []
                    authors = ", ".join(authors_list[:3]) if isinstance(authors_list, list) else str(authors_list)
                    abstract = (p.get("abstract") or "").strip().replace("\n", " ")
                    if len(abstract) > 280:
                        abstract = abstract[:280].rsplit(" ", 1)[0] + "..."
                    lit_lines.append(f"- \"{title}\" ({year}, {src}) — {authors}")
                    if abstract:
                        lit_lines.append(f"    {abstract}")
                lit_block = "\n".join(lit_lines)
                # Append to every existing archetype's enrichment, and seed one
                # synthetic entry so even archetype-less generation still sees it.
                if enrichment_data:
                    for k in list(enrichment_data.keys()):
                        enrichment_data[k] = (enrichment_data[k] or "").rstrip() + "\n\n" + lit_block
                else:
                    enrichment_data = {"__literature__": lit_block}
                logger.info(f"Merged {len(saved_papers)} saved papers into enrichment ({len(enrichment_data)} archetypes total)")

            # Persist whatever we ended up with to the simulation dir so the
            # generator and future runs see it.
            if enrichment_data:
                try:
                    with open(enrichment_file, 'w', encoding='utf-8') as f:
                        json.dump(enrichment_data, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    logger.warning(f"Failed to persist enrichment data to sim dir: {e}")
            
            # ========== Phase 1: Read and filter entities ==========
            if progress_callback:
                progress_callback("reading", 0, "Connecting to graph...")

            if not storage:
                raise ValueError("storage (GraphStorage) is required for prepare_simulation")
            reader = EntityReader(storage)
            
            if progress_callback:
                progress_callback("reading", 30, "Reading node data...")
            
            filtered = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=defined_entity_types,
                enrich_with_edges=True
            )
            
            state.entities_count = filtered.filtered_count
            state.entity_types = list(filtered.entity_types)
            
            if progress_callback:
                progress_callback(
                    "reading", 100, 
                    f"Completed, total {filtered.filtered_count} entities",
                    current=filtered.filtered_count,
                    total=filtered.filtered_count
                )
            
            # The cast comes from the persona library, not from these entities, so an
            # empty graph is no longer fatal — it only means thinner CONTEXT. The graph
            # entities feed DocumentContextEngine + archetype enrichment below.
            if filtered.filtered_count == 0:
                logger.warning(
                    "No graph entities matched — context will be thin, but the cast is "
                    "drawn from the persona library so the simulation can still run."
                )
            
            # ========== Phase 1.5: Deep research enrichment ==========
            # Run only if no enrichment already loaded and Firecrawl is configured.
            def _normalize_archetype(t: str) -> str:
                s = re.sub(r'([A-Z])', r'_\1', t).lower().lstrip('_')
                return re.sub(r'[\s\-]+', '_', s.strip())

            if not enrichment_data:
                try:
                    if progress_callback:
                        progress_callback("generating_profiles", 0, "Running web research for archetypes...")
                    entity_types = list({_normalize_archetype(e.type) for e in filtered.entities if e.type})
                    seed = document_text or simulation_requirement or ""
                    raw_research = _deep_research_archetypes(
                        archetypes=entity_types,
                        query=seed or "current socio-economic conditions South Africa 2025",
                        document_text=seed,
                    )
                    if raw_research:
                        enrichment_data = AgentContextEnricher.enrich_from_web_research(raw_research, entity_types)
                        # Persist raw research so the API endpoint can serve it
                        with open(enrichment_file, 'w', encoding='utf-8') as f:
                            json.dump(raw_research, f, ensure_ascii=False, indent=2)
                        logger.info(f"Deep research complete: {len(enrichment_data)} archetypes enriched")
                except Exception as research_err:
                    logger.warning(f"Deep research failed (continuing without enrichment): {research_err}")

            # ========== Build prepare-time client + finalise mode (before cast) ==========
            # The mode tiebreak must run BEFORE cast selection, because the cast's
            # product economics (budget_tier) are computed at build time from `mode`.
            # The LLM_* client built here is reused for context extraction below.
            from openai import OpenAI
            client = OpenAI(
                api_key=Config.LLM_API_KEY,
                base_url=Config.LLM_BASE_URL,
            )

            # Mode tiebreak: only when the keyword margin was thin AND the user did not
            # manually pin the mode. Manual choice always wins. Any failure falls back to
            # the keyword decision (mode unchanged), so the final mode is authoritative
            # for the cast economics, the rule engine, and framing.
            converged = bool(detection.get("converged")) if detection else False
            secondary_lens = detection.get("secondary_lens") if detection else None
            used_llm_tiebreak = False
            if detection and not mode_is_manual:
                try:
                    refined = mode_detector.llm_tiebreak(
                        simulation_requirement, document_text, detection,
                        llm_client=client, model_name=Config.LLM_MODEL,
                    )
                    used_llm_tiebreak = bool(refined.get("used_llm_tiebreak"))
                    if used_llm_tiebreak:
                        mode = refined["mode"]
                        converged = bool(refined.get("converged"))
                        secondary_lens = refined.get("secondary_lens")
                        logger.info(
                            f"Mode tiebreak refined mode -> {mode} "
                            f"(converged={converged}, lens={secondary_lens})"
                        )
                except Exception as e:
                    logger.warning(f"Mode tiebreak failed, keeping keyword mode: {e}")

            # ========== Phase 2: Assemble the cast from the persona library ==========
            # CAST comes from the curated, survey-grounded library — NEVER from seed
            # entities. This is what stops brands/products/labels (Netflix, YouthX,
            # "Parents or Guardians") leaking in as agents: they aren't in the library.
            # The seed/document only shapes CONTEXT (Phase 2.5 below). All of this is
            # deterministic and LLM-free.
            if progress_callback:
                progress_callback("generating_profiles", 0, "Selecting cast from persona library...")

            run_custom_only = bool(custom_only and custom_profiles and len(custom_profiles) > 0)

            if run_custom_only:
                # The run consists solely of the user's hand-defined agents. No library
                # cast, and no leak guard (customs legitimately carry their own provenance).
                logger.info(f"Custom-only mode: running on {len(custom_profiles)} custom agents")
                profiles = CustomAgentParser.merge_profiles([], custom_profiles)
            else:
                if custom_only:
                    logger.warning("custom_only requested but no usable custom profiles — using library cast")

                library = get_library()
                if library.is_empty() and not (custom_profiles and len(custom_profiles) > 0):
                    state.status = SimulationStatus.FAILED
                    state.error = "Persona library is empty — run build_library.py to populate it."
                    self._save_simulation_state(state)
                    return state

                n = max(1, min(DEFAULT_MAIN_CAST_SIZE, MAX_CAST_SIZE))
                cast_query = simulation_requirement or document_text or ""
                cast = select_for_query(n, cast_query, library=library, seed=0)
                # Convert library identities to sim-ready profiles (stamps library
                # provenance + deterministic budget economics in product mode).
                library_profiles = [_build_profile(p, i, mode) for i, p in enumerate(cast)]
                # Leak guard — runs on the LIBRARY portion only, before any custom merge.
                assert_library_cast(library_profiles)
                logger.info(f"Selected {len(library_profiles)} library personas as the cast")

                # Merge custom agents (mixed mode). Custom overrides library by name and
                # gets sequential IDs reassigned. Do NOT re-guard after merge — customs
                # carry their own (non-library) provenance by design.
                if custom_profiles and len(custom_profiles) > 0:
                    profiles = CustomAgentParser.merge_profiles(library_profiles, custom_profiles)
                    logger.info(f"Merged {len(custom_profiles)} custom agents: final count = {len(profiles)}")
                else:
                    profiles = library_profiles

            state.profiles_count = len(profiles)
            # The cast no longer equals the graph entity count — report the cast size so
            # the status endpoint's expected-count converges to reality.
            state.entities_count = len(profiles)

            # Save the cast. No LLM ran on this path, so prepare token/cost stays zero —
            # which keeps "no model in the cast path" assertable.
            with open(os.path.join(sim_dir, "agentsociety_profiles.json"), 'w', encoding='utf-8') as f:
                json.dump(profiles, f, ensure_ascii=False, indent=2)
            state.prepare_prompt_tokens = 0
            state.prepare_completion_tokens = 0
            state.prepare_cost_usd = 0.0
            self._save_simulation_state(state)

            if progress_callback:
                progress_callback(
                    "generating_profiles", 100,
                    f"Cast ready, total {len(profiles)} agents",
                    current=len(profiles),
                    total=len(profiles)
                )

            # ========== Phase 2.5: Build and save document context for runtime ==========
            if progress_callback:
                progress_callback(
                    "building_context", 0,
                    "Building document context...",
                    current=0,
                    total=2
                )

            try:
                ctx_engine = DocumentContextEngine(storage=storage, mode=mode)
                ctx_engine.build_from_graph(state.graph_id)

                facts = []
                competitive_landscape = []
                if document_text:
                    try:
                        facts = ctx_engine.extract_facts(
                            document_text=document_text,
                            llm_client=client,
                            model_name=Config.LLM_MODEL,
                        )
                        if mode == "product":
                            competitive_landscape = ctx_engine.extract_competitive_landscape(
                                document_text=document_text,
                                llm_client=client,
                                model_name=Config.LLM_MODEL,
                            )
                            ctx_engine._build_document_context_block()
                    except Exception as e:
                        logger.warning(f"LLM extraction skipped: {e}")

                doc_context = {
                    "mode": mode,  # PRIMARY mode — authoritative for runtime + rules
                    "converged": converged,
                    "secondary_lens": secondary_lens,  # "product"|"policy"|None
                    "mode_detection": {
                        "scores": (detection or {}).get("scores", {}),
                        "decided_mode": (detection or {}).get("mode"),
                        "confidence": (detection or {}).get("confidence"),
                        "used_llm_tiebreak": used_llm_tiebreak,
                        "manual_override": mode_is_manual,
                    },
                    "domain": ctx_engine.domain,
                    "domain_profile": ctx_engine.get_domain_profile(),
                    "document_context_block": ctx_engine.get_document_context_block(),
                    "dynamic_rules": ctx_engine.get_dynamic_rules(),
                    "facts": facts,
                    "competitive_landscape": competitive_landscape,
                }

                ctx_path = os.path.join(sim_dir, "document_context.json")
                with open(ctx_path, 'w', encoding='utf-8') as f:
                    json.dump(doc_context, f, ensure_ascii=False, indent=2)

                logger.info(f"Saved document context to {ctx_path} ({len(facts)} facts)")
            except Exception as e:
                logger.warning(f"Document context building failed: {e}")

            if progress_callback:
                progress_callback(
                    "building_context", 100,
                    "Document context saved",
                    current=2,
                    total=2
                )

            # ========== Phase 3: LLM intelligent generation of simulation config ==========
            if progress_callback:
                progress_callback(
                    "generating_config", 0, 
                    "Analyzing simulation requirements...",
                    current=0,
                    total=3
                )
            
            config_generator = SimulationConfigGenerator()
            
            if progress_callback:
                progress_callback(
                    "generating_config", 30, 
                    "Calling LLM to generate config...",
                    current=1,
                    total=3
                )
            
            # The cast is library personas, not graph entities, so pass entities=[] —
            # time/event config still generate from the requirement + document context,
            # and per-agent activity configs come from the cast below (not EntityNodes).
            sim_params = config_generator.generate_config(
                simulation_id=simulation_id,
                project_id=state.project_id,
                graph_id=state.graph_id,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                entities=[],
            )

            # Give every cast member an AgentActivityConfig. With entities=[] there are
            # no existing configs, so this injects one per profile (library agents get
            # the standard config honouring their stance; is_core_focus customs get the
            # elevated one).
            sim_params = config_generator.inject_core_focus_configs(
                sim_params, profiles
            )
            
            if progress_callback:
                progress_callback(
                    "generating_config", 70, 
                    "Saving config files...",
                    current=2,
                    total=3
                )
            
            # Save config files
            config_path = os.path.join(sim_dir, "simulation_config.json")
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(sim_params.to_json())
            
            state.config_generated = True
            state.config_reasoning = sim_params.generation_reasoning
            
            if progress_callback:
                progress_callback(
                    "generating_config", 100, 
                    "Config generation completed",
                    current=3,
                    total=3
                )
            
            # Note: Run scripts remain in backend/scripts/ directory, no longer copy to simulation directory
            # When starting simulation, simulation_runner runs scripts from scripts/ directory
            
            # Update status
            state.status = SimulationStatus.READY
            self._save_simulation_state(state)
            
            logger.info(f"Simulation preparation completed: {simulation_id}, "
                       f"entities={state.entities_count}, profiles={state.profiles_count}")
            
            return state
            
        except Exception as e:
            logger.error(f"Simulation preparation failed: {simulation_id}, error={str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            state.status = SimulationStatus.FAILED
            state.error = str(e)
            self._save_simulation_state(state)
            raise
    
    def get_simulation(self, simulation_id: str) -> Optional[SimulationState]:
        """Get simulation state"""
        return self._load_simulation_state(simulation_id)
    
    def list_simulations(self, project_id: Optional[str] = None) -> List[SimulationState]:
        """List all simulations"""
        simulations = []
        
        if os.path.exists(self.SIMULATION_DATA_DIR):
            for sim_id in os.listdir(self.SIMULATION_DATA_DIR):
                # Skip hidden files (such as .DS_Store) and non-directory files
                sim_path = os.path.join(self.SIMULATION_DATA_DIR, sim_id)
                if sim_id.startswith('.') or not os.path.isdir(sim_path):
                    continue
                
                state = self._load_simulation_state(sim_id)
                if state:
                    if project_id is None or state.project_id == project_id:
                        simulations.append(state)
        
        return simulations
    
    def get_profiles(self, simulation_id: str, platform: str = "opinion_space") -> List[Dict[str, Any]]:
        """Get Agent Profiles for simulation"""
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"Simulation does not exist: {simulation_id}")

        sim_dir = self._get_simulation_dir(simulation_id)
        profile_path = os.path.join(sim_dir, "agentsociety_profiles.json")

        if not os.path.exists(profile_path):
            return []

        with open(profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_simulation_config(self, simulation_id: str) -> Optional[Dict[str, Any]]:
        """Get simulation config"""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        
        if not os.path.exists(config_path):
            return None
        
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_run_instructions(self, simulation_id: str) -> Dict[str, str]:
        """Get run instructions"""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts'))
        
        return {
            "simulation_dir": sim_dir,
            "scripts_dir": scripts_dir,
            "config_file": config_path,
            "commands": {
                "opinion_space": f"python {scripts_dir}/run_simulation_as.py --config {config_path}",
            },
            "instructions": (
                f"1. Run simulation: python {scripts_dir}/run_simulation_as.py --config {config_path}"
            )
        }
