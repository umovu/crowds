"""
OpinionCitizenAgent — agentsociety2 PersonAgent for policy wind tunnel simulation.

Extends PersonAgent with policy stress-testing specific functionality:
- Radicalism spectrum (1-5) with stance tracking
- Actor archetypes with voice anchors
- SA policy context
- Interview mode: policy makers can engage agents and test persuasion
- Post history tracking for narrative analysis
- Propagation support: stance changes cascade to affiliated agents

Framework integration points:
- Overrides _build_external_question_context() to inject simulation state
- Uses answer_external_question() for policy-maker interviews (not ask())
- Stores interview_memory and posts_history in skill_state
- Implements stance_change detection and apply_intervention()
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from agentsociety2 import PersonAgent

from .document_context_engine import sanitize_language_drift
from ..utils.logger import get_logger

logger = get_logger("fub.opinion_agent")


class OpinionCitizenAgent(PersonAgent):
    """Policy wind tunnel stakeholder agent using agentsociety2 PersonAgent.

    Design: This agent represents a stakeholder archetype in a policy simulation.
    It expresses opinions in a simulated social media feed, and can be interviewed
    by a policy maker to test persuasion strategies.

    agentsociety2 integration:
    - _build_external_question_context() injects simulation-specific state
    - answer_external_question() handles policy-maker interviews
    - set_skill_state("interview_memory", ...) persists conversation history
    - dump()/load() support simulation forking and state serialization
    """

    description = (
        "A South African stakeholder participating in a policy wind tunnel simulation. "
        "Expresses opinions, reacts to policy events, and can be interviewed by policy makers."
    )

    # Stance taxonomy for policy wind tunnel
    STANCE_SUPPORT = "support"
    STANCE_NEUTRAL = "neutral"
    STANCE_CONCERNED = "concerned"
    STANCE_OPPOSE = "oppose"
    STANCE_RESIST = "resist"
    VALID_STANCES = [STANCE_SUPPORT, STANCE_NEUTRAL, STANCE_CONCERNED, STANCE_OPPOSE, STANCE_RESIST]

    # Product mode reuses the same 5-point stance machinery but relabels it as a
    # reaction/willingness ladder — NOT a buy/no-buy verdict (product honesty rule).
    PRODUCT_STANCE_LABELS = {
        STANCE_SUPPORT: "Won over",
        STANCE_NEUTRAL: "Curious",
        STANCE_CONCERNED: "Unconvinced",
        STANCE_OPPOSE: "Resistant",
        STANCE_RESIST: "Hostile",
    }

    @classmethod
    def stance_label(cls, stance: Optional[str], mode: str = "policy") -> Optional[str]:
        """Human-readable label for a stance. In product mode, map to the
        reaction ladder; in policy mode, return the raw stance unchanged."""
        if stance is None:
            return None
        if mode == "product":
            return cls.PRODUCT_STANCE_LABELS.get(stance, stance)
        return stance

    def __init__(
        self,
        id: int,
        profile: Dict[str, Any],
        name: Optional[str] = None,
        init_state: Optional[Dict[str, Any]] = None,
        capability_kwargs: Optional[Dict[str, Any]] = None,
        # simulation control fields (stored in skill_state)
        interested_topics: Optional[List[str]] = None,
        stance: Optional[str] = None,
        activity_level: float = 0.5,
        active_hours: Optional[List[int]] = None,
        group_affiliation: Optional[str] = None,
        actor_archetype: Optional[str] = None,
        behavioral_tendencies: Optional[str] = None,
        source_entity_uuid: Optional[str] = None,
        base_radicalism: int = 1,
        activation_triggers: Optional[List[str]] = None,
        is_institutional: bool = False,
    ):
        # Build profile for PersonAgent
        agent_profile = {
            "id": id,
            "name": name or profile.get("name", f"Citizen_{id}"),
            **profile,
        }

        # Initialize skill state with simulation fields
        skill_state = init_state or {}
        skill_state.update({
            "interested_topics": interested_topics or [],
            "stance": self._normalize_stance(stance),
            "previous_stance": None,
            "activity_level": activity_level,
            "active_hours": active_hours or list(range(24)),
            "group_affiliation": group_affiliation,
            "actor_archetype": actor_archetype,
            "behavioral_tendencies": behavioral_tendencies,
            "source_entity_uuid": source_entity_uuid,
            "base_radicalism": max(1, min(5, base_radicalism)),
            "current_radicalism": max(1, min(5, base_radicalism)),
            "activation_triggers": activation_triggers or [],
            "is_institutional": is_institutional,
            "posts_history": [],
            "interview_memory": [],
            "interview_count": 0,
            "mobilization_level": 0,  # 0=none, 1=discussing, 2=organizing, 3=acting
            "last_post_round": -1,
        })

        # Carry occupation/background so downstream (budget tier, grant detection)
        # can read them from init_state without re-opening the profile.
        skill_state.setdefault("occupation", profile.get("occupation"))
        skill_state.setdefault("background_story", profile.get("background_story"))

        # Grant beneficiary detection — deterministic, from existing signals only.
        # SASSA amounts are published policy → a real KNOWN income for this cohort.
        try:
            from .income_seeder import detect_grant, GRANT_PROVENANCE
            # needs is populated later (_init_psychological_state); read from the
            # raw profile here. Tolerate dict {safety_economic: n} or list of
            # {need_type, intensity} objects.
            _se = None
            _raw_needs = profile.get("needs")
            if isinstance(_raw_needs, dict):
                _se = _raw_needs.get("safety_economic")
            elif isinstance(_raw_needs, list):
                for _n in _raw_needs:
                    if isinstance(_n, dict) and _n.get("need_type") == "safety_economic":
                        # intensity may be 0–1 or 0–100; normalise high-precision to 0–100
                        _iv = _n.get("intensity")
                        if isinstance(_iv, (int, float)):
                            _se = int(_iv * 100) if _iv <= 1 else int(_iv)
                        break
            _is_grant, _gtype, _gamount = detect_grant(
                actor_archetype=actor_archetype,
                occupation=profile.get("occupation"),
                background_story=profile.get("background_story"),
                safety_economic=_se,
            )
            skill_state["is_grant_dependent"] = _is_grant
            skill_state["grant_type"] = _gtype
            if _is_grant and _gamount is not None:
                skill_state["monthly_income_rand"] = _gamount
                skill_state["income_provenance"] = GRANT_PROVENANCE
        except Exception as e:
            logger.debug(f"Grant detection skipped for agent {id}: {e}")
            skill_state.setdefault("is_grant_dependent", False)
            skill_state.setdefault("grant_type", None)

        super().__init__(
            id=id,
            profile=agent_profile,
            name=name,
            init_state=skill_state,
            capability_kwargs=capability_kwargs,
        )

        # Store init_state locally since PersonAgent doesn't expose it
        self.init_state = skill_state

        # Initialize psychological state from profile (if present)
        self._init_psychological_state(profile)

        # Store reference for archetype anchors
        self._actor_archetype = actor_archetype

    # ------------------------------------------------------------------
    # Psychological state: emotion, needs, attitudes (AgentSociety-inspired)
    # ------------------------------------------------------------------

    EMOTION_KEYS = ["sadness", "joy", "fear", "disgust", "anger", "surprise"]
    NEEDS_KEYS = [
        "physiological_hunger", "physiological_tired",
        "safety_physical", "safety_economic",
        "belonging", "affection", "respect", "status",
        "achievement", "personal_growth", "purpose",
    ]

    def _init_psychological_state(self, profile: Dict[str, Any]) -> None:
        """Read emotion/needs/attitudes from profile into live skill_state."""
        # Emotion: 6 core emotions rated 0-10
        emotion = profile.get("emotion", {})
        if not isinstance(emotion, dict):
            emotion = {}
        self.init_state["emotion"] = {
            k: max(0, min(10, int(emotion.get(k, 0))))
            for k in self.EMOTION_KEYS
        }

        # Needs: Maslow hierarchy rated 0-100
        needs = profile.get("needs", {})
        if not isinstance(needs, dict):
            needs = {}
        self.init_state["needs"] = {
            k: max(0, min(100, int(needs.get(k, 50))))
            for k in self.NEEDS_KEYS
        }

        # Attitudes: topic ratings 0-10
        attitudes = profile.get("attitudes", {})
        if not isinstance(attitudes, dict):
            attitudes = {}
        self.init_state["attitudes"] = dict(attitudes)

        # Persist
        self.set_skill_state("emotion", self.init_state["emotion"])
        self.set_skill_state("needs", self.init_state["needs"])
        self.set_skill_state("attitudes", self.init_state["attitudes"])

    def update_emotion_from_post(self, content: str) -> None:
        """Simple keyword-based heuristic to adjust emotion after a post."""
        text = content.lower()
        delta = {k: 0 for k in self.EMOTION_KEYS}

        fear_keywords = ["scared", "terrified", "afraid", "fear", "terror", "panic", "worried", "anxious"]
        anger_keywords = ["angry", "furious", "rage", "outraged", "mad", "livid", "resent", "hate"]
        sadness_keywords = ["sad", "depressed", "grief", "sorrow", "heartbroken", "devastated", "hopeless"]
        joy_keywords = ["happy", "joyful", "excited", "relieved", "glad", "celebrate", "proud", "hopeful"]
        disgust_keywords = ["disgusted", "sick", "appalled", "revolted", "ashamed", "dismayed"]
        surprise_keywords = ["shocked", "surprised", "stunned", "amazed", "unexpected", "unbelievable"]

        for kw in fear_keywords:
            if kw in text:
                delta["fear"] += 1
        for kw in anger_keywords:
            if kw in text:
                delta["anger"] += 1
        for kw in sadness_keywords:
            if kw in text:
                delta["sadness"] += 1
        for kw in joy_keywords:
            if kw in text:
                delta["joy"] += 1
        for kw in disgust_keywords:
            if kw in text:
                delta["disgust"] += 1
        for kw in surprise_keywords:
            if kw in text:
                delta["surprise"] += 1

        emotion = self.init_state.get("emotion", {})
        for k in self.EMOTION_KEYS:
            emotion[k] = max(0, min(10, emotion.get(k, 0) + delta[k]))
        self.init_state["emotion"] = emotion
        self.set_skill_state("emotion", emotion)

    def _get_dominant_emotion(self) -> Tuple[str, int]:
        """Return (emotion_key, score) for the highest emotion."""
        emotion = self.init_state.get("emotion", {})
        if not emotion:
            return ("neutral", 0)
        return max(emotion.items(), key=lambda x: x[1])

    # ------------------------------------------------------------------
    # Stance helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_stance(stance: Optional[str]) -> str:
        """Normalize stance to valid taxonomy."""
        if not stance:
            return OpinionCitizenAgent.STANCE_NEUTRAL
        s = stance.lower().strip()
        if s in OpinionCitizenAgent.VALID_STANCES:
            return s
        # Map synonyms
        if s in ("for", "in favor", "approve", "endorse"):
            return OpinionCitizenAgent.STANCE_SUPPORT
        if s in ("against", "reject", "fight", "combat"):
            return OpinionCitizenAgent.STANCE_OPPOSE
        if s in ("worried", "alarm", "uneasy", "apprehensive"):
            return OpinionCitizenAgent.STANCE_CONCERNED
        if s in ("block", "stop", "defy", "disobey"):
            return OpinionCitizenAgent.STANCE_RESIST
        return OpinionCitizenAgent.STANCE_NEUTRAL

    # ------------------------------------------------------------------
    # agentsociety2: External question context override
    # ------------------------------------------------------------------

    def _build_external_question_context(self, t: datetime) -> dict[str, Any]:
        """Override to inject policy simulation state into interview context.

        agentsociety2's answer_external_question() calls this to build the
        "Internal agent context" JSON that the LLM sees during interviews.
        We add: stance, radicalism, posts history, interview memory, and
        mobilization level so the agent responds consistently with its
        simulation trajectory.
        """
        # Get base context from AgentBase (profile, skill_states, etc.).
        # During pause-and-intervene, the agent's skill-runtime workspace is not
        # initialized, and the parent implementation probes it via
        # workspace_exists() → raises "Agent workspace is not initialized".
        # That filesystem probe is irrelevant to interviews/interventions, so
        # fall back to a minimal context (profile + skill_state) when it fails.
        try:
            context = super()._build_external_question_context(t)
        except RuntimeError as e:
            if "workspace is not initialized" not in str(e):
                raise
            context = {
                "profile": self.get_profile(),
                "skill_state": dict(self.init_state),
            }

        # Inject simulation-specific state
        dom_emotion, dom_score = self._get_dominant_emotion()
        sim_state = {
            "current_stance": self.init_state.get("stance", "neutral"),
            "previous_stance": self.init_state.get("previous_stance"),
            "base_radicalism": self.init_state.get("base_radicalism", 1),
            "current_radicalism": self.init_state.get("current_radicalism", 1),
            "mobilization_level": self.init_state.get("mobilization_level", 0),
            "group_affiliation": self.init_state.get("group_affiliation"),
            "actor_archetype": self.init_state.get("actor_archetype"),
            "is_institutional": self.init_state.get("is_institutional", False),
            "interview_count": self.init_state.get("interview_count", 0),
            "recent_posts": self._get_recent_posts(limit=5),
            "recent_interviews": self._get_recent_interviews(limit=3),
            # Psychological state (AgentSociety-inspired)
            "emotion": self.init_state.get("emotion", {}),
            "dominant_emotion": dom_emotion,
            "dominant_emotion_score": dom_score,
            "needs": self.init_state.get("needs", {}),
            "attitudes": self.init_state.get("attitudes", {}),
        }

        context["simulation_state"] = sim_state
        return context

    # ------------------------------------------------------------------
    # Post history tracking
    # ------------------------------------------------------------------

    def record_post(self, round_num: int, post_type: str, content: str, impact_score: float = 0.0):
        """Record a post emitted by this agent during simulation.

        Called by opinion_block.py after an agent generates a post.
        Persists in skill_state so interview context includes post history.
        Updates emotion heuristically based on post content.
        """
        # Update emotional state from post content
        self.update_emotion_from_post(content)
        dom_emotion, dom_score = self._get_dominant_emotion()

        posts = self.init_state.get("posts_history", [])
        posts.append({
            "round": round_num,
            "type": post_type,
            "content": content[:500],  # Truncate for memory
            "impact_score": impact_score,
            "timestamp": datetime.now().isoformat(),
            # Emotional tags for causal memory
            "dominant_emotion": dom_emotion,
            "dominant_emotion_score": dom_score,
            "stance_at_post": self.init_state.get("stance", "neutral"),
        })
        # Keep last 20 posts
        self.init_state["posts_history"] = posts[-20:]
        self.init_state["last_post_round"] = round_num
        self.set_skill_state("posts_history", self.init_state["posts_history"])

    def _get_recent_posts(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent posts for interview context."""
        posts = self.init_state.get("posts_history", [])
        return posts[-limit:] if posts else []

    # ------------------------------------------------------------------
    # Interview memory tracking
    # ------------------------------------------------------------------

    def _get_recent_interviews(self, limit: int = 3) -> List[Dict[str, Any]]:
        """Get recent interviews for context."""
        interviews = self.init_state.get("interview_memory", [])
        return interviews[-limit:] if interviews else []

    def _record_interview(self, question: str, response: str, stance_before: str, stance_after: str):
        """Record an interview in memory with emotional context."""
        dom_emotion, dom_score = self._get_dominant_emotion()
        interviews = self.init_state.get("interview_memory", [])
        interviews.append({
            "question": question[:300],
            "response": response[:500],
            "stance_before": stance_before,
            "stance_after": stance_after,
            "timestamp": datetime.now().isoformat(),
            # Emotional + causal tags
            "dominant_emotion": dom_emotion,
            "dominant_emotion_score": dom_score,
            "stance_delta": self._stance_delta_value(stance_before, stance_after),
        })
        # Keep last 10 interviews
        self.init_state["interview_memory"] = interviews[-10:]
        self.init_state["interview_count"] = self.init_state.get("interview_count", 0) + 1
        self.set_skill_state("interview_memory", self.init_state["interview_memory"])
        self.set_skill_state("interview_count", self.init_state["interview_count"])

    def _stance_delta_value(self, before: str, after: str) -> int:
        """Numeric stance change: positive = moved toward support."""
        order = [self.STANCE_RESIST, self.STANCE_OPPOSE, self.STANCE_CONCERNED,
                 self.STANCE_NEUTRAL, self.STANCE_SUPPORT]
        try:
            return order.index(after) - order.index(before)
        except ValueError:
            return 0

    # ------------------------------------------------------------------
    # Character context helper (used by opinion prompts and interviews)
    # ------------------------------------------------------------------

    async def character_context(self, detail: str = "full") -> str:
        """Build character description from profile."""
        profile = self.get_profile()

        persona = profile.get("persona", "")
        age = profile.get("age", 0)
        gender = profile.get("gender", "")
        occupation = profile.get("occupation", "")
        education = profile.get("education", "")
        marriage = profile.get("marriage_status", "")
        province = profile.get("province", "")
        bg_story = profile.get("background_story", "")
        group_affiliation = self.init_state.get("group_affiliation", "")
        voice_guide = profile.get("voice_guide", "")
        actor_archetype = self.init_state.get("actor_archetype", "")
        behavioral_tendencies = self.init_state.get("behavioral_tendencies", "")
        stance = self.init_state.get("stance", "neutral")
        current_radicalism = self.init_state.get("current_radicalism", 1)
        is_institutional = self.init_state.get("is_institutional", False)

        lines = []

        identity_parts = []
        if group_affiliation:
            identity_parts.append(f"GROUP: {group_affiliation}")
        if actor_archetype:
            identity_parts.append(f"ARCHETYPE: {actor_archetype}")
        if identity_parts:
            lines.append(f"[{' | '.join(identity_parts)}]")

        lines.append(persona)

        attrs = []
        if age:
            attrs.append(f"Age {age}")
        if gender:
            attrs.append(gender.capitalize())
        if occupation:
            attrs.append(occupation)
        if education:
            attrs.append(f"Education: {education}")
        if marriage:
            attrs.append(marriage)
        if province:
            attrs.append(f"Province: {province}")
        if stance and stance != "neutral":
            attrs.append(f"Stance: {stance}")
        if current_radicalism != self.init_state.get("base_radicalism", 1):
            attrs.append(f"Radicalism: {current_radicalism}/5 (activated)")
        else:
            attrs.append(f"Radicalism: {current_radicalism}/5")
        if attrs:
            lines.append(" | ".join(attrs))

        if detail == "full":
            if bg_story:
                lines.append(f"\nBackground: {bg_story[:600]}")
            if voice_guide:
                lines.append(f"\nVOICE INSTRUCTIONS — follow exactly:\n{voice_guide}")
            if behavioral_tendencies:
                lines.append(f"\nBEHAVIORAL PATTERN — this shapes how you act:\n{behavioral_tendencies}")
            if is_institutional:
                lines.append("\n[INSTITUTIONAL AGENT: Speak as 'we/our organization', not as an individual.]")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def agent_id(self) -> int:
        return self.id

    @property
    def interested_topics(self) -> List[str]:
        return self.init_state.get("interested_topics", [])

    @property
    def stance(self) -> str:
        return self.init_state.get("stance", "neutral")

    @property
    def activity_level(self) -> float:
        return self.init_state.get("activity_level", 0.5)

    @property
    def active_hours(self) -> List[int]:
        return self.init_state.get("active_hours", list(range(24)))

    @property
    def group_affiliation(self) -> Optional[str]:
        return self.init_state.get("group_affiliation")

    @property
    def actor_archetype(self) -> Optional[str]:
        return self.init_state.get("actor_archetype")

    @property
    def base_radicalism(self) -> int:
        return self.init_state.get("base_radicalism", 1)

    @property
    def current_radicalism(self) -> int:
        return self.init_state.get("current_radicalism", 1)

    @property
    def activation_triggers(self) -> List[str]:
        return self.init_state.get("activation_triggers", [])

    @property
    def is_institutional(self) -> bool:
        return self.init_state.get("is_institutional", False)

    @property
    def mobilization_level(self) -> int:
        return self.init_state.get("mobilization_level", 0)

    @property
    def interview_count(self) -> int:
        return self.init_state.get("interview_count", 0)

    # ------------------------------------------------------------------
    # Radicalism spectrum
    # ------------------------------------------------------------------

    def calculate_activated_radicalism(self, query_context: Optional[dict] = None) -> int:
        """Calculate activated radicalism level based on query context."""
        base = self.base_radicalism

        if not query_context or not self.activation_triggers:
            return base

        activation_boost = 0
        query_entities = query_context.get("entities", [])
        query_topics = query_context.get("topics", [])

        for entity in query_entities:
            entity_name = entity.get("name", "").lower()
            entity_type = entity.get("type", "").lower()

            for trigger in self.activation_triggers:
                trigger_lower = trigger.lower()
                if trigger_lower in entity_name or trigger_lower in entity_type:
                    activation_boost += 1
                    break

        for topic in query_topics:
            topic_lower = topic.lower()
            for trigger in self.activation_triggers:
                if trigger.lower() in topic_lower:
                    activation_boost += 0.5
                    break

        activated = min(base + int(activation_boost), 5)
        self.init_state["current_radicalism"] = activated
        self.set_skill_state("current_radicalism", activated)
        return activated

    def get_radicalism_tone(self, radicalism_level: int) -> dict:
        """Get tone mapping for radicalism level."""
        tone_map = {
            1: {
                "tone": "I understand the concerns, but peaceful channels exist for change.",
                "action": "vote",
                "urgency": "low",
                "description": "Passive - expresses opinion without advocating action"
            },
            2: {
                "tone": "I agree with the frustration. We need change, but it must be done right.",
                "action": "discuss",
                "urgency": "moderate",
                "description": "Sympathetic - supports cause but prefers peaceful approaches"
            },
            3: {
                "tone": "If called to protest, I'd be there. The system must hear us.",
                "action": "protest",
                "urgency": "high",
                "description": "Active supporter - willing to participate in peaceful protest"
            },
            4: {
                "tone": "We're organizing. People are ready. This is bigger than any one leader.",
                "action": "mobilize",
                "urgency": "very_high",
                "description": "Mobilizer - actively organizes and encourages others"
            },
            5: {
                "tone": "They can jail him. The revolution doesn't stop with one person. We'll resist with everything we have.",
                "action": "escalate",
                "urgency": "critical",
                "description": "Revolutionary - believes in radical change, willing to push boundaries"
            },
        }
        return tone_map.get(radicalism_level, tone_map[1])

    # ------------------------------------------------------------------
    # Interview mode: policy maker engagement
    # ------------------------------------------------------------------

    async def do_interview(
        self,
        question: str,
        t: Optional[datetime] = None,
        response_type: str = "text",
    ) -> Dict[str, Any]:
        """Policy-maker interview using agentsociety2's answer_external_question().

        This is the correct API for external interviews (not ask()).
        It builds context via _build_external_question_context() which we've
        overridden to include simulation state, then calls the LLM directly.

        Args:
            question: The policy maker's question.
            t: Current simulation time (defaults to now).
            response_type: "text", "choice", or "json".

        Returns:
            Dict with "response", "stance_before", "stance_after", "stance_changed".
        """
        if t is None:
            t = datetime.now()

        stance_before = self.init_state.get("stance", "neutral")

        # Use agentsociety2's built-in interview method
        # This injects _build_external_question_context() automatically
        try:
            response = await self.answer_external_question(
                prompt=question,
                t=t,
                response_type=response_type,
            )
            response = sanitize_language_drift(response, label=f"interview_{self.id}")
        except Exception as e:
            logger.error(f"Interview failed for agent {self.id}: {e}")
            return {
                "response": "I have no comment on that.",
                "stance_before": stance_before,
                "stance_after": stance_before,
                "stance_changed": False,
                "error": str(e),
            }

        # Detect stance change from response (heuristic)
        stance_after = self._detect_stance_from_response(response, stance_before)

        # Record the interview
        self._record_interview(question, response, stance_before, stance_after)

        # Update state if stance changed
        if stance_after != stance_before:
            self.init_state["previous_stance"] = stance_before
            self.init_state["stance"] = stance_after
            self.set_skill_state("stance", stance_after)
            self.set_skill_state("previous_stance", stance_before)

        return {
            "response": response,
            "stance_before": stance_before,
            "stance_after": stance_after,
            "stance_changed": stance_after != stance_before,
        }

    async def do_impact_interview(
        self,
        reframed_question: str,
        original_question: str = "",
        t: Optional[datetime] = None,
        response_type: str = "text",
    ) -> Dict[str, Any]:
        """Impact-extraction interview with structured metadata output.

        Uses a pre-reframed question tailored to this agent's persona.
        Returns natural language response + impact metadata for aggregation.

        Args:
            reframed_question: The persona-specific question (from PromptReframer).
            original_question: The user's raw question (for reference).
            t: Simulation time.
            response_type: "text" or "json".

        Returns:
            Dict with "response", "internal_state", "impact_metadata", etc.
        """
        if t is None:
            t = datetime.now()

        stance_before = self.init_state.get("stance", "neutral")
        dom_emotion_before, dom_score_before = self._get_dominant_emotion()

        try:
            response = await self.answer_external_question(
                prompt=reframed_question,
                t=t,
                response_type=response_type,
            )
            response = sanitize_language_drift(response, label=f"impact_interview_{self.id}")
        except Exception as e:
            logger.error(f"Impact interview failed for agent {self.id}: {e}")
            return {
                "response": "I have no comment on that.",
                "stance_before": stance_before,
                "stance_after": stance_before,
                "stance_changed": False,
                "internal_state": {},
                "impact_metadata": {"error": str(e)},
                "reframed_question": reframed_question,
                "original_question": original_question,
            }

        stance_after = self._detect_stance_from_response(response, stance_before)
        self._record_interview(reframed_question, response, stance_before, stance_after)

        if stance_after != stance_before:
            self.init_state["previous_stance"] = stance_before
            self.init_state["stance"] = stance_after
            self.set_skill_state("stance", stance_after)
            self.set_skill_state("previous_stance", stance_before)

        dom_emotion_after, dom_score_after = self._get_dominant_emotion()

        # Lightweight heuristic: extract mentioned entities/people from response
        mentioned_entities = self._extract_mentioned_entities(response)

        impact_metadata = {
            "granularity": self._detect_impact_granularity(response),
            "affected_entity": mentioned_entities[0] if mentioned_entities else None,
            "emotional_tone": dom_emotion_after,
            "emotional_intensity": dom_score_after,
            "emotional_shift": dom_score_after - dom_score_before,
            "stance_stability": "stable" if stance_after == stance_before else "shifted",
            "predicted_action": self._extract_predicted_action(response),
            "reasoning_anchors": mentioned_entities,
        }

        internal_state = {
            "dominant_emotion": dom_emotion_after,
            "dominant_emotion_score": dom_score_after,
            "emotion": dict(self.init_state.get("emotion", {})),
            "needs": dict(self.init_state.get("needs", {})),
            "attitudes": dict(self.init_state.get("attitudes", {})),
            "stance": stance_after,
            "current_radicalism": self.init_state.get("current_radicalism", 1),
            "mobilization_level": self.init_state.get("mobilization_level", 0),
        }

        return {
            "response": response,
            "stance_before": stance_before,
            "stance_after": stance_after,
            "stance_changed": stance_after != stance_before,
            "internal_state": internal_state,
            "impact_metadata": impact_metadata,
            "reframed_question": reframed_question,
            "original_question": original_question,
        }

    def _detect_impact_granularity(self, response: str) -> str:
        """Heuristic: micro (personal), meso (community), or macro (systemic)."""
        text = response.lower()
        micro_markers = ["i ", "my ", "myself", "my family", "my son", "my daughter", "my child", "my home", "my street"]
        macro_markers = ["the government", "the state", "society", "the economy", "the country", "national", "policy"]
        micro_score = sum(1 for m in micro_markers if m in text)
        macro_score = sum(1 for m in macro_markers if m in text)
        if micro_score > macro_score:
            return "micro"
        elif macro_score > micro_score:
            return "macro"
        return "meso"

    def _extract_mentioned_entities(self, response: str) -> List[str]:
        """Simple heuristic: extract capitalized proper nouns and quoted names."""
        import re
        # Quoted names: "Deon" or 'Deon'
        quoted = re.findall(r'["\']([A-Z][a-z]+)["\']', response)
        # Capitalized words that look like names (not sentence-start)
        caps = re.findall(r'\b[A-Z][a-z]{2,}\b', response)
        # Deduplicate and filter common false positives
        skip = {"The", "This", "That", "These", "Those", "What", "When", "Where", "Why", "How",
                "But", "And", "Or", "If", "Then", "Than", "So", "Because", "Although"}
        entities = []
        for e in quoted + caps:
            if e not in skip and e not in entities:
                entities.append(e)
        return entities[:5]

    def _extract_predicted_action(self, response: str) -> Optional[str]:
        """Heuristic: look for future-tense action statements."""
        text = response.lower()
        action_markers = ["i will", "i'll", "i am going to", "i'm going to", "i plan to", "i intend to", "we will", "we'll"]
        for marker in action_markers:
            idx = text.find(marker)
            if idx != -1:
                # Extract the clause
                start = idx
                end = text.find(".", start)
                if end == -1:
                    end = text.find(",", start)
                if end == -1:
                    end = len(text)
                return response[start:end].strip()
        return None

    async def do_structured_interview(
        self,
        question_type: str,
        policy_context: str,
        t: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Structured interview with predefined question types.

        Args:
            question_type: One of:
                - "biggest_concern": What is your biggest concern about this policy?
                - "what_would_change": What would change your position?
                - "willing_to_negotiate": Are you willing to negotiate?
                - "mobilization_intent": Are you planning to take action?
                - "message_to_government": What message do you have for government?
            policy_context: Description of the policy being discussed.
            t: Simulation time.

        Returns:
            Interview result dict.
        """
        question_templates = {
            "biggest_concern": (
                f"Policy or question: {policy_context}\n\n"
                "As a South African with direct experience of your situation, "
                "what is your BIGGEST concern about how this policy or question affects you, your family, or your community? "
                "Be concrete and specific about the direct impacts."
            ),
            "what_would_change": (
                f"Policy or question: {policy_context}\n\n"
                "As someone living in South Africa with firsthand experience of these issues, "
                "what ONE specific change would make you shift your position on THIS policy or question? "
                "Ground your answer in your lived experience."
            ),
            "willing_to_negotiate": (
                f"Policy or question: {policy_context}\n\n"
                "As a South African directly affected by this policy or question, "
                "are you willing to negotiate on THIS policy or question? State your specific conditions based on your reality."
            ),
            "mobilization_intent": (
                f"Policy or question: {policy_context}\n\n"
                "As someone representing or speaking for your community in South Africa, "
                "are you or your community planning any action regarding THIS policy or question specifically? "
                "What exactly would you and your community do?"
            ),
            "message_to_government": (
                f"Policy or question: {policy_context}\n\n"
                "As a South African directly impacted by this policy or question, "
                "what direct message do you have for the policy makers about THIS policy or question? "
                "Be specific about what you or your community needs."
            ),
        }

        question = question_templates.get(
            question_type,
            f"Regarding this policy: {policy_context}\n\n{question_type}"
        )

        return await self.do_interview(question, t=t)

    def _detect_stance_from_response(self, response: str, default_stance: str) -> str:
        """Heuristic stance detection from interview response.

        Looks for keywords indicating shift toward support or opposition.
        This is a lightweight heuristic; full NLP could replace it later.
        """
        text = response.lower()

        # Strong support signals
        support_signals = [
            "i support", "we support", "i accept", "we accept",
            "this is good", "this will help", "fair enough",
            "i'm satisfied", "we're satisfied", "this works",
            "i agree with", "we agree with", "reasonable compromise",
            "significant step", "step in the right direction", "welcome move",
            "addressing our concerns", "addresses our concerns", "directly addresses",
            "cautiously optimistic", "optimistic", "positive development",
            "we welcome", "i welcome", "this shows", "willing to engage",
            "open to", "consider supporting", "reconsider our position",
        ]
        # Strong oppose/resist signals
        oppose_signals = [
            "i oppose", "we oppose", "i reject", "we reject",
            "this is unacceptable", "we will not accept", "absolutely not",
            "we will resist", "we will fight", "no compromise",
            "strike", "shutdown", "boycott", "march", "protest",
            "not enough", "insufficient", "inadequate", "falls short",
            "we remain opposed", "our position has not changed",
        ]
        # Concern signals (moderate opposition)
        concern_signals = [
            "i'm concerned", "we're concerned", "worried about",
            "this will hurt", "negative impact", "not enough",
            "needs more work", "insufficient", "inadequate",
            "cautious", "skeptical", "wait and see", "monitor",
            "doesn't go far enough", "more needs to be done",
        ]

        support_score = sum(1 for s in support_signals if s in text)
        oppose_score = sum(1 for s in oppose_signals if s in text)
        concern_score = sum(1 for s in concern_signals if s in text)

        # If scores are low, maintain current stance
        if support_score == 0 and oppose_score == 0 and concern_score == 0:
            return default_stance

        # Determine new stance based on dominant signal
        if oppose_score > support_score and oppose_score > concern_score:
            return self.STANCE_RESIST if oppose_score >= 2 else self.STANCE_OPPOSE
        if concern_score > support_score and concern_score >= oppose_score:
            return self.STANCE_CONCERNED
        if support_score > oppose_score and support_score > concern_score:
            return self.STANCE_SUPPORT

        # Tie or unclear: stay with default but nudge if strong signals
        return default_stance

    # ------------------------------------------------------------------
    # Intervention: apply policy-maker persuasion
    # ------------------------------------------------------------------

    async def apply_intervention(
        self,
        intervention_text: str,
        t: Optional[datetime] = None,
        mode: str = "policy",
    ) -> Dict[str, Any]:
        """Apply an intervention and update agent state.

        This is used during pause-and-intervene mode.

        - policy mode: a policy maker tells the agent something (e.g. "We will
          offer a taxi subsidy") and the agent updates its stance / mobilization.
        - product mode: a founder tells/shows the agent something about the
          product (e.g. "It works offline and costs R49/month") and the agent
          reacts as a market participant — objections, conditions, willingness.
          NEVER a buy/no-buy verdict (product-mode honesty rule).

        Returns:
            Dict with "response", "stance_before", "stance_after",
            "stance_before_label", "stance_after_label", "radicalism_before",
            "radicalism_after", "mobilization_before", "mobilization_after",
            "mode".
        """
        if t is None:
            t = datetime.now()

        stance_before = self.init_state.get("stance", "neutral")
        radicalism_before = self.init_state.get("current_radicalism", 1)
        mobilization_before = self.init_state.get("mobilization_level", 0)

        # Build a special prompt that asks the agent to react to the intervention
        char_ctx = await self.character_context(detail="brief")
        if mode == "product":
            prompt = (
                f"{char_ctx}\n\n"
                f"A founder building this product has just told you the following:\n\n"
                f"\"{intervention_text}\"\n\n"
                f"React to this as the market participant you are. Does it change how you'd "
                f"respond to this product, if at all? Be authentic to your character — raise "
                f"your real objections, conditions, or confusion; if it genuinely addresses "
                f"what was holding you back, say so. Do NOT give a buy / no-buy verdict or a "
                f"purchase probability — just react with your reasoning."
            )
        else:
            prompt = (
                f"{char_ctx}\n\n"
                f"A policy maker has just told you the following:\n\n"
                f"\"{intervention_text}\"\n\n"
                f"React to this. How does it change your position, if at all? "
                f"Be authentic to your character. If it genuinely addresses your concerns, "
                f"acknowledge that. If it doesn't, say so clearly."
            )

        try:
            response = await self.answer_external_question(prompt=prompt, t=t)
            response = sanitize_language_drift(response, label=f"intervention_{self.id}")
        except Exception as e:
            import traceback as _tb
            logger.error(f"Intervention failed for agent {self.id}: {e}\n{_tb.format_exc()}")
            return {
                "response": "No response.",
                "stance_before": stance_before,
                "stance_after": stance_before,
                "stance_before_label": self.stance_label(stance_before, mode),
                "stance_after_label": self.stance_label(stance_before, mode),
                "radicalism_before": radicalism_before,
                "radicalism_after": radicalism_before,
                "mobilization_before": mobilization_before,
                "mobilization_after": mobilization_before,
                "mode": mode,
                "error": str(e),
            }

        # Detect stance and radicalism changes
        stance_after = self._detect_stance_from_response(response, stance_before)

        # Heuristic: if stance improved (oppose -> concerned -> neutral -> support),
        # reduce radicalism. If worsened, increase it.
        stance_order = [self.STANCE_RESIST, self.STANCE_OPPOSE,
                        self.STANCE_CONCERNED, self.STANCE_NEUTRAL, self.STANCE_SUPPORT]
        try:
            before_idx = stance_order.index(stance_before)
            after_idx = stance_order.index(stance_after)
            delta = after_idx - before_idx  # positive = moved toward support
            radicalism_after = max(1, min(5, radicalism_before - delta))
        except ValueError:
            radicalism_after = radicalism_before

        # Update mobilization based on new stance/radicalism
        mobilization_after = self._calculate_mobilization(stance_after, radicalism_after)

        # Persist changes
        self.init_state["previous_stance"] = stance_before
        self.init_state["stance"] = stance_after
        self.init_state["current_radicalism"] = radicalism_after
        self.init_state["mobilization_level"] = mobilization_after

        self.set_skill_state("stance", stance_after)
        self.set_skill_state("previous_stance", stance_before)
        self.set_skill_state("current_radicalism", radicalism_after)
        self.set_skill_state("mobilization_level", mobilization_after)

        # Record as interview
        self._record_interview(intervention_text, response, stance_before, stance_after)

        return {
            "response": response,
            "stance_before": stance_before,
            "stance_after": stance_after,
            "stance_before_label": self.stance_label(stance_before, mode),
            "stance_after_label": self.stance_label(stance_after, mode),
            "radicalism_before": radicalism_before,
            "radicalism_after": radicalism_after,
            "mobilization_before": mobilization_before,
            "mobilization_after": mobilization_after,
            "stance_changed": stance_after != stance_before,
            "radicalism_changed": radicalism_after != radicalism_before,
            "mode": mode,
        }

    def _calculate_mobilization(self, stance: str, radicalism: int) -> int:
        """Calculate mobilization level from stance and radicalism."""
        if stance == self.STANCE_SUPPORT:
            return 0
        if stance == self.STANCE_NEUTRAL:
            return 0
        if stance == self.STANCE_CONCERNED:
            return 1 if radicalism >= 2 else 0
        if stance == self.STANCE_OPPOSE:
            return 2 if radicalism >= 3 else 1
        if stance == self.STANCE_RESIST:
            return 3 if radicalism >= 4 else 2
        return 0

    # ------------------------------------------------------------------
    # Stance propagation: cascade to affiliated agents
    # ------------------------------------------------------------------

    def get_propagation_delta(self) -> Optional[Dict[str, Any]]:
        """Get stance change delta for propagation to affiliated agents.

        If this agent's stance recently changed (due to interview or intervention),
        return the delta so the simulation engine can apply it to other agents
        with the same group_affiliation or actor_archetype.

        Returns:
            Dict with "stance_delta", "radicalism_delta", "source_agent_id",
            "group_affiliation", "actor_archetype" — or None if no recent change.
        """
        previous = self.init_state.get("previous_stance")
        current = self.init_state.get("stance", "neutral")

        if previous is None or previous == current:
            return None

        prev_rad = self.init_state.get("base_radicalism", 1)
        curr_rad = self.init_state.get("current_radicalism", 1)

        stance_order = [self.STANCE_RESIST, self.STANCE_OPPOSE,
                        self.STANCE_CONCERNED, self.STANCE_NEUTRAL, self.STANCE_SUPPORT]
        try:
            stance_delta = stance_order.index(current) - stance_order.index(previous)
        except ValueError:
            stance_delta = 0

        return {
            "stance_delta": stance_delta,  # positive = moved toward support
            "radicalism_delta": curr_rad - prev_rad,
            "source_agent_id": self.id,
            "group_affiliation": self.group_affiliation,
            "actor_archetype": self.actor_archetype,
            "from_stance": previous,
            "to_stance": current,
        }

    def apply_propagation_delta(self, delta: Dict[str, Any]) -> bool:
        """Apply a propagation delta received from another agent.

        Modifies this agent's stance and radicalism slightly in the direction
        of the source agent's change (if affiliation/archetype matches).

        Returns:
            True if state was modified.
        """
        # Check affinity
        my_group = self.group_affiliation
        my_archetype = self.actor_archetype
        source_group = delta.get("group_affiliation")
        source_archetype = delta.get("actor_archetype")

        has_affinity = False
        if my_group and source_group and my_group == source_group:
            has_affinity = True
        if my_archetype and source_archetype and my_archetype == source_archetype:
            has_affinity = True

        if not has_affinity:
            return False

        # Apply dampened delta (50% strength for propagation)
        stance_delta = delta.get("stance_delta", 0)
        radicalism_delta = delta.get("radicalism_delta", 0)

        if stance_delta == 0 and radicalism_delta == 0:
            return False

        stance_order = [self.STANCE_RESIST, self.STANCE_OPPOSE,
                        self.STANCE_CONCERNED, self.STANCE_NEUTRAL, self.STANCE_SUPPORT]
        current_stance = self.init_state.get("stance", "neutral")
        current_rad = self.init_state.get("current_radicalism", 1)

        try:
            current_idx = stance_order.index(current_stance)
            new_idx = max(0, min(len(stance_order) - 1,
                                 current_idx + int(stance_delta * 0.5)))
            new_stance = stance_order[new_idx]
        except ValueError:
            new_stance = current_stance

        new_rad = max(1, min(5, current_rad + int(radicalism_delta * 0.5)))

        if new_stance != current_stance or new_rad != current_rad:
            self.init_state["previous_stance"] = current_stance
            self.init_state["stance"] = new_stance
            self.init_state["current_radicalism"] = new_rad
            self.init_state["mobilization_level"] = self._calculate_mobilization(new_stance, new_rad)

            self.set_skill_state("stance", new_stance)
            self.set_skill_state("previous_stance", current_stance)
            self.set_skill_state("current_radicalism", new_rad)
            self.set_skill_state("mobilization_level", self.init_state["mobilization_level"])
            return True

        return False

    # ------------------------------------------------------------------
    # agentsociety2: Serialization for fork/resume
    # ------------------------------------------------------------------

    async def dump(self) -> dict:
        """Serialize full agent state including simulation-specific fields.

        Overrides PersonAgent.dump() to include our init_state (stance,
        radicalism, interview memory, posts history) so simulations can
        be forked from any point.
        """
        base = await super().dump()
        base["init_state"] = self.init_state
        return base

    async def load(self, dump_data: dict):
        """Restore agent state from dump.

        Overrides PersonAgent.load() to restore simulation-specific fields.
        """
        await super().load(dump_data)
        if "init_state" in dump_data:
            self.init_state = dump_data["init_state"]
            # Sync skill states
            for key in ["stance", "current_radicalism", "mobilization_level",
                        "interview_memory", "interview_count", "posts_history"]:
                if key in self.init_state:
                    self.set_skill_state(key, self.init_state[key])

    # ------------------------------------------------------------------
    # Backwards compatibility
    # ------------------------------------------------------------------

    async def do_interview_with_context(
        self,
        prompt: str,
        query_context: Optional[dict] = None,
    ) -> str:
        """Legacy interview method — redirects to do_interview().

        DEPRECATED: Use do_interview() or do_structured_interview() instead.
        Kept for backwards compatibility.
        """
        result = await self.do_interview(prompt)
        return result.get("response", "I have no comment on that.")
