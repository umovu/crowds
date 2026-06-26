"""
AgentSociety opinion-capture simulation runner — agentsociety2 integration.

Uses agentsociety2's PersonAgent with OpinionCaptureSkill.
Sets env vars for LLM (Ollama via litellm).

Output: {simulation_dir}/opinion_space/actions.jsonl
"""

import argparse
import asyncio
import json
import logging
import os
import random
import signal
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# ── path setup ────────────────────────────────────────────────
_scripts_dir  = os.path.dirname(os.path.abspath(__file__))
_backend_dir  = os.path.abspath(os.path.join(_scripts_dir, ".."))
_project_root = os.path.abspath(os.path.join(_backend_dir, ".."))
sys.path.insert(0, _backend_dir)

from dotenv import load_dotenv
_env = os.path.join(_project_root, ".env")
_env_file = _env if os.path.exists(_env) else os.path.join(_backend_dir, ".env")
print(f"Loading .env from: {_env_file}")
load_dotenv(_env_file)

# ── Pre-set agentsociety2 env vars BEFORE import ───────────────
# agentsociety2 reads these at module import time, so we must set them early
# Simulation model = SIM_LLM_* (separate from the research/persona LLM_* model).
# Each SIM_LLM_* var falls back to the research key/base/model when left blank.
api_key  = os.environ.get("AGENTSOCIETY_LLM_API_KEY") or os.environ.get("SIM_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY", "sk-test")
base_url = os.environ.get("AGENTSOCIETY_LLM_API_BASE") or os.environ.get("SIM_LLM_BASE_URL") or os.environ.get("LLM_BASE_URL") or "http://localhost:11434/v1"
model    = os.environ.get("AGENTSOCIETY_LLM_MODEL") or os.environ.get("SIM_LLM_MODEL") or os.environ.get("LLM_MODEL_NAME") or "ollama/mistral"
print(f"Configuring LLM: model={model}, base_url={base_url}")
# Use direct assignment (not setdefault) to override any defaults
os.environ["AGENTSOCIETY_LLM_API_KEY"] = api_key
os.environ["AGENTSOCIETY_LLM_API_BASE"] = base_url
os.environ["AGENTSOCIETY_LLM_MODEL"] = model
# agentsociety2 PersonAgent uses "nano" model type by default — must set all variants
os.environ["AGENTSOCIETY_NANO_LLM_MODEL"] = model
os.environ["AGENTSOCIETY_NANO_LLM_API_KEY"] = api_key
os.environ["AGENTSOCIETY_NANO_LLM_API_BASE"] = base_url
os.environ["AGENTSOCIETY_CODER_LLM_MODEL"] = model
os.environ["AGENTSOCIETY_CODER_LLM_API_KEY"] = api_key
os.environ["AGENTSOCIETY_CODER_LLM_API_BASE"] = base_url
os.environ["AGENTSOCIETY_ANALYSIS_LLM_MODEL"] = model
os.environ["AGENTSOCIETY_ANALYSIS_LLM_API_KEY"] = api_key
os.environ["AGENTSOCIETY_ANALYSIS_LLM_API_BASE"] = base_url

# ── Disable Qwen "thinking" on the sim path (huge token saver) ──────
# Qwen reasoning models emit hidden chain-of-thought that counts as completion
# tokens — measured at ~94% of sim output (≈1600 of ≈1700 tokens/call), all of
# which the simulation discards. agentsociety2 builds its litellm Router with
# hardcoded litellm_params (no extra_body hook) and PersonAgent.acompletion takes
# no kwargs, so the only injection point is litellm.acompletion itself. Wrapping
# it here — BEFORE the library imports/builds its router — makes every sim call
# carry extra_body={"enable_thinking": False}. Verified to cut completion from
# ~1700 → ~30-100 tokens with no loss of answer quality. The research/persona path
# already disables thinking via Config.llm_extra_body(); this closes the sim gap.
if "qwen" in (model or "").lower():
    import litellm as _litellm
    _orig_acompletion = _litellm.acompletion

    async def _acompletion_no_thinking(*args, **kwargs):
        eb = dict(kwargs.get("extra_body") or {})
        eb.setdefault("enable_thinking", False)
        kwargs["extra_body"] = eb
        return await _orig_acompletion(*args, **kwargs)

    _litellm.acompletion = _acompletion_no_thinking
    print("Token saver: Qwen thinking disabled on sim path (extra_body.enable_thinking=False)")

# ── agentsociety2 imports ────────────────────────────────────────
from agentsociety2 import PersonAgent

# ── project imports ────────────────────────────────────────────
from app.services.agentsociety_opinion_block import (
    OpinionEnvironment,
    OpinionActionType,
)
from app.services.opinion_agent import OpinionCitizenAgent
from app.services.opinion_block import OpinionCaptureSkill
from app.services.agentsociety_output_writer import AgentSocietyOutputWriter
from app.services.event_rule_engine import EventRuleEngine
from app.services.replay_storage import ReplayStorage
from app.services.document_context_engine import DocumentContextEngine
from app.services.convergence_detector import ConvergenceDetector
from app.services.agent_sampler import AgentSampler

# ── logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(asctime)s - %(name)s - %(message)s",
)
logger = logging.getLogger("agentsociety.runner")

# Generic founder attribution for posted pitches / announcements (product mode).
# Kept generic by design (no name detection) per product-framing decision.
FOUNDER_LABEL = "The founder"

# Substrings that mark an LLM failure as *fatal for the whole run* — i.e. retrying
# won't help because it's an account/quota/auth problem, not a transient blip. When
# every active agent in a round fails with one of these, we stop the sim and mark it
# errored instead of silently looping all remaining rounds (the "dead but looks
# running" trap). Kept as plain text matching so it works across providers without
# importing provider-specific exception types.
_FATAL_LLM_ERROR_MARKERS = (
    "free tier of the model has been exhausted",
    "insufficient_quota",
    "exceeded your current quota",
    "quota exceeded",
    "invalid api key",
    "incorrect api key",
    "authenticationerror",
    "401",
    "403",
)


def _is_fatal_llm_error(exc: BaseException) -> bool:
    """True if the exception text looks like an unrecoverable auth/quota error."""
    msg = str(exc).lower()
    return any(marker in msg for marker in _FATAL_LLM_ERROR_MARKERS)

_shutdown_event: Optional[asyncio.Event] = None
_cleanup_done = False

IPC_COMMANDS_DIR  = "ipc_commands"
IPC_RESPONSES_DIR = "ipc_responses"
ENV_STATUS_FILE   = "env_status.json"


# ─────────────────────────────────────────────────────────────
# Profile loading
# ─────────────────────────────────────────────────────────────

