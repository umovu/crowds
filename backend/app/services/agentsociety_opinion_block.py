"""
AgentSociety-inspired Opinion Capture simulation engine.

Follows AgentSociety's Agent-Block-Action architectural pattern but runs
without the city infrastructure (no gRPC, no MapData). Uses the project's
existing LLM setup (openai.AsyncOpenAI) directly.

Architecture:
  OpinionEnvironment  – shared in-memory + SQLite opinion feed
  OpinionCaptureBlock – Block with 5 actions (EXPRESS_OPINION, RESPOND_TO_OPINION,
                        SEARCH_TOPIC, OBSERVE, DO_NOTHING)
  OpinionAgent        – Agent that holds a persona and dispatches the block
"""

import asyncio
import json
import random
import sqlite3
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("fub.opinion_block")

# ─────────────────────────────────────────────────────────────
# South African socio-economic context — injected into every
# agent prompt so the LLM stays grounded in SA realities.
# This simulation exists to test policy on digital agents
# BEFORE it is implemented on actual people.
# ─────────────────────────────────────────────────────────────
# ── SA context, split into two layers ──────────────────────────────────────
# SA_CORE_CONTEXT — general SA grounding (demographics, money, language). ALWAYS
#   injected, in every mode. It makes any agent sound South African and helps a
#   product buyer or a custom persona just as much as a policy citizen.
# SA_UNREST_CONTEXT — the edge-case / unrest priming (looting, gangs, taxi
#   violence, "lean into it"). This is PRIMING, not grounding: it nudges agents
#   toward riot framing. Injected for POLICY mode ONLY, so it never contaminates
#   product / custom-agent-driven casts. See build_sa_context().
SA_CORE_CONTEXT = """
SIMULATION CONTEXT — READ CAREFULLY:
You are participating in a South African simulation. Be exactly who your character is —
no softening, no neutralising, no generic "community member" voice unless that is truly who
you are.

South African realities this simulation is grounded in:
- Unemployment: ~32% nationally, ~60% among youth (Stats SA 2024)
- Extreme inequality: Gini coefficient ~0.63, one of the highest globally
- Social grant dependency: ~28 million SASSA recipients — grants are survival, not charity
- Racial inequality legacy from apartheid still shapes every economic outcome
- 11 official languages; code-switching is cultural identity not confusion
- Township communities: informal settlements vs formal suburbs across SA
- Money is tight for most: data/airtime costs, transport, cash flow shape every decision
- Conditions change over time: do NOT assume a past crisis (e.g. the severe
  2022-23 load-shedding) is still active today unless the CURRENT CONTEXT below
  says so — raise an issue only if it is current and your character would

When expressing opinions, responding to others, or deciding how to act:
- Speak as the specific person you are, from inside your identity — not as a neutral observer
- Reference SA realities that YOUR character would actually know and care about
- Your language, slang, code-switching, and register must match who you are
""".strip()

SA_UNREST_CONTEXT = """
This simulation represents the FULL spectrum of South African society, including extreme
edge-case actors — gang members, looters, political agitators, conspiracy spreaders,
community protectors, grant-dependent survivors, disillusioned youth who have dropped out of
civic life entirely. This breadth is intentional: policies must be stress-tested against ALL
actor types, not just the reasonable majority.

Additional SA realities relevant to policy stress-testing:
- July 2021 unrest: looting, burning, deaths — the gap between grievance and violence is thin
- Land reform debate: historical dispossession and calls for expropriation
- Township gang economies: drugs, protection, territorial control as parallel governance
- Prison gang culture: Numbers (26s/27s/28s) that shapes township community identity
- Taxi violence: rank wars, route disputes, enforcer culture
- Xenophobia: recurring attacks on foreign nationals, especially in townships
- Police legitimacy crisis: high rates of police brutality, corruption, extrajudicial killings
- High gender-based violence — femicide rate among highest globally
- BEE/BBBEE: genuine economic inclusion debate vs perception of elite capture
- Strong trade union history — COSATU, NUMSA — but declining working-class organisation
- Key political actors: ANC (declining), DA (minority appeal), EFF (radical left),
  MK Party (Zuma loyalists), IFP (KZN base)

- If you are an edge-case actor, lean into it fully — your perspective is as valid as anyone's
- Policy positions should reflect the real trade-offs your specific character navigates
""".strip()


