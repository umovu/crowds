"""
ReplayStorage — structured SQLite storage for simulation replay and analysis.

Provides typed tables for opinion actions, agent activities, injected events,
and per-round sentiment snapshots. Used both during simulation runtime and
for post-simulation analytics.
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger

logger = get_logger("fub.replay_storage")


class ReplayStorage:
    """
    Structured SQLite storage for simulation data.

    Schema:
        - simulation_meta: Simulation-level metadata
        - opinion_actions: Every agent action per round
        - agent_activities: All activities including OBSERVE/DO_NOTHING
        - injected_events: Events triggered by rule engine
        - sentiment_snapshots: Per-round aggregate metrics
        - agent_profiles: Static agent profile data
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_db_dir()
        self._init_schema()

    def _ensure_db_dir(self):
        """Ensure parent directory exists."""
        dir_path = os.path.dirname(self.db_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

    def _init_schema(self):
        """Create tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                -- Simulation metadata
                CREATE TABLE IF NOT EXISTS simulation_meta (
                    simulation_id TEXT PRIMARY KEY,
                    project_id TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    total_rounds INTEGER,
                    total_agents INTEGER,
                    llm_model TEXT,
                    config_json TEXT
                );

                -- Every agent action (express, respond, search, observe, do_nothing)
                CREATE TABLE IF NOT EXISTS opinion_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    simulation_id TEXT NOT NULL,
                    round_num INTEGER NOT NULL,
                    agent_id INTEGER NOT NULL,
                    agent_name TEXT,
                    archetype TEXT,
                    action_type TEXT NOT NULL,
                    content TEXT,
                    topics_json TEXT,
                    impact_score REAL DEFAULT 0.0,
                    internal_thought TEXT,
                    reason TEXT,
                    opinion_id INTEGER,
                    target_opinion_id INTEGER,
                    target_agent_name TEXT,
                    created_at TEXT NOT NULL
                );

                -- Injected system events
                CREATE TABLE IF NOT EXISTS injected_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    simulation_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    rule_id TEXT NOT NULL,
                    round_injected INTEGER NOT NULL,
                    event_type TEXT,
                    category TEXT,
                    source TEXT,
                    title TEXT,
                    content TEXT,
                    affected_archetypes_json TEXT,
                    severity TEXT,
                    persist_rounds INTEGER,
                    trigger_metrics_json TEXT,
                    created_at TEXT NOT NULL
                );

                -- Per-round sentiment snapshots
                CREATE TABLE IF NOT EXISTS sentiment_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    simulation_id TEXT NOT NULL,
                    round_num INTEGER NOT NULL,
                    total_actions INTEGER,
                    avg_impact_score REAL,
                    pct_high_impact REAL,
                    avg_radicalism REAL,
                    non_participation_count INTEGER,
                    non_participation_pct REAL,
                    top_topics_json TEXT,
                    active_archetypes_json TEXT,
                    events_injected_count INTEGER,
                    created_at TEXT NOT NULL
                );

                -- Agent profiles (static)
                CREATE TABLE IF NOT EXISTS agent_profiles (
                    simulation_id TEXT NOT NULL,
                    agent_id INTEGER NOT NULL,
                    name TEXT,
                    archetype TEXT,
                    persona TEXT,
                    province TEXT,
                    age INTEGER,
                    gender TEXT,
                    occupation TEXT,
                    education TEXT,
                    stance TEXT,
                    base_radicalism INTEGER,
                    interested_topics_json TEXT,
                    group_affiliation TEXT,
                    background_story TEXT,
                    PRIMARY KEY (simulation_id, agent_id)
                );

                -- Indexes for common query patterns
                CREATE INDEX IF NOT EXISTS idx_actions_sim_round
                    ON opinion_actions(simulation_id, round_num);
                CREATE INDEX IF NOT EXISTS idx_actions_sim_agent
                    ON opinion_actions(simulation_id, agent_id);
                CREATE INDEX IF NOT EXISTS idx_actions_sim_archetype
                    ON opinion_actions(simulation_id, archetype);
                CREATE INDEX IF NOT EXISTS idx_events_sim_round
                    ON injected_events(simulation_id, round_injected);
                CREATE INDEX IF NOT EXISTS idx_snapshots_sim_round
                    ON sentiment_snapshots(simulation_id, round_num);
            """)
            conn.commit()
        logger.info(f"ReplayStorage initialized: {self.db_path}")

    # ── Simulation lifecycle ────────────────────────────────────

    def start_simulation(
        self,
        simulation_id: str,
        project_id: Optional[str] = None,
        total_agents: int = 0,
        llm_model: str = "",
        config: Optional[Dict] = None,
    ):
        """Record simulation start."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO simulation_meta
                (simulation_id, project_id, started_at, total_agents, llm_model, config_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    simulation_id,
                    project_id,
                    datetime.now().isoformat(),
                    total_agents,
                    llm_model,
                    json.dumps(config) if config else None,
                ),
            )
            conn.commit()
        logger.info(f"Simulation started: {simulation_id}")

    def complete_simulation(self, simulation_id: str, total_rounds: int):
        """Mark simulation as completed."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE simulation_meta
                SET completed_at = ?, total_rounds = ?
                WHERE simulation_id = ?
                """,
                (datetime.now().isoformat(), total_rounds, simulation_id),
            )
            conn.commit()

    # ── Agent profiles ──────────────────────────────────────────

    def store_agent_profiles(self, simulation_id: str, profiles: List[Dict[str, Any]]):
        """Store static agent profile data."""
        with sqlite3.connect(self.db_path) as conn:
            for p in profiles:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO agent_profiles
                    (simulation_id, agent_id, name, archetype, persona, province,
                     age, gender, occupation, education, stance, base_radicalism,
                     interested_topics_json, group_affiliation, background_story)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        simulation_id,
                        p.get("id", p.get("agent_id", 0)),
                        p.get("name"),
                        p.get("actor_archetype"),
                        p.get("persona"),
                        p.get("province"),
                        p.get("age"),
                        p.get("gender"),
                        p.get("occupation"),
                        p.get("education"),
                        p.get("stance"),
                        p.get("base_radicalism", 1),
                        json.dumps(p.get("interested_topics", [])),
                        p.get("group_affiliation"),
                        p.get("background_story"),
                    ),
                )
            conn.commit()

    # ── Opinion actions ─────────────────────────────────────────

    def store_action(
        self,
        simulation_id: str,
        round_num: int,
        agent_id: int,
        agent_name: str,
        archetype: str,
        action_type: str,
        content: str = "",
        topics: Optional[List[str]] = None,
        impact_score: float = 0.0,
        internal_thought: str = "",
        reason: str = "",
        opinion_id: Optional[int] = None,
        target_opinion_id: Optional[int] = None,
        target_agent_name: str = "",
    ):
        """Store a single agent action."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO opinion_actions
                (simulation_id, round_num, agent_id, agent_name, archetype,
                 action_type, content, topics_json, impact_score, internal_thought,
                 reason, opinion_id, target_opinion_id, target_agent_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    simulation_id,
                    round_num,
                    agent_id,
                    agent_name,
                    archetype,
                    action_type,
                    content,
                    json.dumps(topics or []),
                    impact_score,
                    internal_thought,
                    reason,
                    opinion_id,
                    target_opinion_id,
                    target_agent_name,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()

    def store_actions_batch(self, simulation_id: str, actions: List[Dict[str, Any]]):
        """Store multiple actions in a batch."""
        if not actions:
            return
        with sqlite3.connect(self.db_path) as conn:
            for a in actions:
                conn.execute(
                    """
                    INSERT INTO opinion_actions
                    (simulation_id, round_num, agent_id, agent_name, archetype,
                     action_type, content, topics_json, impact_score, internal_thought,
                     reason, opinion_id, target_opinion_id, target_agent_name, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        simulation_id,
                        a.get("round_num", 0),
                        a.get("agent_id", 0),
                        a.get("agent_name", ""),
                        a.get("archetype", ""),
                        a.get("action_type", ""),
                        a.get("content", ""),
                        json.dumps(a.get("topics", [])),
                        a.get("impact_score", 0.0),
                        a.get("internal_thought", ""),
                        a.get("reason", ""),
                        a.get("opinion_id"),
                        a.get("target_opinion_id"),
                        a.get("target_agent_name", ""),
                        datetime.now().isoformat(),
                    ),
                )
            conn.commit()

    # ── Injected events ─────────────────────────────────────────

    def store_injected_event(self, simulation_id: str, event: Dict[str, Any]):
        """Store a triggered/injected event."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO injected_events
                (simulation_id, event_id, rule_id, round_injected, event_type,
                 category, source, title, content, affected_archetypes_json,
                 severity, persist_rounds, trigger_metrics_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    simulation_id,
                    event.get("event_id", ""),
                    event.get("rule_id", ""),
                    event.get("round_injected", 0),
                    event.get("type", ""),
                    event.get("category", ""),
                    event.get("source", ""),
                    event.get("title", ""),
                    event.get("content", ""),
                    json.dumps(event.get("affected_archetypes", [])),
                    event.get("severity", "low"),
                    event.get("persist_rounds", 1),
                    json.dumps(event.get("trigger_metrics", {})),
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()

    # ── Sentiment snapshots ─────────────────────────────────────

    def store_sentiment_snapshot(
        self,
        simulation_id: str,
        round_num: int,
        metrics: Dict[str, Any],
        events_injected_count: int = 0,
    ):
        """Store per-round aggregate sentiment metrics."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO sentiment_snapshots
                (simulation_id, round_num, total_actions, avg_impact_score,
                 pct_high_impact, avg_radicalism, non_participation_count,
                 non_participation_pct, top_topics_json, active_archetypes_json,
                 events_injected_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    simulation_id,
                    round_num,
                    metrics.get("total_actions", 0),
                    metrics.get("avg_impact_score", 0.0),
                    metrics.get("pct_agents_with_impact_above_07", 0.0),
                    metrics.get("avg_radicalism", 0.0),
                    metrics.get("non_participation_count", 0),
                    metrics.get("non_participation_proportion", 0.0),
                    json.dumps(metrics.get("topic_counts", {})),
                    json.dumps(metrics.get("archetype_counts", {})),
                    events_injected_count,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()

    # ── Query helpers ───────────────────────────────────────────

    def query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute a raw SQL query and return results as dicts."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def get_simulation_ids(self) -> List[str]:
        """List all simulation IDs."""
        rows = self.query("SELECT simulation_id FROM simulation_meta ORDER BY started_at DESC")
        return [r["simulation_id"] for r in rows]

    def get_simulation_meta(self, simulation_id: str) -> Optional[Dict[str, Any]]:
        """Get simulation metadata."""
        rows = self.query(
            "SELECT * FROM simulation_meta WHERE simulation_id = ?",
            (simulation_id,),
        )
        return rows[0] if rows else None

    def close(self):
        """No-op — SQLite connections are per-operation."""
        pass
