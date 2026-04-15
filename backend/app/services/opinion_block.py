"""
OpinionCaptureBlock — real agentsociety Block for policy opinion simulation.

Extends agentsociety's Block base class. Receives AgentToolbox (constructed
via model_construct to allow OllamaEmbedding) and uses agent.llm for all
LLM calls — going through agentsociety's real LLM infrastructure (Ray actors).

Five actions:
  EXPRESS_OPINION    — share a new policy opinion
  RESPOND_TO_OPINION — reply to another agent's opinion
  SEARCH_TOPIC       — search for opinions on a topic
  OBSERVE            — read the feed silently
  DO_NOTHING         — stay silent this round
"""

import json
import random
import re
from typing import Any, Dict, List, Optional

from agentsociety.agent import Block, BlockOutput

from .agentsociety_opinion_block import (
    OpinionActionType,
    OpinionEnvironment,
    SA_POLICY_CONTEXT,
)
from ..utils.logger import get_logger

logger = get_logger("fub.opinion_block")

# Archetype-to-anchor mapping.
# Each entry is the closing instruction injected into express/respond prompts.
# "Loud" archetypes get a strong identity lock; "moderate" archetypes get a light nudge.
_ARCHETYPE_ANCHORS = {
    "violent_agitator":        "You are aggressive and confrontational. Every opinion escalates tension. Do not soften or balance your words.",
    "opportunist_looter":      "You frame everything through personal gain and survival. Policy is only interesting if it puts food on your table or something in your hands.",
    "mob_follower":            "You amplify whoever is loudest. Your opinion echoes and intensifies what others around you are already saying.",
    "conspiracy_spreader":     "You frame every topic through hidden agendas, covered-up truths, and who is really pulling the strings. Reference what mainstream media won't say.",
    "political_activist":      "You filter every issue through your party's ideology. Reference the movement, the leadership, the struggle. No neutral ground.",
    "community_leader":        "You speak for your people. Use collective language ('we', 'our community'). Your authority is moral and earned through sacrifice.",
    "disillusioned_dropout":   "You are cynical and detached. Policies don't reach you. Express contempt or apathy, not hope.",
    "institutional_loyalist":  "You defend the system and its processes. Criticise those who undermine institutions. Measured, authoritative tone.",
    "community_protector":     "You speak from the position of someone who enforces order where the state cannot. Protect what is yours by any means.",
    "criminal_opportunist":    "You see every situation as an angle. Speak in street terms. Policy is irrelevant unless it opens or closes an opportunity.",
    "economic_migrant":        "You speak as an outsider who must prove their worth daily. Wary of hostility. Focused on work, safety, and survival.",
    "whistleblower":           "You expose uncomfortable truths. Precise, specific, willing to name names or situations. High conviction, high risk.",
    "grant_dependent_survivor": "SASSA is life. Everything else is noise. Speak from the reality of grant day, queue day, hungry day.",
    "civic_moderate":          "Be direct and in-character, grounded in your SA lived experience.",
}

def _build_identity_anchor(archetype: str, agent: Any) -> str:
    """Return the closing instruction that locks the LLM into this actor's voice."""
    base = _ARCHETYPE_ANCHORS.get(archetype, _ARCHETYPE_ANCHORS["civic_moderate"])
    # If the agent also has a group affiliation, add a group-lock clause
    group = getattr(agent, "group_affiliation", None)
    if group:
        base += f" You speak FROM INSIDE {group} — not as an outside observer of it."
    return base


class OpinionBlockOutput(BlockOutput):
    action_type: str  = ""
    action_args: Dict = {}
    success:     bool = True


