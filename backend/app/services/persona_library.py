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

# Where the library JSON lives. Locally it's the in-repo path (gitignored, built
# by scripts/build_library.py). On hosts it lives on the persistent volume —
# set PERSONA_LIBRARY_PATH=/data/persona_library/personas.json — and is seeded
# once from Supabase Storage on first boot (see _seed_from_storage). It is NOT
# shipped in git.
_IMAGE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "persona_library", "personas.json"
)


def _default_library_path() -> str:
    return os.environ.get("PERSONA_LIBRARY_PATH") or _IMAGE_PATH


def _seed_from_storage(dest_path: str) -> bool:
    """Download the library from a private Supabase Storage bucket to dest_path.

    Lets the persistent volume be seeded on first boot without the file ever
    being in git. No-op (returns False) unless the storage env vars are set.
    Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, PERSONA_LIBRARY_BUCKET,
         PERSONA_LIBRARY_OBJECT (default "personas.json").
    """
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    bucket = os.environ.get("PERSONA_LIBRARY_BUCKET", "")
    obj = os.environ.get("PERSONA_LIBRARY_OBJECT", "personas.json")
    if not (url and key and bucket):
        return False
    try:
        import requests
        endpoint = f"{url}/storage/v1/object/{bucket}/{obj}"
        resp = requests.get(
            endpoint,
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=60,
        )
        resp.raise_for_status()
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(resp.content)
        logger.info(
            "Seeded persona library from Supabase Storage (%d bytes) -> %s",
            len(resp.content), dest_path,
        )
        return True
    except Exception as e:
        logger.error("Could not seed persona library from storage: %s", e)
        return False


class PersonaLibrary:
    """JSON-backed persona library. The query/filter/sample interface is the contract
    a future SupabasePersonaLibrary would implement unchanged."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or _default_library_path()
        self._personas: List[Dict] = []
        self._loaded = False

    # ── loading ──────────────────────────────────────────────────────────
    def load(self) -> "PersonaLibrary":
        if self._loaded:
            return self
        # On hosts the volume starts empty — seed it once from Supabase Storage.
        if not os.path.exists(self.path):
            _seed_from_storage(self.path)
        if not os.path.exists(self.path):
            logger.warning(f"Persona library not found at {self.path}; library is empty. "
                           f"Seed Supabase Storage or run scripts/build_library.py to populate it.")
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
