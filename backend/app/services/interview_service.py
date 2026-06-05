"""
Interview Service — Post-hoc agent interviews for policy wind tunnel.

Provides structured and free-text interviews with simulated stakeholders
without requiring a running simulation environment.

Uses OpinionCitizenAgent.answer_external_question() via agentsociety2's
built-in interview primitive, with simulation state injected via
_build_external_question_context() override.
"""

import os
import json
import asyncio
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

from .opinion_agent import OpinionCitizenAgent
from .prompt_reframer import ImpactReframer
from .data_exporter import SimulationDataExporter
from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("fub.interview_service")


class InterviewService:
    """Service for conducting post-hoc interviews with simulated agents."""

    def __init__(self, simulation_id: str):
        self.simulation_id = simulation_id
        self.sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
        self.profiles_path = os.path.join(self.sim_dir, "agentsociety_profiles.json")
        self.profiles: List[Dict[str, Any]] = []
        self.mode = self._load_mode()
        self._load_profiles()

    def _load_mode(self) -> str:
        """Read the simulation mode ('policy' or 'product') from document_context.json.

        Written by simulation_manager at build time. Defaults to 'policy' if the
        file is missing or unreadable, so interviews never error on mode alone.
        """
        ctx_path = os.path.join(self.sim_dir, "document_context.json")
        try:
            with open(ctx_path, 'r', encoding='utf-8') as f:
                ctx = json.load(f)
            mode = (ctx.get("mode") or "policy").strip().lower()
            return mode if mode in ("policy", "product") else "policy"
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return "policy"

    def _load_profiles(self):
        """Load agent profiles from simulation directory."""
        if not os.path.exists(self.profiles_path):
            raise FileNotFoundError(f"Profiles not found: {self.profiles_path}")
        with open(self.profiles_path, 'r', encoding='utf-8') as f:
            self.profiles = json.load(f)
        logger.info(f"Loaded {len(self.profiles)} profiles for {self.simulation_id}")

    def get_agent_profile(self, agent_id: int) -> Optional[Dict[str, Any]]:
        """Get profile for a specific agent."""
        for p in self.profiles:
            if p.get("id") == agent_id or p.get("agent_id") == agent_id:
                return p
        return None

    def list_agents(self) -> List[Dict[str, Any]]:
        """List all agents with their simulation-relevant fields."""
        result = []
        for p in self.profiles:
            result.append({
                "id": p.get("id", p.get("agent_id")),
                "name": p.get("name"),
                "occupation": p.get("occupation"),
                "actor_archetype": p.get("actor_archetype"),
                "group_affiliation": p.get("group_affiliation"),
                "is_institutional": p.get("is_institutional", False),
                "stance": p.get("stance", "neutral"),
                "base_radicalism": p.get("base_radicalism", 1),
                "interested_topics": p.get("interested_topics", []),
            })
        return result

    def _create_agent(self, profile: Dict[str, Any]) -> OpinionCitizenAgent:
        """Instantiate an OpinionCitizenAgent from a stored profile.

        This creates a standalone agent with LLM initialized via env vars.
        No simulation environment is needed for post-hoc interviews.
        """
        agent_id = profile.get("id", profile.get("agent_id", 0))
        name = profile.get("name", f"Agent_{agent_id}")

        # Extract simulation fields from profile (if present from newer generations)
        init_state = {
            "stance": profile.get("stance", "neutral"),
            "actor_archetype": profile.get("actor_archetype"),
            "group_affiliation": profile.get("group_affiliation"),
            "behavioral_tendencies": profile.get("behavioral_tendencies"),
            "base_radicalism": profile.get("base_radicalism", 1),
            "current_radicalism": profile.get("current_radicalism", profile.get("base_radicalism", 1)),
            "is_institutional": profile.get("is_institutional", False),
            "interested_topics": profile.get("interested_topics", []),
            "posts_history": profile.get("posts_history", []),
            "interview_memory": profile.get("interview_memory", []),
            "interview_count": profile.get("interview_count", 0),
            "mobilization_level": profile.get("mobilization_level", 0),
            "source_entity_uuid": profile.get("source_entity_uuid"),
        }

        # Remove None values
        init_state = {k: v for k, v in init_state.items() if v is not None}

        agent = OpinionCitizenAgent(
            id=agent_id,
            profile=profile,
            name=name,
            init_state=init_state,
            capability_kwargs={
                "max_tool_rounds": 4,  # Interviews don't need many tool rounds
                "system_prompt_max_identity_chars": 12000,
            },
        )

        # Initialize workspace directory for standalone interview mode.
        # PersonAgent's _build_external_question_context() reads workspace files;
        # without a simulation env, the skill runtime work_dir is None.
        work_dir = Path(tempfile.gettempdir()) / "fub_interviews" / f"agent_{agent_id:04d}"
        work_dir.mkdir(parents=True, exist_ok=True)
        agent._skill_runtime._agent_work_dir = work_dir

        return agent

    async def interview_agent(
        self,
        agent_id: int,
        question: str,
        question_type: Optional[str] = None,
        policy_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Conduct an interview with a specific agent.

        Args:
            agent_id: The agent's ID.
            question: Free-text question (used if question_type is None).
            question_type: Structured question type (overrides question if provided).
            policy_context: Policy description for structured questions.

        Returns:
            Interview result with response, stance tracking, and metadata.
        """
        profile = self.get_agent_profile(agent_id)
        if not profile:
            raise ValueError(f"Agent {agent_id} not found in simulation {self.simulation_id}")

        agent = self._create_agent(profile)
        t = datetime.now()

        if question_type:
            result = await agent.do_structured_interview(
                question_type=question_type,
                policy_context=policy_context or "a recent government policy announcement",
                t=t,
            )
        else:
            result = await agent.do_interview(
                question=question,
                t=t,
            )

        # Enrich with agent metadata
        result["agent_id"] = agent_id
        result["agent_name"] = profile.get("name")
        result["actor_archetype"] = profile.get("actor_archetype")
        result["group_affiliation"] = profile.get("group_affiliation")
        result["is_institutional"] = profile.get("is_institutional", False)
        result["question_type"] = question_type
        result["question"] = question
        result["policy_context"] = policy_context
        result["timestamp"] = datetime.now().isoformat()

        return result

    async def intervene_with_agent(
        self,
        agent_id: int,
        intervention_text: str,
    ) -> Dict[str, Any]:
        """Apply a policy-maker intervention to an agent.

        Args:
            agent_id: The agent's ID.
            intervention_text: What the policy maker told the agent.

        Returns:
            Intervention result with before/after state comparison.
        """
        profile = self.get_agent_profile(agent_id)
        if not profile:
            raise ValueError(f"Agent {agent_id} not found in simulation {self.simulation_id}")

        agent = self._create_agent(profile)
        t = datetime.now()

        result = await agent.apply_intervention(intervention_text, t=t, mode=self.mode)

        # Enrich with agent metadata
        result["agent_id"] = agent_id
        result["agent_name"] = profile.get("name")
        result["actor_archetype"] = profile.get("actor_archetype")
        result["group_affiliation"] = profile.get("group_affiliation")
        result["intervention_text"] = intervention_text
        result["timestamp"] = datetime.now().isoformat()

        return result

    async def batch_interview(
        self,
        question: str,
        agent_ids: Optional[List[int]] = None,
        question_type: Optional[str] = None,
        policy_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Interview multiple agents with the same question.

        Args:
            question: The interview question.
            agent_ids: Specific agent IDs, or None for all agents.
            question_type: Structured question type.
            policy_context: Policy description.

        Returns:
            Batch result with individual responses and aggregate statistics.
        """
        targets = agent_ids if agent_ids else [p.get("id", p.get("agent_id")) for p in self.profiles]
        targets = [t for t in targets if t is not None]

        results = []
        for aid in targets:
            try:
                result = await self.interview_agent(
                    agent_id=aid,
                    question=question,
                    question_type=question_type,
                    policy_context=policy_context,
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Interview failed for agent {aid}: {e}")
                results.append({
                    "agent_id": aid,
                    "error": str(e),
                    "response": "Interview failed.",
                })

        # Aggregate statistics
        stance_counts = {}
        changed_count = 0
        for r in results:
            stance = r.get("stance_after", "unknown")
            stance_counts[stance] = stance_counts.get(stance, 0) + 1
            if r.get("stance_changed"):
                changed_count += 1

        return {
            "simulation_id": self.simulation_id,
            "total_interviewed": len(results),
            "successful": len([r for r in results if "error" not in r]),
            "failed": len([r for r in results if "error" in r]),
            "stance_distribution": stance_counts,
            "any_stance_changed": changed_count > 0,
            "results": results,
        }

    async def batch_impact_interview(
        self,
        question: str,
        agent_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Batch impact-extraction interview with auto-reframing per agent.

        Each agent receives a persona-specific version of the question.
        Returns individual responses + aggregate impact dashboard.

        Args:
            question: The user's generic policy question.
            agent_ids: Specific agent IDs, or None for all agents.

        Returns:
            Batch result with reframed questions, impact metadata, and aggregate stats.
        """
        reframer = ImpactReframer()
        targets = agent_ids if agent_ids else [p.get("id", p.get("agent_id")) for p in self.profiles]
        targets = [t for t in targets if t is not None]

        results = []
        for aid in targets:
            try:
                profile = self.get_agent_profile(aid)
                if not profile:
                    continue

                agent = self._create_agent(profile)
                t = datetime.now()

                # Reframe question for this specific agent
                reframed = reframer.reframe(question, profile)
                archetype = reframer.detect_archetype(question)

                result = await agent.do_impact_interview(
                    reframed_question=reframed,
                    original_question=question,
                    t=t,
                )

                # Enrich with metadata
                result["agent_id"] = aid
                result["agent_name"] = profile.get("name")
                result["actor_archetype"] = profile.get("actor_archetype")
                result["group_affiliation"] = profile.get("group_affiliation")
                result["question_archetype"] = archetype
                result["timestamp"] = datetime.now().isoformat()
                results.append(result)

            except Exception as e:
                logger.error(f"Impact interview failed for agent {aid}: {e}")
                results.append({
                    "agent_id": aid,
                    "error": str(e),
                    "response": "Interview failed.",
                    "original_question": question,
                })

        # Build aggregate impact dashboard
        dashboard = self._build_impact_dashboard(results)

        output = {
            "simulation_id": self.simulation_id,
            "original_question": question,
            "total_interviewed": len(results),
            "successful": len([r for r in results if "error" not in r]),
            "failed": len([r for r in results if "error" in r]),
            "question_archetype": reframer.detect_archetype(question),
            "impact_dashboard": dashboard,
            "results": results,
        }

        # Persist for later export
        try:
            exporter = SimulationDataExporter(self.simulation_id)
            exporter.save_impact_results(output)
        except Exception as e:
            logger.warning(f"Failed to save impact results: {e}")

        return output

    def _build_impact_dashboard(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate impact metadata across all agents."""
        emotional_temperature = {}
        stance_distribution = {}
        mobilization_risk = {"low": 0, "medium": 0, "high": 0}
        granularity_distribution = {"micro": 0, "meso": 0, "macro": 0}
        affected_entities = []
        stance_changed_count = 0
        emotional_shifts = []
        predicted_actions = []

        for r in results:
            if "error" in r:
                continue

            # Stance
            stance = r.get("stance_after", "unknown")
            stance_distribution[stance] = stance_distribution.get(stance, 0) + 1
            if r.get("stance_changed"):
                stance_changed_count += 1

            # Impact metadata
            meta = r.get("impact_metadata", {})

            # Emotional temperature
            emotion = meta.get("emotional_tone", "neutral")
            emotional_temperature[emotion] = emotional_temperature.get(emotion, 0) + 1

            # Granularity
            gran = meta.get("granularity", "meso")
            granularity_distribution[gran] = granularity_distribution.get(gran, 0) + 1

            # Mobilization risk
            internal = r.get("internal_state", {})
            mob = internal.get("mobilization_level", 0)
            if mob >= 2:
                mobilization_risk["high"] += 1
            elif mob == 1:
                mobilization_risk["medium"] += 1
            else:
                mobilization_risk["low"] += 1

            # Affected entities
            ent = meta.get("affected_entity")
            if ent and ent not in affected_entities:
                affected_entities.append(ent)

            # Emotional shift
            shift = meta.get("emotional_shift", 0)
            if shift != 0:
                emotional_shifts.append({
                    "agent_id": r.get("agent_id"),
                    "agent_name": r.get("agent_name"),
                    "shift": shift,
                })

            # Predicted actions
            action = meta.get("predicted_action")
            if action:
                predicted_actions.append({
                    "agent_id": r.get("agent_id"),
                    "agent_name": r.get("agent_name"),
                    "action": action,
                })

        return {
            "emotional_temperature": emotional_temperature,
            "stance_distribution": stance_distribution,
            "stance_changed_count": stance_changed_count,
            "stance_changed_rate": stance_changed_count / max(len(results), 1),
            "mobilization_risk": mobilization_risk,
            "granularity_distribution": granularity_distribution,
            "affected_entities": affected_entities,
            "emotional_shifts": emotional_shifts,
            "predicted_actions": predicted_actions,
        }

    def fork_simulation(
        self,
        new_simulation_id: str,
        agent_modifications: Optional[Dict[int, Dict[str, Any]]] = None,
    ) -> str:
        """Fork a simulation, optionally modifying agent profiles.

        Args:
            new_simulation_id: ID for the new simulation.
            agent_modifications: Dict mapping agent_id -> field updates.
                e.g. {5: {"stance": "support", "current_radicalism": 2}}

        Returns:
            Path to the new simulation directory.
        """
        import shutil

        new_sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, new_simulation_id)
        if os.path.exists(new_sim_dir):
            raise ValueError(f"Simulation {new_simulation_id} already exists")

        # Copy entire simulation directory
        shutil.copytree(self.sim_dir, new_sim_dir)

        # Apply modifications to profiles
        if agent_modifications:
            profiles_path = os.path.join(new_sim_dir, "agentsociety_profiles.json")
            with open(profiles_path, 'r', encoding='utf-8') as f:
                profiles = json.load(f)

            modified_count = 0
            for p in profiles:
                pid = p.get("id", p.get("agent_id"))
                if pid in agent_modifications:
                    p.update(agent_modifications[pid])
                    modified_count += 1

            with open(profiles_path, 'w', encoding='utf-8') as f:
                json.dump(profiles, f, ensure_ascii=False, indent=2)

            logger.info(f"Forked {self.simulation_id} -> {new_simulation_id}, modified {modified_count} agents")
        else:
            logger.info(f"Forked {self.simulation_id} -> {new_simulation_id} (no modifications)")

        # Update simulation config with new ID
        config_path = os.path.join(new_sim_dir, "simulation_config.json")
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            config["simulation_id"] = new_simulation_id
            config["forked_from"] = self.simulation_id
            config["forked_at"] = datetime.now().isoformat()
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

        return new_sim_dir
