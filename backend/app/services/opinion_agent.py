"""
OpinionCitizenAgent — proper agentsociety CitizenAgentBase subclass.

Extends CitizenAgentBase with city bindings overridden as no-ops.
Uses real KVMemory (profile) + StreamMemory (simulation diary) from agentsociety.
do_interview() is inherited from CitizenAgentBase — it searches real memory.
"""

from typing import Any, List, Optional

from agentsociety.agent import CitizenAgentBase
from agentsociety.agent.memory_config_generator import MemoryAttribute, MemoryConfig
from agentsociety.memory import Memory

from ..utils.logger import get_logger

logger = get_logger("fub.opinion_agent")

# Dummy position so StreamMemory.add() resolves location without crashing
_DUMMY_POSITION = {"unknown_position": True}


def build_memory_config(profile: dict) -> MemoryConfig:
    """
    Build a MemoryConfig pre-populated from an agentsociety profile dict.
    All fields are embedded for semantic search during do_interview().
    """
    attrs = [
        MemoryAttribute(
            name="id",
            type=int,
            default_or_value=profile.get("id", 0),
            description="agent id",
            whether_embedding=False,
        ),
        MemoryAttribute(
            name="name",
            type=str,
            default_or_value=profile.get("name", ""),
            description="agent name",
            whether_embedding=True,
        ),
        MemoryAttribute(
            name="persona",
            type=str,
            default_or_value=profile.get("persona", ""),
            description="short role descriptor",
            whether_embedding=True,
        ),
        MemoryAttribute(
            name="background_story",
            type=str,
            default_or_value=profile.get("background_story", ""),
            description="narrative background",
            whether_embedding=True,
        ),
        MemoryAttribute(
            name="age",
            type=int,
            default_or_value=profile.get("age", 0),
            description="age",
            whether_embedding=True,
        ),
        MemoryAttribute(
            name="gender",
            type=str,
            default_or_value=profile.get("gender", ""),
            description="gender",
            whether_embedding=True,
        ),
        MemoryAttribute(
            name="education",
            type=str,
            default_or_value=profile.get("education", ""),
            description="education level",
            whether_embedding=True,
        ),
        MemoryAttribute(
            name="occupation",
            type=str,
            default_or_value=profile.get("occupation", ""),
            description="occupation",
            whether_embedding=True,
        ),
        MemoryAttribute(
            name="marriage_status",
            type=str,
            default_or_value=profile.get("marriage_status", ""),
            description="marital status",
            whether_embedding=True,
        ),
        MemoryAttribute(
            name="province",
            type=str,
            default_or_value=profile.get("province", ""),
            description="province",
            whether_embedding=True,
        ),
        MemoryAttribute(
            name="interested_topics",
            type=list,
            default_or_value=profile.get("interested_topics", []),
            description="topics the agent cares about",
            whether_embedding=True,
        ),
        MemoryAttribute(
            name="stance",
            type=str,
            default_or_value="neutral",
            description="stance on current policy debate",
            whether_embedding=True,
        ),
        MemoryAttribute(
            name="group_affiliation",
            type=str,
            default_or_value=profile.get("group_affiliation", ""),
            description="gang, faction, organisation, or community group this agent belongs to",
            whether_embedding=True,
        ),
        MemoryAttribute(
            name="voice_guide",
            type=str,
            default_or_value=profile.get("voice_guide", ""),
            description="concrete speech instructions for this persona's voice and vocabulary",
            whether_embedding=False,
        ),
        MemoryAttribute(
            name="actor_archetype",
            type=str,
            default_or_value=profile.get("actor_archetype", "civic_moderate"),
            description="where on the civic-to-extreme spectrum this actor sits",
            whether_embedding=True,
        ),
        MemoryAttribute(
            name="behavioral_tendencies",
            type=str,
            default_or_value=profile.get("behavioral_tendencies", ""),
            description="specific behavioral patterns this agent exhibits during simulation",
            whether_embedding=False,
        ),
        MemoryAttribute(
            name="survey_responses",
            type=list,
            default_or_value=[],
            description="responses to surveys",
            whether_embedding=False,
        ),
        # Dummy position so StreamMemory.add() doesn't raise on position lookup
        MemoryAttribute(
            name="position",
            type=dict,
            default_or_value=_DUMMY_POSITION,
            description="simulation position (stub)",
            whether_embedding=False,
        ),
    ]
    return MemoryConfig.from_list(attrs)