def load_profiles(simulation_dir: str) -> List[Dict]:
    path = os.path.join(simulation_dir, "agentsociety_profiles.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Profile file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────
# IPC handler
# ─────────────────────────────────────────────────────────────

class IPCHandler:
    def __init__(
        self,
        simulation_dir: str,
        agents: Dict[int, PersonAgent],
        mode: str = "policy",
        runner: "AgentSocietyRunner" = None,
        company_label: str = "",
    ):
        self.simulation_dir = simulation_dir
        self.agents         = agents
        self.mode           = mode
        # runner is needed for founder broadcasts: they ride the same
        # _pending_events rail the round loop already drains (feed post +
        # whole-room reaction). company_label anchors the "founder of X" framing.
        self.runner         = runner
        self.company_label  = (company_label or "").strip()
        self.commands_dir   = os.path.join(simulation_dir, IPC_COMMANDS_DIR)
        self.responses_dir  = os.path.join(simulation_dir, IPC_RESPONSES_DIR)
        self.status_file    = os.path.join(simulation_dir, ENV_STATUS_FILE)
        self._paused        = False
        self._pause_event   = asyncio.Event()
        self._inflight      = set()   # command_ids of interventions running concurrently
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)

    def is_paused(self) -> bool:
        return self._paused

    def pause(self):
        self._paused = True
        self._pause_event.clear()

    def resume(self):
        self._paused = False
        self._pause_event.set()

    def update_status(self, status: str, extra: Dict = None):
        payload = {"status": status, "timestamp": datetime.now().isoformat()}
        if extra:
            payload.update(extra)
        with open(self.status_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def poll_command(self) -> Optional[Dict]:
        if not os.path.isdir(self.commands_dir):
            return None
        files = sorted(
            (
                os.path.join(self.commands_dir, fn)
                for fn in os.listdir(self.commands_dir)
                if fn.endswith(".json")
            ),
            key=os.path.getmtime,
        )
        # Load all pending commands first so we can prioritize control commands
        # (pause/resume/close_env) ahead of slow ones (interview/intervention).
        # Otherwise an old or slow command at the front of the queue blocks
        # resume from ever being processed — making the sim "hard to resume".
        pending = []
        for fp in files:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    pending.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                continue
        if not pending:
            return None
        control_types = ("resume", "pause", "close_env")
        for cmd in pending:
            if cmd.get("command_type") in control_types:
                return cmd
        # Skip commands already dispatched as background tasks (interventions
        # run concurrently and delete their own file when done).
        for cmd in pending:
            if cmd.get("command_id") not in self._inflight:
                return cmd
        return None

    def consume_command(self, command_id: str):
        """Delete a command file immediately so it isn't re-polled while its
        handler runs in the background (used for concurrent interventions)."""
        try:
            os.remove(os.path.join(self.commands_dir, f"{command_id}.json"))
        except OSError:
            pass

    def send_response(self, command_id: str, status: str, result=None, error: str = None):
        resp = {
            "command_id": command_id,
            "status":     status,
            "result":     result,
            "error":      error,
            "timestamp":  datetime.now().isoformat(),
        }
        with open(
            os.path.join(self.responses_dir, f"{command_id}.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(resp, f, ensure_ascii=False)
        try:
            os.remove(os.path.join(self.commands_dir, f"{command_id}.json"))
        except OSError:
            pass

    async def handle_interview(
        self,
        command_id: str,
        agent_id: int,
        prompt: str,
        query_context: dict = None
    ):
        """Uses agentsociety2's PersonAgent.ask() for interviews."""
        agent = self.agents.get(agent_id)
        if not agent:
            self.send_response(command_id, "failed", error=f"Agent {agent_id} not found")
            return True
        try:
            if hasattr(agent, 'do_interview_with_context'):
                response = await agent.do_interview_with_context(
                    prompt,
                    query_context=query_context
                )
            else:
                response = await agent.ask(prompt)
            self.send_response(command_id, "completed", result={
                "agent_id":  agent_id,
                "response":  response,
                "query_context": query_context,
                "timestamp": datetime.now().isoformat(),
            })
        except Exception as e:
            logger.error(f"Interview failed for agent {agent_id}: {e}")
            self.send_response(command_id, "failed", error=str(e))
        return True

    async def handle_batch_interview(self, command_id: str, interviews: List[Dict]):
        results = {}
        for iv in interviews:
            aid   = iv.get("agent_id", 0)
            agent = self.agents.get(aid)
            if not agent:
                continue
            try:
                query_context = iv.get("query_context")
                if query_context and hasattr(agent, 'do_interview_with_context'):
                    response = await agent.do_interview_with_context(
                        iv.get("prompt", ""),
                        query_context=query_context
                    )
                else:
                    response = await agent.ask(iv.get("prompt", ""))
                results[f"opinion_space_{aid}"] = {"agent_id": aid, "response": response}
            except Exception as e:
                results[f"opinion_space_{aid}"] = {"agent_id": aid, "error": str(e)}
        self.send_response(command_id, "completed", result={
            "interviews_count": len(results),
            "results": results,
        })
        return True

    async def handle_apply_intervention(
        self,
        command_id: str,
        agent_id: int,
        intervention_text: str,
    ):
        """Apply a policy-maker intervention to an agent and propagate to affiliates."""
        agent = self.agents.get(agent_id)
        if not agent:
            self.send_response(command_id, "failed", error=f"Agent {agent_id} not found")
            return True
        try:
            if hasattr(agent, 'apply_intervention'):
                result = await agent.apply_intervention(intervention_text, mode=self.mode)
                # Propagate to affiliated agents (same group/archetype)
                propagation_count = 0
                delta = agent.get_propagation_delta()
                if delta:
                    for other_agent in self.agents.values():
                        if other_agent.id == agent_id:
                            continue
                        if other_agent.apply_propagation_delta(delta):
                            propagation_count += 1
                result["propagation_count"] = propagation_count
                self.send_response(command_id, "completed", result=result)
            else:
                self.send_response(command_id, "failed", error="Agent does not support interventions")
        except Exception as e:
            logger.error(f"Intervention failed for agent {agent_id}: {e}")
            self.send_response(command_id, "failed", error=str(e))
        return True

    def _founder_label(self, founder_name: str = "") -> str:
        """Attribution for a founder broadcast, degrading gracefully:
        name+company -> name only -> company only -> generic. A supplied name
        is always kept (don't discard it just because the company is unknown)."""
        name = (founder_name or "").strip()
        company = self.company_label
        if name and company:
            return f"{name}, founder of {company}"
        if name:
            return f"{name}, the founder"
        if company:
            return f"The founder of {company}"
        return "The founder of this product"

    def handle_broadcast_intervention(
        self,
        command_id: str,
        intervention_text: str,
        founder_name: str = "",
    ) -> bool:
        """Queue a founder announcement onto the shared event rail.

        The round loop drains _pending_events: it posts each as a News_Source
        opinion (visible in the feed) AND feeds it to every active agent's
        'RECENT EVENTS' prompt (whole-room reaction). So a founder broadcast
        reuses that exact path — no separate feed/fan-out logic needed.
        """
        text = (intervention_text or "").strip()
        if not text:
            self.send_response(command_id, "failed", error="Empty intervention_text")
            return True
        if self.runner is None:
            self.send_response(command_id, "failed", error="Broadcast not available (no runner)")
            return True

        label = self._founder_label(founder_name)
        event = {
            "rule_id": f"founder_broadcast_{command_id}",
            "source": label,
            "title": f"{label} makes an announcement",
            "content": text,
            "category": "founder_announcement",
        }
        self.runner._pending_events.append(event)
        self.send_response(command_id, "completed", result={
            "broadcast": True,
            "source": label,
            "content": text,
            "message": "Founder announcement queued — it will post to the opinion space and the room will react next round.",
            "timestamp": datetime.now().isoformat(),
        })
        return True

    async def process_commands(self) -> bool:
        cmd = self.poll_command()
        if not cmd:
            return True
        cid   = cmd.get("command_id")
        ctype = cmd.get("command_type")
        args  = cmd.get("args", {})
        logger.info(f"IPC command: {ctype}, id={cid}")
        if ctype == "pause":
            self.pause()
            self.send_response(cid, "completed", result={"message": "Simulation paused", "paused": True})
            return True
        elif ctype == "resume":
            self.resume()
            self.send_response(cid, "completed", result={"message": "Simulation resumed", "paused": False})
            return True
        elif ctype == "interview":
            return await self.handle_interview(
                cid,
                args.get("agent_id", 0),
                args.get("prompt", ""),
                query_context=args.get("query_context")
            )
        elif ctype == "batch_interview":
            return await self.handle_batch_interview(cid, args.get("interviews", []))
        elif ctype == "apply_intervention":
            # Run interventions concurrently: consume the command now and
            # dispatch as a background task so a global broadcast (many agents
            # at once) doesn't serialize one LLM call at a time.
            self._inflight.add(cid)
            self.consume_command(cid)

            async def _run_intervention(_cid, _agent_id, _text):
                try:
                    await self.handle_apply_intervention(_cid, _agent_id, _text)
                finally:
                    self._inflight.discard(_cid)

            asyncio.ensure_future(_run_intervention(
                cid,
                args.get("agent_id", 0),
                args.get("intervention_text", "")
            ))
            return True
        elif ctype == "broadcast_intervention":
            # Founder broadcast: post the message into the opinion space as a
            # founder announcement and let the whole active room react next round.
            return self.handle_broadcast_intervention(
                cid,
                args.get("intervention_text", ""),
                args.get("founder_name") or "",
            )
        elif ctype == "close_env":
            self.send_response(cid, "completed", result={"message": "Environment will close"})
            return False
        else:
            self.send_response(cid, "failed", error=f"Unknown command: {ctype}")
            return True


# ─────────────────────────────────────────────────────────────
# Main simulation runner
# ─────────────────────────────────────────────────────────────

class AgentSocietyRunner:
    PLATFORM = "opinion_space"

    def __init__(self, config_path: str, wait_for_commands: bool = True, fast_mode: bool = False):
        self.config_path       = config_path
        self.simulation_dir    = os.path.dirname(os.path.abspath(config_path))
        self.wait_for_commands = wait_for_commands
        self.fast_mode         = fast_mode

        with open(config_path, "r", encoding="utf-8") as f:
            self.config: Dict[str, Any] = json.load(f)

        self.output_dir = os.path.join(self.simulation_dir, self.PLATFORM)
        os.makedirs(self.output_dir, exist_ok=True)

        self._agents_expressed: set = set()
        self._event_engine = EventRuleEngine()
        self._pending_events: List[Dict[str, Any]] = []
        self._injected_events_history: List[Dict[str, Any]] = []

        # Structured replay storage
        replay_db_path = os.path.join(self.output_dir, "replay.db")
        self._replay = ReplayStorage(replay_db_path)

    def _log_fact_gap(self, round_num: int, agent: "PersonAgent", needed_fact: str) -> None:
        """Append one fact-gap (an agent needed a real cost not provided) to
        fact_gaps.jsonl in the output dir. Append-only, best-effort — a logging
        failure must never disturb the sim."""
        try:
            rec = {
                "round": round_num,
                "agent_id": agent.id,
                "agent_name": getattr(agent, "name", str(agent.id)),
                "archetype": agent.init_state.get("actor_archetype", "unknown")
                if hasattr(agent, "init_state") else "unknown",
                "needed_fact": needed_fact,
                "timestamp": datetime.now().isoformat(),
            }
            path = os.path.join(self.output_dir, "fact_gaps.jsonl")
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug(f"fact-gap log skipped: {e}")

    def _get_active_agents(
        self,
        all_agents: Dict[int, PersonAgent],
        current_hour: int,
        round_num: int,
    ) -> List[PersonAgent]:
        """Use AgentSampler for probabilistic agent selection."""
        hot_topics = []
        if self.config.get("event_config"):
            hot_topics = self.config["event_config"].get("hot_topics", [])
        
        # Get max agents from preset or default
        max_agents = self.config.get("max_agents_per_round", 8)
        min_agents = self.config.get("min_agents_per_round", 2)
        
        return self.sampler.sample(
            round_num=round_num,
            hot_topics=hot_topics,
            min_agents=min_agents,
            max_agents=max_agents,
        )

    async def run(self, max_rounds: Optional[int] = None):
        print("=" * 60)
        print("AgentSociety Opinion-Capture Simulation")
        print("  Framework : agentsociety2 (PersonAgent)")
        print(f"  Sim ID    : {self.config.get('simulation_id', 'unknown')}")
        print("=" * 60)

        tc                = self.config.get("time_config", {})
        total_hours       = tc.get("total_simulation_hours", 12)
        minutes_per_round = tc.get("minutes_per_round", 60)
        
        # Fast mode: reduce simulation duration
        if self.fast_mode:
            total_hours = min(total_hours, 6)
            minutes_per_round = max(minutes_per_round, 60)
        
        total_rounds      = int(total_hours * 60 / minutes_per_round)
        if max_rounds:
            total_rounds = min(total_rounds, max_rounds)

        # ── Set LLM config from environment (v2 uses env vars) ───────
        api_key  = os.environ.get("AGENTSOCIETY_LLM_API_KEY") or os.environ.get("SIM_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY", "sk-test")
        base_url = os.environ.get("AGENTSOCIETY_LLM_API_BASE") or os.environ.get("SIM_LLM_BASE_URL") or os.environ.get("LLM_BASE_URL") or "http://localhost:11434/v1"
        model    = (
            os.environ.get("AGENTSOCIETY_LLM_MODEL")
            or os.environ.get("SIM_LLM_MODEL")
            or self.config.get("llm_model", "ollama/mistral")
        )
        os.environ["AGENTSOCIETY_LLM_API_KEY"] = api_key
        os.environ["AGENTSOCIETY_LLM_API_BASE"] = base_url
        os.environ["AGENTSOCIETY_LLM_MODEL"] = model
        os.environ["AGENTSOCIETY_NANO_LLM_MODEL"] = model
        os.environ["AGENTSOCIETY_NANO_LLM_API_KEY"] = api_key
        os.environ["AGENTSOCIETY_NANO_LLM_API_BASE"] = base_url
        os.environ["AGENTSOCIETY_CODER_LLM_MODEL"] = model
        os.environ["AGENTSOCIETY_CODER_LLM_API_KEY"] = api_key
        os.environ["AGENTSOCIETY_CODER_LLM_API_BASE"] = base_url
        os.environ["AGENTSOCIETY_ANALYSIS_LLM_MODEL"] = model
        os.environ["AGENTSOCIETY_ANALYSIS_LLM_API_KEY"] = api_key
        os.environ["AGENTSOCIETY_ANALYSIS_LLM_API_BASE"] = base_url
        print(f"  LLM       : {model} @ {base_url}")

        # ── Build document context ────────────────────────────────
        graph_id = self.config.get("graph_id")
        document_context = ""
        dynamic_rules = []
        facts = []
        sim_mode = self.config.get("mode", "policy")
        # Company/product label anchors founder broadcasts ("founder of X").
        # Prefer an explicit company name from saved context; else fall back
        # to the detected domain; else stay empty -> generic "this product".
        company_label = ""

        # 1. Try to load pre-built document context from simulation directory
        ctx_path = os.path.join(self.simulation_dir, "document_context.json")
        if os.path.exists(ctx_path):
            try:
                with open(ctx_path, 'r', encoding='utf-8') as f:
                    saved_ctx = json.load(f)
                document_context = saved_ctx.get("document_context_block", "")
                dynamic_rules = saved_ctx.get("dynamic_rules", [])
                facts = saved_ctx.get("facts", [])
                domain = saved_ctx.get("domain", "unknown")
                sim_mode = saved_ctx.get("mode", "policy")
                company_label = saved_ctx.get("company") or (domain if domain and domain != "unknown" else "")
                dp = saved_ctx.get("domain_profile", {})
                print(f"  Document  : Domain={domain} (from saved context, mode={sim_mode})")
                print(f"  Entities  : {dp.get('total_entities', 0)} extracted")
                if dp.get('organizations'):
                    print(f"  Orgs      : {', '.join(dp['organizations'][:5])}")
                if facts:
                    print(f"  Facts     : {len(facts)} extracted")
                if dynamic_rules:
                    print(f"  DynRules  : {len(dynamic_rules)} generated")
            except Exception as e:
                logger.warning(f"Failed to load saved document context: {e}")

        # 2. Fall back to building from Neo4j graph
        if not document_context and graph_id:
            try:
                from app.storage.neo4j_storage import Neo4jStorage
                from app.config import Config
                storage = Neo4jStorage(
                    uri=os.environ.get("NEO4J_URI", Config.NEO4J_URI),
                    user=os.environ.get("NEO4J_USER", Config.NEO4J_USER),
                    password=os.environ.get("NEO4J_PASSWORD", Config.NEO4J_PASSWORD),
                )
                sim_mode = self.config.get("mode", "policy")
                ctx_engine = DocumentContextEngine(storage, mode=sim_mode)
                profile = ctx_engine.build_from_graph(graph_id)
                document_context = ctx_engine.get_document_context_block()
                dynamic_rules = ctx_engine.get_dynamic_rules()

                print(f"  Document  : Domain={profile.get('domain', 'unknown')} (from Neo4j)")
                print(f"  Entities  : {profile.get('total_entities', 0)} extracted")
                if profile.get('organizations'):
                    print(f"  Orgs      : {', '.join(profile['organizations'][:5])}")
                if dynamic_rules:
                    print(f"  DynRules  : {len(dynamic_rules)} generated")
            except Exception as e:
                logger.warning(f"Failed to build document context from Neo4j: {e}")
                print(f"  Document  : Neo4j context failed, using generic SA context")
        elif not document_context:
            print("  Document  : No saved context or graph_id, using generic SA context")

        # 3. Append facts to document context for grounding
        if facts:
            fact_block = (
                "\n" + "=" * 60 + "\n"
                "DOCUMENT FACTS — these are established facts from the policy document.\n"
                "Ground your opinions in these facts. Do NOT invent facts not listed here.\n"
                "=" * 60 + "\n"
                + "\n".join(f"- {f}" for f in facts)
                + "\n" + "=" * 60 + "\n"
            )
            document_context = (document_context or "") + fact_block

        # 3b. WORLD FACTS injection intentionally removed. Dropping a list of
        # generic SA costs (bread/petrol/taxi/electricity) into every prompt made
        # agents fixate on those costs — reciting and even policing them ("bread
        # is R16 not R10") — and drift off the actual scenario, in both policy and
        # product runs. Affordability that genuinely matters is still grounded:
        # product mode's economic lens supplies each persona's REAL budget. The
        # world_facts module/JSON remain for inspection + scripts/promote_fact.py,
        # just not force-fed to the room. (Re-add here if a future scenario needs
        # specific, scenario-relevant costs rather than a blanket cost list.)

        # ── Shared opinion feed (SQLite) ───────────────────────
        db_path = os.path.join(self.output_dir, "opinion_simulation.db")
        env     = OpinionEnvironment(db_path=db_path)
        print(f"  DB       : {db_path}")

        # ── Shared Opinion Capture Skill ────────────────────────────
        # ── Event-driven components ──────────────────────────
        from app.services.convergence_detector import ConvergenceDetector
        from app.services.agent_sampler import AgentSampler

        from app.config import Config as _Cfg
        # saturation_rounds: dedicated coverage knob, falling back to convergence_window.
        _sat_rounds = self.config.get(
            "coverage_saturation_rounds",
            self.config.get("convergence_window", _Cfg.COVERAGE_SATURATION_ROUNDS),
        )
        self.detector = ConvergenceDetector(
            threshold=self.config.get("convergence_threshold", 0.05),
            window=self.config.get("convergence_window", 3),
            saturation_rounds=_sat_rounds,
        )
        self._use_coverage_stop = self.config.get("use_coverage_stop", _Cfg.USE_COVERAGE_STOP)

        # Coverage metric: cumulative, stance-aware distinct-position registry.
        # Lives for the whole run; feeds both the snapshot metric and the
        # coverage-saturation stop. Never fatal (lexical fallback if Ollama down).
        from app.services.position_clustering import PositionRegistry
        self.position_registry = PositionRegistry(threshold=_Cfg.POSITION_SIM_THRESHOLD)
        # Note: sampler will be initialized after all_agents is created

        # ── Product mode: extract the pitch object once (one cheap LLM call) ──
        # The economic-reasoning lens needs a structured {what/pricing/problem/
        # status_quo} to react to. Best-effort: any failure → empty pitch, and
        # the lens degrades to generic "the product being pitched" phrasing.
        pitch = None
        if sim_mode == "product":
            try:
                import re
                from openai import OpenAI as _OpenAI
                from app.services.mode_specs import (
                    build_pitch_extraction_prompt,
                    PRODUCT_PITCH_EXTRACTION_SYSTEM,
                )
                _client = _OpenAI(api_key=api_key, base_url=base_url)
                _pp = build_pitch_extraction_prompt(
                    document_context, self.config.get("simulation_requirement", "")
                )
                _resp = _client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": PRODUCT_PITCH_EXTRACTION_SYSTEM},
                        {"role": "user", "content": _pp},
                    ],
                    temperature=0.3,
                    max_tokens=400,
                )
                _raw = (_resp.choices[0].message.content or "").strip()
                _raw = re.sub(r"<think>[\s\S]*?</think>", "", _raw)
                _raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", _raw.strip(), flags=re.MULTILINE).strip()
                _m = re.search(r'\{[\s\S]*\}', _raw)
                pitch = json.loads(_m.group()) if _m else None
                if pitch:
                    print(f"  Pitch     : {pitch.get('what_it_is', '?')[:70]}")
            except Exception as e:
                logger.warning(f"Pitch extraction failed (lens will use generic phrasing): {e}")
                pitch = None

        opinion_skill = OpinionCaptureSkill(
            env=env, document_context=document_context, fast_mode=self.fast_mode,
            model_name=model, mode=sim_mode, pitch=pitch,
        )
        
        # ── Event Rule Engine with dynamic rules ──────────────────
        # Mode-gated: the bundled static rules are policy-domain (SAPS, Parliament,
        # Eskom…). A product sim loads none of them and relies on dynamic rules
        # from the document context, so riot police never deploy into a product
        # stress-test.
        self._event_engine = EventRuleEngine(dynamic_rules=dynamic_rules, mode=sim_mode)

        # ── Load profiles → cap agents → create agents ──────
        profiles      = load_profiles(self.simulation_dir)
        agent_cfg_map = {
            ac["agent_id"]: ac
            for ac in self.config.get("agent_configs", [])
        }

        # No hard agent cap — use all generated profiles for richer simulation
        max_agents = int(os.environ.get("MAX_SIMULATION_AGENTS", 9999))
        if len(profiles) > max_agents:
            print(f"  WARNING   : {len(profiles)} profiles generated, capping to {max_agents}")
            # Prioritize diversity: ensure all archetypes represented
            archetype_groups = {}
            for p in profiles:
                arch = p.get("actor_archetype", "civic_moderate")
                if arch not in archetype_groups:
                    archetype_groups[arch] = []
                archetype_groups[arch].append(p)
            
            selected = []
            # Round-robin across archetypes until cap
            while len(selected) < max_agents and any(archetype_groups.values()):
                for arch in list(archetype_groups.keys()):
                    if len(selected) >= max_agents:
                        break
                    if archetype_groups[arch]:
                        selected.append(archetype_groups[arch].pop(0))
            
            profiles = selected
            print(f"  Selection : {len(profiles)} agents (diverse archetypes)")
        else:
            print(f"  Agents    : {len(profiles)} profiles (no cap applied)")

        _ARCHETYPE_ACTIVITY = {
            "violent_agitator":         0.95,
            "conspiracy_spreader":      0.90,
            "political_activist":       0.85,
            "opportunist_looter":       0.85,
            "mob_follower":             0.80,
            "community_leader":         0.80,
            "community_protector":      0.75,
            "criminal_opportunist":     0.75,
            "whistleblower":            0.70,
            "economic_migrant":         0.60,
            "civic_moderate":           0.60,
            "institutional_loyalist":   0.55,
            "grant_dependent_survivor": 0.45,
            "disillusioned_dropout":    0.25,
        }

        all_agents: Dict[int, OpinionCitizenAgent] = {}
        for p in profiles:
            uid = p.get("id", p.get("user_id", 0))
            ac  = agent_cfg_map.get(uid, {})

            archetype = p.get("actor_archetype") or "civic_moderate"
            # Custom-agent-first: a known archetype uses its tuned activity weight.
            # An unknown (custom) archetype uses the agent's OWN activity_level
            # (from its profile / agent_config), falling back to a neutral 0.6 —
            # so custom agents aren't silently flattened to the policy default.
            if archetype in _ARCHETYPE_ACTIVITY:
                activity_level = _ARCHETYPE_ACTIVITY[archetype]
            else:
                activity_level = p.get("activity_level", ac.get("activity_level", 0.6))

            agent = OpinionCitizenAgent(
                id=uid,
                profile=p,
                name=p.get("name", f"agent_{uid}"),
                interested_topics=p.get("interested_topics", []),
                stance=ac.get("stance", p.get("stance", "neutral")),
                activity_level=activity_level,
                active_hours=ac.get("active_hours", list(range(8, 23))),
                group_affiliation=p.get("group_affiliation"),
                actor_archetype=p.get("actor_archetype"),
                behavioral_tendencies=p.get("behavioral_tendencies"),
                source_entity_uuid=p.get("source_entity_uuid"),
                is_institutional=p.get("is_institutional", False),
                is_core_focus=p.get("is_core_focus", False),
            )
            all_agents[uid] = agent
            # Register similarity attrs for homophily-biased feeds. init_state is
            # passed by reference so the agent's CURRENT stance is read live.
            env.register_agent_attrs(
                uid,
                archetype=archetype,
                group=p.get("group_affiliation"),
                init_state=getattr(agent, "init_state", None),
            )

        print(f"  Agents    : {len(all_agents)} loaded\n")

        # Initialize sampler now that all_agents is ready
        self.sampler = AgentSampler(
            all_agents=all_agents,
            agent_configs={ac["agent_id"]: ac for ac in self.config.get("agent_configs", [])}
        )

        writer = AgentSocietyOutputWriter(self.output_dir)
        ipc    = IPCHandler(self.simulation_dir, all_agents, mode=sim_mode,
                            runner=self, company_label=company_label)

        # Initialize replay storage
        sim_id = self.config.get("simulation_id", os.path.basename(self.simulation_dir))
        self._replay.start_simulation(
            simulation_id=sim_id,
            project_id=self.config.get("project_id"),
            total_agents=len(all_agents),
            llm_model=model,
            config=self.config,
        )
        self._replay.store_agent_profiles(
            simulation_id=sim_id,
            profiles=[p for p in profiles],
        )

        ipc.update_status("running", {
            "total_agents":           len(all_agents),
            "agents_expressed_count": 0,
            "agents_expressed":       [],
        })

        # ── Seed initial posts ────────────────────────────────
        event_cfg = self.config.get("event_config", {})
        for post in event_cfg.get("initial_posts", []):
            agent_id = post.get("poster_agent_id", 0)
            content  = post.get("content", "")
            agent    = all_agents.get(agent_id)
            if agent and content:
                oid = await env.add_opinion(agent_id, agent.name, content, [], 0)
                self._agents_expressed.add(agent_id)
                writer.write_action(0, agent_id, agent.name, {
                    "action_type": OpinionActionType.EXPRESS_OPINION,
                    "action_args": {"content": content, "opinion_id": oid},
                    "success": True,
                })

        print(f"Seeded {len(event_cfg.get('initial_posts', []))} initial opinions")

        # ── Product mode: post the pitch as a founder announcement ─────────
        # So agents respond directly TO the pitch (an actual post they react to),
        # not just to ambient background context. Rides the same _pending_events
        # rail as manual founder broadcasts; drained at round 0 below.
        self._pitch_event = None  # the re-anchor reminder source, set when posted

        # ── Policy mode: hold the scenario for re-anchoring on a cadence ────
        # The scenario is seeded once at round 0; without a reminder the room
        # drifts off the question within a round or two (cost-of-living capture).
        # Mirror the product pitch re-anchor: keep the scenario text so the loop
        # can re-post it every N rounds. None in product mode (pitch covers it).
        self._scenario_reanchor = None
        if sim_mode != "product":
            _scenario = (self.config.get("simulation_requirement", "") or "").strip()
            if _scenario:
                self._scenario_reanchor = _scenario

        if sim_mode == "product" and pitch:
            try:
                from app.services.mode_specs import build_pitch_announcement
                announcement = build_pitch_announcement(pitch, short=False)
                self._pitch_event = {
                    "rule_id": "founder_pitch_round0",
                    "source": FOUNDER_LABEL,
                    "title": f"{FOUNDER_LABEL} makes an announcement",
                    "content": announcement,
                    "category": "founder_announcement",
                }
                self._pending_events.append(self._pitch_event)
                print(f"  Pitch posted as founder announcement (round 0)")
            except Exception as e:
                logger.warning(f"Founder pitch post failed: {e}")

        if self.fast_mode:
            print("FAST MODE: Reduced rounds (6h), abbreviated prompts, higher concurrency (10)")
        print("Starting simulation loop...\n")

        start_time = datetime.now()
        # Higher concurrency for faster simulation; reduce if hitting rate limits
        concurrency = 10 if self.fast_mode else 8
        semaphore  = asyncio.Semaphore(concurrency)

        async def step_agent(agent: OpinionCitizenAgent, rn: int, events_prompt: Optional[str] = None):
            async with semaphore:
                return await opinion_skill.execute(agent, round_num=rn, initial_prompt=events_prompt)

        # Re-anchor cadence: re-post a short pitch reminder every N rounds so the
        # room keeps returning to the pitch instead of drifting. 0 disables.
        # Cadence is preset-aware: scale with run length so a short run still gets
        # re-anchored (every-4 would only fire once on a 6-round Quick run). Aim
        # for ~3-4 re-anchors regardless of length. An explicit override wins:
        # run-config value first, then an explicitly-set PITCH_REANCHOR_EVERY env.
        _auto_cadence = max(2, total_rounds // 4)
        _env_cadence = os.environ.get("PITCH_REANCHOR_EVERY")
        _default_cadence = int(_env_cadence) if _env_cadence else _auto_cadence
        pitch_reanchor_every = int(self.config.get("pitch_reanchor_every", _default_cadence))

        for round_num in range(total_rounds):
            simulated_minutes = round_num * minutes_per_round
            simulated_hour    = (simulated_minutes // 60) % 24
            simulated_day     = simulated_minutes // (24 * 60) + 1

            # ── Product mode: re-anchor the pitch on a cadence ─────────────
            # Skip round 0 (already posted). Re-post a short reminder so agents
            # re-centre on the pitch; they remain free to keep objecting.
            if (self._pitch_event and pitch_reanchor_every > 0
                    and round_num > 0 and round_num % pitch_reanchor_every == 0):
                try:
                    from app.services.mode_specs import build_pitch_announcement
                    self._pending_events.append({
                        "rule_id": f"founder_pitch_reanchor_r{round_num}",
                        "source": FOUNDER_LABEL,
                        "title": f"{FOUNDER_LABEL} follows up",
                        "content": build_pitch_announcement(pitch, short=True),
                        "category": "founder_announcement",
                    })
                except Exception as e:
                    logger.debug(f"Pitch re-anchor skipped at round {round_num}: {e}")

            # ── Policy mode: re-anchor the scenario on the same cadence ────
            # Re-post the original question as a News_Source item so agents
            # respond to the TOPIC again instead of only to each other's drift.
            # They stay free to object or relate it to their lives.
            if (self._scenario_reanchor and pitch_reanchor_every > 0
                    and round_num > 0 and round_num % pitch_reanchor_every == 0):
                self._pending_events.append({
                    "rule_id": f"scenario_reanchor_r{round_num}",
                    "source": "News_Source",
                    "title": "The question still stands",
                    "content": (
                        f"Back to the matter at hand: {self._scenario_reanchor} "
                        f"Where do you stand on THIS specifically?"
                    ),
                    "category": "news",
                })

            # ── Inject pending events as "News_Source" opinions ─────────
            # Snapshot the events to inject this round. Anything appended to
            # _pending_events *after* this point (e.g. a founder broadcast that
            # arrives over IPC mid-round while paused) is intentionally left for
            # the next round, and is carried past the end-of-round assignment.
            events_to_inject = list(self._pending_events)
            for evt in events_to_inject:
                await env.add_opinion(
                    agent_id=-1,
                    agent_name=evt.get("source", "News_Source"),
                    content=f"[{evt['title']}] {evt['content']}",
                    topics=[evt.get("category", "news")],
                    round_num=round_num,
                    reason=f"Injected event: {evt['rule_id']}",
                    internal_thought="System event injection.",
                    impact_score=0.5,
                )
                self._injected_events_history.append({
                    "round_injected": round_num,
                    **evt,
                })
                writer.write_action(round_num, -1, evt.get("source", "News_Source"), {
                    "action_type": "SYSTEM_EVENT",
                    "action_args": {"event": evt},
                    "success": True,
                })

            # Build events prompt for agents (from the same snapshot we injected)
            events_prompt = None
            if events_to_inject:
                events_lines = ["RECENT EVENTS — these have just happened:"]
                for evt in events_to_inject:
                    if evt.get("category") == "founder_announcement":
                        # Surface the founder's actual words so the room reacts to
                        # the announcement itself, not just a headline.
                        events_lines.append(f"  • {evt['source']} says directly: \"{evt['content']}\"")
                    else:
                        events_lines.append(f"  • {evt['source']}: {evt['title']}")
                events_prompt = "\n".join(events_lines)

            active = self._get_active_agents(all_agents, simulated_hour, round_num)
            if not active:
                # Keep events appended mid-round (e.g. founder broadcasts) for a
                # later active round; drop the ones we already injected above.
                self._pending_events = [e for e in self._pending_events
                                        if e not in events_to_inject]
                continue

            tasks   = [step_agent(a, round_num, events_prompt) for a in active]
            gather_task = asyncio.ensure_future(
                asyncio.gather(*tasks, return_exceptions=True)
            )
            # While agents are acting (the slow part — minutes for big sims),
            # keep polling for IPC commands so a pause click registers promptly
            # instead of waiting for the whole round + the post-round window.
            while not gather_task.done():
                await ipc.process_commands()
                try:
                    await asyncio.wait_for(asyncio.shield(gather_task), timeout=0.3)
                except asyncio.TimeoutError:
                    pass
                except Exception:
                    break
            results = await gather_task

            # ── Fatal LLM failure guard ─────────────────────────────────
            # If every active agent this round failed with an auth/quota error,
            # the model is unavailable and retrying further rounds is pointless
            # (and would spin a tight failure loop). Stop, mark the sim errored
            # with a human reason, and break — so the UI reflects reality instead
            # of showing a "running" sim that can't be paused.
            exc_results = [r for r in results if isinstance(r, BaseException)]
            if active and len(exc_results) == len(results) and all(
                _is_fatal_llm_error(r) for r in exc_results
            ):
                reason = "LLM unavailable — quota exhausted or invalid credentials"
                logger.error(
                    f"Round {round_num + 1}: all {len(active)} agents failed with a "
                    f"fatal LLM error; stopping simulation. ({exc_results[0]})"
                )
                print(f"\n  [STOPPED] {reason}. Halting at round {round_num + 1}.")
                ipc.update_status("error", {
                    "current_round": round_num + 1,
                    "total_rounds": total_rounds,
                    "error": reason,
                    "message": f"Simulation stopped at round {round_num + 1}: {reason}",
                })
                break

            # ── Collect actions with archetype for event engine ─────────
            actions_for_rules = []
            posted_agent_ids = set()
            for agent, result in zip(active, results):
                if isinstance(result, Exception):
                    logger.warning(f"Agent {agent.name} step failed: {result}")
                    continue

                action_type = result.get("action_type", "") if isinstance(result, dict) else ""
                if action_type in (
                    OpinionActionType.EXPRESS_OPINION,
                    OpinionActionType.RESPOND_TO_OPINION,
                ):
                    self._agents_expressed.add(agent.id)
                    posted_agent_ids.add(agent.id)

                record = result if isinstance(result, dict) else {"result": str(result)}
                writer.write_action(round_num, agent.id, agent.name, record)

                # Fact-gap loop: when an agent flagged it needed a real cost that
                # wasn't in WORLD FACTS / its own numbers, log it (instead of the
                # agent inventing a figure). Reviewed after the run and promoted
                # into the curated world-facts via scripts/promote_fact.py.
                if isinstance(record, dict) and record.get("needed_fact"):
                    self._log_fact_gap(round_num, agent, record["needed_fact"])

                # Store in replay
                if isinstance(record, dict):
                    self._replay.store_action(
                        simulation_id=sim_id,
                        round_num=round_num,
                        agent_id=agent.id,
                        agent_name=agent.name,
                        archetype=getattr(agent, 'actor_archetype', None) or agent.init_state.get("actor_archetype", "unknown"),
                        action_type=record.get("action_type", ""),
                        content=record.get("action_args", {}).get("content", ""),
                        topics=record.get("action_args", {}).get("topics", []),
                        impact_score=record.get("impact_score", 0.0),
                        internal_thought=record.get("internal_thought", ""),
                        reason=record.get("reason", ""),
                        opinion_id=record.get("action_args", {}).get("opinion_id"),
                        target_opinion_id=record.get("action_args", {}).get("target_opinion_id"),
                        target_agent_name=record.get("action_args", {}).get("target_agent_name", ""),
                        economic_reasoning=record.get("economic_reasoning"),
                    )

                # Build action metric for rule engine
                actions_for_rules.append({
                    "action_type": action_type,
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "archetype": getattr(agent, 'actor_archetype', None) or agent.init_state.get("actor_archetype", "unknown"),
                    "impact_score": record.get("impact_score", 0.0) if isinstance(record, dict) else 0.0,
                    "content": record.get("action_args", {}).get("content", "") if isinstance(record, dict) else "",
                    "internal_thought": record.get("internal_thought", "") if isinstance(record, dict) else "",
                    "reason": record.get("reason", "") if isinstance(record, dict) else "",
                    "topics": record.get("action_args", {}).get("topics", []) if isinstance(record, dict) else [],
                    "radicalism_level": getattr(agent, 'base_radicalism', 1),
                    # CURRENT stance (mutates during the run) — drives stance-aware
                    # position clustering. Read live, never cached.
                    "stance": agent.init_state.get("stance", "neutral") if hasattr(agent, "init_state") else "neutral",
                }                )

            # Record posted agents for sampler momentum
            self.sampler.record_posters(posted_agent_ids)

            # Collect actions for convergence detection
            round_actions = []
            for agent, result in zip(active, results):
                if isinstance(result, dict):
                    round_actions.append(result)

            # ── Coverage metric → stop decision ────────────────────────
            # Cluster this round's expressed stances and update the cumulative
            # registry FIRST, because the coverage-saturation stop depends on it.
            # Only EXPRESS/RESPOND posts carry a stance position.
            position_posts = [
                {"content": a.get("content", ""), "stance": a.get("stance", "neutral")}
                for a in actions_for_rules
                if a.get("action_type") in (
                    OpinionActionType.EXPRESS_OPINION,
                    OpinionActionType.RESPOND_TO_OPINION,
                ) and a.get("content")
            ]
            pos = self.position_registry.ingest_round(position_posts)
            self._last_position_result = pos
            print(
                f"    [Coverage] round {round_num}: distinct={pos['total_distinct']} "
                f"new={pos['n_new_positions']} spread={pos['spread']} mode={pos['mode']}"
            )
            # A mode flip (embed<->lexical) makes counts incomparable — reset baseline.
            if pos.get("mode_changed"):
                self.detector.reset_coverage()
            self.detector.record_coverage(pos["n_new_positions"], pos["total_distinct"])

            # Legacy sentiment-stability detector — kept as SHADOW only (logged,
            # never acts) so we can validate the inversion before retiring it.
            self.detector.record_round(round_actions)
            old_should_stop, divergence, stable_rounds = self.detector.check()
            cov_should_stop, total_distinct, rounds_since_new = self.detector.coverage_saturated()

            if self._use_coverage_stop:
                if old_should_stop:
                    print(f"    [shadow] old sentiment-detector WOULD have stopped here "
                          f"(stable_rounds={stable_rounds}, divergence={divergence:.4f}) — ignored.")
                if cov_should_stop:
                    print(f"    [Coverage saturated] No new position for {rounds_since_new} rounds "
                          f"(distinct={total_distinct}). Stopping simulation.")
                    break
            else:
                # Legacy behaviour: stop on sentiment stability (the old failure mode).
                if old_should_stop:
                    print(f"    [Convergence] Detected after {stable_rounds} stable rounds "
                          f"(divergence={divergence:.4f}). Stopping simulation.")
                    break

            # ── Evaluate event rules ──────────────────────────────────
            new_events = self._event_engine.evaluate(round_num, actions_for_rules)
            # Carry over anything appended to _pending_events *after* this round's
            # injection pass — i.e. founder broadcasts that arrived over IPC
            # mid-round (often while paused). Without this, the assignment below
            # would clobber them before they're ever posted to the feed.
            carried = [e for e in self._pending_events if e not in events_to_inject]
            self._pending_events = carried + new_events

            if new_events:
                print(f"    [Events triggered this round: {len(new_events)}] " +
                      ", ".join(e["title"] for e in new_events))

            # Store events in replay
            for evt in self._pending_events:
                self._replay.store_injected_event(sim_id, evt)

            # Calculate metrics for snapshot. Coverage figures were computed above
            # (the stop depends on them); fold them into the persisted metrics.
            metrics = self._event_engine._calculate_metrics(actions_for_rules)
            metrics["distinct_positions"] = pos["total_distinct"]
            metrics["new_positions"] = pos["n_new_positions"]
            metrics["position_spread"] = pos["spread"]

            self._replay.store_sentiment_snapshot(
                simulation_id=sim_id,
                round_num=round_num,
                metrics=metrics,
                events_injected_count=len(self._pending_events),
            )

            ipc.update_status("running", {
                "total_agents":             len(all_agents),
                "agents_expressed_count":   len(self._agents_expressed),
                "agents_expressed":         list(self._agents_expressed),
                "simulation_actions_count": writer.total_actions,
                "current_round":            round_num + 1,
                "total_rounds":             total_rounds,
                "events_injected_this_round": len(self._pending_events),
                "total_events_injected":    len(self._injected_events_history),
            })

            writer.write_round_end(round_num, simulated_minutes / 60)

            if (round_num + 1) % 5 == 0 or round_num == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                pct     = (round_num + 1) / total_rounds * 100
                print(
                    f"  [Day {simulated_day}, {simulated_hour:02d}:00] "
                    f"Round {round_num + 1}/{total_rounds} ({pct:.1f}%) "
                    f"expressed={len(self._agents_expressed)}/{len(all_agents)} "
                    f"actions={writer.total_actions} elapsed={elapsed:.0f}s"
                )

            # ── Pause check ─────────────────────────────────────────
            # A pause clicked mid-round is already detected (we poll commands
            # during the agent gather above), so just check once here — no need
            # to delay every round with a polling window when nobody paused.
            await ipc.process_commands()
            if ipc.is_paused():
                print(f"\n  [PAUSED] Round {round_num + 1} complete. Simulation paused for intervention.")
                ipc.update_status("paused", {
                    "current_round": round_num + 1,
                    "total_rounds": total_rounds,
                    "message": "Simulation paused — interventions can be applied",
                })
                # Enter pause loop: process commands until resume.
                # Poll quickly (every 0.2s) so resume is picked up promptly
                # even right after a slow intervention.
                while ipc.is_paused():
                    await ipc.process_commands()
                    await asyncio.sleep(0.2)
                print(f"  [RESUMED] Continuing to round {round_num + 2}...")
                ipc.update_status("running", {
                    "current_round": round_num + 1,
                    "total_rounds": total_rounds,
                })

            if not _shutdown_event.is_set() and not ipc.is_paused():
                # Check if we should continue or if close_env was received
                pass  # Continue to next round

        # Token & cost summary
        token_stats = opinion_skill.get_token_stats()

        writer.write_simulation_end(total_rounds, extra=token_stats)
        self._replay.complete_simulation(sim_id, total_rounds)
        elapsed = (datetime.now() - start_time).total_seconds()
        print(
            f"\nSimulation complete — "
            f"rounds={total_rounds} actions={writer.total_actions} "
            f"agents_expressed={len(self._agents_expressed)}/{len(all_agents)} "
            f"events_injected={len(self._injected_events_history)} "
            f"time={elapsed:.0f}s"
        )
        print(
            f"Token usage  — "
            f"prompt={token_stats['total_prompt_tokens']} "
            f"completion={token_stats['total_completion_tokens']} "
            f"total={token_stats['total_tokens']} "
            f"est_cost=${token_stats['estimated_cost_usd']:.4f}"
        )

        # ── Wait for interview calls ──────────────────────────────
        if self.wait_for_commands:
            print("\n" + "=" * 60)
            print("Agents ready for interview.")
            ipc.update_status("alive", {
                "total_agents":             len(all_agents),
                "agents_expressed_count":   len(self._agents_expressed),
                "agents_expressed":         list(self._agents_expressed),
                "simulation_actions_count": writer.total_actions,
            })
            try:
                while not _shutdown_event.is_set():
                    should_continue = await ipc.process_commands()
                    if not should_continue:
                        break
                    try:
                        await asyncio.wait_for(_shutdown_event.wait(), timeout=0.5)
                        break
                    except asyncio.TimeoutError:
                        pass
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass

        ipc.update_status("stopped")
        print("Runner exited.")
        print("=" * 60)


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

async def main():
    global _shutdown_event
    _shutdown_event = asyncio.Event()

    parser = argparse.ArgumentParser()
    parser.add_argument("--config",     required=True)
    parser.add_argument("--max-rounds", type=int, default=None)
    parser.add_argument("--no-wait",    action="store_true", default=False)
    parser.add_argument("--fast",       action="store_true", default=False, help="Fast mode: abbreviated prompts, reduced concurrency")
    parser.add_argument("--convergence-threshold", type=float, default=0.05, help="Convergence threshold (default: 0.05)")
    parser.add_argument("--convergence-window",  type=int,   default=3,     help="Convergence window (default: 3)")
    parser.add_argument("--coverage-saturation-rounds", type=int, default=None, help="Stop after N rounds with no new distinct position (coverage stop)")
    parser.add_argument("--no-coverage-stop", action="store_true", default=False, help="Use the legacy sentiment-stability stop instead of coverage saturation")
    parser.add_argument("--max-agents-per-round", type=int,   default=8,    help="Max agents per round (default: 8)")
    parser.add_argument("--min-agents-per-round", type=int,   default=2,     help="Min agents per round (default: 2)")
    parser.add_argument("--preset", choices=["quick", "balanced", "deep"], default=None, help="Simulation preset")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"Error: config not found: {args.config}")
        sys.exit(1)

    # Load and update config with preset params
    with open(args.config, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # Apply preset if specified
    if args.preset:
        presets = {
            "quick":  {"convergence_threshold": 0.10, "convergence_window": 2, "coverage_saturation_rounds": 3, "max_agents_per_round": 6, "min_agents_per_round": 2, "total_simulation_hours": 6, "minutes_per_round": 60},
            "balanced": {"convergence_threshold": 0.05, "convergence_window": 3, "coverage_saturation_rounds": 4, "max_agents_per_round": 10, "min_agents_per_round": 3, "total_simulation_hours": 12, "minutes_per_round": 60},
            "deep":     {"convergence_threshold": 0.03, "convergence_window": 5, "coverage_saturation_rounds": 6, "max_agents_per_round": 20, "min_agents_per_round": 5, "total_simulation_hours": 24, "minutes_per_round": 60},
        }
        config.update(presets[args.preset])
        print(f"  Preset    : {args.preset}")

    # Apply command line overrides
    if args.convergence_threshold != 0.05: config["convergence_threshold"] = args.convergence_threshold
    if args.convergence_window != 3:     config["convergence_window"] = args.convergence_window
    if args.coverage_saturation_rounds is not None: config["coverage_saturation_rounds"] = args.coverage_saturation_rounds
    if args.no_coverage_stop:            config["use_coverage_stop"] = False
    if args.max_agents_per_round != 15: config["max_agents_per_round"] = args.max_agents_per_round
    if args.min_agents_per_round != 3:  config["min_agents_per_round"] = args.min_agents_per_round

    # Save updated config
    with open(args.config, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    runner = AgentSocietyRunner(
        config_path=args.config,
        wait_for_commands=not args.no_wait,
        fast_mode=args.fast,
    )
    await runner.run(max_rounds=args.max_rounds)


def _signal_handler(signum, frame):
    global _cleanup_done
    if not _cleanup_done:
        _cleanup_done = True
        if _shutdown_event:
            _shutdown_event.set()
    else:
        sys.exit(1)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    asyncio.run(main())