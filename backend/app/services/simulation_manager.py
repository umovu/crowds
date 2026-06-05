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
from .agent_profile_generator import AgentProfileGenerator, AgentProfile
from .simulation_config_generator import SimulationConfigGenerator, SimulationParameters
from .document_context_engine import DocumentContextEngine
from .custom_agent_parser import CustomAgentParser
from .deep_research_service import research_archetypes as _deep_research_archetypes
from .agent_enricher import AgentContextEnricher

logger = get_logger('fub.simulation')


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
    SIMULATION_DATA_DIR = os.path.join(
        os.path.dirname(__file__), 
        '../../uploads/simulations'
    )
    
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
        use_llm_for_profiles: bool = True,
        progress_callback: Optional[callable] = None,
        parallel_profile_count: int = 3,
        storage: 'GraphStorage' = None,
        custom_profiles: Optional[List] = None,
        custom_only: bool = False,
        mode: str = 'policy',
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
            use_llm_for_profiles: Whether to use LLM to generate detailed profiles
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

            # Load enrichment data if it exists (from MiroFlow deep research)
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
            
            if filtered.filtered_count == 0:
                state.status = SimulationStatus.FAILED
                state.error = "No entities matching criteria found, check if graph is correctly constructed"
                self._save_simulation_state(state)
                return state
            
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
                        enrichment_data = AgentContextEnricher.enrich_from_miroflow(raw_research, entity_types)
                        # Persist raw research so the API endpoint can serve it
                        with open(enrichment_file, 'w', encoding='utf-8') as f:
                            json.dump(raw_research, f, ensure_ascii=False, indent=2)
                        logger.info(f"Deep research complete: {len(enrichment_data)} archetypes enriched")
                except Exception as research_err:
                    logger.warning(f"Deep research failed (continuing without enrichment): {research_err}")

            # ========== Phase 2: Generate Agent Profile ==========
            total_entities = len(filtered.entities)

            if progress_callback:
                progress_callback(
                    "generating_profiles", 0,
                    "Starting generation...",
                    current=0,
                    total=total_entities
                )

            # Pass graph_id to enable graph retrieval functionality, get richer context
            generator = AgentProfileGenerator(
                storage=storage,
                graph_id=state.graph_id,
                enrichment_data=enrichment_data,
                mode=mode
            )
            
            def profile_progress(current, total, msg):
                if progress_callback:
                    progress_callback(
                        "generating_profiles", 
                        int(current / total * 100), 
                        msg,
                        current=current,
                        total=total,
                        item_name=msg
                    )
            
            realtime_output_path = os.path.join(sim_dir, "agentsociety_profiles.json")

            # ========== Custom-only mode: skip auto-generation entirely ==========
            # When the user opts to run on custom agents alone, we don't read the
            # graph population or LLM-expand — the run consists solely of their
            # hand-defined agents. Falls back to normal generation if custom_only
            # was requested but no usable custom profiles came through.
            run_custom_only = bool(custom_only and custom_profiles and len(custom_profiles) > 0)

            if run_custom_only:
                logger.info(f"Custom-only mode: running on {len(custom_profiles)} custom agents, skipping auto-generation")
                if progress_callback:
                    progress_callback(
                        "generating_profiles", 90,
                        f"Custom-only mode — using {len(custom_profiles)} custom agents...",
                        current=len(custom_profiles),
                        total=len(custom_profiles)
                    )
                # merge against an empty auto population to assign sequential IDs
                profiles = CustomAgentParser.merge_profiles([], custom_profiles)
                state.profiles_count = len(profiles)
                logger.info(f"Custom-only population: {len(profiles)} agents")
            else:
                if custom_only:
                    logger.warning("custom_only requested but no usable custom profiles — falling back to auto-generation")

                profiles = generator.generate_profiles_from_entities(
                    entities=filtered.entities,
                    use_llm=use_llm_for_profiles,
                    progress_callback=profile_progress,
                    graph_id=state.graph_id,
                    parallel_count=parallel_profile_count,
                    realtime_output_path=realtime_output_path,
                    output_platform="opinion_space"
                )

                state.profiles_count = len(profiles)

            # ========== Expand population if needed (LLM self-generation) ==========
            # Always expand if we have fewer than 20 agents — richer simulations need scale.
            # Skipped in custom-only mode (the cast is deliberately exactly what the user defined).
            target_min = 20
            if not run_custom_only and len(profiles) < target_min and document_text:
                needed = target_min - len(profiles)
                logger.info(f"Seed population small ({len(profiles)}), expanding by {needed} via LLM...")
                if progress_callback:
                    progress_callback(
                        "generating_profiles", 85,
                        f"Expanding agent population by {needed}...",
                        current=len(profiles),
                        total=target_min
                    )
                
                profiles = generator.expand_population(
                    seed_profiles=profiles,
                    document_text=document_text,
                    target_count=target_min,
                    progress_callback=lambda curr, tot, msg: progress_callback(
                        "generating_profiles", 85 + int(curr / tot * 10),
                        msg,
                        current=curr,
                        total=tot
                    ) if progress_callback else None,
                )
                
                state.profiles_count = len(profiles)
                logger.info(f"Population expanded to {len(profiles)} agents")

            # ========== Merge custom agents if provided ==========
            # In custom-only mode the custom profiles are already the population, so skip.
            if not run_custom_only and custom_profiles and len(custom_profiles) > 0:
                if progress_callback:
                    progress_callback(
                        "generating_profiles", 92,
                        f"Merging {len(custom_profiles)} custom agents...",
                        current=len(profiles),
                        total=len(profiles) + len(custom_profiles)
                    )
                profiles = CustomAgentParser.merge_profiles(profiles, custom_profiles)
                state.profiles_count = len(profiles)
                logger.info(f"Merged custom agents: final count = {len(profiles)}")

            if progress_callback:
                progress_callback(
                    "generating_profiles", 95,
                    "Saving Profile files...",
                    current=total_entities,
                    total=total_entities
                )

            generator.save_profiles(
                profiles=profiles,
                file_path=os.path.join(sim_dir, "agentsociety_profiles.json"),
                platform="opinion_space"
            )

            usage = generator.get_usage_stats()
            state.prepare_prompt_tokens = usage["prompt_tokens"]
            state.prepare_completion_tokens = usage["completion_tokens"]
            state.prepare_cost_usd = usage["estimated_cost_usd"]
            self._save_simulation_state(state)

            if progress_callback:
                progress_callback(
                    "generating_profiles", 100,
                    f"Completed, total {len(profiles)} Profiles",
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
                        from openai import OpenAI
                        client = OpenAI(
                            api_key=Config.LLM_API_KEY,
                            base_url=Config.LLM_BASE_URL,
                        )
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
                    "mode": mode,
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
            
            sim_params = config_generator.generate_config(
                simulation_id=simulation_id,
                project_id=state.project_id,
                graph_id=state.graph_id,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                entities=filtered.entities,
            )

            if custom_profiles:
                core_focus_custom = [p for p in custom_profiles if p.get("is_core_focus", False)]
                if core_focus_custom:
                    sim_params = config_generator.inject_core_focus_configs(
                        sim_params, custom_profiles
                    )
                    logger.info(f"Injected core focus configs for {len(core_focus_custom)} agents")
            
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
