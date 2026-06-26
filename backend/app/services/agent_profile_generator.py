"""
Agent profile data structure.

NOTE: LLM-based persona *generation* has been removed. Personas are never authored
by an LLM (curated library first, custom agents second — see CLAUDE.md). This module
now only defines `AgentProfile`, the profile shape consumed by OpinionAgent /
run_simulation_as.py and produced by the persona library and the custom-agent parser.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AgentProfile:
    """Profile data structure consumed by OpinionAgent (AgentSociety-compatible)."""
    id: int
    name: str
    persona: str
    background_story: str

    # AgentSociety core fields
    age: Optional[int] = None
    gender: Optional[str] = None
    education: Optional[str] = None
    occupation: Optional[str] = None
    marriage_status: Optional[str] = None

    # Extended attributes
    mbti: Optional[str] = None
    country: Optional[str] = None
    province: Optional[str] = None
    interested_topics: List[str] = field(default_factory=list)

    # Group identity — injected into every simulation prompt as a first-class signal.
    # Works for ANY group: gang, political movement, church, taxi association, etc.
    # e.g. "Gang member, Township, City"
    group_affiliation: Optional[str] = None
    # How this persona speaks — injected verbatim into LLM prompts.
    # Covers vocabulary, attitude, what they reference, what they would never say.
    voice_guide: Optional[str] = None
    # Where on the spectrum from civic to extreme this actor sits.
    # e.g. "civic_moderate", "political_activist", "opportunist_looter",
    #       "conspiracy_spreader", "mob_follower", "institutional_loyalist",
    #       "violent_agitator", "criminal_opportunist", "community_protector"
    actor_archetype: Optional[str] = None
    # Specific behavioral tendencies relevant to simulation actions.
    # e.g. "Joins crowd actions when momentum builds. Spreads unverified information
    #       as fact. Takes material advantage during disorder. Defers to dominant voice."
    behavioral_tendencies: Optional[str] = None

    # Institutional / collective agent flag
    # True for organizations, government agencies, political parties, media outlets, gangs,
    # unions, NGOs — any entity that speaks as a collective/institutional voice rather than
    # an individual person. These agents use "we/our mandate" not "I/my opinion".
    is_institutional: bool = False

    # Core focus flag — when True, agent is guaranteed to participate every round
    # and receives higher influence weight (1.5x) in the simulation. Use for protagonist
    # or priority agents that should always be part of the narrative.
    is_core_focus: bool = False

    # Initial stance in the simulation: support / neutral / concerned / oppose / resist.
    # When absent, the simulation config generator or runtime defaults to neutral.
    stance: Optional[str] = None

    # === AgentSociety Psychological Architecture ===
    # Emotions (0-10 scale for each)
    emotions: Optional[Dict[str, float]] = None
    emotion_keyword: Optional[str] = None
    emotion_thought: Optional[str] = None

    # Needs (Maslow's hierarchy)
    needs: Optional[List[Dict]] = None

    # Cognition (attitudes toward topics)
    attitudes: Optional[List[Dict]] = None
    beliefs: Optional[List[str]] = None

    # Source entity tracing
    source_entity_uuid: Optional[str] = None
    source_entity_type: Optional[str] = None

    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))

    def to_agentsociety_format(self) -> Dict[str, Any]:
        """Serialise to the format read by run_simulation_as.py / OpinionAgent."""
        profile: Dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "persona": self.persona,
            "background_story": self.background_story,
            "age": self.age,
            "gender": self.gender,
            "education": self.education,
            "occupation": self.occupation,
            "marriage_status": self.marriage_status,
            "province": self.province,
            "interested_topics": self.interested_topics or [],
            "group_affiliation": self.group_affiliation,
            "voice_guide": self.voice_guide,
            "actor_archetype": self.actor_archetype,
            "behavioral_tendencies": self.behavioral_tendencies,
            "is_institutional": self.is_institutional,
            "is_core_focus": self.is_core_focus,
            "stance": self.stance,
            "source_entity_uuid": self.source_entity_uuid,
            "source_entity_type": self.source_entity_type,
            "created_at": self.created_at,
        }
        # Psychological state (used by OpinionCitizenAgent._init_psychological_state)
        if self.emotions:
            profile["emotion"] = self.emotions
        if self.needs:
            profile["needs"] = self.needs
        if self.attitudes:
            profile["attitudes"] = self.attitudes
        if self.beliefs:
            profile["beliefs"] = self.beliefs
        return profile

    def to_dict(self) -> Dict[str, Any]:
        """Full dict (useful for debugging / logging)."""
        d = {
            "id": self.id,
            "name": self.name,
            "persona": self.persona,
            "background_story": self.background_story,
            "age": self.age,
            "gender": self.gender,
            "education": self.education,
            "occupation": self.occupation,
            "marriage_status": self.marriage_status,
            "mbti": self.mbti,
            "country": self.country,
            "province": self.province,
            "interested_topics": self.interested_topics,
            "group_affiliation": self.group_affiliation,
            "voice_guide": self.voice_guide,
            "actor_archetype": self.actor_archetype,
            "behavioral_tendencies": self.behavioral_tendencies,
            "is_institutional": self.is_institutional,
            "is_core_focus": self.is_core_focus,
            "stance": self.stance,
            "emotions": self.emotions,
            "emotion_keyword": self.emotion_keyword,
            "emotion_thought": self.emotion_thought,
            "needs": self.needs,
            "attitudes": self.attitudes,
            "beliefs": self.beliefs,
            "source_entity_uuid": self.source_entity_uuid,
            "source_entity_type": self.source_entity_type,
            "created_at": self.created_at,
        }
        return {k: v for k, v in d.items() if v is not None}
