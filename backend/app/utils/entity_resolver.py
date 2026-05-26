"""
EntityResolver — deduplicate entity names that refer to the same real-world entity.

Example:
  "Julius Malema", "Malema", "J. Malema", "julius malema" → "Julius Malema"

Uses a hybrid approach:
1. Normalization (strip titles, lowercase)
2. Substring containment ("malema" inside "julius malema")
3. Fuzzy similarity (difflib.SequenceMatcher)
4. Optional LLM canonicalization for ambiguous clusters
"""

import difflib
import re
from typing import Dict, List, Optional, Set, Tuple


# Common titles/prefixes/suffixes to strip for comparison
_TITLE_STRIP_RE = re.compile(
    r"^(Mr\.?\s+|Mrs\.?\s+|Ms\.?\s+|Dr\.?\s+|Prof\.?\s+|Hon\.?\s+|"
    r"President\s+|Minister\s+|Mayor\s+|Chairman\s+|Chairperson\s+|"
    r"CEO\s+|CFO\s+|COO\s+|MD\s+|"
    r"the\s+|a\s+)|"
    r"(\s+(Jr\.?|Sr\.?|III|II|IV|PhD|MP|MA|BA|BSc|MSc|MBA))$",
    re.IGNORECASE,
)

# Common stop words that make two names look different but often co-occur
_STOP_WORDS = {"the", "of", "and", "for", "in", "on", "at", "to", "a", "an"}


def _normalize(name: str) -> str:
    """Strip titles, lower-case, collapse whitespace."""
    cleaned = _TITLE_STRIP_RE.sub("", name.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.lower()


def _token_set(name: str) -> Set[str]:
    """Return token set minus stop words."""
    return {t for t in _normalize(name).split() if t not in _STOP_WORDS and len(t) > 1}


def _is_subsumed(name_a: str, name_b: str) -> bool:
    """
    Return True if one normalized name is a substring of the other
    OR if one's token set is fully contained in the other's.
    """
    na = _normalize(name_a)
    nb = _normalize(name_b)
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    ta = _token_set(name_a)
    tb = _token_set(name_b)
    if not ta or not tb:
        return False
    if ta.issubset(tb) or tb.issubset(ta):
        return True
    return False


def _fuzzy_similarity(name_a: str, name_b: str) -> float:
    """ difflib ratio between normalized names. """
    return difflib.SequenceMatcher(None, _normalize(name_a), _normalize(name_b)).ratio()


class EntityResolver:
    """
    Cluster entity names into canonical groups.

    Parameters
    ----------
    substring_threshold : float
        Minimum fuzzy similarity for names that do NOT subsume each other.
    llm_callback : callable, optional
        Async function ``(names: List[str]) -> str`` that returns the canonical
        form for a cluster.  If not provided, the longest name is used.
    """

    def __init__(
        self,
        substring_threshold: float = 0.75,
        llm_callback: Optional[callable] = None,
    ):
        self.substring_threshold = substring_threshold
        self.llm_callback = llm_callback

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self, names: List[str]) -> Dict[str, str]:
        """
        Return a mapping ``original_name -> canonical_name``.

        Parameters
        ----------
        names : list of str
            Raw entity names (may contain duplicates or near-duplicates).

        Returns
        -------
        dict
            {original: canonical}
        """
        # Deduplicate while preserving order
        seen: Set[str] = set()
        unique_names: List[str] = []
        for n in names:
            if n and n.strip() and n.strip().lower() not in seen:
                seen.add(n.strip().lower())
                unique_names.append(n.strip())

        if len(unique_names) <= 1:
            return {n: n for n in unique_names}

        # 1. Build clusters via union-find
        clusters = self._cluster_names(unique_names)

        # 2. Pick canonical name per cluster
        mapping: Dict[str, str] = {}
        for cluster in clusters:
            canonical = self._pick_canonical(cluster)
            for member in cluster:
                mapping[member] = canonical

        return mapping

    def resolve_lists(
        self,
        people: List[str],
        organizations: Optional[List[str]] = None,
        locations: Optional[List[str]] = None,
    ) -> Tuple[List[str], Optional[List[str]], Optional[List[str]]]:
        """
        Convenience wrapper that resolves each list and returns de-duplicated
        canonical lists (preserving original order, first occurrence wins).
        """
        def _dedup_canonical(raw: List[str]) -> List[str]:
            mapping = self.resolve(raw)
            seen: Set[str] = set()
            out: List[str] = []
            for r in raw:
                can = mapping.get(r, r)
                if can.lower() not in seen:
                    seen.add(can.lower())
                    out.append(can)
            return out

        return (
            _dedup_canonical(people),
            _dedup_canonical(organizations) if organizations is not None else None,
            _dedup_canonical(locations) if locations is not None else None,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _cluster_names(self, names: List[str]) -> List[List[str]]:
        """Union-find clustering."""
        parent = list(range(len(names)))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry

        n = len(names)
        for i in range(n):
            for j in range(i + 1, n):
                if self._should_merge(names[i], names[j]):
                    union(i, j)

        # Collect clusters
        groups: Dict[int, List[str]] = {}
        for idx in range(n):
            root = find(idx)
            groups.setdefault(root, []).append(names[idx])

        return list(groups.values())

    def _should_merge(self, a: str, b: str) -> bool:
        """Decide whether two names refer to the same entity."""
        if _is_subsumed(a, b):
            return True
        sim = _fuzzy_similarity(a, b)
        return sim >= self.substring_threshold

    def _pick_canonical(self, cluster: List[str]) -> str:
        """
        Pick the best canonical name from a cluster.
        Default heuristic: longest name (usually the most complete).
        If an LLM callback is provided, it may override.
        """
        if not cluster:
            return ""
        if len(cluster) == 1:
            return cluster[0]

        # Heuristic: pick the longest original name as canonical
        # (usually the un-abbreviated full name)
        canonical = max(cluster, key=lambda x: len(x.strip()))

        # Optional LLM refinement (sync — caller can provide an async wrapper
        # if they want to await it, but resolve() itself is sync)
        if self.llm_callback is not None:
            try:
                result = self.llm_callback(cluster)
                if result and isinstance(result, str):
                    canonical = result.strip()
            except Exception:
                pass

        return canonical


# ------------------------------------------------------------------
# Stand-alone helper for quick use
# ------------------------------------------------------------------

def quick_resolve(names: List[str], threshold: float = 0.75) -> Dict[str, str]:
    """One-shot deduplication without LLM."""
    return EntityResolver(substring_threshold=threshold).resolve(names)


def quick_resolve_lists(
    people: List[str],
    organizations: Optional[List[str]] = None,
    locations: Optional[List[str]] = None,
    threshold: float = 0.75,
) -> Tuple[List[str], Optional[List[str]], Optional[List[str]]]:
    """One-shot deduplication of multiple lists without LLM."""
    return EntityResolver(substring_threshold=threshold).resolve_lists(
        people, organizations, locations
    )
