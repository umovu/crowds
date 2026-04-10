"""
AgentSociety opinion-capture simulation runner.

Replaces run_twitter_simulation.py + run_reddit_simulation.py with a single
platform-agnostic runner that follows AgentSociety's Agent-Block-Action model.

Output: {simulation_dir}/opinion_space/actions.jsonl  (same schema as OASIS runners)

Usage:
    python run_simulation_as.py --config /path/to/simulation_config.json
    python run_simulation_as.py --config /path/to/simulation_config.json --no-wait
    python run_simulation_as.py --config /path/to/simulation_config.json --max-rounds 10
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
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.abspath(os.path.join(_scripts_dir, ".."))
_project_root = os.path.abspath(os.path.join(_backend_dir, ".."))
sys.path.insert(0, _backend_dir)

from dotenv import load_dotenv
_env = os.path.join(_project_root, ".env")
load_dotenv(_env if os.path.exists(_env) else os.path.join(_backend_dir, ".env"))

from openai import AsyncOpenAI

from app.services.agentsociety_opinion_block import (
    OpinionEnvironment,
    OpinionCaptureBlock,
    OpinionAgent,
    OpinionActionType,
)
from app.services.agentsociety_output_writer import AgentSocietyOutputWriter

# ── logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(asctime)s - %(name)s - %(message)s",
)
logger = logging.getLogger("agentsociety.runner")

_shutdown_event: Optional[asyncio.Event] = None
_cleanup_done = False

# ── IPC constants (same as OASIS runners) ─────────────────────
IPC_COMMANDS_DIR = "ipc_commands"
IPC_RESPONSES_DIR = "ipc_responses"
ENV_STATUS_FILE = "env_status.json"


# ─────────────────────────────────────────────────────────────
# Profile loading
# ─────────────────────────────────────────────────────────────

def load_profiles(simulation_dir: str) -> List[Dict]:
    """Load agent profiles from agentsociety_profiles.json."""
    path = os.path.join(simulation_dir, "agentsociety_profiles.json")
    if not os.path.exists(path):
        # Fallback: try reddit_profiles.json (same schema)
        path = os.path.join(simulation_dir, "reddit_profiles.json")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No profile file found in {simulation_dir}. "
            "Expected agentsociety_profiles.json or reddit_profiles.json."
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────
# IPC handler (interviews, close)
# ─────────────────────────────────────────────────────────────

class IPCHandler:
    def __init__(self, simulation_dir: str, agents: Dict[int, OpinionAgent], block: OpinionCaptureBlock):
        self.simulation_dir = simulation_dir
        self.agents = agents
        self.block = block
        self.commands_dir = os.path.join(simulation_dir, IPC_COMMANDS_DIR)
        self.responses_dir = os.path.join(simulation_dir, IPC_RESPONSES_DIR)
        self.status_file = os.path.join(simulation_dir, ENV_STATUS_FILE)
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)

    def update_status(self, status: str):
        with open(self.status_file, "w", encoding="utf-8") as f:
            json.dump({"status": status, "timestamp": datetime.now().isoformat()}, f)

    def poll_command(self) -> Optional[Dict]:
        if not os.path.isdir(self.commands_dir):
            return None
        files = sorted(
            (os.path.join(self.commands_dir, fn) for fn in os.listdir(self.commands_dir) if fn.endswith(".json")),
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
        resp = {"command_id": command_id, "status": status, "result": result,
                "error": error, "timestamp": datetime.now().isoformat()}
        with open(os.path.join(self.responses_dir, f"{command_id}.json"), "w", encoding="utf-8") as f:
            json.dump(resp, f, ensure_ascii=False)
        cmd_file = os.path.join(self.commands_dir, f"{command_id}.json")
        try:
            os.remove(cmd_file)
        except OSError:
            pass

    async def handle_interview(self, command_id: str, agent_id: int, prompt: str):
        agent = self.agents.get(agent_id)
        if not agent:
            self.send_response(command_id, "failed", error=f"Agent {agent_id} not found")
            return True
        try:
            result = await self.block.forward(agent, round_num=-1, initial_prompt=prompt)
            self.send_response(command_id, "completed", result={
                "agent_id": agent_id,
                "response": result.get("action_args", {}).get("content", "(no response)"),
                "timestamp": datetime.now().isoformat(),
            })
        except Exception as e:
            self.send_response(command_id, "failed", error=str(e))
        return True

    async def handle_batch_interview(self, command_id: str, interviews: List[Dict]):
        results = {}
        for iv in interviews:
            aid = iv.get("agent_id", 0)
            agent = self.agents.get(aid)
            if not agent:
                continue
            try:
                r = await self.block.forward(agent, round_num=-1, initial_prompt=iv.get("prompt", ""))
                results[aid] = {
                    "agent_id": aid,
                    "response": r.get("action_args", {}).get("content", ""),
                }
            except Exception as e:
                results[aid] = {"agent_id": aid, "error": str(e)}
        self.send_response(command_id, "completed", result={"interviews_count": len(results), "results": results})
        return True

    async def process_commands(self) -> bool:
        """Returns False if runner should exit."""
        cmd = self.poll_command()
        if not cmd:
            return True
        cid = cmd.get("command_id")
        ctype = cmd.get("command_type")
        args = cmd.get("args", {})
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
        self.config_path = config_path
        self.simulation_dir = os.path.dirname(os.path.abspath(config_path))
        self.wait_for_commands = wait_for_commands

        with open(config_path, "r", encoding="utf-8") as f:
            self.config: Dict[str, Any] = json.load(f)

        # output directory
        self.output_dir = os.path.join(self.simulation_dir, self.PLATFORM)
        os.makedirs(self.output_dir, exist_ok=True)

    # ── LLM client ────────────────────────────────────────────

    def _create_llm_client(self) -> tuple:
        """Return (AsyncOpenAI, model_name)."""
        api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
        base_url = os.environ.get("LLM_BASE_URL") or None
        model = (
            os.environ.get("LLM_MODEL_NAME")
            or self.config.get("llm_model", "gpt-4o-mini")
        )
        if not api_key:
            raise ValueError("LLM_API_KEY not set in environment")
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
        client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=120)
        logger.info(f"LLM: model={model}, base_url={str(base_url)[:40] if base_url else 'default'}")
        return client, model

    # ── Agent selection (same logic as OASIS runners) ─────────

    def _get_active_agents(
        self,
        all_agents: Dict[int, OpinionAgent],
        current_hour: int,
    ) -> List[OpinionAgent]:
        tc = self.config.get("time_config", {})
        base_min = tc.get("agents_per_hour_min", 5)
        base_max = tc.get("agents_per_hour_max", 20)
        peak_hours = tc.get("peak_hours", [19, 20, 21, 22])
        off_peak_hours = tc.get("off_peak_hours", [0, 1, 2, 3, 4, 5])

        if current_hour in peak_hours:
            mult = tc.get("peak_activity_multiplier", 1.5)
        elif current_hour in off_peak_hours:
            mult = tc.get("off_peak_activity_multiplier", 0.05)
        else:
            mult = 1.0

        target = int(random.uniform(base_min, base_max) * mult)

        candidates = [
            a for a in all_agents.values()
            if current_hour in a.active_hours and random.random() < a.activity_level
        ]
        random.shuffle(candidates)
        return candidates[:target]

    # ── Main run ──────────────────────────────────────────────

    async def run(self, max_rounds: Optional[int] = None):
        print("=" * 60)
        print("AgentSociety Opinion-Capture Simulation")
        print(f"Config: {self.config_path}")
        print(f"Simulation ID: {self.config.get('simulation_id', 'unknown')}")
        print("=" * 60)

        tc = self.config.get("time_config", {})
        total_hours = tc.get("total_simulation_hours", 72)
        minutes_per_round = tc.get("minutes_per_round", 60)
        total_rounds = int(total_hours * 60 / minutes_per_round)
        if max_rounds:
            total_rounds = min(total_rounds, max_rounds)

        print(f"\nParameters:")
        print(f"  total_hours={total_hours}  minutes_per_round={minutes_per_round}  total_rounds={total_rounds}")

        # ── Setup LLM + env + block ───────────────────────────
        llm_client, model_name = self._create_llm_client()

        db_path = os.path.join(self.output_dir, "opinion_simulation.db")
        env = OpinionEnvironment(db_path=db_path)
        block = OpinionCaptureBlock(llm_client=llm_client, model_name=model_name, env=env)

        # ── Load profiles → create agents ─────────────────────
        profiles = load_profiles(self.simulation_dir)
        agent_cfg_map: Dict[int, Dict] = {
            ac["agent_id"]: ac for ac in self.config.get("agent_configs", [])
        }

        all_agents: Dict[int, OpinionAgent] = {}
        for p in profiles:
            uid = p.get("user_id", p.get("id", 0))
            ac = agent_cfg_map.get(uid, {})
            agent = OpinionAgent(
                agent_id=uid,
                name=p.get("user_name") or p.get("username") or p.get("name", f"agent_{uid}"),
                persona=p.get("persona") or p.get("bio", ""),
                interested_topics=p.get("interested_topics", []),
                stance=ac.get("stance", "neutral"),
                activity_level=ac.get("activity_level", 0.5),
                active_hours=ac.get("active_hours", list(range(8, 23))),
                block=block,
                source_entity_uuid=p.get("source_entity_uuid"),
            )
            all_agents[uid] = agent

        print(f"  Loaded {len(all_agents)} agents\n")

        # ── Output writer ─────────────────────────────────────
        writer = AgentSocietyOutputWriter(self.output_dir)

        # ── IPC handler ───────────────────────────────────────
        ipc = IPCHandler(self.simulation_dir, all_agents, block)
        ipc.update_status("running")

        # ── Initial posts → seed opinions ─────────────────────
        event_cfg = self.config.get("event_config", {})
        for post in event_cfg.get("initial_posts", []):
            agent_id = post.get("poster_agent_id", 0)
            content = post.get("content", "")
            agent = all_agents.get(agent_id)
            if agent and content:
                oid = await env.add_opinion(agent_id, agent.name, content, [], 0)
                writer.write_action(0, agent_id, agent.name, {
                    "action_type": OpinionActionType.EXPRESS_OPINION,
                    "action_args": {"content": content, "opinion_id": oid},
                    "success": True,
                })
        print(f"Seeded {len(event_cfg.get('initial_posts', []))} initial opinions\n")
        print("Starting simulation loop...")

        start_time = datetime.now()

        # ── Main loop ─────────────────────────────────────────
        semaphore = asyncio.Semaphore(20)  # cap concurrent LLM calls

        async def step_agent(agent: OpinionAgent, rn: int) -> Dict:
            async with semaphore:
                return await agent.forward(rn)

        for round_num in range(total_rounds):
            simulated_minutes = round_num * minutes_per_round
            simulated_hour = (simulated_minutes // 60) % 24
            simulated_day = simulated_minutes // (24 * 60) + 1

            active = self._get_active_agents(all_agents, simulated_hour)
            if not active:
                continue

            tasks = [step_agent(a, round_num) for a in active]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for agent, result in zip(active, results):
                if isinstance(result, Exception):
                    logger.warning(f"Agent {agent.name} step failed: {result}")
                    continue
                writer.write_action(round_num, agent.agent_id, agent.name, result)

            # round end marker
            writer.write_round_end(round_num, simulated_minutes / 60)

            if (round_num + 1) % 5 == 0 or round_num == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                pct = (round_num + 1) / total_rounds * 100
                print(
                    f"  [Day {simulated_day}, {simulated_hour:02d}:00] "
                    f"Round {round_num + 1}/{total_rounds} ({pct:.1f}%) "
                    f"agents={len(active)} actions={writer.total_actions} "
                    f"elapsed={elapsed:.0f}s"
                )

        writer.write_simulation_end(total_rounds)
        total_elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\nSimulation complete! rounds={total_rounds} actions={writer.total_actions} time={total_elapsed:.0f}s")

        # ── Wait for IPC commands (interviews) ────────────────
        if self.wait_for_commands:
            print("\n" + "=" * 60)
            print("Waiting for commands (interview / close_env)...")
            ipc.update_status("alive")
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

    parser = argparse.ArgumentParser(description="AgentSociety Opinion-Capture Simulation")
    parser.add_argument("--config", required=True, help="Path to simulation_config.json")
    parser.add_argument("--max-rounds", type=int, default=None)
    parser.add_argument("--no-wait", action="store_true", default=False)
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
