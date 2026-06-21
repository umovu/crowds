"""
EventRuleEngine — reactive event detection for SA policy opinion simulation.

Evaluates a set of configurable rules against simulation state after each round.
When conditions are met, generates events to be injected into the simulation.

Rules are loaded from JSON config and support:
- Threshold triggers (sentiment, impact scores)
- Topic mention counts
- Archetype interactions
- Sustained non-participation
- Radicalism drift
- Scheduled shocks
"""

import json
import os
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger

logger = get_logger("fub.event_rules")

# Default path to event rules config
DEFAULT_RULES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "config", "event_rules.json"
)


class EventRuleEngine:
    """
    Loads event rules from JSON config and evaluates them against
    per-round simulation metrics.
    
    Supports both static rules (from JSON) and dynamic rules (from DocumentContextEngine).
    """

    def __init__(self, rules_path: Optional[str] = None, dynamic_rules: Optional[List[Dict[str, Any]]] = None,
                 mode: str = "policy"):
        self.rules_path = rules_path or DEFAULT_RULES_PATH
        self.mode = (mode or "policy").strip().lower()
        self.rules: List[Dict[str, Any]] = []
        self.trigger_history: List[Dict[str, Any]] = []
        self.cooldowns: Dict[str, int] = {}  # rule_id -> last_triggered_round
        self.trigger_counts: Dict[str, int] = {}  # rule_id -> total_triggers
        self._load_rules()

        # Inject dynamic rules from document context if provided
        if dynamic_rules:
            self._inject_dynamic_rules(dynamic_rules)

    def _inject_dynamic_rules(self, dynamic_rules: List[Dict[str, Any]]):
        """Inject domain-specific dynamic rules. Prioritize over static rules."""
        # Add dynamic rules first (they take precedence)
        for rule in dynamic_rules:
            if not any(r["id"] == rule["id"] for r in self.rules):
                self.rules.insert(0, rule)
                logger.info(f"Injected dynamic rule: {rule['id']}")
            else:
                # Replace existing static rule with dynamic version
                for i, existing in enumerate(self.rules):
                    if existing["id"] == rule["id"]:
                        self.rules[i] = rule
                        logger.info(f"Replaced static rule with dynamic: {rule['id']}")
                        break

    def _load_rules(self):
        """Load rules from JSON config."""
        if not os.path.exists(self.rules_path):
            logger.warning(f"Event rules config not found: {self.rules_path}")
            return

        try:
            with open(self.rules_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                all_rules = config.get("rules", [])
            # The static rules are POLICY-domain reactive events (SAPS deployment,
            # parliamentary debates, Eskom shocks, taxi strikes). They make no sense
            # in a PRODUCT stress-test — riot police don't deploy because parents
            # dislike an app's price. A rule applies to a mode if its
            # `applies_to_modes` list contains it, OR (default) if it's unset and
            # the sim is in policy mode. Product sims rely on dynamic rules derived
            # from the document context instead.
            self.rules = [r for r in all_rules if self._rule_applies(r)]
            skipped = len(all_rules) - len(self.rules)
            logger.info(
                f"Loaded {len(self.rules)} event rules ({skipped} skipped for mode="
                f"'{self.mode}') from {self.rules_path}"
            )
        except Exception as e:
            logger.error(f"Failed to load event rules: {e}")
            self.rules = []

    def _rule_applies(self, rule: Dict[str, Any]) -> bool:
        """Whether a static rule applies in the current sim mode. Rules may declare
        `applies_to_modes`; unset = policy-only (the legacy default, since every
        bundled static rule is a policy/civic event)."""
        modes = rule.get("applies_to_modes")
        if modes is None:
            return self.mode == "policy"
        return self.mode in modes

    def evaluate(self, round_num: int, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Evaluate all rules against the current round's actions.

        Args:
            round_num: Current simulation round (0-indexed)
            actions: List of action dicts from all agents this round.
                     Each dict should have keys like:
                     - action_type (str)
                     - agent_id (int)
                     - agent_name (str)
                     - archetype (str, optional)
                     - impact_score (float)
                     - content (str)
                     - internal_thought (str)
                     - reason (str)
                     - topics (List[str])

        Returns:
            List of event dicts to inject this round.
        """
        if not self.rules:
            return []

        metrics = self._calculate_metrics(actions)
        events = []

        for rule in self.rules:
            rule_id = rule["id"]

            # Check max triggers
            max_triggers = rule.get("max_triggers_per_simulation", 999)
            if self.trigger_counts.get(rule_id, 0) >= max_triggers:
                continue

            # Check cooldown
            if self._is_on_cooldown(rule_id, round_num, rule.get("cooldown_rounds", 0)):
                continue

            # Check trigger
            if self._check_trigger(rule.get("trigger", {}), metrics, round_num):
                event = self._build_event(rule, round_num, metrics)
                events.append(event)

                # Track trigger
                self.cooldowns[rule_id] = round_num
                self.trigger_counts[rule_id] = self.trigger_counts.get(rule_id, 0) + 1
                self.trigger_history.append({
                    "rule_id": rule_id,
                    "round_num": round_num,
                    "timestamp": datetime.now().isoformat(),
                    "event": event,
                })

                logger.info(
                    f"Event triggered: {rule_id} at round {round_num} — {event['title']}"
                )

        return events

    def _calculate_metrics(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate aggregate metrics from a round's actions.
        """
        if not actions:
            return self._empty_metrics()

        total = len(actions)

        # Impact score distribution
        impact_scores = [
            a.get("impact_score", 0.0)
            for a in actions
            if a.get("impact_score") is not None
        ]
        avg_impact = sum(impact_scores) / len(impact_scores) if impact_scores else 0.0
        pct_above_07 = sum(1 for s in impact_scores if s > 0.7) / total if total else 0.0
        pct_above_085 = sum(1 for s in impact_scores if s > 0.85) / total if total else 0.0

        # Archetype activity
        archetype_counts = Counter()
        archetype_action_counts = Counter()
        for a in actions:
            archetype = a.get("archetype", "unknown")
            archetype_counts[archetype] += 1
            archetype_action_counts[(archetype, a.get("action_type", "UNKNOWN"))] += 1

        # Topic mentions
        topic_counts = Counter()
        for a in actions:
            for topic in a.get("topics", []) or []:
                topic_counts[topic.lower()] += 1

        # Non-participation
        non_participation_actions = ["DO_NOTHING", "NON_PARTICIPATION", "OBSERVE"]
        non_participation_count = sum(
            1 for a in actions if a.get("action_type") in non_participation_actions
        )
        non_participation_reasons = Counter()
        for a in actions:
            if a.get("action_type") in non_participation_actions:
                reason = a.get("reason", "").lower()
                if "distrust" in reason:
                    non_participation_reasons["distrust"] += 1
                elif "fear" in reason:
                    non_participation_reasons["fear"] += 1
                elif "time" in reason or "busy" in reason:
                    non_participation_reasons["time_constraints"] += 1
                elif "care" in reason or "apathy" in reason:
                    non_participation_reasons["apathy"] += 1
                else:
                    non_participation_reasons["other"] += 1

        # Radicalism (from agent state if available, else estimate from impact)
        radicalism_scores = []
        for a in actions:
            # Try to get explicit radicalism, fall back to impact score proxy
            rad = a.get("radicalism_level")
            if rad is not None:
                radicalism_scores.append(float(rad))
            else:
                # Rough proxy: high impact + expressing opinion = higher radicalism
                impact = a.get("impact_score", 0.0)
                is_expressive = a.get("action_type") in ("EXPRESS_OPINION", "RESPOND_TO_OPINION")
                proxy = 2.0 + (impact * 2.0) + (0.5 if is_expressive else 0.0)
                radicalism_scores.append(min(proxy, 5.0))

        avg_radicalism = sum(radicalism_scores) / len(radicalism_scores) if radicalism_scores else 0.0

        # Archetype response tracking (who responded to whom)
        archetype_responses = Counter()
        for a in actions:
            if a.get("action_type") == "RESPOND_TO_OPINION":
                responder_arch = a.get("archetype", "unknown")
                archetype_responses[responder_arch] += 1

        return {
            "total_actions": total,
            "avg_impact_score": round(avg_impact, 3),
            "pct_agents_with_impact_above_07": round(pct_above_07, 3),
            "pct_agents_with_impact_above_085": round(pct_above_085, 3),
            "archetype_counts": dict(archetype_counts),
            "archetype_action_counts": {f"{k[0]}:{k[1]}": v for k, v in archetype_action_counts.items()},
            "topic_counts": dict(topic_counts),
            "non_participation_count": non_participation_count,
            "non_participation_proportion": round(non_participation_count / total, 3) if total else 0.0,
            "non_participation_reasons": dict(non_participation_reasons),
            "avg_radicalism": round(avg_radicalism, 3),
            "radicalism_scores": [round(r, 2) for r in radicalism_scores],
            "archetype_responses": dict(archetype_responses),
        }

    def _empty_metrics(self) -> Dict[str, Any]:
        return {
            "total_actions": 0,
            "avg_impact_score": 0.0,
            "pct_agents_with_impact_above_07": 0.0,
            "pct_agents_with_impact_above_085": 0.0,
            "archetype_counts": {},
            "archetype_action_counts": {},
            "topic_counts": {},
            "non_participation_count": 0,
            "non_participation_proportion": 0.0,
            "non_participation_reasons": {},
            "avg_radicalism": 0.0,
            "radicalism_scores": [],
            "archetype_responses": {},
        }

    def _is_on_cooldown(self, rule_id: str, current_round: int, cooldown_rounds: int) -> bool:
        """Check if rule is still on cooldown."""
        if cooldown_rounds <= 0:
            return False
        last_triggered = self.cooldowns.get(rule_id)
        if last_triggered is None:
            return False
        return (current_round - last_triggered) < cooldown_rounds

    def _check_trigger(
        self,
        trigger: Dict[str, Any],
        metrics: Dict[str, Any],
        round_num: int,
    ) -> bool:
        """Evaluate a single rule's trigger conditions."""
        trigger_type = trigger.get("type", "")

        if trigger_type == "threshold":
            return self._check_threshold_trigger(trigger, metrics)

        elif trigger_type == "topic_mention_count":
            return self._check_topic_mention_trigger(trigger, metrics)

        elif trigger_type == "archetype_interaction":
            return self._check_archetype_interaction_trigger(trigger, metrics)

        elif trigger_type == "sustained_non_participation":
            return self._check_sustained_non_participation_trigger(trigger, metrics)

        elif trigger_type == "non_participation_reason_threshold":
            return self._check_non_participation_reason_trigger(trigger, metrics)

        elif trigger_type == "radicalism_drift":
            return self._check_radicalism_drift_trigger(trigger, metrics)

        elif trigger_type == "archetype_impact_threshold":
            return self._check_archetype_impact_trigger(trigger, metrics)

        elif trigger_type == "archetype_response_count":
            return self._check_archetype_response_trigger(trigger, metrics)

        elif trigger_type == "scheduled":
            return self._check_scheduled_trigger(trigger, round_num)

        else:
            logger.warning(f"Unknown trigger type: {trigger_type}")
            return False

    def _check_threshold_trigger(self, trigger: Dict[str, Any], metrics: Dict[str, Any]) -> bool:
        """Check threshold-based triggers (e.g., pct with impact above X)."""
        metric_name = trigger.get("metric", "")
        threshold = trigger.get("value", 0.0)
        min_proportion = trigger.get("min_proportion", 0.0)

        if metric_name == "pct_agents_with_impact_above":
            if threshold <= 0.7:
                actual = metrics.get("pct_agents_with_impact_above_07", 0.0)
            else:
                actual = metrics.get("pct_agents_with_impact_above_085", 0.0)
            return actual >= min_proportion

        return False

    def _check_topic_mention_trigger(self, trigger: Dict[str, Any], metrics: Dict[str, Any]) -> bool:
        """Check if any of the specified topics were mentioned enough times."""
        topics = [t.lower() for t in trigger.get("topics", [])]
        min_count = trigger.get("min_count", 5)
        topic_counts = metrics.get("topic_counts", {})

        total_mentions = sum(
            topic_counts.get(topic, 0) for topic in topics
        )
        return total_mentions >= min_count

    def _check_archetype_interaction_trigger(
        self, trigger: Dict[str, Any], metrics: Dict[str, Any]
    ) -> bool:
        """Check if primary archetype is active and enough secondary archetypes responded."""
        primary = trigger.get("primary_archetype", "")
        secondaries = trigger.get("secondary_archetypes", [])
        min_secondary = trigger.get("min_secondary_count", 1)

        archetype_counts = metrics.get("archetype_counts", {})

        # Primary must be active
        if archetype_counts.get(primary, 0) < 1:
            return False

        # Count secondary archetype activity
        secondary_count = sum(
            archetype_counts.get(sec, 0) for sec in secondaries
        )
        return secondary_count >= min_secondary

    def _check_sustained_non_participation_trigger(
        self, trigger: Dict[str, Any], metrics: Dict[str, Any]
    ) -> bool:
        """
        Check sustained non-participation.
        NOTE: This requires cross-round state tracking that is maintained
        externally (in the runner). The engine stores a simple flag.
        """
        min_proportion = trigger.get("min_proportion", 0.5)
        current_prop = metrics.get("non_participation_proportion", 0.0)
        return current_prop >= min_proportion

    def _check_non_participation_reason_trigger(
        self, trigger: Dict[str, Any], metrics: Dict[str, Any]
    ) -> bool:
        """Check if a specific non-participation reason dominates."""
        reason_category = trigger.get("reason_category", "")
        min_proportion = trigger.get("min_proportion_of_non_participants", 0.3)

        reasons = metrics.get("non_participation_reasons", {})
        non_participation_count = metrics.get("non_participation_count", 0)

        if non_participation_count == 0:
            return False

        reason_count = reasons.get(reason_category, 0)
        return (reason_count / non_participation_count) >= min_proportion

    def _check_radicalism_drift_trigger(
        self, trigger: Dict[str, Any], metrics: Dict[str, Any]
    ) -> bool:
        """
        Check radicalism drift.
        NOTE: This requires tracking radicalism history across rounds.
        The engine maintains a simple window of recent values.
        """
        from_max = trigger.get("from_max", 2.5)
        to_min = trigger.get("to_min", 3.5)
        current_radicalism = metrics.get("avg_radicalism", 0.0)

        # Store in engine state for drift detection
        if not hasattr(self, "_radicalism_history"):
            self._radicalism_history = []
        self._radicalism_history.append(current_radicalism)
        if len(self._radicalism_history) > 10:
            self._radicalism_history = self._radicalism_history[-10:]

        # Need at least window_rounds of data
        window = trigger.get("window_rounds", 4)
        if len(self._radicalism_history) < window:
            return False

        # Check if recent values show escalation from below from_max to above to_min
        recent = self._radicalism_history[-window:]
        early_avg = sum(recent[: window // 2]) / (window // 2)
        late_avg = sum(recent[window // 2 :]) / (window - window // 2)

        return early_avg <= from_max and late_avg >= to_min

    def _check_archetype_impact_trigger(
        self, trigger: Dict[str, Any], metrics: Dict[str, Any]
    ) -> bool:
        """Check if a specific archetype posted high-impact content."""
        target_archetype = trigger.get("archetype", "")
        min_impact = trigger.get("min_impact_score", 0.8)

        # We need per-archetype impact data. Since metrics only has counts,
        # this trigger requires the raw actions to be passed in.
        # For now, approximate: if archetype is active and avg impact is high.
        archetype_counts = metrics.get("archetype_counts", {})
        if archetype_counts.get(target_archetype, 0) < 1:
            return False

        # Approximate: if overall avg impact is high and archetype is active
        return metrics.get("avg_impact_score", 0.0) >= min_impact * 0.8

    def _check_archetype_response_trigger(
        self, trigger: Dict[str, Any], metrics: Dict[str, Any]
    ) -> bool:
        """Check if an archetype received enough responses."""
        target_archetype = trigger.get("archetype", "")
        min_responses = trigger.get("min_responses", 3)

        archetype_responses = metrics.get("archetype_responses", {})
        return archetype_responses.get(target_archetype, 0) >= min_responses

    def _check_scheduled_trigger(self, trigger: Dict[str, Any], round_num: int) -> bool:
        """Check if this is a scheduled round for an event."""
        scheduled_rounds = trigger.get("rounds", [])
        return round_num in scheduled_rounds

    def _build_event(
        self,
        rule: Dict[str, Any],
        round_num: int,
        metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build the event dict to inject into the simulation."""
        event_template = rule.get("event", {})
        return {
            "event_id": f"{rule['id']}_r{round_num}_{len(self.trigger_history)}",
            "rule_id": rule["id"],
            "round_injected": round_num,
            "type": event_template.get("type", "generic"),
            "category": rule.get("category", "general"),
            "source": event_template.get("source", "Unknown"),
            "title": event_template.get("title", "Event"),
            "content": event_template.get("content", ""),
            "affected_archetypes": event_template.get("affected_archetypes", []),
            "severity": event_template.get("severity", "low"),
            "persist_rounds": event_template.get("persist_rounds", 1),
            "trigger_metrics": {k: v for k, v in metrics.items() if isinstance(v, (int, float, str, bool))},
        }

    def get_trigger_history(self) -> List[Dict[str, Any]]:
        """Return full history of triggered events."""
        return self.trigger_history.copy()

    def reset(self):
        """Reset trigger history and cooldowns for a new simulation."""
        self.trigger_history = []
        self.cooldowns = {}
        self.trigger_counts = {}
        if hasattr(self, "_radicalism_history"):
            self._radicalism_history = []
        logger.info("EventRuleEngine reset for new simulation")
