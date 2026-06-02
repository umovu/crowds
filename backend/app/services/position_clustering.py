"""
PositionRegistry — stance-aware, cumulative distinct-position tracking.

This is a COVERAGE simulator: it must count how many genuinely DISTINCT
positions have appeared, so the run can stop on coverage saturation (no new
position for N rounds) rather than on agreement. Two design rules drive this
module, both learned the hard way:

1. CUMULATIVE, not per-round high-water. A round is "novel" only if it produces a
   position cluster matching NONE seen so far across the whole run. A per-round
   count is blind to swaps (3 new objections replacing 3 old ones leaves the count
   flat) and inflated by rephrasings.

2. STANCE-FIRST clustering. A general embedder groups by SUBJECT, so "this tax
   punishes poor families" and "good, junk food should cost more" — opposite
   stances, similar words — would merge into one position. We partition posts by
   stance bucket first and cluster only WITHIN a bucket, so opposed reactions can
   never collapse into one position.

Embeddings come from the existing Ollama EmbeddingService (no new dep). If that
is unreachable we fall back to lexical (Jaccard) clustering. The two modes are not
comparable; a mid-run mode flip logs a warning and resets the saturation baseline
via ``mode_changed`` on the result so Fix 1 never compares across metrics.
"""

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from ..utils.logger import get_logger

logger = get_logger("fub.position_clustering")

# Canonical 5-point stance taxonomy (mirrors opinion_agent.OpinionCitizenAgent;
# duplicated as plain strings to keep this module import-light in the subprocess).
_VALID_STANCES = {"support", "neutral", "concerned", "oppose", "resist"}
_STANCE_SYNONYMS = {
    "for": "support", "in favor": "support", "approve": "support", "endorse": "support",
    "against": "oppose", "reject": "oppose", "fight": "oppose", "combat": "oppose",
    "worried": "concerned", "alarm": "concerned", "uneasy": "concerned", "apprehensive": "concerned",
    "block": "resist", "stop": "resist", "defy": "resist", "disobey": "resist",
}

_WORD_RE = re.compile(r"[a-z0-9']+")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "to", "of", "in", "on", "for",
    "is", "are", "was", "were", "be", "this", "that", "it", "i", "we", "they",
    "you", "he", "she", "my", "our", "their", "with", "as", "at", "by", "from",
    "not", "no", "so", "do", "does", "did", "have", "has", "will", "would",
}


def normalize_stance(stance: Optional[str]) -> str:
    """Normalize a stance string into the 5-point taxonomy. Defaults to neutral."""
    if not stance:
        return "neutral"
    s = stance.lower().strip()
    if s in _VALID_STANCES:
        return s
    return _STANCE_SYNONYMS.get(s, "neutral")


def _cosine(a: List[float], b: List[float]) -> float:
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _centroid(vectors: List[List[float]]) -> List[float]:
    n = len(vectors)
    if n == 0:
        return []
    dim = len(vectors[0])
    out = [0.0] * dim
    for v in vectors:
        for i in range(dim):
            out[i] += v[i]
    return [x / n for x in out]


def _tokens(text: str) -> set:
    return {w for w in _WORD_RE.findall((text or "").lower()) if w not in _STOPWORDS and len(w) > 2}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


