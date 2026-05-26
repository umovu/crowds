"""Convergence detector for event-driven simulation stopping."""

import math
from collections import defaultdict
from typing import Dict, List, Optional


class ConvergenceDetector:
    """Detects when opinion distribution stabilizes across rounds."""

    def __init__(
        self,
        threshold: float = 0.05,
        window: int = 3,
    ):
        self.threshold = threshold
        self.window = window
        self._round_distributions: List[Dict[str, float]] = []
        self._stable_count = 0

    def record_round(self, actions: List[Dict]):
        """Record opinion distribution for a round."""
        if not actions:
            self._round_distributions.append({})
            return

        sentiment_counts = defaultdict(float)
        total = 0

        for action in actions:
            args = action.get("action_args", {})
            impact = action.get("impact_score", 0.0)

            # Simple sentiment proxy from impact score
            if impact > 0.6:
                sentiment_counts["positive"] += 1
            elif impact < 0.3:
                sentiment_counts["negative"] += 1
            else:
                sentiment_counts["neutral"] += 1

            total += 1

        # Normalize to distribution
        dist = {}
        if total > 0:
            for k, v in sentiment_counts.items():
                dist[k] = v / total

        self._round_distributions.append(dist)

    def check(self) -> tuple:
        """Check if converged. Returns (should_stop, divergence, stable_rounds)."""
        if len(self._round_distributions) < self.window + 1:
            return False, 1.0, 0

        recent = self._round_distributions[-(self.window + 1):]
        divergences = []

        for i in range(len(recent) - 1):
            d = self._js_divergence(recent[i], recent[i + 1])
            divergences.append(d)

        avg_divergence = sum(divergences) / len(divergences)

        if avg_divergence < self.threshold:
            self._stable_count += 1
        else:
            self._stable_count = 0

        should_stop = self._stable_count >= self.window
        return should_stop, avg_divergence, self._stable_count

    @staticmethod
    def _js_divergence(p: Dict[str, float], q: Dict[str, float]) -> float:
        """Jensen-Shannon divergence between two distributions."""
        all_keys = set(p.keys()) | set(q.keys())
        if not all_keys:
            return 0.0

        m = {}
        for k in all_keys:
            m[k] = (p.get(k, 0) + q.get(k, 0)) / 2

        def _kl(a: Dict, b: Dict) -> float:
            result = 0.0
            for k in all_keys:
                ak = a.get(k, 0)
                bk = b.get(k, 0)
                if ak > 0 and bk > 0:
                    result += ak * math.log2(ak / bk)
            return result

        return 0.5 * _kl(p, m) + 0.5 * _kl(q, m)
