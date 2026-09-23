"""
SimulationDataExporter — structured data export for external validation.

Enables correlation of simulation outputs with real-world data sources
(e.g., crime stats, poll results, economic indicators).
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from ..config import Config
from ..utils.logger import get_logger
from . import data_model

logger = get_logger("fub.data_exporter")


class SimulationDataExporter:
    """Export agent states and impact data in structured formats."""

    def __init__(self, simulation_id: str):
        self.simulation_id = simulation_id
        self.sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)

    def export_agent_states(self, rounds: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Export time-series agent state data.

        Reads from persisted state snapshots (if available) or reconstructs
        from profile + posts_history.

        Returns:
            {
                "simulation_id": str,
                "generated_at": str,
                "records": [
                    {
                        "agent_id": int,
                        "agent_name": str,
                        "round": int,
                        "stance": str,
                        "current_radicalism": int,
                        "mobilization_level": int,
                        "safety_economic": int,
                        "safety_physical": int,
                        "post_count": int,
                    }
                ]
            }
        """
        records = []
        profiles_path = os.path.join(self.sim_dir, "agentsociety_profiles.json")

        if not os.path.exists(profiles_path):
            return {
                "simulation_id": self.simulation_id,
                "generated_at": datetime.now().isoformat(),
                "records": [],
                "error": "Profiles not found",
            }

        with open(profiles_path, 'r', encoding='utf-8') as f:
            profiles = json.load(f)

        for profile in profiles:
            agent_id = profile.get("id", profile.get("agent_id"))
            name = profile.get("name", f"Agent_{agent_id}")

            # Extract current state from profile (last known state)
            needs = profile.get("needs", {})
            posts = profile.get("posts_history", [])

            # Build one record per agent (current state snapshot)
            # In a full implementation, this would read round-by-round snapshots
            record = {
                "agent_id": agent_id,
                "agent_name": name,
                "round": profile.get("last_post_round", 0),
                "stance": profile.get("stance", "neutral"),
                "current_radicalism": profile.get("current_radicalism", profile.get("base_radicalism", 1)),
                "mobilization_level": profile.get("mobilization_level", 0),
                "safety_economic": needs.get("safety_economic", 0),
                "safety_physical": needs.get("safety_physical", 0),
                "post_count": len(posts),
            }
            records.append(record)

        return {
            "simulation_id": self.simulation_id,
            "generated_at": datetime.now().isoformat(),
            "record_count": len(records),
            "records": records,
        }

    def export_impact_summary(self) -> Dict[str, Any]:
        """
        Export aggregate impact summary from latest impact interviews.

        Reads from persisted impact interview results if available.
        """
        # Check for cached impact results
        impact_path = os.path.join(self.sim_dir, "impact_interviews.json")
        if os.path.exists(impact_path):
            with open(impact_path, 'r', encoding='utf-8') as f:
                return json.load(f)

        # Fallback: return empty structure
        return {
            "simulation_id": self.simulation_id,
            "generated_at": datetime.now().isoformat(),
            "stance_distribution": {},
            "mobilization_risk": {"low": 0, "medium": 0, "high": 0},
            "granularity_distribution": {"micro": 0, "meso": 0, "macro": 0},
            "affected_entities": [],
            "predicted_actions": [],
            "note": "No impact interviews conducted yet. Run /interview/impact first.",
        }

    def save_impact_results(self, results: Dict[str, Any]) -> None:
        """Persist impact interview results for later export."""
        impact_path = os.path.join(self.sim_dir, "impact_interviews.json")
        data_model.warn_if_off_model(logger, f"Impact interviews {self.simulation_id}", "answer", results,
                                     check=data_model.round_result_problems)
        with open(impact_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved impact results to {impact_path}")

