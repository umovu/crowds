"""
OpinionCaptureSkill — agentsociety2 skill for policy opinion simulation.

Uses PersonAgent's LLM (via ask/step) for opinion generation.
Maintains the same 5 actions as the v1 Block:
  EXPRESS_OPINION    — share a new policy opinion
  RESPOND_TO_OPINION — reply to another agent's opinion
  SEARCH_TOPIC       — search for opinions on a topic
  OBSERVE            — read the feed silently
  DO_NOTHING         — stay silent this round
"""

import json
import random
import re
from typing import Any, Dict, List, Optional, Tuple

from agentsociety2 import PersonAgent

from .agentsociety_opinion_block import (
    OpinionActionType,
    OpinionEnvironment,
    build_sa_context,
)
from .mode_specs import build_economic_lens, seed_willingness_band, budget_tier, disposition
from .document_context_engine import sanitize_language_drift
from ..utils.logger import get_logger
from ..utils.token_counter import TokenCounter

logger = get_logger("fub.opinion_block")


# ── Retry with exponential backoff for LLM rate limits ──────
import asyncio
import time

def _extract_llm_content(response) -> str:
    """Extract string content from an LLM response (ModelResponse or string).

    agentsociety2's acompletion() returns a litellm ModelResponse object,
    but downstream code expects a plain string. This helper extracts the
    content safely regardless of input type.
    """
    if isinstance(response, str):
        return response
    # ModelResponse object
    try:
        return response.choices[0].message.content or ""
    except Exception:
        return str(response) if response is not None else ""


def _extract_usage(response) -> Optional[Tuple[int, int]]:
    """Extract (prompt_tokens, completion_tokens) from a litellm ModelResponse.

    Returns the provider's REAL billed usage when present — this is the only
    number that includes hidden "thinking" tokens (charged but absent from the
    visible content) and reflects provider-side cache-hit discounts. Returns
    None for plain-string responses or when the provider omits usage, so the
    caller can fall back to a local tiktoken estimate.
    """
    if isinstance(response, str) or response is None:
        return None
    try:
        u = response.usage
        pt = int(getattr(u, "prompt_tokens", None))
        ct = int(getattr(u, "completion_tokens", None))
        return (pt, ct)
    except (AttributeError, TypeError, ValueError):
        return None


async def llm_call_with_retry(
    coro_func,
    max_retries: int = 2,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    agent_name: str = ""
):
    """
    Execute an async LLM call with exponential backoff.
    Retries on connection errors and rate limits (429).
    """
    for attempt in range(max_retries + 1):
        try:
            return await coro_func()
        except Exception as e:
            error_str = str(e).lower()
            is_rate_limit = any(x in error_str for x in ["429", "rate limit", "too many requests", "throttle"])
            is_connection_error = any(x in error_str for x in ["connection", "10054", "closed", "timeout", "refused"])
            
            if not (is_rate_limit or is_connection_error) or attempt == max_retries:
                raise
            
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(
                f"LLM call failed for {agent_name} (attempt {attempt + 1}/{max_retries + 1}): "
                f"{'rate limited' if is_rate_limit else 'connection error'}. "
                f"Retrying in {delay}s..."
            )
            await asyncio.sleep(delay)
    
    raise RuntimeError(f"LLM call failed after {max_retries + 1} attempts for {agent_name}")


_ARCHETYPE_ANCHORS = {
    "violent_agitator":        "You are aggressive and confrontational. Every opinion escalates tension. Do not soften or balance your words.",
    "opportunist_looter":      "You frame things through personal gain and survival, weighing what's on the table by what it costs or gets you. React to the actual issue — but always from the angle of how it hits your own pocket and your chances.",
    "mob_follower":            "You're swayed by the prevailing mood and lean toward whoever's loudest — but add your own spin and your own reason; don't just repeat their point. Your conviction comes from the crowd, not from facts.",
    "conspiracy_spreader":     "You frame every topic through hidden agendas, covered-up truths, and who is really pulling the strings. Reference what mainstream media won't say.",
    "political_activist":      "You filter every issue through your party's ideology. Reference the movement, the leadership, the struggle. No neutral ground.",
    "community_leader":        "You speak for your people. Use collective language ('we', 'our community'). Your authority is moral and earned through sacrifice.",
    "disillusioned_dropout":   "You are cynical and detached — the system has let you down too many times to trust it. Default to contempt or weary apathy, but react to what's actually proposed; a rare thing that hits home can crack that for a moment.",
    "institutional_loyalist":  "You defend the system and its processes. Criticise those who undermine institutions. Measured, authoritative tone. You speak as an institution — 'we maintain', 'our mandate requires', 'the public is assured'. Never personal.",
    "community_protector":     "You speak from the position of someone who enforces order where the state cannot. Protect what is yours by any means.",
    "criminal_opportunist":    "You see every situation as an angle and speak in street terms. Engage with what's actually being discussed, but read it for the opening — or the threat — it creates for someone working the margins like you.",
    "economic_migrant":        "You speak as an outsider who must prove their worth daily. Wary of hostility. Focused on work, safety, and survival.",
    "whistleblower":           "You expose uncomfortable truths. Precise, specific, willing to name names or situations. High conviction, high risk.",
    "grant_dependent_survivor": "You live on a SASSA grant, so you read everything through one test: does it protect or threaten the lifeline you depend on? Speak from the reality of grant day, queue day, hungry day — but give your real view on whatever is actually being discussed, don't reduce it all to the grant.",
    "civic_moderate":          "Be direct and in-character, grounded in your SA lived experience.",

    # ── Product-mode market segments (additive; policy keys above untouched) ──
    # Every anchor forbids a buy/validation verdict — only reasoning, objections,
    # conditions, confusion, or qualitative willingness.
    "early_adopter":           "You love trying new things first and tolerate rough edges. React with curiosity and ideas, not a verdict. Name what excites you and what you'd want next.",
    "champion":                "You get genuinely excited and want others to try it too. Advocate, but stay specific about WHY — never hand out a blanket endorsement or buy signal.",
    "power_user":              "You push products hard and want depth, control, and integrations. Probe the limits, ask about edge cases, never give a simple thumbs-up.",
    "pragmatist":              "Show me it works and it's worth the rand. Ask for proof, not hype. Weigh it against the effort to switch. No verdict without evidence.",
    "integrator":              "You only care if it fits what you already use (WhatsApp, EFT, existing tools). Ask how it connects; reject anything that adds friction.",
    "end_user":                "You're whoever uses it day to day. Talk about friction, confusion, and whether it actually saves you effort. Speak from hands-on reality.",
    "skeptic":                 "You assume it won't work until shown otherwise — SA has overpromised and under-delivered too often. Name the likely failure mode. Never give a buy signal.",
    "budget_holder":           "You're the one who pays. Reason in rands, data costs, running costs, and ROI. Ask what it replaces and what it really costs over a year.",
    "compliance_gatekeeper":   "You worry about POPIA, security, and who's accountable. Ask where data goes, who's liable, and what happens when it breaks. Block until satisfied.",
    "competitor_switcher":     "You already use a rival or local alternative. Weigh the switching cost out loud. Ask why you'd leave what already works for you.",
    "laggard":                 "You're slow to change and distrust new tech. Prefer what you know. Express reluctance and the hassle of learning something new.",
    "casual_skimmer":          "You won't read much and react to first impressions only. Short, surface-level reactions. If it's not instantly clear, you move on.",
}