class PositionRegistry:
    """Cumulative, stance-bucketed registry of distinct positions seen in a run.

    One instance lives for the whole simulation. Call ``ingest_round`` once per
    round with that round's expressed posts.
    """

    def __init__(
        self,
        threshold: float = 0.82,
        embedding_service: Optional[Any] = None,
    ):
        self.threshold = threshold
        # Registry entry: {"stance": str, "centroid": [float] | None, "tokens": set | None}
        self._entries: List[Dict[str, Any]] = []
        self._mode: Optional[str] = None  # "embed" | "lexical", set on first use

        # Resolve an embedding service unless one is injected. A failure here just
        # means we run in lexical mode — never fatal for a coverage run.
        self._embed = embedding_service
        if self._embed is None:
            try:
                from ..storage.embedding_service import EmbeddingService
                svc = EmbeddingService()
                self._embed = svc if svc.health_check() else None
            except Exception as e:
                logger.warning(f"EmbeddingService unavailable, using lexical clustering: {e}")
                self._embed = None

    # ── public API ──────────────────────────────────────────────

    def ingest_round(self, posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Ingest one round's posts and update the cumulative registry.

        ``posts`` items need ``content`` (the stance text) and ``stance`` (the
        agent's CURRENT stance). Only non-empty content is considered.

        Returns:
            {
              "n_positions_this_round": int,   # distinct clusters this round
              "n_new_positions": int,          # clusters new to the registry
              "total_distinct": int,           # registry size (cumulative)
              "spread": float,                 # mean pairwise distance of registry centroids
              "mode": "embed" | "lexical" | "none",
              "mode_changed": bool,            # True if mode flipped this round (baseline must reset)
            }
        """
        texts: List[str] = []
        stances: List[str] = []
        for p in posts:
            content = (p.get("content") or "").strip()
            if not content:
                continue
            texts.append(content)
            stances.append(normalize_stance(p.get("stance")))

        if not texts:
            return {
                "n_positions_this_round": 0,
                "n_new_positions": 0,
                "total_distinct": len(self._entries),
                "spread": self._registry_spread(),
                "mode": self._mode or "none",
                "mode_changed": False,
            }

        use_embed = self._embed is not None
        mode = "embed" if use_embed else "lexical"
        mode_changed = self._mode is not None and mode != self._mode
        if mode_changed:
            logger.warning(
                f"Position-clustering mode changed {self._mode!r} -> {mode!r}; "
                f"resetting registry (metrics across modes are not comparable)."
            )
            self._entries = []
        self._mode = mode

        # Partition this round's posts by stance bucket — clustering happens only
        # WITHIN a bucket, so opposite stances never merge into one position.
        by_stance: Dict[str, List[int]] = {}
        for i, st in enumerate(stances):
            by_stance.setdefault(st, []).append(i)

        vectors: List[Optional[List[float]]] = [None] * len(texts)
        if use_embed:
            try:
                vectors = self._embed.embed_batch(texts)  # type: ignore[assignment]
            except Exception as e:
                # Embedding died mid-run — degrade to lexical for THIS round.
                logger.warning(f"embed_batch failed, degrading to lexical this round: {e}")
                use_embed = False
                mode = "lexical"
                if self._mode == "embed":
                    mode_changed = True
                    self._entries = []
                self._mode = "lexical"

        n_positions_this_round = 0
        n_new_positions = 0

        for stance, idxs in by_stance.items():
            # 1) cluster this round's posts within the stance bucket
            clusters = self._cluster_bucket(stance, idxs, texts, vectors, use_embed)
            n_positions_this_round += len(clusters)
            # 2) check each cluster against the cumulative registry (same stance only)
            for cluster in clusters:
                if not self._matches_registry(stance, cluster, use_embed):
                    self._entries.append({
                        "stance": stance,
                        "centroid": cluster.get("centroid"),
                        "tokens": cluster.get("tokens"),
                    })
                    n_new_positions += 1

        return {
            "n_positions_this_round": n_positions_this_round,
            "n_new_positions": n_new_positions,
            "total_distinct": len(self._entries),
            "spread": self._registry_spread(),
            "mode": mode,
            "mode_changed": mode_changed,
        }

    # ── internals ───────────────────────────────────────────────

    def _cluster_bucket(
        self,
        stance: str,
        idxs: List[int],
        texts: List[str],
        vectors: List[Optional[List[float]]],
        use_embed: bool,
    ) -> List[Dict[str, Any]]:
        """Greedy-cluster the posts in one stance bucket. Returns cluster dicts
        with a centroid (embed mode) or token set (lexical mode)."""
        clusters: List[Dict[str, Any]] = []
        for i in idxs:
            if use_embed:
                vec = vectors[i]
                if not vec:
                    continue
                best = None
                best_sim = self.threshold
                for c in clusters:
                    sim = _cosine(vec, c["centroid"])
                    if sim >= best_sim:
                        best, best_sim = c, sim
                if best is None:
                    clusters.append({"vectors": [vec], "centroid": list(vec)})
                else:
                    best["vectors"].append(vec)
                    best["centroid"] = _centroid(best["vectors"])
            else:
                toks = _tokens(texts[i])
                if not toks:
                    continue
                best = None
                best_sim = self.threshold
                for c in clusters:
                    sim = _jaccard(toks, c["tokens"])
                    if sim >= best_sim:
                        best, best_sim = c, sim
                if best is None:
                    clusters.append({"tokens": set(toks)})
                else:
                    best["tokens"] |= toks
        return clusters

    def _matches_registry(self, stance: str, cluster: Dict[str, Any], use_embed: bool) -> bool:
        """True if this cluster matches a registry entry of the SAME stance."""
        for e in self._entries:
            if e["stance"] != stance:
                continue
            if use_embed:
                if e.get("centroid") and cluster.get("centroid"):
                    if _cosine(cluster["centroid"], e["centroid"]) >= self.threshold:
                        return True
            else:
                if e.get("tokens") and cluster.get("tokens"):
                    if _jaccard(cluster["tokens"], e["tokens"]) >= self.threshold:
                        return True
        return False

    def _registry_spread(self) -> float:
        """Mean pairwise distance between registry centroids — how far apart the
        distinct positions are. Embed mode only; lexical returns 0.0."""
        cents = [e["centroid"] for e in self._entries if e.get("centroid")]
        if len(cents) < 2:
            return 0.0
        total = 0.0
        pairs = 0
        for i in range(len(cents)):
            for j in range(i + 1, len(cents)):
                total += 1.0 - _cosine(cents[i], cents[j])
                pairs += 1
        return round(total / pairs, 4) if pairs else 0.0
