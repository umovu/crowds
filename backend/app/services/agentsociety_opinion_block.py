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

logger = get_logger("mirofish.opinion_block")

# ─────────────────────────────────────────────────────────────
# South African socio-economic context — injected into every
# agent prompt so the LLM stays grounded in SA realities.
# This simulation exists to test policy on digital agents
# BEFORE it is implemented on actual people.
# ─────────────────────────────────────────────────────────────
SA_POLICY_CONTEXT = """
SIMULATION CONTEXT — READ CAREFULLY:
You are participating in a South African policy simulation. Agents are digital
representations of South African people used to stress-test policy proposals
before they affect real citizens. Your responses must reflect the lived realities
of South Africa.

Key socio-economic realities to stay grounded in:
- Unemployment: ~32% nationally, ~60% among youth (Stats SA 2024)
- Extreme inequality: Gini coefficient ~0.63, one of the highest globally
- Persistent load-shedding (Eskom power cuts) affecting daily life and business
- Land reform debate: historical dispossession and calls for redistribution
- Social grant dependency: ~28 million SASSA recipients (SRD, child support, pension)
- Racial inequality legacy from apartheid still shapes economic access
- 11 official languages; communities often multilingual (code-switching common)
- Urban/rural divide: Johannesburg, Cape Town, Durban vs rural Eastern Cape, Limpopo
- Township communities (Soweto, Khayelitsha, Umlazi) vs formal suburbs
- High gender-based violence (GBV) rates — a major policy concern
- Public healthcare (clinics, hospitals) vs private medical aid — NHI debate active
- BEE/BBBEE policies and debates about economic inclusion
- High crime rates affecting safety perceptions and movement
- Xenophobia tensions, especially toward other African migrants
- Strong trade union influence (COSATU, NUMSA)
- Key political actors: ANC, DA, EFF, MK Party, IFP
- Water access crises in parts of the country
- Education inequality: no-fee schools, Nsfas bursaries, school infrastructure gaps

When expressing opinions, responding to others, or deciding how to act:
- Speak as a person shaped by these realities, not as a neutral observer
- Reference specific SA concerns naturally (load-shedding, unemployment, grants, etc.)
- Reflect your character's language background, province, class, and lived experience
- Policy positions should reflect real trade-offs South Africans navigate daily
""".strip()

# ─────────────────────────────────────────────────────────────
# Action constants  (maps to JSONL action_type field)
# ─────────────────────────────────────────────────────────────
class OpinionActionType:
    EXPRESS_OPINION    = "EXPRESS_OPINION"
    RESPOND_TO_OPINION = "RESPOND_TO_OPINION"
    SEARCH_TOPIC       = "SEARCH_TOPIC"
    OBSERVE            = "OBSERVE"
    DO_NOTHING         = "DO_NOTHING"

    ALL = [EXPRESS_OPINION, RESPOND_TO_OPINION, SEARCH_TOPIC, OBSERVE, DO_NOTHING]


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
        self._init_db()

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
                created_at TEXT NOT NULL
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
                created_at    TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    # ── Feed operations ───────────────────────────────────────

    async def get_feed(self, exclude_agent_id: int) -> List[Dict]:
        """Return recent opinions excluding this agent's own."""
        async with self._lock:
            return [o for o in self._opinions if o["agent_id"] != exclude_agent_id][
                -self.FEED_SIZE:
            ]

    async def search(self, query: str) -> List[Dict]:
        """Simple keyword search over the in-memory feed."""
        q = query.lower()
        async with self._lock:
            return [o for o in self._opinions if q in o["content"].lower()][
                -10:
            ]

    async def add_opinion(self, agent_id: int, agent_name: str,
                          content: str, topics: List[str], round_num: int) -> int:
        """Persist an expressed opinion; return its ID."""
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "INSERT INTO opinion (agent_id, agent_name, content, topics, round_num, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (agent_id, agent_name, content, json.dumps(topics), round_num, now),
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
        }
        async with self._lock:
            self._opinions.append(record)
            if len(self._opinions) > 200:
                self._opinions = self._opinions[-200:]

        return opinion_id

    async def add_response(self, agent_id: int, agent_name: str,
                           opinion_id: int, content: str, round_num: int):
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO opinion_response"
            " (agent_id, agent_name, opinion_id, content, round_num, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (agent_id, agent_name, opinion_id, content, round_num, now),
        )
        conn.commit()
        conn.close()


# ─────────────────────────────────────────────────────────────
# OpinionCaptureBlock  (AgentSociety Block pattern)
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
        OpinionActionType.EXPRESS_OPINION:    "Share a new opinion or perspective on a relevant topic.",
        OpinionActionType.RESPOND_TO_OPINION: "Respond to or engage with another agent's opinion.",
        OpinionActionType.SEARCH_TOPIC:       "Search for opinions related to a specific topic or keyword.",
        OpinionActionType.OBSERVE:            "Read the feed silently without posting.",
        OpinionActionType.DO_NOTHING:         "Take no action this round.",
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
        else:
            return self._do_nothing(agent, round_num)

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

You are {agent.name}. {agent.persona[:300]}

Current shared opinion feed (recent):
{feed_preview}

Choose ONE action for this round. Respond with ONLY the action name:
- EXPRESS_OPINION    (share your view on a policy or issue relevant to your life)
- RESPOND_TO_OPINION (engage with someone's opinion above)
- SEARCH_TOPIC       (look up opinions on a specific policy or topic)
- OBSERVE            (read silently)
- DO_NOTHING         (stay quiet this round)
{f'Special prompt: {initial_prompt}' if initial_prompt else ''}
Action:"""

        try:
            resp = await self._llm.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=20,
                temperature=0.7,
            )
            raw = resp.choices[0].message.content.strip().upper()
            for act in OpinionActionType.ALL:
                if act in raw:
                    return act
        except Exception as e:
            logger.warning(f"Dispatcher failed for {agent.name}: {e}")

        # Default: express opinion if feed is sparse, else observe
        return OpinionActionType.EXPRESS_OPINION if len(feed) < 3 else OpinionActionType.OBSERVE

    # ── Action implementations ────────────────────────────────

    async def _express_opinion(self, agent: "OpinionAgent", feed: List[Dict], round_num: int) -> Dict:
        topic_hint = random.choice(agent.interested_topics) if agent.interested_topics else "the current situation"
        feed_ctx = "\n".join(f"- {o['agent_name']}: {o['content'][:80]}" for o in feed[-3:]) or "(none yet)"

        prompt = f"""{SA_POLICY_CONTEXT}

You are {agent.name}. {agent.persona[:500]}

Recent opinions from others:
{feed_ctx}

Share your genuine opinion about "{topic_hint}" in 1-3 sentences. Be direct and in-character.
Ground your view in your lived South African experience — your province, employment situation,
language background, and relationship with government services. Be opinionated, not generic.
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

You are {agent.name}. {agent.persona[:400]}

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

    # ── LLM helper ────────────────────────────────────────────

    async def _call_llm(self, prompt: str, agent_name: str, max_tokens: int = 200) -> str:
        try:
            resp = await self._llm.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.8,
            )
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

    async def forward(self, round_num: int, initial_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Execute one simulation step; returns the action record dict."""
        return await self._block.forward(self, round_num, initial_prompt)