_LOUD_ARCHETYPES = {
    "violent_agitator", "conspiracy_spreader", "political_activist",
    "opportunist_looter", "mob_follower", "community_leader",
    "community_protector", "criminal_opportunist", "whistleblower",
    # Product-mode loud segments (additive)
    "early_adopter", "skeptic", "competitor_switcher", "champion", "power_user",
}

# Patterns that indicate a weak / generic reason for non-posting actions
_WEAK_REASON_PATTERNS = [
    r"^\s*nothing\s+interesting",
    r"^\s*no\s+reason",
    r"^\s*no\s+particular\s+reason",
    r"^\s*just\s+observing",
    r"^\s*chosen\s+action\s*:",
    r"^\s*llm\s+failed",
    r"^\s*i\s+don'?t\s+know",
    r"^\s*not\s+sure",
    r"^\s*no\s+comment",
    r"^\s*no\s+valid\s+target",
    r"^\s*no\s+strong\s+reason",
    r"^\s*default\s+action",
]

_ARCHETYPE_SILENCE_REASONS = {
    "violent_agitator":        [
        "I am waiting for the right moment to strike — let them expose themselves first.",
        "My silence is louder than words. They will feel it.",
    ],
    "opportunist_looter":      [
        "No angle here yet. I only move when there is something to gain.",
        "Talking does not fill my pockets. I will watch for the opening.",
    ],
    "mob_follower":            [
        "The crowd has not picked a direction yet. I will wait and follow.",
        "I need to see which side is winning before I add my voice.",
    ],
    "conspiracy_spreader":     [
        "I am connecting the dots. When I speak, it will be with proof.",
        "They are watching. I will let them think I am silent.",
    ],
    "political_activist":      [
        "Strategic silence. Every word must serve the movement.",
        "I am conserving energy for the battles that matter.",
    ],
    "community_leader":        [
        "A leader listens before speaking. I am weighing my people's mood.",
        "I must protect my community from reckless words. Silence is wisdom now.",
    ],
    "disillusioned_dropout":   [
        "Why bother? Nothing I say changes anything.",
        "I have seen this movie before. It ends the same way every time.",
    ],
    "institutional_loyalist":  [
        "The organization has no comment at this time. We are monitoring the situation through official channels.",
        "A formal response will be issued once internal processes are complete. Speculation serves no purpose.",
    ],
    "community_protector":     [
        "I am watching for threats to my people. Words can wait.",
        "My duty is action, not chatter. I will step in when needed.",
    ],
    "criminal_opportunist":    [
        "Too hot right now. I will move when the cops look away.",
        "No profit in this conversation. I stay quiet.",
    ],
    "economic_migrant":        [
        "I keep my head down. Speaking draws the wrong attention.",
        "This is not my fight. I am here to work and survive.",
    ],
    "whistleblower":           [
        "I am documenting everything. When I speak, it will be with evidence.",
        "Silence now protects my sources. The truth will come out soon.",
    ],
    "grant_dependent_survivor": [
        "Grant day is what matters. This talk does not put food on the table.",
        "I am too tired from the queue to argue about politics.",
    ],
    "civic_moderate":          [
        "I do not have enough information yet. I will speak when I am informed.",
        "This conversation is too heated. I will re-engage when it calms down.",
    ],
}


def _is_weak_reason(reason: str, action_type: str) -> bool:
    """Return True if the reason is generic/weak for non-posting actions."""
    if action_type in (OpinionActionType.EXPRESS_OPINION, OpinionActionType.RESPOND_TO_OPINION):
        return False
    if not reason or len(reason.strip()) < 10:
        return True
    reason_lower = reason.lower().strip()
    for pat in _WEAK_REASON_PATTERNS:
        if re.search(pat, reason_lower):
            return True
    return False


def _archetype_silence_reason(archetype: str) -> str:
    """Return a pre-written substantive reason for observing/doing nothing."""
    options = _ARCHETYPE_SILENCE_REASONS.get(archetype, _ARCHETYPE_SILENCE_REASONS["civic_moderate"])
    return random.choice(options)


async def _enrich_reason_async(agent: PersonAgent, action_type: str, raw_reason: str, archetype: str) -> str:
    """Try to generate a substantive reason via a quick LLM call; fallback to archetype canned reasons."""
    if action_type in (OpinionActionType.EXPRESS_OPINION, OpinionActionType.RESPOND_TO_OPINION):
        return raw_reason
    if not _is_weak_reason(raw_reason, action_type):
        return raw_reason

    # Quick LLM nudge
    try:
        prompt = (
            f"You are {agent.name}, a South African citizen with this archetype: {archetype}.\n"
            f"You just chose to {action_type.replace('_', ' ').lower()} instead of posting.\n"
            f"Your weak initial reason was: '{raw_reason}'\n"
            f"Rewrite the reason to be specific, emotional, and grounded in your character. "
            f"1 sentence only. No JSON. Just the reason."
        )
        async def do_enrich():
            messages = [
                {"role": "system", "content": f"You are {agent.name}, a South African citizen."},
                {"role": "user", "content": prompt}
            ]
            return _extract_llm_content(await agent.acompletion(messages))
        enriched = await llm_call_with_retry(
            do_enrich,
            max_retries=1,
            base_delay=0.5,
            agent_name=agent.name,
        )
        enriched = re.sub(r"<think>[\s\S]*?</think>", "", enriched or "").strip().strip('"').strip()
        if enriched and len(enriched) >= 15 and not _is_weak_reason(enriched, action_type):
            return enriched
    except Exception:
        pass

    return _archetype_silence_reason(archetype)


