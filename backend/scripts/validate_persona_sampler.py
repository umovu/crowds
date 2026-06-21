"""
validate_persona_sampler — prove the skeleton sampler reproduces SA marginals.

This is the first-probe deliverable: confidence that sampled identity skeletons
match the real population distribution, with NO LLM involved. If this passes, the
persona-library foundation is sound and texture generation can be built on top.

Run:  python backend/scripts/validate_persona_sampler.py
Exit code 0 = within tolerance; 1 = drift detected (bad weights / decode).
"""

from __future__ import annotations

import sys
from collections import Counter

from persona_sampler import sample_skeletons, population_marginals

# Tolerance in percentage points. A large weighted sample should land very close
# to the population marginals; ±2pp catches real skew without flagging sampling noise.
TOLERANCE_PP = 2.0
SAMPLE_N = 20000
SEED = 42


def _sample_pct(skeletons, key) -> dict:
    c = Counter(s[key] for s in skeletons if s.get(key) is not None)
    total = sum(c.values())
    return {k: round(v / total * 100, 2) for k, v in c.items()}


def _check(dim_name: str, sample_pct: dict, truth_pct: dict) -> bool:
    print(f"\n=== {dim_name}: sample vs population (pp diff) ===")
    ok = True
    for label, truth in sorted(truth_pct.items(), key=lambda kv: -kv[1]):
        got = sample_pct.get(label, 0.0)
        diff = got - truth
        flag = "" if abs(diff) <= TOLERANCE_PP else "  <-- OUT OF TOLERANCE"
        if abs(diff) > TOLERANCE_PP:
            ok = False
        print(f"  {label:34} sample {got:5.2f}  pop {truth:5.2f}  ({diff:+.2f}){flag}")
    return ok


def main() -> int:
    try:
        skeletons = sample_skeletons(SAMPLE_N, seed=SEED)
    except FileNotFoundError as e:
        print(f"SKIP: {e}")
        return 0  # absence of licensed data is not a test failure

    truth = population_marginals()

    prov_ok = _check("Province", _sample_pct(skeletons, "province"), truth["Province"])
    stat_ok = _check("Employment status", _sample_pct(skeletons, "employment_status"), truth["Status"])

    # Sanity invariants that whole-row sampling guarantees — assert them anyway.
    assert all(s["age"] >= 15 for s in skeletons), "age < 15 leaked in"
    assert all(s["province"] for s in skeletons), "missing province"
    assert all(s["occupation"] for s in skeletons), "missing occupation descriptor"

    print("\n" + "=" * 60)
    print("20 sample skeletons (eyeball for plausibility):")
    print("=" * 60)
    import json
    for sk in sample_skeletons(20, seed=1):
        print(json.dumps(sk, ensure_ascii=False))

    passed = prov_ok and stat_ok
    print("\n" + ("PASS — sampler reproduces SA marginals within tolerance."
                  if passed else
                  f"FAIL — some marginals drift > {TOLERANCE_PP}pp. Check weights/decode."))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