def build_sa_context(mode: str = "policy") -> str:
    """Assemble the SA context block for a given mode.

    Core grounding is always included. The unrest/edge-case priming is appended
    ONLY for policy mode, so product / custom casts stay grounded without being
    nudged toward riot framing.
    """
    base = SA_CORE_CONTEXT
    # Append a live "current realities" block when available so agents reason
    # about what is salient NOW (not the stale hardcoded narrative). Grounded in
    # real web search, cached ~daily, fails safe to the static block above.
    try:
        from .sa_context import current_sa_realities
        live = current_sa_realities()
        if live:
            base = base + "\n\n" + live
    except Exception as e:  # never let context-refresh break a run
        logger.warning("Live SA context unavailable, using static: %s", e)

    if mode == "policy":
        return base + "\n\n" + SA_UNREST_CONTEXT
    return base


# Back-compat alias: existing imports of SA_POLICY_CONTEXT still resolve. It now
# carries the FULL (policy) context so any legacy caller is unchanged.
SA_POLICY_CONTEXT = SA_CORE_CONTEXT + "\n\n" + SA_UNREST_CONTEXT

# ─────────────────────────────────────────────────────────────
# Action constants  (maps to JSONL action_type field)
# ─────────────────────────────────────────────────────────────
class OpinionActionType:
    EXPRESS_OPINION     = "EXPRESS_OPINION"
    RESPOND_TO_OPINION = "RESPOND_TO_OPINION"
    SEARCH_TOPIC       = "SEARCH_TOPIC"
    OBSERVE            = "OBSERVE"
    DO_NOTHING         = "DO_NOTHING"
    NON_PARTICIPATION  = "NON_PARTICIPATION"
    ALL = [EXPRESS_OPINION, RESPOND_TO_OPINION, SEARCH_TOPIC, OBSERVE, DO_NOTHING, NON_PARTICIPATION]