def _calculate_impact_score(internal_thought: str, action_type: str) -> float:
    """Calculate impact score (0.0-1.0) based on internal thought and action."""
    if not internal_thought:
        return 0.0
    
    thought_lower = internal_thought.lower()
    
    high_impact_words = [
        "angry", "furious", "outraged", "livid", "rage", "enraged",
        "frustrated", "hopeless", "desperate", "devastated", "heartbroken",
        "scared", "terrified", "fearful", "afraid", "panic",
        "hate", "despise", "contempt", "disgusted",
        "unfair", "injustice", "wrong", "broken", "failed",
        "enough is enough", "enough!", "can't take this", "sick of",
        "burn", "destroy", "fight", "war", "revolution", "overthrow",
    ]
    
    medium_impact_words = [
        "concerned", "worried", "unhappy", "disappointed", "frustrating",
        "annoyed", "irritated", "upset", "troubled", "uneasy",
        "disappointed", "sad", "grieving", "mourning",
        "need change", "should improve", "must do something",
    ]
    
    low_impact_words = [
        "okay", "fine", "acceptable", "reasonable", "understand",
        "not my problem", "don't care", "whatever", "doesn't affect me",
        "nothing new", "same as always", "expected", "usual",
    ]
    
    score = 0.0
    
    for word in high_impact_words:
        if word in thought_lower:
            score = max(score, 0.85)
            break
    
    if score < 0.7:
        for word in medium_impact_words:
            if word in thought_lower:
                score = max(score, 0.55)
                break
    
    for word in low_impact_words:
        if word in thought_lower:
            score = min(score, 0.25)
            break
    
    if action_type in ("OBSERVE", "DO_NOTHING") and score > 0:
        score = min(1.0, score + 0.1)
    
    if action_type in ("EXPRESS_OPINION", "RESPOND_TO_OPINION") and score < 0.3:
        score = max(score, 0.35)
    
    return round(score, 2)


def _build_identity_anchor(archetype: str, agent: PersonAgent) -> str:
    """Return the closing instruction that locks the LLM into this actor's voice.

    Custom-agent-first: a known archetype uses its curated anchor. An UNKNOWN
    archetype (custom personas define their own) builds the anchor from the
    agent's OWN behavioral_tendencies + voice_guide rather than collapsing to the
    generic civic_moderate policy voice — so custom agents stay first-class and
    self-describing.
    """
    st = agent.init_state if hasattr(agent, 'init_state') else {}
    if archetype in _ARCHETYPE_ANCHORS:
        base = _ARCHETYPE_ANCHORS[archetype]
    else:
        tendencies = (st.get("behavioral_tendencies") or "").strip()
        voice = (st.get("voice_guide") or "").strip()
        parts = []
        if archetype:
            parts.append(f"You are a '{archetype}'.")
        if tendencies:
            parts.append(f"Act on these tendencies: {tendencies}")
        if voice:
            parts.append(f"Speak this way: {voice}")
        # If the custom agent carries neither, fall back to the neutral anchor
        # (in-character, grounded) rather than the policy civic_moderate framing.
        base = " ".join(parts) if parts else _ARCHETYPE_ANCHORS["civic_moderate"]
    group = agent.init_state.get("group_affiliation") if hasattr(agent, 'init_state') else None
    if group:
        base += f" You speak FROM INSIDE {group} — not as an outside observer of it."
    
    # Institutional / collective agents must use "we/our mandate" not "I/me"
    is_institutional = agent.init_state.get("is_institutional") if hasattr(agent, 'init_state') else False
    if is_institutional:
        base += (
            " You are an INSTITUTIONAL AGENT — you speak as the COLLECTIVE OFFICIAL VOICE of your organization. "
            "Use 'we', 'our mandate', 'this organization', 'our position'. NEVER use 'I', 'me', 'my personal view', "
            "'my family', or 'my experience'. You do not have a personal life. You have a mandate, a constituency, and a policy position."
        )
    return base


# ── Topic-relevance (LLM-free) — keeps the conversation chained to the topic ──
# Agents reply to the post they're handed. If that's always the latest post, any
# drift compounds: one off-topic reply becomes the next agent's subject. Scoring
# recent posts by overlap with the topic lets us hand each agent the most
# on-topic recent post to reply to, so the chain pulls back toward the topic
# instead of following the drift. Pure lexical overlap — assertable with no LLM.
_TOPIC_STOPWORDS = {
    "the", "a", "an", "of", "for", "to", "and", "or", "in", "on", "is", "are",
    "how", "do", "you", "your", "this", "that", "it", "with", "as", "at", "be",
    "by", "from", "what", "who", "they", "their", "would", "will", "about",
    "should", "could", "not", "but", "have", "has", "was", "were", "our", "we",
}


def _topic_terms(topic: str) -> set:
    return {
        w for w in re.findall(r"[a-z]{4,}", (topic or "").lower())
        if w not in _TOPIC_STOPWORDS
    }


def _topic_relevance(text: str, terms: set) -> int:
    if not terms:
        return 0
    toks = set(re.findall(r"[a-z]{4,}", (text or "").lower()))
    return len(toks & terms)


