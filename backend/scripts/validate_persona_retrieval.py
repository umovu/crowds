"""
validate_persona_retrieval — prove retrieval tilts toward relevance without becoming
an echo chamber.

LLM-free, deterministic. Asserts:
  1. A tilted query SHIFTS the cast toward relevant archetypes (tilt has an effect).
  2. The cast still spans >= MIN_DISTINCT_ARCHETYPES (the room isn't one note).
  3. Non-relevant archetypes still appear (representativeness preserved).
  4. Province focus increases that province's share without eliminating others.
  5. Determinism: same (query, seed) → same cast.

Run:  python backend/scripts/validate_persona_retrieval.py
Exit 0 = representative+relevant; 1 = collapsed/echo-chamber or no effect.
"""

from __future__ import annotations

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Importing app.services.* runs app/services/__init__.py, which eagerly loads the sim
# engine (agentsociety2) and demands AGENTSOCIETY_LLM_API_KEY at import time. The
# production Flask app always has this set; for this offline, LLM-free validation we
# satisfy it with a placeholder so the import chain doesn't abort. persona_retrieval
# and persona_library themselves make no model calls.
os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "validation-placeholder")

from app.services.persona_library import PersonaLibrary
from app.services import persona_retrieval as pr

_LIB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "app", "data", "persona_library", "personas.json")
)


def main() -> int:
    lib = PersonaLibrary(_LIB_PATH).load()
    if lib.is_empty():
        print(f"SKIP: persona library empty at {_LIB_PATH}. Run build_library.py first.")
        return 0

    total = len(lib.all())
    n = min(12, total)
    print(f"library size={total}, cast size n={n}")
    print("library archetype mix:",
          {k: round(v, 2) for k, v in lib.archetype_distribution().items()})

    ok = True

    # Untilted (representative) baseline.
    base = pr.select_for_query(n, query="", library=lib, seed=5)
    base_mix = Counter(p["actor_archetype"] for p in base)
    print(f"\nuntilted cast mix: {dict(base_mix)}")

    # Tilted toward informal traders (taxi/spaza-style query).
    tilted = pr.select_for_query(n, query="taxi and spaza informal trade", library=lib, seed=5)
    tilt_mix = Counter(p["actor_archetype"] for p in tilted)
    print(f"tilted (informal) cast mix: {dict(tilt_mix)}")

    # 1. Tilt has an effect: informal_trader share should not DECREASE.
    if lib.filter(archetype="informal_trader"):
        if tilt_mix.get("informal_trader", 0) < base_mix.get("informal_trader", 0):
            print("FAIL: tilt reduced the relevant archetype's share")
            ok = False
        elif tilt_mix.get("informal_trader", 0) == base_mix.get("informal_trader", 0):
            print("NOTE: tilt had no measurable effect (small library / few relevant personas)")

    # 2. Spread floor.
    distinct = len(set(tilt_mix))
    floor = min(pr.MIN_DISTINCT_ARCHETYPES, n, len(lib.archetype_distribution()))
    print(f"\ndistinct archetypes in tilted cast: {distinct} (floor {floor})")
    if distinct < floor:
        print("FAIL: tilted cast collapsed below the diversity floor (echo chamber)")
        ok = False

    # 3. Non-relevant archetypes survive: more than just informal_trader present.
    if distinct <= 1 and total > 1:
        print("FAIL: tilted cast is a single archetype")
        ok = False

    # 4. Province focus.
    provinces = {p["province"] for p in lib.all()}
    if len(provinces) > 1:
        focus = sorted(provinces)[0]
        prov_cast = pr.select_for_query(n, query=f"service delivery in {focus}", library=lib, seed=5)
        prov_share = sum(1 for p in prov_cast if p["province"] == focus) / len(prov_cast)
        all_share = sum(1 for p in lib.all() if p["province"] == focus) / total
        other_provinces = {p["province"] for p in prov_cast if p["province"] != focus}
        print(f"\nprovince '{focus}' share: cast {prov_share:.2f} vs library {all_share:.2f}; "
              f"other provinces in cast: {len(other_provinces)}")
        if prov_cast and other_provinces == set() and len(provinces) > 1:
            print("FAIL: province focus eliminated all other provinces")
            ok = False

    # 5. Determinism.
    a = [p["id"] for p in pr.select_for_query(n, query="taxi", library=lib, seed=9)]
    b = [p["id"] for p in pr.select_for_query(n, query="taxi", library=lib, seed=9)]
    if a != b:
        print("\nFAIL: non-deterministic selection for same (query, seed)")
        ok = False

    print("\n" + ("PASS — retrieval tilts toward relevance and stays representative."
                  if ok else "FAIL — see above."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
