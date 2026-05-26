"""Probabilistic agent sampler for event-driven simulation."""

import random
from typing import Dict, List, Optional


class AgentSampler:
    """Samples agents probabilistically based on activity level and context."""

    def __init__(self, all_agents: Dict, agent_configs: Dict):
        self.all_agents = all_agents
        self.agent_configs = agent_configs  # agent_id -> config
        self._recent_posters: set = set()
        self._round_history: List[set] = []  # Track posters per round for cooldown
        self._round_num = 0

    def sample(
        self,
        round_num: int,
        hot_topics: Optional[List[str]] = None,
        min_agents: int = 3,
        max_agents: int = 15,
    ) -> List:
        """Sample active agents for this round.

        Core focus agents (is_core_focus=True) are GUARANTEED to be included
        every round, regardless of probabilistic sampling.
        """
        self._round_num = round_num
        candidates = list(self.all_agents.values())

        if not candidates:
            return []

        # Separate core focus and regular agents
        core_focus_agents = [a for a in candidates if getattr(a, 'is_core_focus', False)]
        regular_candidates = [a for a in candidates if not getattr(a, 'is_core_focus', False)]

        # Guaranteed inclusion for core focus agents
        selected = core_focus_agents.copy()
        remaining_slots = max_agents - len(selected)

        if remaining_slots <= 0:
            return selected[:max_agents]

        # Compute weights for regular agents
        weights = []
        for agent in regular_candidates:
            w = self._compute_weight(agent, hot_topics)
            weights.append(w)

        # Normalize weights
        total_w = sum(weights)
        if total_w == 0:
            weights = [1.0] * len(regular_candidates)
        else:
            weights = [w / total_w for w in weights]

        # Sample regular agents without replacement up to remaining_slots
        target = min(remaining_slots, len(regular_candidates))
        selected_indices = set()

        available = list(range(len(regular_candidates)))
        avail_weights = list(weights)

        for _ in range(target):
            if not available:
                break
            total = sum(avail_weights)
            if total == 0:
                idx = random.choice(available)
            else:
                r = random.random() * total
                cumulative = 0
                idx = available[0]
                for i, w in zip(available, avail_weights):
                    cumulative += w
                    if r <= cumulative:
                        idx = i
                        break

            selected_indices.add(idx)
            pos = available.index(idx)
            available.pop(pos)
            avail_weights.pop(pos)

        # Ensure minimum agents (only for regular agents, core focus already guaranteed)
        min_regular = min_agents - len(core_focus_agents)
        while len(selected_indices) < min_regular and len(selected_indices) < len(regular_candidates):
            remaining = [i for i in range(len(regular_candidates)) if i not in selected_indices]
            if remaining:
                selected_indices.add(random.choice(remaining))
            else:
                break

        regular_selected = [regular_candidates[i] for i in sorted(selected_indices)]
        return selected + regular_selected

    def _compute_weight(self, agent, hot_topics: Optional[List[str]] = None) -> float:
        """Compute activation weight for an agent."""
        base = getattr(agent, 'activity_level', 0.5)

        # Decay over rounds (conversation fatigue)
        fatigue = max(0.3, 1.0 - (self._round_num * 0.02))

        # Cooldown: reduce weight for agents who spoke in recent rounds
        # so the same agents don't dominate every round
        cooldown = 1.0
        for history_set in self._round_history[-3:]:
            if agent.id in history_set:
                cooldown *= 0.5  # Halve weight for each recent appearance
        cooldown = max(0.15, cooldown)

        # Boost for recent posters (momentum) — but capped by cooldown
        momentum = 1.2 if agent.id in self._recent_posters else 1.0

        # Boost for topic relevance
        topic_boost = 1.0
        if hot_topics:
            agent_topics = set(getattr(agent, 'interested_topics', []))
            overlap = len(agent_topics & set(hot_topics))
            if overlap > 0:
                topic_boost = 1.0 + (overlap * 0.2)

        return base * fatigue * cooldown * momentum * topic_boost

    def record_posters(self, agent_ids: set):
        """Track which agents posted this round."""
        self._recent_posters = agent_ids
        self._round_history.append(set(agent_ids))
        # Keep only last 5 rounds of history
        if len(self._round_history) > 5:
            self._round_history.pop(0)
