"""
validate_ghs_adapter — hard asserts over the GHS education-skeleton adapter.

Everything here is LLM-free: role constraints, sentinel handling, determinism,
decode sanity, and a marginal check that the weighted learner sample tracks the
pool's province distribution. Run from backend/:
    python scripts/validate_ghs_adapter.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from ghs_adapter import (
    education_marginals,
    sample_education_skeletons,
    LEARNER_MAX_AGE,
    MIN_PERSONA_AGE,
    GUARDIAN_MIN_AGE,
)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def main():
    skeletons = sample_education_skeletons(n_learners=120, n_guardians=120, seed=7)
    learners = [s for s in skeletons if s["ghs_role"] == "learner"]
    guardians = [s for s in skeletons if s["ghs_role"] in ("guardian_parent", "gogo_guardian")]
    check("counts honoured", len(learners) == 120 and len(guardians) == 120,
          f"{len(learners)} learners, {len(guardians)} guardians")

    # ── role constraints ──────────────────────────────────────────────────
    check("learner ages within persona universe",
          all(MIN_PERSONA_AGE <= s["age"] <= LEARNER_MAX_AGE for s in learners))
    check("learners are in the school system",
          all(s["edu_institution"] in ("School", "ABET centre", "TVET college", "Home schooling")
              for s in learners))
    check("learners not economically active",
          all(s["employment_status"] == "Other not economically active" for s in learners))
    check("guardian ages sane", all(s["age"] >= GUARDIAN_MIN_AGE for s in guardians))
    check("guardians have learners in household",
          all(s["learners_in_household"] >= 1 for s in guardians))
    gogos = [s for s in guardians if s["ghs_role"] == "gogo_guardian"]
    check("gogo split present and marked", len(gogos) > 0 and
          all(s["guards_grandchildren"] for s in gogos), f"{len(gogos)} gogos")

    # ── decode sanity (no raw codes leaking through) ──────────────────────
    provinces = {s["province"] for s in skeletons}
    check("provinces decoded to labels",
          provinces and all(p and not p[0].isdigit() for p in provinces), str(provinces))
    check("gender decoded", all(s["gender"] in ("Male", "Female") for s in skeletons))
    check("education grouped to QLFS vocab", all(
        s["education"] in ("No schooling", "Primary", "Secondary not completed",
                           "Secondary completed", "Tertiary", None)
        for s in skeletons))
    check("geotype decoded", all(
        s["geotype"] in ("Urban", "Traditional", "Farms", None) for s in skeletons))
    langs = {s["home_language"] for s in skeletons if s["home_language"]}
    check("languages decoded", len(langs) >= 4 and all(not l[0].isdigit() for l in langs), str(langs))
    check("no 'Unspecified' fabricated into employment", all(
        s["employment_status"] in ("Employed", "Unemployed", "Discouraged job seeker",
                                   "Other not economically active", None)
        for s in skeletons))

    # ── real income: present, sane, sentinel-free ─────────────────────────
    incomes = [s["monthly_household_income_rand"] for s in skeletons
               if s["monthly_household_income_rand"] is not None]
    check("income present for most skeletons", len(incomes) >= len(skeletons) * 0.9,
          f"{len(incomes)}/{len(skeletons)}")
    check("income sentinel stripped", all(0 < v <= 800_000 for v in incomes),
          f"max={max(incomes) if incomes else None}")
    check("income provenance tied to value", all(
        (s["monthly_household_income_rand"] is None) == (s["income_provenance"] is None)
        for s in skeletons))

    # ── determinism ───────────────────────────────────────────────────────
    again = sample_education_skeletons(n_learners=120, n_guardians=120, seed=7)
    check("deterministic for seed", skeletons == again)
    other = sample_education_skeletons(n_learners=120, n_guardians=120, seed=8)
    check("different seed differs", skeletons != other)

    # ── representativeness: sampled learner provinces track the weighted pool ──
    marg = education_marginals()
    pool_pct = marg["learner_province_pct"]
    sample_counts = {}
    for s in learners:
        sample_counts[s["province"]] = sample_counts.get(s["province"], 0) + 1
    worst = 0.0
    for prov, pct in pool_pct.items():
        got = sample_counts.get(prov, 0) / len(learners) * 100
        worst = max(worst, abs(got - pct))
    check("learner province marginals within 12pp of pool (n=120)", worst <= 12.0,
          f"worst gap {worst:.1f}pp")

    # ── the gogo fact stays visible ───────────────────────────────────────
    split = marg["guardian_household_split"]
    check("gogo households are a major share (data sanity)",
          25.0 <= split["gogo_pct"] <= 55.0, str(split))

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