class OpinionCitizenAgent(CitizenAgentBase):
    """
    Policy-simulation citizen agent built on agentsociety's CitizenAgentBase.

    City gRPC methods are overridden as no-ops — we don't run a city simulator.
    Real KVMemory stores agent profile; real StreamMemory stores expressed opinions.
    do_interview() is inherited from CitizenAgentBase and searches both memories.
    """

    description = (
        "A South African citizen participating in a policy opinion simulation. "
        "Expresses, responds to, and reflects on policy-relevant opinions."
    )

    def __init__(
        self,
        agent_id: int,
        name: str,
        toolbox: Any,           # AgentToolbox (constructed via model_construct)
        memory: Memory,         # real agentsociety Memory
        block: Any,             # OpinionCaptureBlock
        # simulation control
        interested_topics: List[str],
        stance: str,
        activity_level: float,
        active_hours: List[int],
        group_affiliation: Optional[str] = None,
        actor_archetype: Optional[str] = None,
        behavioral_tendencies: Optional[str] = None,
        source_entity_uuid: Optional[str] = None,
    ):
        super().__init__(
            id=agent_id,
            name=name,
            toolbox=toolbox,
            memory=memory,
            blocks=[block],
        )
        self.interested_topics    = interested_topics
        self.stance               = stance
        self.activity_level       = activity_level
        self.active_hours         = active_hours
        self.group_affiliation    = group_affiliation
        self.actor_archetype      = actor_archetype       # used by dispatcher for action weighting
        self.behavioral_tendencies = behavioral_tendencies  # used in opinion/response prompts
        self.source_entity_uuid = source_entity_uuid
        self._block             = block

    # ------------------------------------------------------------------
    # Override city gRPC bindings — no city simulator running
    # ------------------------------------------------------------------

    async def _bind_to_simulator(self):
        """No-op: we have no city gRPC server."""
        pass

    async def _bind_to_economy(self):
        """No-op: we have no economy simulator."""
        pass

    async def before_forward(self):
        """No-op: skip update_motion() which requires the city simulator."""
        pass

    # ------------------------------------------------------------------
    # Agent behaviour
    # ------------------------------------------------------------------

    async def forward(self):
        """Delegate to OpinionCaptureBlock."""
        await self._block.forward_agent(self)

    async def reset(self):
        pass

    async def react_to_intervention(self, intervention_message: str):
        pass

    # ------------------------------------------------------------------
    # Character context helper (used by OpinionCaptureBlock for prompts)
    # ------------------------------------------------------------------

    async def character_context(self, detail: str = "full") -> str:
        """Build rich character description for LLM prompts from KVMemory."""
        persona               = await self.status.get("persona", "")
        age                   = await self.status.get("age", 0)
        gender                = await self.status.get("gender", "")
        occupation            = await self.status.get("occupation", "")
        education             = await self.status.get("education", "")
        marriage              = await self.status.get("marriage_status", "")
        province              = await self.status.get("province", "")
        bg_story              = await self.status.get("background_story", "")
        group_affiliation     = await self.status.get("group_affiliation", "")
        voice_guide           = await self.status.get("voice_guide", "")
        actor_archetype       = await self.status.get("actor_archetype", "")
        behavioral_tendencies = await self.status.get("behavioral_tendencies", "")

        lines = []

        # Identity anchors first — these override generic demographic framing
        identity_parts = []
        if group_affiliation:
            identity_parts.append(f"GROUP: {group_affiliation}")
        if actor_archetype:
            identity_parts.append(f"ARCHETYPE: {actor_archetype}")
        if identity_parts:
            lines.append(f"[{' | '.join(identity_parts)}]")

        lines.append(persona)

        attrs = []
        if age:        attrs.append(f"Age {age}")
        if gender:     attrs.append(gender.capitalize())
        if occupation: attrs.append(occupation)
        if education:  attrs.append(f"Education: {education}")
        if marriage:   attrs.append(marriage)
        if province:   attrs.append(f"Province: {province}")
        if self.stance and self.stance != "neutral":
            attrs.append(f"Stance: {self.stance}")
        if attrs:
            lines.append(" | ".join(attrs))

        if detail == "full":
            if bg_story:
                lines.append(f"\nBackground: {bg_story[:600]}")
            if voice_guide:
                lines.append(f"\nVOICE INSTRUCTIONS — follow exactly:\n{voice_guide}")
            if behavioral_tendencies:
                lines.append(f"\nBEHAVIORAL PATTERN — this shapes how you act:\n{behavioral_tendencies}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def agent_id(self) -> int:
        return self._id

    @property
    def name(self) -> str:
        return self._name
