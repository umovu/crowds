"""
PostSimAnalytics — query engine for post-simulation analysis.

Provides structured data for dashboard visualizations:
- Sentiment timeline with event markers
- Archetype activity heatmap
- Event impact before/after comparisons
- Topic cascade detection
- Radicalism drift tracking
- Non-participation breakdown
"""

import json
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from .replay_storage import ReplayStorage
from ..utils.logger import get_logger

logger = get_logger("fub.analytics")


class PostSimAnalytics:
    """
    Analysis layer on top of ReplayStorage.
    """

    def __init__(self, storage: ReplayStorage):
        self.storage = storage

    # ── Sentiment Timeline ──────────────────────────────────────

    def sentiment_timeline(self, simulation_id: str) -> List[Dict[str, Any]]:
        """
        Returns per-round sentiment metrics with event markers.

        Output: [{round, avg_impact, avg_radicalism, non_participation_pct,
                  events: [{title, severity, source}], top_topics}, ...]
        """
        snapshots = self.storage.query(
            "SELECT * FROM sentiment_snapshots WHERE simulation_id = ? ORDER BY round_num",
            (simulation_id,),
        )

        events = self.storage.query(
            "SELECT round_injected, title, severity, source, category FROM injected_events WHERE simulation_id = ? ORDER BY round_injected",
            (simulation_id,),
        )
        events_by_round = defaultdict(list)
        for e in events:
            events_by_round[e["round_injected"]].append({
                "title": e["title"],
                "severity": e["severity"],
                "source": e["source"],
                "category": e["category"],
            })

        timeline = []
        for snap in snapshots:
            timeline.append({
                "round": snap["round_num"],
                "avg_impact": snap["avg_impact_score"],
                "avg_radicalism": snap["avg_radicalism"],
                "non_participation_pct": snap["non_participation_pct"],
                "total_actions": snap["total_actions"],
                # Coverage metric — first-class: cumulative distinct positions,
                # how many were new this round, and their spread.
                "distinct_positions": snap["distinct_positions"] if "distinct_positions" in snap.keys() else 0,
                "new_positions": snap["new_positions"] if "new_positions" in snap.keys() else 0,
                "position_spread": snap["position_spread"] if "position_spread" in snap.keys() else 0.0,
                "events": events_by_round.get(snap["round_num"], []),
                "top_topics": self._parse_json(snap["top_topics_json"]),
            })

        return timeline

    # ── Archetype Activity ──────────────────────────────────────

    def archetype_activity(self, simulation_id: str) -> List[Dict[str, Any]]:
        """
        Returns per-round archetype activity metrics.

        Output: [{round, archetype, action_count, avg_impact, 
                  express_count, respond_count, observe_count}, ...]
        """
        rows = self.storage.query(
            """
            SELECT round_num, archetype, action_type, COUNT(*) as count,
                   AVG(impact_score) as avg_impact
            FROM opinion_actions
            WHERE simulation_id = ? AND agent_id >= 0
            GROUP BY round_num, archetype, action_type
            ORDER BY round_num, archetype
            """,
            (simulation_id,),
        )

        # Pivot
        activity = defaultdict(lambda: defaultdict(dict))
        for r in rows:
            rn = r["round_num"]
            arch = r["archetype"] or "unknown"
            atype = r["action_type"]
            activity[rn][arch][atype] = {
                "count": r["count"],
                "avg_impact": round(r["avg_impact"] or 0, 3),
            }

        result = []
        for rn in sorted(activity.keys()):
            for arch in sorted(activity[rn].keys()):
                counts = activity[rn][arch]
                result.append({
                    "round": rn,
                    "archetype": arch,
                    "action_count": sum(c.get("count", 0) for c in counts.values()),
                    "avg_impact": round(
                        sum(
                            (c.get("avg_impact", 0) * c.get("count", 0))
                            for c in counts.values()
                        )
                        / max(sum(c.get("count", 0) for c in counts.values()), 1),
                        3,
                    ),
                    "express_count": counts.get("EXPRESS_OPINION", {}).get("count", 0),
                    "respond_count": counts.get("RESPOND_TO_OPINION", {}).get("count", 0),
                    "observe_count": counts.get("OBSERVE", {}).get("count", 0),
                })

        return result

    # ── Event Impact ────────────────────────────────────────────

    def event_impact(self, simulation_id: str, event_id: str) -> Dict[str, Any]:
        """
        Returns before/after impact comparison for a specific event.

        Output: {
            event: {title, round_injected, category, severity},
            before: {rounds, avg_impact, avg_radicalism, top_topics, sample_contents},
            after: {rounds, avg_impact, avg_radicalism, top_topics, sample_contents},
            affected_agents: [{agent_id, name, archetype, reaction_content}]
        }
        """
        events = self.storage.query(
            "SELECT * FROM injected_events WHERE simulation_id = ? AND event_id = ?",
            (simulation_id, event_id),
        )
        if not events:
            return {"error": "Event not found"}

        event = events[0]
        round_injected = event["round_injected"]
        window = 3  # rounds before/after

        # Before
        before_actions = self.storage.query(
            """
            SELECT * FROM opinion_actions
            WHERE simulation_id = ? AND round_num >= ? AND round_num < ? AND agent_id >= 0
            ORDER BY round_num
            """,
            (simulation_id, max(0, round_injected - window), round_injected),
        )

        # After
        after_actions = self.storage.query(
            """
            SELECT * FROM opinion_actions
            WHERE simulation_id = ? AND round_num > ? AND round_num <= ? AND agent_id >= 0
            ORDER BY round_num
            """,
            (simulation_id, round_injected, round_injected + window),
        )

        def summarize(actions):
            if not actions:
                return {"rounds": 0, "avg_impact": 0, "avg_radicalism": 0, "top_topics": {}, "sample_contents": []}
            impacts = [a["impact_score"] or 0 for a in actions]
            contents = [a["content"] for a in actions if a["content"]]
            topics = Counter()
            for a in actions:
                for t in self._parse_json(a.get("topics_json", "[]")):
                    topics[t] += 1
            return {
                "rounds": len(set(a["round_num"] for a in actions)),
                "action_count": len(actions),
                "avg_impact": round(sum(impacts) / len(impacts), 3),
                "top_topics": dict(topics.most_common(5)),
                "sample_contents": contents[:5],
            }

        # Affected agents = agents who acted in the round after injection
        affected = self.storage.query(
            """
            SELECT DISTINCT agent_id, agent_name, archetype, content
            FROM opinion_actions
            WHERE simulation_id = ? AND round_num = ? AND agent_id >= 0
            AND action_type IN ('EXPRESS_OPINION', 'RESPOND_TO_OPINION')
            LIMIT 20
            """,
            (simulation_id, round_injected + 1),
        )

        return {
            "event": {
                "event_id": event["event_id"],
                "title": event["title"],
                "round_injected": event["round_injected"],
                "category": event["category"],
                "severity": event["severity"],
                "content": event["content"],
            },
            "before": summarize(before_actions),
            "after": summarize(after_actions),
            "affected_agents": [
                {"agent_id": a["agent_id"], "name": a["agent_name"], "archetype": a["archetype"], "reaction": a["content"]}
                for a in affected
            ],
        }

    # ── Topic Cascade ───────────────────────────────────────────

    def topic_cascade(self, simulation_id: str) -> List[Dict[str, Any]]:
        """
        Detects when topics first appeared, peaked, and faded.

        Output: [{topic, first_round, peak_round, peak_count, total_mentions, trend}, ...]
        """
        actions = self.storage.query(
            "SELECT round_num, topics_json FROM opinion_actions WHERE simulation_id = ? AND agent_id >= 0",
            (simulation_id,),
        )

        topic_rounds = defaultdict(lambda: Counter())
        for a in actions:
            rn = a["round_num"]
            for topic in self._parse_json(a.get("topics_json", "[]")):
                topic_rounds[topic][rn] += 1

        cascades = []
        for topic, rounds in topic_rounds.items():
            if not rounds:
                continue
            first_round = min(rounds.keys())
            peak_round = max(rounds.keys(), key=lambda r: rounds[r])
            peak_count = rounds[peak_round]
            total = sum(rounds.values())

            # Trend: rising, falling, steady
            sorted_rounds = sorted(rounds.keys())
            if len(sorted_rounds) >= 3:
                first_half = sum(rounds[r] for r in sorted_rounds[: len(sorted_rounds) // 2])
                second_half = sum(rounds[r] for r in sorted_rounds[len(sorted_rounds) // 2 :])
                if second_half > first_half * 1.5:
                    trend = "rising"
                elif second_half < first_half * 0.5:
                    trend = "falling"
                else:
                    trend = "steady"
            else:
                trend = "brief"

            cascades.append({
                "topic": topic,
                "first_round": first_round,
                "peak_round": peak_round,
                "peak_count": peak_count,
                "total_mentions": total,
                "trend": trend,
            })

        return sorted(cascades, key=lambda x: x["total_mentions"], reverse=True)

    # ── Radicalism Drift ────────────────────────────────────────

    def radicalism_drift(self, simulation_id: str) -> List[Dict[str, Any]]:
        """
        Per-agent radicalism trajectory.

        Output: [{agent_id, name, archetype, rounds: [{round, impact, action_type, content}], 
                  overall_trend}, ...]
        """
        actions = self.storage.query(
            """
            SELECT agent_id, agent_name, archetype, round_num, impact_score, action_type, content
            FROM opinion_actions
            WHERE simulation_id = ? AND agent_id >= 0
            ORDER BY agent_id, round_num
            """,
            (simulation_id,),
        )

        agent_trajectories = defaultdict(list)
        for a in actions:
            agent_trajectories[a["agent_id"]].append({
                "round": a["round_num"],
                "impact": a["impact_score"] or 0,
                "action_type": a["action_type"],
                "content": a["content"],
            })

        profiles = self.storage.query(
            "SELECT agent_id, name, archetype, base_radicalism FROM agent_profiles WHERE simulation_id = ?",
            (simulation_id,),
        )
        profile_map = {p["agent_id"]: p for p in profiles}

        result = []
        for agent_id, rounds in agent_trajectories.items():
            if len(rounds) < 2:
                continue
            p = profile_map.get(agent_id, {})
            first_impact = rounds[0]["impact"]
            last_impact = rounds[-1]["impact"]
            if last_impact > first_impact * 1.3:
                trend = "escalating"
            elif last_impact < first_impact * 0.7:
                trend = "de-escalating"
            else:
                trend = "stable"

            result.append({
                "agent_id": agent_id,
                "name": p.get("name", f"Agent_{agent_id}"),
                "archetype": p.get("archetype", "unknown"),
                "base_radicalism": p.get("base_radicalism", 1),
                "rounds": rounds,
                "overall_trend": trend,
                "avg_impact": round(sum(r["impact"] for r in rounds) / len(rounds), 3),
                "max_impact": max(r["impact"] for r in rounds),
            })

        return sorted(result, key=lambda x: x["max_impact"], reverse=True)

    # ── Non-Participation Breakdown ─────────────────────────────

    def non_participation_breakdown(self, simulation_id: str) -> Dict[str, Any]:
        """
        Analysis of why agents didn't participate.

        Output: {
            total_non_participation_actions,
            by_reason: {reason_category: count},
            by_archetype: {archetype: count},
            by_round: [{round, count, reasons}],
            sample_quotes: [{agent_id, name, reason, internal_thought}]
        }
        """
        actions = self.storage.query(
            """
            SELECT round_num, agent_id, agent_name, archetype, action_type, reason, internal_thought
            FROM opinion_actions
            WHERE simulation_id = ? AND agent_id >= 0
            AND action_type IN ('DO_NOTHING', 'NON_PARTICIPATION', 'OBSERVE')
            """,
            (simulation_id,),
        )

        reason_counts = Counter()
        archetype_counts = Counter()
        round_counts = defaultdict(lambda: {"count": 0, "reasons": Counter()})
        samples = []

        for a in actions:
            reason = (a["reason"] or "").lower()
            arch = a["archetype"] or "unknown"
            archetype_counts[arch] += 1
            round_counts[a["round_num"]]["count"] += 1
            round_counts[a["round_num"]]["reasons"][reason] += 1

            # Categorize reason
            category = "other"
            if any(w in reason for w in ["distrust", "don't trust", "fake", "manipulation"]):
                category = "distrust"
            elif any(w in reason for w in ["busy", "time", "surviving", "struggling"]):
                category = "time_constraints"
            elif any(w in reason for w in ["don't care", "apathetic", "not interested", "irrelevant"]):
                category = "apathy"
            elif any(w in reason for w in ["powerless", "nothing will change", "hopeless", "waste"]):
                category = "cynicism"
            elif any(w in reason for w in ["unheard", "marginalized", "ignored", "voiceless"]):
                category = "exclusion"
            elif any(w in reason for w in ["observe", "watching", "waiting", "see what"]):
                category = "observational"
            elif any(w in reason for w in ["fear", "unsafe", "risk", "retaliation"]):
                category = "fear"

            reason_counts[category] += 1

            if len(samples) < 10 and a.get("internal_thought"):
                samples.append({
                    "agent_id": a["agent_id"],
                    "name": a["agent_name"],
                    "archetype": arch,
                    "action_type": a["action_type"],
                    "reason_category": category,
                    "reason": a["reason"],
                    "internal_thought": a["internal_thought"],
                })

        return {
            "total_non_participation_actions": len(actions),
            "by_reason": dict(reason_counts),
            "by_archetype": dict(archetype_counts),
            "by_round": [
                {"round": r, "count": d["count"], "reasons": dict(d["reasons"])}
                for r, d in sorted(round_counts.items())
            ],
            "sample_quotes": samples,
        }

    # ── Event Summary ───────────────────────────────────────────

    def event_summary(self, simulation_id: str) -> List[Dict[str, Any]]:
        """High-level summary of all injected events."""
        events = self.storage.query(
            "SELECT * FROM injected_events WHERE simulation_id = ? ORDER BY round_injected",
            (simulation_id,),
        )
        return [
            {
                "event_id": e["event_id"],
                "rule_id": e["rule_id"],
                "round_injected": e["round_injected"],
                "title": e["title"],
                "category": e["category"],
                "severity": e["severity"],
                "source": e["source"],
                "content": e["content"],
            }
            for e in events
        ]

    # ── Agent Summary ───────────────────────────────────────────

    def agent_summary(self, simulation_id: str) -> List[Dict[str, Any]]:
        """Summary stats per agent, plus each agent's latest expressed opinion
        and stance — enough to decide what intervention to pose post-sim."""
        rows = self.storage.query(
            """
            SELECT agent_id, agent_name, archetype,
                   COUNT(*) as action_count,
                   AVG(impact_score) as avg_impact,
                   SUM(CASE WHEN action_type = 'EXPRESS_OPINION' THEN 1 ELSE 0 END) as express_count,
                   SUM(CASE WHEN action_type = 'RESPOND_TO_OPINION' THEN 1 ELSE 0 END) as respond_count
            FROM opinion_actions
            WHERE simulation_id = ? AND agent_id >= 0
            GROUP BY agent_id, agent_name, archetype
            ORDER BY action_count DESC
            """,
            (simulation_id,),
        )

        # Per-agent stance from the stored profiles (may be empty for older runs).
        stance_rows = self.storage.query(
            "SELECT agent_id, stance FROM agent_profiles WHERE simulation_id = ?",
            (simulation_id,),
        )
        stance_by_id = {r["agent_id"]: r["stance"] for r in stance_rows}

        out = []
        for r in rows:
            agent_id = r["agent_id"]
            # Latest opinion this agent actually voiced (prefer an expressed
            # opinion; fall back to any action with content).
            latest = self.storage.query(
                """
                SELECT content, round_num FROM opinion_actions
                WHERE simulation_id = ? AND agent_id = ?
                  AND action_type = 'EXPRESS_OPINION' AND content IS NOT NULL AND content != ''
                ORDER BY round_num DESC, created_at DESC
                LIMIT 1
                """,
                (simulation_id, agent_id),
            )
            if not latest:
                latest = self.storage.query(
                    """
                    SELECT content, round_num FROM opinion_actions
                    WHERE simulation_id = ? AND agent_id = ?
                      AND content IS NOT NULL AND content != ''
                    ORDER BY round_num DESC, created_at DESC
                    LIMIT 1
                    """,
                    (simulation_id, agent_id),
                )
            latest_opinion = latest[0]["content"] if latest else ""
            latest_round = latest[0]["round_num"] if latest else None

            out.append({
                "agent_id": agent_id,
                "name": r["agent_name"],
                "archetype": r["archetype"],
                "action_count": r["action_count"],
                "avg_impact": round(r["avg_impact"] or 0, 3),
                "express_count": r["express_count"],
                "respond_count": r["respond_count"],
                "stance": stance_by_id.get(agent_id) or "",
                "latest_opinion": latest_opinion,
                "latest_opinion_round": latest_round,
            })
        return out

    # ── Helpers ─────────────────────────────────────────────────

    def _parse_json(self, val: Any) -> Any:
        """Safely parse JSON string."""
        if not val:
            return {}
        if isinstance(val, dict):
            return val
        try:
            return json.loads(val)
        except Exception:
            return {}