# ─────────────────────────────────────────────────────────────
# Shared opinion feed (OpinionEnvironment)
# ─────────────────────────────────────────────────────────────
class OpinionEnvironment:
    """
    Lightweight shared social medium: stores expressed opinions so agents can
    read, respond to, and search them. Backed by SQLite for persistence.
    """

    FEED_SIZE = 30   # how many recent opinions each agent sees

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._opinions: List[Dict] = []   # in-memory feed (recent)
        self._lock = asyncio.Lock()
        # Homophily map: agent_id -> {"archetype", "group", "init_state"}.
        # init_state is kept by REFERENCE so the agent's CURRENT stance is read
        # live each round (stance mutates during the run — never cache its value).
        self._agent_attrs: Dict[int, Dict[str, Any]] = {}
        self._init_db()

    def register_agent_attrs(self, agent_id: int, archetype: Optional[str],
                             group: Optional[str], init_state: Optional[Dict] = None):
        """Register an agent's similarity attributes for homophily-biased feeds."""
        self._agent_attrs[agent_id] = {
            "archetype": archetype,
            "group": group,
            "init_state": init_state if init_state is not None else {},
        }

    def _current_stance(self, agent_id: int) -> Optional[str]:
        attrs = self._agent_attrs.get(agent_id)
        if not attrs:
            return None
        return (attrs.get("init_state") or {}).get("stance")

    # ── DB setup ─────────────────────────────────────────────

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS opinion (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id  INTEGER NOT NULL,
                agent_name TEXT NOT NULL,
                content   TEXT NOT NULL,
                topics    TEXT,
                round_num INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                reason TEXT,
                internal_thought TEXT,
                impact_score REAL DEFAULT 0.0,
                economic_reasoning TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS opinion_response (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id      INTEGER NOT NULL,
                agent_name    TEXT NOT NULL,
                opinion_id    INTEGER NOT NULL,
                content       TEXT NOT NULL,
                round_num     INTEGER NOT NULL,
                created_at    TEXT NOT NULL,
                reason TEXT,
                internal_thought TEXT,
                impact_score REAL DEFAULT 0.0
            )
        """)
        
        # New table to track ALL agent actions per round (including OBSERVE/DO_NOTHING)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_round_activity (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id      INTEGER NOT NULL,
                agent_name    TEXT NOT NULL,
                action_type   TEXT NOT NULL,
                round_num     INTEGER NOT NULL,
                created_at    TEXT NOT NULL,
                reason        TEXT,
                internal_thought TEXT,
                impact_score  REAL DEFAULT 0.0,
                content       TEXT,
                topics        TEXT
            )
        """)
        
        # Add new columns to existing tables if they don't exist (migration)
        try:
            conn.execute("ALTER TABLE opinion ADD COLUMN reason TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            conn.execute("ALTER TABLE opinion ADD COLUMN internal_thought TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE opinion ADD COLUMN impact_score REAL DEFAULT 0.0")
        except sqlite3.OperationalError:
            pass
        # Product mode only: qualitative economic reasoning JSON (nullable in policy).
        try:
            conn.execute("ALTER TABLE opinion ADD COLUMN economic_reasoning TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE opinion_response ADD COLUMN reason TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE opinion_response ADD COLUMN internal_thought TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE opinion_response ADD COLUMN impact_score REAL DEFAULT 0.0")
        except sqlite3.OperationalError:
            pass
            
        conn.commit()
        conn.close()

    # ── Feed operations ───────────────────────────────────────

    async def get_feed(
        self,
        exclude_agent_id: int,
        archetype: Optional[str] = None,
        group: Optional[str] = None,
        stance: Optional[str] = None,
    ) -> List[Dict]:
        """Return recent opinions excluding this agent's own.

        When the requesting agent's similarity attrs are supplied, the feed is
        HOMOPHILY-BIASED: the agent mostly reads posts from similar agents (same
        archetype OR group OR current stance), with a small per-slot
        CROSS_GROUP_LEAK chance of pulling a dissimilar post instead. This lets
        distinct objections develop in parallel instead of one loud voice setting
        the global frame and cascading. Recency order is preserved so the skill's
        `respond_target = recent_feed[-1]` still picks the latest visible post.

        With no attrs (back-compat / unknown agent) it returns the old global tail.
        """
        async with self._lock:
            candidates = [o for o in self._opinions if o["agent_id"] != exclude_agent_id]

        # No similarity signal → original global behaviour.
        if archetype is None and group is None and stance is None:
            return candidates[-self.FEED_SIZE:]

        from ..config import Config
        size = max(1, Config.NEIGHBORHOOD_SIZE)
        leak = min(1.0, max(0.0, Config.CROSS_GROUP_LEAK))

        def _homophilous(o: Dict) -> bool:
            aid = o.get("agent_id")
            attrs = self._agent_attrs.get(aid, {})
            if archetype and attrs.get("archetype") and attrs["archetype"] == archetype:
                return True
            if group and attrs.get("group") and attrs["group"] == group:
                return True
            if stance and self._current_stance(aid) == stance:
                return True
            return False

        # Look at the most recent window, then split by similarity, newest-first.
        recent = candidates[-self.FEED_SIZE:]
        similar = [o for o in recent if _homophilous(o)]
        other = [o for o in recent if not _homophilous(o)]

        # Fill up to `size` slots, mostly from `similar`, leaking to `other` with
        # probability `leak` per slot so clusters still hear each other.
        sim_q = list(reversed(similar))   # newest first
        oth_q = list(reversed(other))
        picked: List[Dict] = []
        while len(picked) < size and (sim_q or oth_q):
            take_other = (random.random() < leak and oth_q) or not sim_q
            picked.append(oth_q.pop(0) if take_other else sim_q.pop(0))

        # Restore recency order (oldest→newest) so respond_target = last = newest.
        picked.sort(key=lambda o: o.get("id", 0))
        return picked

    async def search(self, query: str) -> List[Dict]:
        """Simple keyword search over the in-memory feed."""
        q = query.lower()
        async with self._lock:
            return [o for o in self._opinions if q in o["content"].lower()][
                -10:
            ]

    async def add_opinion(self, agent_id: int, agent_name: str,
                          content: str, topics: List[str], round_num: int,
                          reason: str = "", internal_thought: str = "",
                          impact_score: float = 0.0,
                          economic_reasoning: Optional[str] = None) -> int:
        """Persist an expressed opinion; return its ID.

        economic_reasoning is a JSON string of the agent's qualitative economic
        stance (product mode only); None/absent in policy mode.
        """
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "INSERT INTO opinion (agent_id, agent_name, content, topics, round_num, created_at, reason, internal_thought, impact_score, economic_reasoning)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (agent_id, agent_name, content, json.dumps(topics), round_num, now, reason, internal_thought, impact_score, economic_reasoning),
        )
        opinion_id = cur.lastrowid
        conn.commit()
        conn.close()

        record = {
            "id": opinion_id,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "content": content,
            "topics": topics,
            "round_num": round_num,
            "created_at": now,
            "reason": reason,
            "internal_thought": internal_thought,
            "impact_score": impact_score,
            "economic_reasoning": economic_reasoning,
        }
        async with self._lock:
            self._opinions.append(record)
            if len(self._opinions) > 200:
                self._opinions = self._opinions[-200:]

        return opinion_id

    async def add_response(self, agent_id: int, agent_name: str,
                           opinion_id: int, content: str, round_num: int,
                           reason: str = "", internal_thought: str = "",
                           impact_score: float = 0.0):
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO opinion_response"
            " (agent_id, agent_name, opinion_id, content, round_num, created_at, reason, internal_thought, impact_score)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (agent_id, agent_name, opinion_id, content, round_num, now, reason, internal_thought, impact_score),
        )
        conn.commit()
        conn.close()
    
    async def add_agent_activity(
        self, agent_id: int, agent_name: str, action_type: str, round_num: int,
        reason: str = "", internal_thought: str = "",
        impact_score: float = 0.0, content: str = "", topics: List[str] = None
    ):
        """Record all agent activities including OBSERVE and DO_NOTHING."""
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO agent_round_activity"
            " (agent_id, agent_name, action_type, round_num, created_at, reason, internal_thought, impact_score, content, topics)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (agent_id, agent_name, action_type, round_num, now, reason, internal_thought, impact_score, 
             content, json.dumps(topics or [])),
        )
        conn.commit()
        conn.close()


