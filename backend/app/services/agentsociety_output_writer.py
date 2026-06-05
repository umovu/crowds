"""
AgentSociety JSONL output writer.

Converts OpinionCaptureBlock action records into the exact same JSONL format
that graph_memory_updater.py already consumes — so the downstream pipeline
(Neo4j, graph tools, report agent) is completely unchanged.

JSONL line format (one JSON object per line):
{
    "round_num": int,
    "timestamp": str (ISO 8601),
    "platform": "opinion_space",
    "agent_id": int,
    "agent_name": str,
    "action_type": str,   # EXPRESS_OPINION | RESPOND_TO_OPINION | SEARCH_TOPIC | OBSERVE | DO_NOTHING | NON_PARTICIPATION
    "action_args": dict,
    "result": null,
    "success": bool,
    "reason": str,
    "internal_thought": str,
    "impact_score": float
}

Special event lines (same format as OASIS):
  {"event_type": "round_end",        "round": int, "simulated_hours": float}
  {"event_type": "simulation_end",   "total_rounds": int, "total_actions": int}
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

PLATFORM = "opinion_space"


class AgentSocietyOutputWriter:
    """
    Writes simulation action records to actions.jsonl in the simulation directory.
    Thread-safe via a simple file append pattern (one writer per simulation).
    """

    def __init__(self, simulation_dir: str):
        self.simulation_dir = simulation_dir
        self.jsonl_path = os.path.join(simulation_dir, "actions.jsonl")
        self._total_actions = 0

        # Truncate any previous run file
        os.makedirs(simulation_dir, exist_ok=True)
        open(self.jsonl_path, "w", encoding="utf-8").close()

    # ── Public API ────────────────────────────────────────────

    def write_action(
        self,
        round_num: int,
        agent_id: int,
        agent_name: str,
        action_result: Dict[str, Any],
    ):
        """Write a single agent action record."""
        action_type = action_result.get("action_type", "DO_NOTHING")
        if action_type not in ("DO_NOTHING", "OBSERVE"):
            self._total_actions += 1

        record = {
            "round_num": round_num,
            "timestamp": datetime.now().isoformat(),
            "platform": PLATFORM,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "action_type": action_type,
            "action_args": action_result.get("action_args", {}),
            "result": None,
            "success": action_result.get("success", True),
            "reason": action_result.get("reason", ""),
            "internal_thought": action_result.get("internal_thought", ""),
            "impact_score": action_result.get("impact_score", 0.0),
            # Product mode only: qualitative economic stance JSON (impulse / budget_tier
            # / disposition + objections). None in policy mode.
            "economic_reasoning": action_result.get("economic_reasoning"),
            "prompt_tokens": action_result.get("prompt_tokens", 0),
            "completion_tokens": action_result.get("completion_tokens", 0),
            "estimated_cost_usd": action_result.get("estimated_cost_usd", 0.0),
        }
        self._append(record)

    def write_round_end(self, round_num: int, simulated_hours: float):
        """Write a round_end event marker."""
        self._append({
            "event_type": "round_end",
            "round": round_num,
            "simulated_hours": simulated_hours,
        })

    def write_simulation_end(self, total_rounds: int, extra: Dict[str, Any] = None):
        """Write simulation_end event marker."""
        record = {
            "event_type": "simulation_end",
            "total_rounds": total_rounds,
            "total_actions": self._total_actions,
        }
        if extra:
            record.update(extra)
        self._append(record)

    @property
    def total_actions(self) -> int:
        return self._total_actions

    # ── Internal ──────────────────────────────────────────────

    def _append(self, record: Dict[str, Any]):
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
