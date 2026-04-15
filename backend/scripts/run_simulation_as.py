"""
AgentSociety opinion-capture simulation runner — full framework integration.

Uses agentsociety's real infrastructure:
  ray.init()              — local Ray cluster for parallel LLM calls
  LLM (Ray actors)        — agentsociety's LLM class with concurrent request handling
  AgentToolbox            — bundles LLM + OllamaEmbedding
  KVMemory                — agent profile stored in vector-searchable memory
  StreamMemory            — agent's diary of expressed opinions (recalled in do_interview)
  CitizenAgentBase        — base agent with do_interview() + do_survey()
  Block                   — OpinionCaptureBlock dispatches actions

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
load_dotenv(_env if os.path.exists(_env) else os.path.join(_backend_dir, ".env"))

# ── agentsociety imports ───────────────────────────────────────
import ray
from agentsociety.agent import AgentToolbox
from agentsociety.llm import LLM, LLMConfig, LLMProviderType
from agentsociety.memory import Memory

# ── project imports ────────────────────────────────────────────
from app.services.agentsociety_opinion_block import (
    OpinionEnvironment,
    OpinionActionType,
)
from app.services.ollama_embedding import OllamaEmbedding
from app.services.sim_environment import SimEnvironment
from app.services.opinion_agent import OpinionCitizenAgent, build_memory_config
from app.services.opinion_block import OpinionCaptureBlock
from app.services.agentsociety_output_writer import AgentSocietyOutputWriter

# ── logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(asctime)s - %(name)s - %(message)s",
)
logger = logging.getLogger("agentsociety.runner")

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
# LLM factory
# ─────────────────────────────────────────────────────────────

def create_agentsociety_llm(api_key: str, model: str, base_url: Optional[str]) -> LLM:
    """
    Create agentsociety's real LLM object.
    Uses LLMProviderType.VLLM when a custom base_url is set (Ollama, local endpoints).
    Uses LLMProviderType.OpenAI for standard OpenAI API.
    """
    if base_url:
        # Ollama / local endpoint — must use VLLM provider (only one that accepts base_url)
        provider = LLMProviderType.VLLM
        # Ensure Ollama's OpenAI-compatible endpoint
        if not base_url.endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"
    else:
        provider = LLMProviderType.OpenAI
        base_url = None

    config = LLMConfig(
        provider=provider,
        api_key=api_key or "ollama",
        model=model,
        base_url=base_url,
        concurrency=10,   # max parallel LLM requests
        timeout=30,
    )
    return LLM(configs=[config])


# ─────────────────────────────────────────────────────────────
# IPC handler
# ─────────────────────────────────────────────────────────────

class IPCHandler:
    def __init__(
        self,
        simulation_dir: str,
        agents: Dict[int, OpinionCitizenAgent],
    ):
        self.simulation_dir = simulation_dir
        self.agents         = agents
        self.commands_dir   = os.path.join(simulation_dir, IPC_COMMANDS_DIR)
        self.responses_dir  = os.path.join(simulation_dir, IPC_RESPONSES_DIR)
        self.status_file    = os.path.join(simulation_dir, ENV_STATUS_FILE)
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)

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
        for fp in files:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
        return None

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

    async def handle_interview(self, command_id: str, agent_id: int, prompt: str):
        """
        Uses agentsociety's CitizenAgentBase.do_interview().
        The agent searches KVMemory (profile) + StreamMemory (expressed opinions)
        to answer in character based on their simulation history.
        """
        agent = self.agents.get(agent_id)
        if not agent:
            self.send_response(command_id, "failed", error=f"Agent {agent_id} not found")
            return True
        try:
            # Real do_interview() — inherited from CitizenAgentBase
            response = await agent.do_interview(prompt)
            self.send_response(command_id, "completed", result={
                "agent_id":  agent_id,
                "response":  response,
                "timestamp": datetime.now().isoformat(),
            })
        except Exception as e:
            logger.error(f"do_interview failed for agent {agent_id}: {e}")
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
                response = await agent.do_interview(iv.get("prompt", ""))
                results[f"opinion_space_{aid}"] = {"agent_id": aid, "response": response}
            except Exception as e:
                results[f"opinion_space_{aid}"] = {"agent_id": aid, "error": str(e)}
        self.send_response(command_id, "completed", result={
            "interviews_count": len(results),
            "results": results,
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
        if ctype == "interview":
            return await self.handle_interview(cid, args.get("agent_id", 0), args.get("prompt", ""))
        elif ctype == "batch_interview":
            return await self.handle_batch_interview(cid, args.get("interviews", []))
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

    def __init__(self, config_path: str, wait_for_commands: bool = True):
        self.config_path       = config_path
        self.simulation_dir    = os.path.dirname(os.path.abspath(config_path))
        self.wait_for_commands = wait_for_commands

        with open(config_path, "r", encoding="utf-8") as f:
            self.config: Dict[str, Any] = json.load(f)

        self.output_dir = os.path.join(self.simulation_dir, self.PLATFORM)
        os.makedirs(self.output_dir, exist_ok=True)

        self._agents_expressed: set = set()

    def _get_active_agents(
        self,
        all_agents: Dict[int, OpinionCitizenAgent],
        current_hour: int,
    ) -> List[OpinionCitizenAgent]:
        tc             = self.config.get("time_config", {})
        base_min       = tc.get("agents_per_hour_min", 5)
        base_max       = tc.get("agents_per_hour_max", 20)
        peak_hours     = tc.get("peak_hours", [19, 20, 21, 22])
        off_peak_hours = tc.get("off_peak_hours", [0, 1, 2, 3, 4, 5])

        if current_hour in peak_hours:
            mult = tc.get("peak_activity_multiplier", 1.5)
        elif current_hour in off_peak_hours:
            mult = tc.get("off_peak_activity_multiplier", 0.05)
        else:
            mult = 1.0

        target = int(random.uniform(base_min, base_max) * mult)
        # Cap should never be smaller than total agents — avoids randomly excluding
        # agents when the pool is small. The probability gate (activity_level) is
        # the right place to control participation density, not the hard cap.
        target = max(target, len(all_agents))
        candidates = [
            a for a in all_agents.values()
            if current_hour in a.active_hours
            and random.random() < a.activity_level
        ]
        random.shuffle(candidates)
        return candidates[:target]

    async def run(self, max_rounds: Optional[int] = None):
        print("=" * 60)
        print("AgentSociety Opinion-Capture Simulation")
        print("  Framework : agentsociety (CitizenAgentBase + Block + Memory)")
        print("  LLM       : agentsociety LLM (Ray actors)")
        print("  Embedding : Ollama nomic-embed-text")
        print("  Memory    : KVMemory (profile) + StreamMemory (diary)")
        print(f"  Sim ID    : {self.config.get('simulation_id', 'unknown')}")
        print("=" * 60)

        # ── Initialise Ray (local, no cluster needed) ──────────
        ray.init(ignore_reinit_error=True)
        print("  Ray       : initialised (local)")

        tc                = self.config.get("time_config", {})
        total_hours       = tc.get("total_simulation_hours", 72)
        minutes_per_round = tc.get("minutes_per_round", 60)
        total_rounds      = int(total_hours * 60 / minutes_per_round)
        if max_rounds:
            total_rounds = min(total_rounds, max_rounds)

        # ── Read LLM config from environment ──────────────────
        api_key  = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
        base_url = os.environ.get("LLM_BASE_URL") or None
        model    = (
            os.environ.get("LLM_MODEL_NAME")
            or self.config.get("llm_model", "gpt-4o-mini")
        )
        if not api_key:
            raise ValueError("LLM_API_KEY not set in environment")

        # ── Real agentsociety LLM (Ray actors) ────────────────
        llm = create_agentsociety_llm(api_key, model, base_url)
        print(f"  LLM model : {model}")

        # ── Ollama embedding for KVMemory + StreamMemory ───────
        ollama_base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        embed_model = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        embedding   = OllamaEmbedding(model=embed_model, base_url=ollama_base)

        if not embedding.health_check():
            logger.warning(
                f"Ollama embedding model '{embed_model}' not found at {ollama_base}. "
                "Memory search will return zero vectors. Run: ollama pull nomic-embed-text"
            )
        else:
            print(f"  Embedding : {embed_model} via Ollama")

        # ── AgentToolbox — use model_construct to bypass type validation ──
        # (OllamaEmbedding is not a fastembed.SparseTextEmbedding subclass)
        toolbox = AgentToolbox.model_construct(
            llm=llm,
            embedding=embedding,
            environment=None,
            messager=None,
            database_writer=None,
        )

        # ── Shared opinion feed (SQLite) ───────────────────────
        db_path = os.path.join(self.output_dir, "opinion_simulation.db")
        env     = OpinionEnvironment(db_path=db_path)

        # ── Shared simulation environment (for StreamMemory timestamps) ──
        sim_env = SimEnvironment()

        # ── Shared Block ───────────────────────────────────────
        block = OpinionCaptureBlock(toolbox=toolbox, env=env)

        # ── Load profiles → create agents ─────────────────────
        profiles      = load_profiles(self.simulation_dir)
        agent_cfg_map = {
            ac["agent_id"]: ac
            for ac in self.config.get("agent_configs", [])
        }

        # Archetype → activity_level override.
        # The config generator assigns activity_level without knowing actor_archetype,
        # so we correct it here. Loud archetypes must participate frequently;
        # quiet archetypes may be pulled back further.
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

            # Build real KVMemory + StreamMemory from profile
            mem_config = build_memory_config(p)
            memory     = Memory(
                environment=sim_env,    # provides get_datetime() for StreamMemory
                embedding=embedding,
                memory_config=mem_config,
            )
            # Initialize KVMemory embeddings so search works immediately
            await memory.initialize_embeddings()

            archetype = p.get("actor_archetype") or "civic_moderate"
            # Use archetype-based activity level; config generator didn't know archetype
            activity_level = _ARCHETYPE_ACTIVITY.get(archetype, ac.get("activity_level", 0.6))

            agent = OpinionCitizenAgent(
                agent_id=uid,
                name=p.get("name", f"agent_{uid}"),
                toolbox=toolbox,
                memory=memory,
                block=block,
                interested_topics=p.get("interested_topics", []),
                stance=ac.get("stance", "neutral"),
                activity_level=activity_level,
                active_hours=ac.get("active_hours", list(range(8, 23))),
                group_affiliation=p.get("group_affiliation"),
                actor_archetype=p.get("actor_archetype"),
                behavioral_tendencies=p.get("behavioral_tendencies"),
                source_entity_uuid=p.get("source_entity_uuid"),
            )
            # Set stance in KVMemory
            await agent.status.update("stance", ac.get("stance", "neutral"))
            all_agents[uid] = agent

        print(f"  Agents    : {len(all_agents)} loaded with KVMemory + StreamMemory\n")

        writer = AgentSocietyOutputWriter(self.output_dir)
        ipc    = IPCHandler(self.simulation_dir, all_agents)
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
                # Save to StreamMemory so agent remembers this in do_interview()
                await agent.memory.stream.add(
                    topic="express opinion",
                    description=content,
                )
                self._agents_expressed.add(agent_id)
                writer.write_action(0, agent_id, agent.name, {
                    "action_type": OpinionActionType.EXPRESS_OPINION,
                    "action_args": {"content": content, "opinion_id": oid},
                    "success": True,
                })

        print(f"Seeded {len(event_cfg.get('initial_posts', []))} initial opinions")
        print("Starting simulation loop...\n")

        start_time = datetime.now()
        semaphore  = asyncio.Semaphore(10)

        async def step_agent(agent: OpinionCitizenAgent, rn: int):
            async with semaphore:
                return await block.forward_agent(agent, round_num=rn)

        for round_num in range(total_rounds):
            simulated_minutes = round_num * minutes_per_round
            simulated_hour    = (simulated_minutes // 60) % 24
            simulated_day     = simulated_minutes // (24 * 60) + 1

            # Advance simulation clock for StreamMemory timestamps
            sim_env.set_round(round_num)

            active = self._get_active_agents(all_agents, simulated_hour)
            if not active:
                continue

            tasks   = [step_agent(a, round_num) for a in active]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for agent, result in zip(active, results):
                if isinstance(result, Exception):
                    logger.warning(f"Agent {agent.name} step failed: {result}")
                    continue

                action_type = getattr(result, "action_type", "")
                if action_type in (
                    OpinionActionType.EXPRESS_OPINION,
                    OpinionActionType.RESPOND_TO_OPINION,
                ):
                    self._agents_expressed.add(agent.agent_id)

                record = (
                    result.model_dump()
                    if hasattr(result, "model_dump")
                    else result
                )
                writer.write_action(round_num, agent.agent_id, agent.name, record)

            ipc.update_status("running", {
                "total_agents":             len(all_agents),
                "agents_expressed_count":   len(self._agents_expressed),
                "agents_expressed":         list(self._agents_expressed),
                "simulation_actions_count": writer.total_actions,
                "current_round":            round_num + 1,
                "total_rounds":             total_rounds,
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

        writer.write_simulation_end(total_rounds)
        elapsed = (datetime.now() - start_time).total_seconds()
        print(
            f"\nSimulation complete — "
            f"rounds={total_rounds} actions={writer.total_actions} "
            f"agents_expressed={len(self._agents_expressed)}/{len(all_agents)} "
            f"time={elapsed:.0f}s"
        )

        # ── Wait for do_interview() calls from Step 5 ─────────
        if self.wait_for_commands:
            print("\n" + "=" * 60)
            print("Agents ready for interview (Step 5).")
            print("do_interview() searches each agent's KVMemory + StreamMemory.")
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
        ray.shutdown()
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
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"Error: config not found: {args.config}")
        sys.exit(1)

    runner = AgentSocietyRunner(
        config_path=args.config,
        wait_for_commands=not args.no_wait,
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
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        print("Process exited.")
