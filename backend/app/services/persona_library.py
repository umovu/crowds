"""
PersonaLibrary — read access to the pre-built persona library.

The library is the offline-built set of representative, survey-grounded SA persona
identities (see build_library.py). The hosted app reads it here to assemble
simulations without paying per-user persona-generation cost.

Storage is JSON today (backend/app/data/persona_library/personas.json) behind a
small interface — all callers go through PersonaLibrary, never the file. Swapping to
a Supabase-backed store later is a new subclass implementing the same methods, not a
rewrite of the retrieval/assembly code.

This module is LLM-free and read-only.
"""

from __future__ import annotations

import json
import os
import random
from typing import Dict, List, Optional

from ..utils.logger import get_logger

logger = get_logger("fub.persona_library")

_DEFAULT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "persona_library", "personas.json"
)


class PersonaLibrary:
    """JSON-backed persona library. The query/filter/sample interface is the contract
    a future SupabasePersonaLibrary would implement unchanged."""

    def __init__(self, path: str = _DEFAULT_PATH):
        self.path = path
        self._personas: List[Dict] = []
        self._loaded = False

    # ── loading ──────────────────────────────────────────────────────────
    def load(self) -> "PersonaLibrary":
        if self._loaded:
            return self
        if not os.path.exists(self.path):
            logger.warning(f"Persona library not found at {self.path}; library is empty. "
                           f"Run scripts/build_library.py to populate it.")
            self._personas = []
        else:
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._personas = data.get("personas", []) if isinstance(data, dict) else list(data)
                logger.info(f"Loaded {len(self._personas)} personas from library.")
            except (OSError, json.JSONDecodeError) as e:
                logger.error(f"Failed to read persona library: {e}")
                self._personas = []
        self._loaded = True
        return self

    def is_empty(self) -> bool:
        return len(self.all()) == 0

    # ── access ───────────────────────────────────────────────────────────
    def all(self) -> List[Dict]:
        if not self._loaded:
            self.load()
        return list(self._personas)

    def get(self, persona_id: str) -> Optional[Dict]:
        for p in self.all():
            if p.get("id") == persona_id:
                return p
        return None

    def filter(
        self,
        *,
        province: Optional[str] = None,
        archetype: Optional[str] = None,
        gender: Optional[str] = None,
        employed: Optional[bool] = None,
    ) -> List[Dict]:
        """Return personas matching all provided constraints (None = no constraint)."""
        out = self.all()
        if province:
            out = [p for p in out if p.get("province") == province]
        if archetype:
            out = [p for p in out if p.get("actor_archetype") == archetype]
        if gender:
            out = [p for p in out if (p.get("gender") or "").lower() == gender.lower()]
        if employed is not None:
            out = [p for p in out if (p.get("employment_status") == "Employed") == employed]
        return out

    def sample(self, n: int, seed: int = 0, pool: Optional[List[Dict]] = None) -> List[Dict]:
        """Uniform random sample of n personas (deterministic for a seed).

        For representativeness-aware selection use persona_retrieval.select_for_query,
        which weights by archetype mix and tilts toward query relevance.
        """
        pool = self.all() if pool is None else pool
        if n >= len(pool):
            return list(pool)
        rng = random.Random(seed)
        return rng.sample(pool, n)

    def archetype_distribution(self) -> Dict[str, float]:
        """The library's archetype mix as fractions — the representative baseline that
        retrieval samples against."""
        counts: Dict[str, int] = {}
        for p in self.all():
            a = p.get("actor_archetype") or "unknown"
            counts[a] = counts.get(a, 0) + 1
        total = sum(counts.values()) or 1
        return {a: c / total for a, c in counts.items()}


# Module-level singleton for the default library.
_default: Optional[PersonaLibrary] = None


def get_library() -> PersonaLibrary:
    global _default
    if _default is None:
        _default = PersonaLibrary().load()
    return _default