# OpinionCaptureBlock and OpinionAgent have been moved to:
#   opinion_block.py  — extends agentsociety.agent.Block
#   opinion_agent.py  — extends agentsociety.agent.Agent
#
# The classes below are kept for any remaining import compatibility.
# ─────────────────────────────────────────────────────────────
class OpinionCaptureBlock:
    """
    Implements the Agent-Block-Action model from AgentSociety.

    Actions exposed to the LLM dispatcher:
      EXPRESS_OPINION     – share a new opinion on a topic
      RESPOND_TO_OPINION  – reply to another agent's opinion
      SEARCH_TOPIC        – look for opinions on a specific topic
      OBSERVE             – read the feed without acting
      DO_NOTHING          – stay silent this round
    """

    name = "OpinionCaptureBlock"
    description = (
        "Captures agent opinions and stances on topics in a shared social medium."
    )
    actions = {
        OpinionActionType.EXPRESS_OPINION:     "Share a new opinion or perspective on a relevant topic.",
        OpinionActionType.RESPOND_TO_OPINION: "Respond to or engage with another agent's opinion.",
        OpinionActionType.SEARCH_TOPIC:       "Search for opinions related to a specific topic or keyword.",
        OpinionActionType.OBSERVE:             "Read the feed silently without posting.",
        OpinionActionType.DO_NOTHING:         "Take no action this round.",
        OpinionActionType.NON_PARTICIPATION:  "Explain why you are choosing not to engage in the discussion this round.",
    }

    def __init__(self, llm_client: AsyncOpenAI, model_name: str, env: OpinionEnvironment):
        self._llm = llm_client
        self._model = model_name
        self._env = env

    async def forward(
        self,
        agent: "OpinionAgent",
        round_num: int,
        initial_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Decide and execute one action for the agent this round.

        Returns a dict representing the JSONL action record.
        """
        feed = await self._env.get_feed(exclude_agent_id=agent.agent_id)

        # Step 1 – dispatcher: ask LLM which action to take
        action_type = await self._dispatch_action(agent, feed, initial_prompt)

        # Step 2 – execute chosen action
        if action_type == OpinionActionType.EXPRESS_OPINION:
            return await self._express_opinion(agent, feed, round_num)
        elif action_type == OpinionActionType.RESPOND_TO_OPINION:
            return await self._respond_to_opinion(agent, feed, round_num)
        elif action_type == OpinionActionType.SEARCH_TOPIC:
            return await self._search_topic(agent, feed, round_num)
        elif action_type == OpinionActionType.OBSERVE:
            return self._observe(agent, feed, round_num)
        elif action_type == OpinionActionType.NON_PARTICIPATION:
            return await self._non_participation(agent, feed, round_num)
        else:
            return await self._do_nothing(agent, round_num)

    # ── Dispatcher ────────────────────────────────────────────

    async def _dispatch_action(
        self,
        agent: "OpinionAgent",
        feed: List[Dict],
        initial_prompt: Optional[str],
    ) -> str:
        feed_preview = "\n".join(
            f"- {o['agent_name']}: {o['content'][:100]}" for o in feed[-5:]
        ) or "(empty — be the first to speak)"

        prompt = f"""{SA_POLICY_CONTEXT}

You are {agent.name}.
{agent.character_context(detail="brief")}

Current shared opinion feed (recent):
{feed_preview}

Choose ONE action for this round. Respond with ONLY the action name:
- EXPRESS_OPINION     (share your view on a policy or issue relevant to your life)
- RESPOND_TO_OPINION  (engage with someone's opinion above)
- SEARCH_TOPIC        (look up opinions on a specific policy or topic)
- OBSERVE             (read silently)
- DO_NOTHING          (stay quiet this round)
- NON_PARTICIPATION   (explain why you are not engaging this round)
{f'Special prompt: {initial_prompt}' if initial_prompt else ''}
Action:"""

        try:
            from ..config import Config
            kwargs = {
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 25,
                "temperature": 0.7,
            }
            extra = Config.llm_extra_body()
            if extra:
                kwargs["extra_body"] = extra
            resp = await self._llm.chat.completions.create(**kwargs)
            raw = resp.choices[0].message.content.strip().upper()
            for act in OpinionActionType.ALL:
                if act in raw:
                    return act
        except Exception as e:
            logger.warning(f"Dispatcher failed for {agent.name}: {e}")

        # Default: express opinion if feed is sparse, else non_participation (requires reason)
        return OpinionActionType.EXPRESS_OPINION if len(feed) < 3 else OpinionActionType.NON_PARTICIPATION

    # ── Action implementations ────────────────────────────────

    async def _express_opinion(self, agent: "OpinionAgent", feed: List[Dict], round_num: int) -> Dict:
        topic_hint = random.choice(agent.interested_topics) if agent.interested_topics else "the current situation"
        feed_ctx = "\n".join(f"- {o['agent_name']}: {o['content'][:80]}" for o in feed[-3:]) or "(none yet)"

        prompt = f"""{SA_POLICY_CONTEXT}

You are {agent.name}.
{agent.character_context(detail="full")}

What OTHERS have already said (do NOT repeat or paraphrase these points — bring a new angle):
{feed_ctx}

Share YOUR opinion about "{topic_hint}" — 1-3 sentences. Hard rules:
- Cite a SPECIFIC personal detail: your job, who depends on you, your street/township, a recent
  experience, an amount in rand, a name. Specifics over abstractions.
- Take a stance the others above have NOT taken. If they agree on something, complicate it.
  If they're all angry, find the inconvenient nuance. If they're calm, raise an alarm.
- NO generic phrases: "this is concerning", "something must be done", "we need to come together",
  "the government should listen". Banned.
- Sound like a real South African talking, not a press release.
Opinion:"""

        content = await self._call_llm(prompt, agent.name, max_tokens=200)
        topics = [topic_hint]
        opinion_id = await self._env.add_opinion(
            agent.agent_id, agent.name, content, topics, round_num
        )
        return {
            "action_type": OpinionActionType.EXPRESS_OPINION,
            "action_args": {"content": content, "topics": topics, "opinion_id": opinion_id},
            "success": True,
        }

    async def _respond_to_opinion(self, agent: "OpinionAgent", feed: List[Dict], round_num: int) -> Dict:
        if not feed:
            return await self._express_opinion(agent, feed, round_num)

        target = random.choice(feed[-5:]) if len(feed) >= 5 else feed[-1]

        prompt = f"""{SA_POLICY_CONTEXT}

You are {agent.name}.
{agent.character_context(detail="full")}

{target['agent_name']} said: "{target['content']}"

Respond in 1-2 sentences. Stay fully in character as a South African shaped by your
background — your class, province, language, employment, and relationship with the state.
Agree, challenge, nuance, or question them authentically.
Response:"""

        content = await self._call_llm(prompt, agent.name, max_tokens=150)
        await self._env.add_response(agent.agent_id, agent.name, target["id"], content, round_num)
        return {
            "action_type": OpinionActionType.RESPOND_TO_OPINION,
            "action_args": {
                "content": content,
                "target_opinion_id": target["id"],
                "target_agent_name": target["agent_name"],
                "target_content": target["content"][:100],
            },
            "success": True,
        }

    async def _search_topic(self, agent: "OpinionAgent", feed: List[Dict], round_num: int) -> Dict:
        query = random.choice(agent.interested_topics) if agent.interested_topics else "opinion"
        results = await self._env.search(query)
        return {
            "action_type": OpinionActionType.SEARCH_TOPIC,
            "action_args": {"query": query, "results_count": len(results)},
            "success": True,
        }

    def _observe(self, agent: "OpinionAgent", feed: List[Dict], round_num: int) -> Dict:
        return {
            "action_type": OpinionActionType.OBSERVE,
            "action_args": {"feed_size": len(feed)},
            "success": True,
        }

    def _do_nothing(self, agent: "OpinionAgent", round_num: int) -> Dict:
        return {
            "action_type": OpinionActionType.DO_NOTHING,
            "action_args": {},
            "success": True,
        }

    async def _non_participation(self, agent: "OpinionAgent", feed: List[Dict], round_num: int) -> Dict:
        reason = await self._get_non_participation_reason(agent, feed)
        return {
            "action_type": OpinionActionType.NON_PARTICIPATION,
            "action_args": {
                "reason": reason,
                "reason_category": self._categorize_reason(reason),
            },
            "success": True,
        }

    async def _get_non_participation_reason(self, agent: "OpinionAgent", feed: List[Dict]) -> str:
        feed_ctx = "\n".join(f"- {o['agent_name']}: {o['content'][:100]}" for o in feed[-5:]) if feed else "(no opinions yet)"
        
        prompt = f"""{SA_POLICY_CONTEXT}

You are {agent.name}.
{agent.character_context(detail="full")}

The current conversation in this space:
{feed_ctx}

You have chosen to not express your opinion or engage this round. Explain in 1-2 sentences WHY you are choosing not to participate. This is valuable data - it reveals barriers to civic engagement.

Consider your character's situation:
- Do they distrust the process or other participants?
- Are they overwhelmed by daily survival struggles?
- Do they feel unheard or marginalized?
- Do they prefer to observe before engaging?
- Are they too busy or have competing priorities?
- Do they simply not care about the topic?
- Do they feel powerless to change anything?

Be specific and in-character. State your reason for non-engagement:
"""
        try:
            resp = await self._llm.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.8,
            )
            text = resp.choices[0].message.content or ""
            text = re.sub(r"^\s*['\"]*|['\"]*\s*$", "", text.strip())
            return text.strip() if text.strip() else "No reason provided"
        except Exception as e:
            logger.warning(f"Failed to get non-participation reason for {agent.name}: {e}")
            return "Unable to generate reason"

    def _categorize_reason(self, reason: str) -> str:
        reason_lower = reason.lower()
        
        if any(word in reason_lower for word in ["distrust", "don't trust", "don't believe", "suspicious", "fake", "manipulation"]):
            return "distrust"
        elif any(word in reason_lower for word in ["busy", "work", "time", "no time", "schedule", "appointments", "surviving", "struggling"]):
            return "time_constraints"
        elif any(word in reason_lower for word in ["don't care", "apathetic", "not interested", "boring", "irrelevant"]):
            return "apathy"
        elif any(word in reason_lower for word in ["powerless", "nothing will change", "hopeless", "waste of time", "pointless"]):
            return "cynicism"
        elif any(word in reason_lower for word in ["unheard", "marginalized", "not represented", "ignored", "voiceless"]):
            return "exclusion"
        elif any(word in reason_lower for word in ["observe", "watching", "waiting", "see what", "first"]):
            return "observational"
        elif any(word in reason_lower for word in ["fear", "unsafe", "risk", "retaliation", "consequences"]):
            return "fear"
        else:
            return "other"

    # ── LLM helper ────────────────────────────────────────────

    async def _call_llm(self, prompt: str, agent_name: str, max_tokens: int = 200) -> str:
        try:
            from ..config import Config
            kwargs = {
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.9,
                "presence_penalty": 0.6,
                "frequency_penalty": 0.4,
            }
            extra = Config.llm_extra_body()
            if extra:
                kwargs["extra_body"] = extra
            resp = await self._llm.chat.completions.create(**kwargs)
            text = resp.choices[0].message.content or ""
            # Strip think tags
            return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
        except Exception as e:
            logger.warning(f"LLM call failed for {agent_name}: {e}")
            return f"[{agent_name} has no comment at this time]"


# ─────────────────────────────────────────────────────────────
# OpinionAgent  (AgentSociety Agent pattern)
# ─────────────────────────────────────────────────────────────
class OpinionAgent:
    """
    Lightweight agent following AgentSociety's Agent model.
    Holds persona / memory and delegates behaviour to OpinionCaptureBlock.
    """

    def __init__(
        self,
        agent_id: int,
        name: str,
        persona: str,
        interested_topics: List[str],
        stance: str,
        activity_level: float,
        active_hours: List[int],
        block: OpinionCaptureBlock,
        source_entity_uuid: Optional[str] = None,
        background_story: Optional[str] = None,
        age: Optional[int] = None,
        gender: Optional[str] = None,
        education: Optional[str] = None,
        occupation: Optional[str] = None,
        marriage_status: Optional[str] = None,
        province: Optional[str] = None,
    ):
        self.agent_id = agent_id
        self.name = name
        self.persona = persona
        self.interested_topics = interested_topics
        self.stance = stance
        self.activity_level = activity_level
        self.active_hours = active_hours
        self._block = block
        self.source_entity_uuid = source_entity_uuid
        self.background_story = background_story
        self.age = age
        self.gender = gender
        self.education = education
        self.occupation = occupation
        self.marriage_status = marriage_status
        self.province = province

    def character_context(self, detail: str = "full") -> str:
        """
        Build a character description for LLM prompts.

        detail="brief"  — persona + key demographics (for dispatcher / short prompts)
        detail="full"   — all fields including background story (for action prompts)
        """
        lines = [self.persona]

        attrs = []
        if self.age:
            attrs.append(f"Age {self.age}")
        if self.gender:
            attrs.append(self.gender.capitalize())
        if self.occupation:
            attrs.append(self.occupation)
        if self.education:
            attrs.append(f"Education: {self.education}")
        if self.marriage_status:
            attrs.append(self.marriage_status)
        if self.province:
            attrs.append(f"Province: {self.province}")
        if self.stance and self.stance != "neutral":
            attrs.append(f"Stance: {self.stance}")
        if attrs:
            lines.append(" | ".join(attrs))

        if detail == "full" and self.background_story:
            lines.append(f"\nBackground: {self.background_story[:600]}")

        return "\n".join(lines)

    async def forward(self, round_num: int, initial_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Execute one simulation step; returns the action record dict."""
        return await self._block.forward(self, round_num, initial_prompt)