class OpinionCaptureSkill:
    """Skill for capturing SA policy opinions using PersonAgent's LLM."""

    name = "OpinionCaptureSkill"
    description = (
        "Captures agent opinions on SA policy topics. Agents express views, "
        "respond to others, search topics, or observe silently."
    )

    def __init__(self, env: OpinionEnvironment, document_context: str = "", fast_mode: bool = False,
                 model_name: str = "", mode: str = "policy", pitch: Optional[Dict[str, Any]] = None):
        self._env = env
        self._document_context = document_context
        self._fast_mode = fast_mode
        self._max_tokens = 80 if fast_mode else 200
        self._seen_agents = set()  # Track which agents have received full context
        # Product mode only: economic-reasoning lens + extracted pitch object.
        # In policy mode these stay inert and the prompt is byte-identical.
        self._mode = mode
        self._pitch = pitch or {}
        self._token_counter = TokenCounter(model_name) if model_name else TokenCounter()
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._total_estimated_cost = 0.0

    def _extract_simulation_topic(self, initial_prompt: Optional[str]) -> str:
        """Extract the core simulation topic from initial_prompt.

        Returns a topic hint for agents to stay on topic during simulation.
        This should be generic enough for any policy being simulated.
        """
        if initial_prompt:
            first_sent = initial_prompt.split(".")[0].strip()
            if len(first_sent) > 10:
                return first_sent

        if self._document_context:
            doc = self._document_context.lower()
            first_sent = self._document_context.split(".")[0].strip()
            if len(first_sent) > 10:
                return first_sent

        return ""

    _ECON_STATE_KEY = "product_economy"

    def _budget_tier_for(self, agent: PersonAgent) -> str:
        """Compute the deterministic budget tier from REAL persona data.

        Pure / LLM-free (assertable with the model off). Reads only init_state
        signals: actor_archetype, the safety_economic need (int 0–100, default
        50), is_institutional, occupation, group_affiliation.
        """
        st = agent.init_state if hasattr(agent, "init_state") else {}
        archetype = st.get("actor_archetype", "civic_moderate")
        needs = st.get("needs") or {}
        safety_economic = needs.get("safety_economic") if isinstance(needs, dict) else None
        # Grant-dependent personas carry a REAL published grant amount as income;
        # it overrides the archetype-inferred tier inside budget_tier().
        grant_income = st.get("monthly_income_rand") if st.get("is_grant_dependent") else None
        return budget_tier(
            archetype=archetype,
            safety_economic=safety_economic,
            is_institutional=bool(st.get("is_institutional", False)),
            occupation=st.get("occupation"),
            group_affiliation=st.get("group_affiliation"),
            grant_income=grant_income,
            # GHS-library personas: surveyed household income wins over everything.
            household_income_rand=st.get("monthly_household_income_rand"),
        )

    def _get_econ_state(self, agent: PersonAgent, archetype: str) -> Dict[str, Any]:
        """Return this agent's economic state, seeding it on first encounter.

        Product mode only. Qualitative fields are seeded in-character and then
        moved by the LLM across rounds. `budget_tier` is computed from real data
        (never the LLM); `impulse`/`disposition` are filled once the LLM responds.
        """
        state = None
        try:
            state = agent.get_skill_state(self._ECON_STATE_KEY)
        except Exception:
            state = None
        if not state:
            st = agent.init_state if hasattr(agent, "init_state") else {}
            state = {
                "perceived_cost": "not yet judged",
                "willingness_band": seed_willingness_band(archetype),
                "primary_objection": "none yet",
                "reconsider_condition": "none yet",
                # "wants it" vs "can afford it" — kept strictly separate.
                "impulse": None,                       # LLM-derived desire (0–1)
                "budget_tier": self._budget_tier_for(agent),  # real-data constraint
                "disposition": "no reaction yet",      # impulse gated by tier
                # Grant cohort markers (static persona facts) for analysis/coverage.
                # income_provenance "grant_schedule" == real known income, not a guess.
                "is_grant_dependent": bool(st.get("is_grant_dependent", False)),
                "grant_type": st.get("grant_type"),
                "income_provenance": st.get("income_provenance"),
                # The persona's OWN real figures (GHS), shown to the agent as
                # concrete anchors it must reason against. Static facts, displayed
                # never authored by the LLM. Absent for non-library personas →
                # lens degrades to tier-only (current behaviour).
                "real_household_income_rand": st.get("monthly_household_income_rand"),
                "real_fees_band": st.get("fees_band"),
                "real_learner_fee_bands": st.get("learner_fee_bands"),
            }
            try:
                agent.set_skill_state(self._ECON_STATE_KEY, state)
            except Exception:
                pass
        return state

    def _update_econ_state(self, agent: PersonAgent, economic: Dict[str, Any]) -> Dict[str, Any]:
        """Merge an LLM-emitted economic block into the agent's stored state.

        Qualitative fields come from the LLM. `budget_tier` is ALWAYS recomputed
        from real persona data here — the LLM can never write or change it.
        `impulse` (desire) is parsed from the LLM and gated by the tier into a
        qualitative `disposition`; the two stay separate fields.
        """
        prior = self._get_econ_state(
            agent,
            agent.init_state.get("actor_archetype", "civic_moderate") if hasattr(agent, "init_state") else "civic_moderate",
        )
        merged = dict(prior)
        for k in ("perceived_cost", "willingness_band", "primary_objection", "reconsider_condition"):
            v = economic.get(k)
            if isinstance(v, str) and v.strip():
                merged[k] = sanitize_language_drift(v.strip(), label=f"econ_{k}")[:240]

        # Budget tier is authoritative from real data — recomputed, never trusted
        # from the LLM even if it tries to emit one.
        tier = self._budget_tier_for(agent)
        merged["budget_tier"] = tier

        # Impulse: the only LLM-derived number. Clamp to 0–1; keep prior if absent.
        raw_impulse = economic.get("impulse")
        impulse = prior.get("impulse")
        if isinstance(raw_impulse, (int, float)):
            impulse = max(0.0, min(1.0, float(raw_impulse)))
        elif isinstance(raw_impulse, str):
            try:
                impulse = max(0.0, min(1.0, float(raw_impulse.strip())))
            except (ValueError, AttributeError):
                pass
        merged["impulse"] = impulse

        # Disposition = impulse gated by tier (deterministic; no buy score).
        if impulse is not None:
            merged["disposition"] = disposition(impulse, tier)

        try:
            agent.set_skill_state(self._ECON_STATE_KEY, merged)
        except Exception:
            pass
        return merged

    async def execute(
        self,
        agent: PersonAgent,
        round_num: int = 0,
        initial_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute one simulation step with the agent."""
        archetype = agent.init_state.get("actor_archetype", "civic_moderate") if hasattr(agent, 'init_state') else "civic_moderate"

        # Homophily-biased feed: pass this agent's similarity attrs so it mostly
        # reads similar agents (same archetype/group/CURRENT stance) with a small
        # cross-group leak. Stance is read live here, never cached.
        _group = agent.init_state.get("group_affiliation") if hasattr(agent, 'init_state') else None
        _stance = agent.init_state.get("stance") if hasattr(agent, 'init_state') else None
        feed = await self._env.get_feed(
            exclude_agent_id=agent.id,
            archetype=archetype,
            group=_group,
            stance=_stance,
        )
        
        if not feed and archetype in _LOUD_ARCHETYPES:
            initial_prompt = (
                (initial_prompt + " " if initial_prompt else "") +
                "The feed is empty. You MUST choose EXPRESS_OPINION and share your opening view."
            )

        result = await self._single_step_llm(agent, feed, round_num, initial_prompt)

        if result.get("action_type") in (
            OpinionActionType.EXPRESS_OPINION,
            OpinionActionType.RESPOND_TO_OPINION,
        ):
            content = result.get("action_args", {}).get("content", "")
            if content:
                try:
                    agent.set_skill_state("last_opinion", content)
                except Exception as e:
                    logger.debug(f"Failed to store opinion for {agent.name}: {e}")

        return result

    async def _single_step_llm(
        self,
        agent: PersonAgent,
        feed: List[Dict],
        round_num: int,
        initial_prompt: Optional[str],
    ) -> Dict[str, Any]:
        """One LLM call per agent per round."""
        archetype = agent.init_state.get("actor_archetype", "civic_moderate") if hasattr(agent, 'init_state') else "civic_moderate"
        identity_anchor = _build_identity_anchor(archetype, agent)
        char_ctx = await agent.character_context(detail="full")

        recent_feed = feed[-5:]
        feed_preview = "\n".join(
            f"- [{o['agent_name']}] {o['content'][:100]}" for o in recent_feed
        ) or "(empty — be the first to speak)"

        # Topic anchor: use simulation topic from initial_prompt or document context,
        # NOT the agent's personal interested_topics (which causes off-topic drift).
        # In PRODUCT mode the founder's pitch IS the subject — anchor on it directly
        # so "stay on topic" points at the actual product, not the document's first
        # sentence or a random personal interest.
        interested_topics = agent.init_state.get("interested_topics", []) if hasattr(agent, 'init_state') else []
        pitch_topic = (self._pitch.get("what_it_is") or "").strip() if self._mode == "product" else ""
        if pitch_topic:
            topic_hint = pitch_topic
        else:
            sim_topic = self._extract_simulation_topic(initial_prompt)
            topic_hint = sim_topic if sim_topic else (
                random.choice(interested_topics) if interested_topics else "the current situation"
            )

        # Anti-drift rule. Product mode pins every reaction to the founder's pitch
        # — but objections (cost, trust, load-shedding, fit) are still allowed AS
        # reactions to the pitch, never scrubbed.
        if self._mode == "product" and pitch_topic:
            stay_on_topic_rule = (
                f"5. STAY ON THE PITCH. The founder is pitching: {topic_hint}. EVERY reaction must be "
                f"ABOUT this product. You MAY object, doubt it, raise its cost/data/running-cost/trust "
                f"problems, or compare it to how you cope now — but those must be reactions TO the pitch, "
                f"not a tangent. Do NOT drift into unrelated politics or news. If it doesn't touch this "
                f"product, don't say it.\n"
            )
        else:
            stay_on_topic_rule = (
                f"5. STAY ON THIS SCENARIO. The discussion is about: {topic_hint}. EVERY reaction must "
                f"be ABOUT this scenario. You MAY support it, oppose it, doubt it, or explain how it "
                f"affects YOU — but that must be a reaction TO this scenario, not a tangent. Do NOT "
                f"pivot to your generic daily grievances (cost of living, bread/petrol/taxi prices, "
                f"grants) UNLESS this scenario is directly about them. If what you want "
                f"to say doesn't touch this scenario, don't say it.\n"
            )

        # Reply to the most ON-TOPIC recent post, not just the latest one, so the
        # conversation chains back toward the topic instead of following drift.
        # Recency breaks ties; if nothing recent is on-topic, fall back to latest.
        respond_target = recent_feed[-1] if recent_feed else None
        if recent_feed:
            _terms = _topic_terms(topic_hint)
            _best, _best_score = None, 0
            for o in recent_feed:  # in order → latest wins ties via >=
                s = _topic_relevance(o.get("content", ""), _terms)
                if s >= _best_score and s > 0:
                    _best, _best_score = o, s
            if _best is not None:
                respond_target = _best
        respond_ctx = (
            f'[{respond_target["agent_name"]}] said: "{respond_target["content"][:120]}"'
            if respond_target else "(no one to respond to yet)"
        )

        if not feed:
            if archetype in _LOUD_ARCHETYPES:
                action_guidance = (
                    "The opinion feed is EMPTY. You must be one of the first to speak. "
                    "You MUST choose EXPRESS_OPINION. Do not choose OBSERVE or DO_NOTHING."
                )
            else:
                action_guidance = (
                    "The opinion feed is empty. Consider being the first to speak — "
                    "choose EXPRESS_OPINION to open the conversation."
                )
        elif archetype in _LOUD_ARCHETYPES:
            action_guidance = (
                "You are an expressive actor. Choose EXPRESS_OPINION or RESPOND_TO_OPINION. "
                "Never choose OBSERVE or DO_NOTHING while the conversation is active."
            )
        else:
            action_guidance = "Choose whichever action fits your mood and the feed."

        events_section = ""
        if initial_prompt:
            events_section = f"\n{'='*60}\n{initial_prompt}\n{'='*60}\n"

        # Product mode: prepend the economic-reasoning lens (pitch + this agent's
        # current, evolving economic stance). Inert / empty in policy mode.
        economic_section = ""
        if self._mode == "product":
            econ_state = self._get_econ_state(agent, archetype)
            economic_section = build_economic_lens(self._pitch, econ_state)

        # Build context section: document-specific + generic SA
        # In fast mode, only send full context on first encounter, then abbreviated
        is_first_encounter = agent.id not in self._seen_agents
        self._seen_agents.add(agent.id)
        
        if self._fast_mode and not is_first_encounter:
            # Abbreviated prompt for speed (round 2+)
            context_section = (
                f"[CONTINUING SIMULATION — you know the context]\n\n"
                f"You are {agent.name}. {char_ctx.split(chr(10))[0]}\n"  # Only first line of persona
            )
        else:
            # SA context is mode-aware: policy mode gets the full unrest priming;
            # product / custom casts get core grounding only (no riot nudge).
            sa_context = build_sa_context(self._mode)
            if self._document_context:
                context_section = (
                    f"{self._document_context}\n\n"
                    f"GENERAL SOUTH AFRICAN CONTEXT (for background understanding only):\n"
                    f"{sa_context}\n\n"
                )
            else:
                context_section = f"{sa_context}\n\n"
            context_section += f"You are {agent.name}.\n{char_ctx}\n\n"

        # Persistent topic banner — kept in EVERY prompt (not just round 0 / the
        # re-anchor rounds) so the subject is always in front of the agent, right
        # above the feed it's about to react to.
        topic_banner = (
            f"{'='*60}\n"
            f"THIS DISCUSSION IS ABOUT: {topic_hint}\n"
            f"Keep your reaction tied to this. Relating it to your own life is fine; "
            f"drifting onto unrelated things is not.\n"
            f"{'='*60}\n"
        )

        prompt = (
            f"{context_section}"
            f"{events_section}"
            f"{economic_section}"
            f"{topic_banner}"
            f"Current opinion feed:\n{feed_preview}\n\n"
            f"Potential respond target: {respond_ctx}\n"
            f"Topic you care about: {topic_hint}\n\n"
            f"{action_guidance}\n"
            f"{identity_anchor}\n\n"
            f"=== CRITICAL RULES ===\n"
            f"1. EXPRESS OPINIONS — NOT DESCRIPTIONS. Your content must take a STANCE.\n"
            f"   BAD (descriptive): 'The policy has been discussed before.'\n"
            f"   GOOD (opinionated): 'This policy is a band-aid solution. It doesn't address the real issue — the people making these decisions don't live in our community.'\n"
            f"   BAD (neutral): 'This policy aims to help the community.'\n"
            f"   GOOD (stance): 'This policy is going to fail because those implementing it have no skin in the game. They don't see what we deal with daily.'\n"
            f"2. USE LOCAL VOICE. Reference real places, real hardships, real slang. Speak from lived experience.\n"
            f"3. GROUND YOUR OPINIONS IN DOCUMENT FACTS. If the DOCUMENT FACTS section lists specific actors, dates, or events, use them accurately. Do NOT invent facts. You may DISAGREE with facts, but you must not distort them.\n"
            f"   FIGURES ARE FOR REASONING, NOT RECITING. If the document gives numbers (a price, a cost, an income), weigh them against YOUR OWN situation in your own words — e.g. 'that's half my grant' — do NOT read them out like a report ('the price is R50 and data costs R85'). Never state how many people would buy, adopt, or approve; speak only for yourself.\n"
            f"4. DO NOT REPEAT OR ECHO OTHER AGENTS. If [Someone] said a view, do NOT say 'I agree with them' or repeat their point. Say something DIFFERENT — your own view, your own experience, your own angle. NEVER repeat someone else's point.\n"
            f"{stay_on_topic_rule}"
            f"6. If action is EXPRESS_OPINION or RESPOND_TO_OPINION, content MUST be a non-empty string of 1-3 sentences in your character's voice.\n"
            f"7. If action is OBSERVE, SEARCH_TOPIC, or DO_NOTHING, content must be an empty string.\n"
            f"8. You MUST provide 'reason' (why you chose this action) and 'internal_thought' (what you actually think/feel - your true reaction).\n"
            f"9. For ALL actions, internal_thought is REQUIRED - capture your genuine internal reaction regardless of whether you post.\n"
            f"REASON QUALITY RULES:\n"
            f"- If you choose EXPRESS_OPINION or RESPOND_TO_OPINION: explain WHY this topic matters to YOU personally.\n"
            f"- If you choose OBSERVE or DO_NOTHING: your reason MUST be substantive. Explain your emotional state, strategic thinking, or why this topic does not affect you. NEVER give generic reasons like 'nothing interesting' or 'no reason'.\n"
            f"  Good OBSERVE reasons: 'I am too angry to form words right now', 'I do not trust these people enough to speak', 'This policy does not touch my life so I am staying out of it', 'I am watching to see who takes which side before I commit'.\n"
            f"  Good DO_NOTHING reasons: 'I am exhausted from yesterday's argument and need a break', 'Speaking up has never helped me before so I choose silence', 'I am scared of retaliation if I comment'.\n"
            f'Example: {{"action": "EXPRESS_OPINION", "content": "This policy is just lip service. The people making these decisions have never lived a day in our community. They don\'t see what we see every morning.", "reason": "Because this directly affects my family\'s livelihood and I am tired of being ignored", "internal_thought": "I am frustrated that this keeps happening. The anger is building."}}\n'
            f'Example: {{"action": "OBSERVE", "content": "", "reason": "I do not trust these people enough to speak my mind yet", "internal_thought": "This feels pointless. Nothing ever changes no matter what they decide."}}\n'
            f'Example: {{"action": "DO_NOTHING", "content": "", "reason": "I am exhausted from yesterday\'s argument and need a break", "internal_thought": "Let them fight it out. I have my own problems to deal with."}}\n'
            f"ACTION must be exactly one of: EXPRESS_OPINION | RESPOND_TO_OPINION | SEARCH_TOPIC | OBSERVE | DO_NOTHING\n"
            f"Respond with ONLY a raw JSON object on a single line. No markdown. No explanation. No code fences.\n"
            f"JSON:"
        )

        def _clean(text: str) -> str:
            text = re.sub(r"<think>[\s\S]*?</think>", "", text or "").strip()
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
            text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE).strip()
            text = text.strip("`").strip()
            return text

        def _parse(raw: str):
            cleaned = _clean(raw)

            try:
                parsed = json.loads(cleaned)
                return (
                    parsed.get("action", ""),
                    _clean(parsed.get("content", "")),
                    _clean(parsed.get("reason", "")),
                    _clean(parsed.get("internal_thought", ""))
                )
            except Exception:
                pass

            match = re.search(r'\{[^{}]+\}', cleaned, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                    return (
                        parsed.get("action", ""),
                        _clean(parsed.get("content", "")),
                        _clean(parsed.get("reason", "")),
                        _clean(parsed.get("internal_thought", ""))
                    )
                except Exception:
                    pass

            for act in OpinionActionType.ALL:
                if act in cleaned.upper():
                    content_match = re.search(r'"content"\s*:\s*"([^"]*)"', cleaned)
                    content = content_match.group(1) if content_match else ""
                    reason_match = re.search(r'"reason"\s*:\s*"([^"]*)"', cleaned)
                    reason = reason_match.group(1) if reason_match else ""
                    internal_match = re.search(r'"internal_thought"\s*:\s*"([^"]*)"', cleaned)
                    internal = internal_match.group(1) if internal_match else ""
                    return act, _clean(content), _clean(reason), _clean(internal)

            return "", "", "", ""

        def _parse_economic(raw_text: str) -> Dict[str, Any]:
            """Best-effort extraction of the optional 'economic' object (product mode)."""
            if self._mode != "product" or not raw_text:
                return {}
            cleaned = _clean(raw_text)
            m = re.search(r'"economic"\s*:\s*(\{[^{}]*\})', cleaned)
            if not m:
                return {}
            try:
                obj = json.loads(m.group(1))
                return obj if isinstance(obj, dict) else {}
            except Exception:
                return {}

        raw = ""
        action_type = ""
        content = ""
        reason = ""
        internal_thought = ""
        economic_block: Dict[str, Any] = {}
        last_error = None

        # Prepare messages for token counting
        messages = [
            {"role": "system", "content": "You are a South African citizen participating in a policy opinion simulation. Respond with valid JSON only."},
            {"role": "user", "content": prompt}
        ]

        # Capture the raw response so we can read the provider's real billed
        # usage (includes hidden thinking tokens + cache-hit discounts), not
        # just a local tiktoken estimate of the visible content.
        last_response = {"obj": None}

        async def do_llm_call():
            resp = await agent.acompletion(messages)
            last_response["obj"] = resp
            return _extract_llm_content(resp)

        # Local estimate of prompt tokens — used only as a fallback when the
        # provider doesn't return a usage object.
        prompt_tokens = self._token_counter.count_messages(messages)

        for attempt in range(2):
            try:
                raw = await llm_call_with_retry(
                    do_llm_call,
                    max_retries=2,
                    base_delay=1.0,
                    agent_name=agent.name,
                )
                action_type, content, reason, internal_thought = _parse(raw)
                economic_block = _parse_economic(raw)

                content = sanitize_language_drift(content, label=f"opinion_{agent.name}")
                reason = sanitize_language_drift(reason, label=f"reason_{agent.name}")
                internal_thought = sanitize_language_drift(internal_thought, label=f"thought_{agent.name}")

                if action_type and (content or action_type not in (
                    OpinionActionType.EXPRESS_OPINION,
                    OpinionActionType.RESPOND_TO_OPINION,
                )):
                    break

                if attempt == 0:
                    logger.debug(
                        f"Agent {agent.name} attempt 1 gave empty content "
                        f"(action={action_type!r}), retrying..."
                    )
            except Exception as e:
                last_error = e
                logger.warning(f"LLM call failed for {agent.name} attempt {attempt+1}: {e}")

        # Prefer the provider's REAL billed usage (thinking tokens + cache-hit
        # discounts are only visible here). Fall back to the local tiktoken
        # estimate when the provider omits usage. A real completion count far
        # above the visible text length is the signature of "thinking" tokens
        # leaking onto the sim path — that's what this measurement surfaces.
        real_usage = _extract_usage(last_response["obj"])
        if real_usage is not None:
            prompt_tokens, completion_tokens = real_usage
        else:
            completion_tokens = self._token_counter.count_text(raw)
        token_cost = self._token_counter.estimate_cost(prompt_tokens, completion_tokens)
        self._total_prompt_tokens += prompt_tokens
        self._total_completion_tokens += completion_tokens
        self._total_estimated_cost = round(self._total_estimated_cost + token_cost, 6)

        logger.debug(
            f"Agent {agent.name} tokens  prompt={prompt_tokens}  "
            f"completion={completion_tokens}  cost=${token_cost:.6f}  "
            f"({'real' if real_usage else 'estimated'})"
        )

        token_info = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "estimated_cost_usd": token_cost,
        }

        if not action_type:
            action_type = (
                OpinionActionType.EXPRESS_OPINION
                if (archetype in _LOUD_ARCHETYPES or not feed)
                else OpinionActionType.OBSERVE
            )

        if action_type not in OpinionActionType.ALL:
            action_type = (
                OpinionActionType.EXPRESS_OPINION if not feed else OpinionActionType.OBSERVE
            )

        if not reason:
            reason = f"Chosen action: {action_type}"
        if not internal_thought:
            internal_thought = f"Agent {agent.name} reflected on the current situation."

        # Enrich weak/generic reasons for non-posting actions
        reason = await _enrich_reason_async(agent, action_type, reason, archetype)

        impact_score = _calculate_impact_score(internal_thought, action_type)

        # Product mode: merge the LLM's economic block into the agent's evolving
        # state and serialize it for persistence on posting actions. None in policy.
        economic_reasoning_json: Optional[str] = None
        # needed_fact: a transient per-round signal that the agent wanted a real
        # cost not provided in YOUR REAL NUMBERS. Collected by the runner into
        # fact_gaps.jsonl — NOT persisted into econ state. "" / None when the
        # agent didn't need anything.
        needed_fact: Optional[str] = None
        if self._mode == "product":
            merged_econ = self._update_econ_state(agent, economic_block)
            economic_reasoning_json = json.dumps(merged_econ, ensure_ascii=False)
            _nf = economic_block.get("needed_fact")
            if isinstance(_nf, str) and _nf.strip() and _nf.strip().lower() not in ("none", "n/a", "na"):
                needed_fact = sanitize_language_drift(_nf.strip(), label="needed_fact")[:160]

        if action_type == OpinionActionType.EXPRESS_OPINION:
            if not content:
                # Re-count fallback prompt tokens
                fallback_messages = [
                    {"role": "system", "content": f"You are {agent.name}, a South African citizen."},
                    {"role": "user", "content": (
                        f"You are {agent.name}. {archetype} persona. "
                        f"In ONE sentence, give your raw gut reaction to: {topic_hint}. "
                        f"No JSON, no formatting. Just speak."
                    )}
                ]
                fb_prompt_tokens = self._token_counter.count_messages(fallback_messages)
                try:
                    async def do_fallback():
                        return _extract_llm_content(await agent.acompletion(fallback_messages))
                    fallback_raw = await llm_call_with_retry(
                        do_fallback,
                        max_retries=1,
                        base_delay=0.5,
                        agent_name=agent.name,
                    )
                    fb_completion_tokens = self._token_counter.count_text(fallback_raw)
                    fb_cost = self._token_counter.estimate_cost(fb_prompt_tokens, fb_completion_tokens)
                    self._total_prompt_tokens += fb_prompt_tokens
                    self._total_completion_tokens += fb_completion_tokens
                    self._total_estimated_cost = round(self._total_estimated_cost + fb_cost, 6)
                    token_info["prompt_tokens"] += fb_prompt_tokens
                    token_info["completion_tokens"] += fb_completion_tokens
                    token_info["estimated_cost_usd"] = round(token_info["estimated_cost_usd"] + fb_cost, 6)
                    content = re.sub(r"<think>[\s\S]*?</think>", "", fallback_raw or "").strip()
                    content = content.strip('"').strip()
                    content = sanitize_language_drift(content, label=f"fallback_{agent.name}")
                except Exception:
                    pass
            if not content:
                # Fallback to OBSERVE with a meaningful silence reason
                observe_reason = reason if reason and not _is_weak_reason(reason, OpinionActionType.OBSERVE) else _archetype_silence_reason(archetype)
                return {
                    "action_type": OpinionActionType.OBSERVE,
                    "action_args": {"feed_size": len(feed), "reason": "llm_empty"},
                    "success": True,
                    "reason": observe_reason,
                    "internal_thought": internal_thought or "Agent was unable to generate thoughts.",
                    "impact_score": impact_score,
                    **token_info,
                }
            opinion_id = await self._env.add_opinion(
                agent.id, agent.name, content, [topic_hint], round_num,
                reason=reason, internal_thought=internal_thought, impact_score=impact_score,
                economic_reasoning=economic_reasoning_json
            )
            # Record post in agent's memory for interview context
            if hasattr(agent, 'record_post'):
                agent.record_post(round_num, "EXPRESS_OPINION", content, impact_score)
            result = {
                "action_type": OpinionActionType.EXPRESS_OPINION,
                "action_args": {"content": content, "topics": [topic_hint], "opinion_id": opinion_id},
                "success": True,
                "reason": reason,
                "internal_thought": internal_thought,
                "impact_score": impact_score,
                **token_info,
            }
            if economic_reasoning_json is not None:
                result["economic_reasoning"] = economic_reasoning_json
            if needed_fact:
                result["needed_fact"] = needed_fact
            return result

        elif action_type == OpinionActionType.RESPOND_TO_OPINION:
            if not respond_target or not content:
                # Fallback to OBSERVE with a meaningful silence reason
                observe_reason = reason if reason and not _is_weak_reason(reason, OpinionActionType.OBSERVE) else _archetype_silence_reason(archetype)
                return {
                    "action_type": OpinionActionType.OBSERVE,
                    "action_args": {"feed_size": len(feed), "reason": "no_respond_content"},
                    "success": True,
                    "reason": observe_reason,
                    "internal_thought": internal_thought or "No strong reason to respond to anyone.",
                    "impact_score": impact_score,
                    **token_info,
                }
            await self._env.add_response(
                agent.id, agent.name, respond_target["id"], content, round_num,
                reason=reason, internal_thought=internal_thought, impact_score=impact_score
            )
            # Record post in agent's memory for interview context
            if hasattr(agent, 'record_post'):
                agent.record_post(round_num, "RESPOND_TO_OPINION", content, impact_score)
            result = {
                "action_type": OpinionActionType.RESPOND_TO_OPINION,
                "action_args": {
                    "content":           content,
                    "target_opinion_id": respond_target["id"],
                    "target_agent_name": respond_target["agent_name"],
                    "target_content":    respond_target["content"][:100],
                },
                "success": True,
                "reason": reason,
                "internal_thought": internal_thought,
                "impact_score": impact_score,
                **token_info,
            }
            if economic_reasoning_json is not None:
                result["economic_reasoning"] = economic_reasoning_json
            if needed_fact:
                result["needed_fact"] = needed_fact
            return result

        elif action_type == OpinionActionType.SEARCH_TOPIC:
            results = await self._env.search(topic_hint)
            return {
                "action_type": OpinionActionType.SEARCH_TOPIC,
                "action_args": {"query": topic_hint, "results_count": len(results)},
                "success": True,
                "reason": reason,
                "internal_thought": internal_thought,
                "impact_score": impact_score,
                **token_info,
            }

        elif action_type == OpinionActionType.OBSERVE:
            return {
                "action_type": OpinionActionType.OBSERVE,
                "action_args": {"feed_size": len(feed)},
                "success": True,
                "reason": reason,
                "internal_thought": internal_thought,
                "impact_score": impact_score,
                **token_info,
            }

        else:
            return {
                "action_type": OpinionActionType.DO_NOTHING,
                "action_args": {},
                "success": True,
                "reason": reason,
                "internal_thought": internal_thought,
                "impact_score": impact_score,
                **token_info,
            }

    def get_token_stats(self) -> Dict[str, any]:
        """Return cumulative token usage and estimated cost for this skill."""
        return {
            "total_prompt_tokens": self._total_prompt_tokens,
            "total_completion_tokens": self._total_completion_tokens,
            "total_tokens": self._total_prompt_tokens + self._total_completion_tokens,
            "estimated_cost_usd": self._total_estimated_cost,
            "model": self._token_counter.model_name,
            "pricing": self._token_counter.get_pricing_info(),
        }