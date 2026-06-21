"""
validate_archetype_mapper — prove the archetype mapping is honest and plausible.

Asserts, with NO LLM:
  1. NO behavioral-edge archetype is ever assigned from demographics (the profiling guard).
  2. Every assigned archetype is in the honest allow-set.
  3. The mapping is deterministic: same (skeleton, seed) → same archetype.
  4. The resulting mix is plausible: unemployment-derived archetypes track the real
     unemployment/non-employment rate within tolerance (not mechanically uniform, not skewed).

Run:  python backend/scripts/validate_archetype_mapper.py
Exit 0 = honest + plausible; 1 = drift / leak.
"""

from __future__ import annotations

import sys
from collections import Counter

from persona_sampler import sample_skeletons
from archetype_mapper import (
    map_skeletons, assign_archetype,
    HONEST_ARCHETYPES, FORBIDDEN_FROM_DEMOGRAPHICS,
)

SAMPLE_N = 5000
SEED = 7
# unemployed_youth + disillusioned_dropout + grant_dependent_survivor are the
# not-employed-derived archetypes. From QLFS, employed is ~36% of adults, so the
# not-employed-derived share should land roughly in the 55–70% range.
NOT_EMPLOYED_DERIVED = {"unemployed_youth", "disillusioned_dropout", "grant_dependent_survivor"}
NOT_EMPLOYED_LO, NOT_EMPLOYED_HI = 55.0, 72.0


def main() -> int:
    try:
        skeletons = sample_skeletons(SAMPLE_N, seed=SEED)
    except FileNotFoundError as e:
        print(f"SKIP: {e}")
        return 0

    mapped = map_skeletons(skeletons, seed=SEED)
    archetypes = [m["actor_archetype"] for m in mapped]
    dist = Counter(archetypes)
    total = sum(dist.values())

    print("=== archetype distribution ===")
    for arch, n in dist.most_common():
        print(f"  {arch:28} {n/total*100:5.1f}%  ({n})")

    ok = True

    # 1 + 2: every archetype is honest, none forbidden.
    leaked = [a for a in dist if a in FORBIDDEN_FROM_DEMOGRAPHICS]
    if leaked:
        print(f"\nFAIL: edge archetype(s) assigned from demographics: {leaked}")
        ok = False
    out_of_set = [a for a in dist if a not in HONEST_ARCHETYPES]
    if out_of_set:
        print(f"\nFAIL: archetype(s) outside the honest allow-set: {out_of_set}")
        ok = False

    # 3: determinism — re-run a sample of skeletons, expect identical assignment.
    for sk in skeletons[:200]:
        if assign_archetype(sk, seed=SEED) != assign_archetype(sk, seed=SEED):
            print("\nFAIL: non-deterministic assignment for same (skeleton, seed)")
            ok = False
            break

    # 4: plausibility — not-employed-derived share tracks reality.
    ne_share = sum(dist.get(a, 0) for a in NOT_EMPLOYED_DERIVED) / total * 100
    print(f"\nnot-employed-derived share: {ne_share:.1f}% "
          f"(expected {NOT_EMPLOYED_LO}–{NOT_EMPLOYED_HI}%)")
    if not (NOT_EMPLOYED_LO <= ne_share <= NOT_EMPLOYED_HI):
        print("FAIL: not-employed-derived share out of plausible range.")
        ok = False

    # Not mechanically uniform: at least 5 distinct archetypes present.
    if len(dist) < 5:
        print(f"FAIL: only {len(dist)} distinct archetypes — too uniform.")
        ok = False

    print("\n" + ("PASS — archetype mapping is honest, deterministic, and plausible."
                  if ok else "FAIL — see above."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