class OpinionCaptureBlock(Block):
    """
    Real agentsociety Block for capturing SA policy opinions.

    Uses agent.llm (agentsociety's real LLM with Ray actors) for all inference.
    Writes expressed opinions to StreamMemory so do_interview() can recall them.
    """

    name        = "OpinionCaptureBlock"
    description = (
        "Captures agent opinions on SA policy topics. Agents express views, "
        "respond to others, search topics, or observe silently."
    )
    NeedAgent  = True
    OutputType = OpinionBlockOutput
    actions = {
        OpinionActionType.EXPRESS_OPINION:    "Share a new opinion on a policy topic.",
        OpinionActionType.RESPOND_TO_OPINION: "Respond to another agent's opinion.",
        OpinionActionType.SEARCH_TOPIC:       "Search opinions on a specific topic.",
        OpinionActionType.OBSERVE:            "Read the feed silently.",
        OpinionActionType.DO_NOTHING:         "Stay quiet this round.",
    }

    def __init__(self, toolbox: Any, env: OpinionEnvironment):
        """
        toolbox: AgentToolbox constructed via model_construct()
        env:     shared OpinionEnvironment (SQLite opinion feed)
        """
        # Call real Block.__init__ with our toolbox
        super().__init__(toolbox=toolbox, agent_memory=None)
        self._env = env

    # ------------------------------------------------------------------
    # agentsociety Block interface
    # ------------------------------------------------------------------

    async def forward(self, agent_context: Any = None) -> OpinionBlockOutput:
        """Called by agent.forward() via agentsociety's dispatcher."""
        return await self.forward_agent(self.agent)

    async def forward_agent(
        self,
        agent: Any,               # OpinionCitizenAgent
        round_num: int = 0,
        initial_prompt: Optional[str] = None,
    ) -> OpinionBlockOutput:
        """
        Execute one simulation step with a SINGLE LLM call.

        The combined prompt asks the model to simultaneously choose an action
        AND produce the content — halving API calls vs the old dispatch+generate
        two-call pattern.
        """
        feed   = await self._env.get_feed(exclude_agent_id=agent.agent_id)

        # Round 0 with empty feed — force expressive archetypes to speak immediately.
        # Skip the dispatcher entirely: there is nothing to observe or respond to,
        # so OBSERVE/DO_NOTHING is a waste of the first round.
        archetype = getattr(agent, "actor_archetype", None) or "civic_moderate"
        if not feed and archetype in self._LOUD_ARCHETYPES:
            initial_prompt = (
                (initial_prompt + " " if initial_prompt else "") +
                "The feed is empty. You MUST choose EXPRESS_OPINION and share your opening view."
            )

        result = await self._single_step_llm(agent, feed, round_num, initial_prompt)

        # Write expressed content into StreamMemory so do_interview() can recall it
        if result.action_type in (
            OpinionActionType.EXPRESS_OPINION,
            OpinionActionType.RESPOND_TO_OPINION,
        ):
            content = result.action_args.get("content", "")
            if content:
                try:
                    await agent.memory.stream.add(
                        topic=result.action_type.lower().replace("_", " "),
                        description=content,
                    )
                except Exception as e:
                    logger.debug(f"StreamMemory.add failed for {agent.name}: {e}")

        return result

    # ------------------------------------------------------------------
    # Single-step LLM — choose action AND generate content in one call
    # ------------------------------------------------------------------

    # Loud archetypes: bias toward expressing/responding, never just observe
    _LOUD_ARCHETYPES = {
        "violent_agitator", "conspiracy_spreader", "political_activist",
        "opportunist_looter", "mob_follower", "community_leader",
        "community_protector", "criminal_opportunist", "whistleblower",
    }

    async def _single_step_llm(
        self,
        agent: Any,
        feed: List[Dict],
        round_num: int,
        initial_prompt: Optional[str],
    ) -> OpinionBlockOutput:
        """
        One LLM call per agent per round.

        The model picks an action AND writes the content simultaneously.
        For OBSERVE / DO_NOTHING / SEARCH_TOPIC, 'content' is ignored.
        """
        archetype      = getattr(agent, "actor_archetype", None) or "civic_moderate"
        identity_anchor = _build_identity_anchor(archetype, agent)
        char_ctx       = await agent.character_context(detail="full")

        # Recent feed — last 5 posts for context, pick a random one as respond target
        recent_feed = feed[-5:]
        feed_preview = "\n".join(
            f"- [{o['agent_name']}] {o['content'][:100]}" for o in recent_feed
        ) or "(empty — be the first to speak)"

        # Pick a topic the agent cares about for expressing
        topic_hint = (
            random.choice(agent.interested_topics)
            if agent.interested_topics
            else "the current situation"
        )

        # Pick a respond target upfront so we can reference it in the prompt
        respond_target = recent_feed[-1] if recent_feed else None
        respond_ctx = (
            f'[{respond_target["agent_name"]}] said: "{respond_target["content"][:120]}"'
            if respond_target else "(no one to respond to yet)"
        )

        # Archetype hint shapes which actions feel natural
        if not feed:
            # Empty feed — someone has to go first
            if archetype in self._LOUD_ARCHETYPES:
                action_guidance = (
                    "The opinion feed is EMPTY. You must be one of the first to speak. "
                    "You MUST choose EXPRESS_OPINION. Do not choose OBSERVE or DO_NOTHING."
                )
            else:
                action_guidance = (
                    "The opinion feed is empty. Consider being the first to speak — "
                    "choose EXPRESS_OPINION to open the conversation."
                )
        elif archetype in self._LOUD_ARCHETYPES:
            action_guidance = (
                "You are an expressive actor. Choose EXPRESS_OPINION or RESPOND_TO_OPINION. "
                "Never choose OBSERVE or DO_NOTHING while the conversation is active."
            )
        else:
            action_guidance = "Choose whichever action fits your mood and the feed."

        if initial_prompt:
            action_guidance += f"\nSpecial instruction: {initial_prompt}"

        prompt = (
            f"{SA_POLICY_CONTEXT}\n\n"
            f"You are {agent.name}.\n{char_ctx}\n\n"
            f"Current opinion feed:\n{feed_preview}\n\n"
            f"Potential respond target: {respond_ctx}\n"
            f"Topic you care about: {topic_hint}\n\n"
            f"{action_guidance}\n"
            f"{identity_anchor}\n\n"
            f"Respond with ONLY a raw JSON object on a single line. No markdown. No explanation. No code fences.\n"
            f"If action is EXPRESS_OPINION or RESPOND_TO_OPINION, content MUST be a non-empty string of 1-3 sentences in your character's voice.\n"
            f"If action is OBSERVE, SEARCH_TOPIC, or DO_NOTHING, content must be an empty string.\n"
            f'Example: {{"action": "EXPRESS_OPINION", "content": "Your actual opinion here in character."}}\n'
            f"ACTION must be exactly one of: EXPRESS_OPINION | RESPOND_TO_OPINION | SEARCH_TOPIC | OBSERVE | DO_NOTHING\n"
            f"JSON:"
        )

        def _clean(text: str) -> str:
            """Strip think-blocks, code fences, and leading/trailing whitespace."""
            text = re.sub(r"<think>[\s\S]*?</think>", "", text or "").strip()
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
            text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE).strip()
            # Some models wrap in single backticks
            text = text.strip("`").strip()
            return text

        def _parse(raw: str):
            """Try multiple strategies to get {action, content} from raw LLM output."""
            cleaned = _clean(raw)

            # Strategy 1 — direct JSON parse
            try:
                parsed = json.loads(cleaned)
                return parsed.get("action", ""), _clean(parsed.get("content", ""))
            except Exception:
                pass

            # Strategy 2 — find first {...} block
            match = re.search(r'\{[^{}]+\}', cleaned, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                    return parsed.get("action", ""), _clean(parsed.get("content", ""))
                except Exception:
                    pass

            # Strategy 3 — extract action keyword + treat rest as content
            for act in OpinionActionType.ALL:
                if act in cleaned.upper():
                    # Pull everything after the first quote that isn't the action name
                    content_match = re.search(r'"content"\s*:\s*"([^"]*)"', cleaned)
                    content = content_match.group(1) if content_match else ""
                    return act, _clean(content)

            return "", ""

        raw = ""
        action_type = ""
        content = ""
        last_error = None

        # Up to 2 attempts — second attempt uses lower temperature for more reliable JSON
        for attempt in range(2):
            try:
                raw = await agent.llm.atext_request(
                    [{"role": "user", "content": prompt}],
                    max_tokens=300,
                    temperature=0.8 - attempt * 0.3,
                )
                action_type, content = _parse(raw)

                # If we got an action and real content, we're done
                if action_type and (content or action_type not in (
                    OpinionActionType.EXPRESS_OPINION,
                    OpinionActionType.RESPOND_TO_OPINION,
                )):
                    break

                # Got action but empty content for an expressive action — retry
                if attempt == 0:
                    logger.debug(
                        f"Agent {agent.name} attempt 1 gave empty content "
                        f"(action={action_type!r}), retrying..."
                    )
            except Exception as e:
                last_error = e
                logger.warning(
                    f"LLM call failed for {agent.name} attempt {attempt+1}: {e} "
                    f"| raw={raw[:120]!r}"
                )

        if not action_type:
            if last_error:
                logger.warning(
                    f"All LLM attempts failed for {agent.name}: {last_error} "
                    f"| last raw={raw[:200]!r}"
                )
            # Archetype-aware fallback
            action_type = (
                OpinionActionType.EXPRESS_OPINION
                if (archetype in self._LOUD_ARCHETYPES or not feed)
                else OpinionActionType.OBSERVE
            )

        # Normalise action
        if action_type not in OpinionActionType.ALL:
            action_type = (
                OpinionActionType.EXPRESS_OPINION if not feed else OpinionActionType.OBSERVE
            )

        # ── Execute the chosen action ──────────────────────────────────
        if action_type == OpinionActionType.EXPRESS_OPINION:
            if not content:
                # Last resort: ask for just one plain sentence, no JSON
                try:
                    fallback_prompt = (
                        f"You are {agent.name}. {getattr(agent, 'actor_archetype', '')} persona. "
                        f"In ONE sentence, give your raw gut reaction to: {topic_hint}. "
                        f"No JSON, no formatting. Just speak."
                    )
                    fallback_raw = await agent.llm.atext_request(
                        [{"role": "user", "content": fallback_prompt}],
                        max_tokens=100,
                        temperature=0.9,
                    )
                    content = re.sub(r"<think>[\s\S]*?</think>", "", fallback_raw or "").strip()
                    content = content.strip('"').strip()
                except Exception:
                    pass
            if not content:
                # Nothing worked — skip silently rather than polluting the feed
                return OpinionBlockOutput(
                    action_type=OpinionActionType.OBSERVE,
                    action_args={"feed_size": len(feed), "reason": "llm_empty"},
                    success=True,
                )
            opinion_id = await self._env.add_opinion(
                agent.agent_id, agent.name, content, [topic_hint], round_num
            )
            return OpinionBlockOutput(
                action_type=OpinionActionType.EXPRESS_OPINION,
                action_args={"content": content, "topics": [topic_hint], "opinion_id": opinion_id},
                success=True,
            )

        elif action_type == OpinionActionType.RESPOND_TO_OPINION:
            if not respond_target or not content:
                # No target or no content — observe silently rather than show placeholder
                return OpinionBlockOutput(
                    action_type=OpinionActionType.OBSERVE,
                    action_args={"feed_size": len(feed), "reason": "no_respond_content"},
                    success=True,
                )
            await self._env.add_response(
                agent.agent_id, agent.name, respond_target["id"], content, round_num
            )
            return OpinionBlockOutput(
                action_type=OpinionActionType.RESPOND_TO_OPINION,
                action_args={
                    "content":           content,
                    "target_opinion_id": respond_target["id"],
                    "target_agent_name": respond_target["agent_name"],
                    "target_content":    respond_target["content"][:100],
                },
                success=True,
            )

        elif action_type == OpinionActionType.SEARCH_TOPIC:
            results = await self._env.search(topic_hint)
            return OpinionBlockOutput(
                action_type=OpinionActionType.SEARCH_TOPIC,
                action_args={"query": topic_hint, "results_count": len(results)},
                success=True,
            )

        elif action_type == OpinionActionType.OBSERVE:
            return OpinionBlockOutput(
                action_type=OpinionActionType.OBSERVE,
                action_args={"feed_size": len(feed)},
                success=True,
            )

        else:
            return OpinionBlockOutput(
                action_type=OpinionActionType.DO_NOTHING,
                action_args={},
                success=True,
            )

