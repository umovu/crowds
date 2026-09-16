"""
PersonaLibrary — read access to the pre-built persona library.

The library is the offline-built set of representative, survey-grounded SA persona
identities (see build_library.py). The hosted app reads it here to assemble
simulations without paying per-user persona-generation cost.

Where the file lives and how it is fetched is app/repositories/persona_repository.py.
This module is the rules on top of it: the drift check against the data model, the
lsm_proxy stamp, and the query/filter/sample interface every caller goes through.

This module is LLM-free and read-only.
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional

from ..repositories import persona_repository
from ..utils.logger import get_logger
from . import data_model
from .lsm_proxy import score_persona

logger = get_logger("fub.persona_library")


def _default_library_path() -> str:
    return persona_repository.library_path()


def _seed_from_storage(dest_path: str) -> bool:
    """Re-sync the library file from Supabase Storage (no-op when unconfigured).

    Kept as a name here because tests and scripts patch it by this path; the
    download itself belongs to the repository.
    """
    return persona_repository.seed_from_storage(dest_path)


class PersonaLibrary:
    """The persona library as the app uses it: checked, scored, and queryable.

    Reading the bytes is persona_repository's job. The query/filter/sample interface
    here is the contract every caller goes through, never the file.
    """

    def __init__(self, path: Optional[str] = None):
        self.path = path or _default_library_path()
        self._personas: List[Dict] = []
        self._people = None
        self._loaded = False

    # ── loading ──────────────────────────────────────────────────────────
    def load(self) -> "PersonaLibrary":
        if self._loaded:
            return self
        # Supabase Storage is the source of truth on hosts. Re-sync on load (not
        # only when the file is missing) so library updates — e.g. a deduped-names
        # pass — propagate to the persistent volume instead of staying pinned to
        # the stale first-boot copy. No-op when storage env vars are unset (local
        # dev uses the in-repo JSON); a failed download leaves any existing file
        # untouched (see _seed_from_storage).
        _seed_from_storage(self.path)
        self._personas = persona_repository.read(self.path)
        if self._personas:
            self._report_model_drift()
            self._stamp_lsm()
            logger.info(f"Loaded {len(self._personas)} personas from library.")
        self._loaded = True
        return self

    def _report_model_drift(self) -> None:
        """Warn when stored personas no longer match app/data/model/persona.json.

        Never blocks a load: a drifted hosted library still serves rooms, but the log
        says so instead of card rules and grounds quietly matching nobody. Runs before
        lsm_proxy is stamped, since that stamp lives in memory only.
        """
        try:
            problems = data_model.library_problems(self._personas)
        except Exception as e:  # noqa: BLE001 — a broken model file must not empty the library
            logger.warning(f"Could not check persona library against its data model: {e}")
            return
        if problems:
            logger.warning(
                f"Persona library does not match its data model: {len(problems)} problem(s). "
                f"First: {'; '.join(problems[:3])}"
            )

    def _stamp_lsm(self) -> None:
        """Attach lsm_proxy {score, band, confidence} to every persona at load.

        Always recomputed from the current rubric and written over any stamp that
        arrived in the stored copy, so a rubric change takes effect on the next
        load without touching the library file. Pure function per persona — no
        LLM anywhere in this path (see lsm_proxy.py).
        """
        for persona in self._personas:
            persona["lsm_proxy"] = score_persona(persona)

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

    def people(self) -> List["LibraryPersona"]:
        """The library as typed objects (app.models.LibraryPersona): `person.medical_aid`,
        `person.fact("internet_use")`. A persona that does not fit the model is left out;
        the load warning already names it."""
        if self._people is None:
            from ..models import LibraryPersona
            people = []
            for p in self.all():
                data = {k: v for k, v in p.items() if k != "lsm_proxy"}  # stamped at load, not stored
                try:
                    people.append(LibraryPersona.model_validate(data))
                except Exception:  # noqa: BLE001 — reported by _report_model_drift
                    continue
            self._people = people
        return list(self._people)

    def person(self, persona_id: str) -> Optional["LibraryPersona"]:
        return next((p for p in self.people() if p.id == persona_id), None)

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
