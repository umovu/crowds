"""Land CHILDREN AT SCHOOL + MEDICAL AID on the persona library from real GHS 2025 microdata.

Why this exists: most of the library was built from QLFS, the labour force survey.
It asks about a person's work, not their household, so it never recorded whether
they live with children. Only the 69 personas built on purpose as learners or
parents carry it. The other 306 read as "unknown", which every consumer treats as
"no":

  * education cards are gated to parents, so a school pitch grounds 18% of a room
  * the room picker cannot find Thuto's market (parents paying school fees)
  * the model decides for itself whether a persona has children when asked about
    a phone ban, which is the model writing identity

Medical aid is blank on 228 personas for the same reason and comes off the same
survey row, so it is filled on the same pass.

Method: donor matching, same discipline as the geography and attitude imports.

  1. Each persona's own demographics pick a pool of real GHS adults like them.
     Age leads the rungs: parenthood turns on age far more than on province.
  2. The pool's weighted spread over `learner_relation` becomes the persona's
     odds, and seats are allocated per (sex, age band, geotype) so the GROUP
     total matches what those same people's pools say, not a lucky streak.
  3. One real person in the pool with that relation is drawn as the donor, and
     every fact is copied from them together. Drawing each fact separately could
     seat someone as a parent with no children in the house.

No LLM, no network, deterministic for a given library.

What is written (as `circumstances` rows, source `ghs_2025:household`):

    learners_in_household  "0".."4" (4 means four or more), school-system only
    ghs_role               guardian_parent | gogo_guardian, only when it applies
    learner_fee_bands      the highest fee band paid, only when there are learners
    medical_aid            "True" | "False"

Each row carries the rung it was matched on, the pool size, the drawn value's
share of that pool, and a `grade`:

    strong   matched on age and sex at least, and the drawn value holds for 60%+
             of the pool — most people like this persona really are like this
    weak     either the match had to loosen past age and sex, or the pool is split

A value on the persona's own survey row (top-level field) is never overwritten.
It is the measured answer and `situation_facts` reads it first.

Parent vs lives-with: GHS records everyone's relation to the HEAD of household,
not to each other. So:

    parent         head or spouse, and a learner is the head's child
    likely_parent  the head's own adult child (18-49), and a learner is the head's
                   grandchild — the common case of a mother in her mother's house.
                   Written as guardian_parent but always graded weak: another
                   adult child may be the parent.
    grandparent    head or spouse, and a learner is the head's grandchild
    other_adult    learners in the house, but none of the above
    none           no learners in the house

Dry run by default. --validate runs the accuracy test on GHS itself before
anything touches the library. --write backs up and applies.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import random
import sys
from typing import Dict, List, Optional, Tuple

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import ghs_adapter as g  # noqa: E402

_ROOT = os.path.join(_HERE, "..")
LIBRARY = os.path.join(_ROOT, "app", "data", "persona_library", "personas.json")
BACKUP = os.path.join(_ROOT, "app", "data", "persona_library",
                      "personas.backup-pre-ghs-household.json")
# "survey:subset", like afrobarometer_r9_sa:students — resolves to a known survey, and is
# not the bare "ghs_2025" the geography pass clears on a re-run.
SOURCE = "ghs_2025:household"

MIN_POOL = 30
STRONG_SHARE = 0.60
ADULT_AGE = 18
LIKELY_PARENT_AGES = (18, 49)
MAX_LEARNERS = 4

_GEOTYPE = {"1": "Urban", "2": "Traditional", "3": "Farms"}

# Widest last. Age and sex are held the longest: whether someone lives with
# school-age children turns on their age before anything else.
_RUNGS: List[Tuple[str, List[str]]] = [
    ("prov_geo_race_sex_age", ["province", "geotype", "race", "gender", "age"]),
    ("geo_race_sex_age",      ["geotype", "race", "gender", "age"]),
    ("geo_sex_age",           ["geotype", "gender", "age"]),
    ("sex_age",               ["gender", "age"]),
    ("age",                   ["age"]),
    ("population",            []),
]
# A match on these rungs kept both age and sex, which is the precondition for strong.
_STRONG_RUNGS = {"prov_geo_race_sex_age", "geo_race_sex_age", "geo_sex_age", "sex_age"}

_RELATION_ROLE = {
    "parent": "guardian_parent",
    "likely_parent": "guardian_parent",
    "grandparent": "gogo_guardian",
}

# ── Loading ──────────────────────────────────────────────────────────────────

def _label(labels: Dict, var: str, code) -> Optional[str]:
    return g._label(labels, var, code)


def load_ghs() -> pd.DataFrame:
    """One row per GHS adult with the household facts a persona would inherit."""
    df, labels = g._load()
    ctx = g._household_learner_context(df, labels)

    df = df[(df["age"] >= ADULT_AGE) & df["person_wgt"].notna() & (df["person_wgt"] > 0)].copy()
    df["province"] = df["prov"].map(lambda c: _label(labels, "prov", c))
    df["gender"] = df["Sex"].map(lambda c: _label(labels, "Sex", c))
    df["race"] = df["Population"].map(lambda c: _label(labels, "Population", c))
    df["geo"] = df["geotype"].astype(str).str.strip().map(_GEOTYPE)

    relations, counts, fees = [], [], []
    for _, row in df.iterrows():
        c = ctx.get(row["uqnr"])
        n = int(c["learner_count"]) if c else 0
        relations.append(learner_relation(row.get("hhc_relationship"), row["age"], c))
        counts.append(str(min(n, MAX_LEARNERS)))
        fees.append(_top_fee(c["fee_bands"]) if c else None)
    df["learner_relation"] = relations
    df["learners"] = counts
    df["fee_band"] = fees
    df["medical_aid"] = df["hlt_medi"].map(g._HLT_MEDI)
    df = df[df["province"].notna() & df["gender"].notna() & df["geo"].notna()]
    return df.reset_index(drop=True)


def learner_relation(rel, age, ctx: Optional[Dict]) -> str:
    """How one adult stands to the learners in their household. `rel` is their GHS
    relation to the head; `ctx` is the household's learner context, or None."""
    if not ctx or not ctx.get("learner_count"):
        return "none"
    if rel in (g._REL_HEAD, g._REL_SPOUSE) and ctx.get("any_child_of_head"):
        return "parent"
    if rel in (g._REL_HEAD, g._REL_SPOUSE) and ctx.get("any_grandchild_of_head"):
        return "grandparent"
    if (rel == g._REL_CHILD and ctx.get("any_grandchild_of_head")
            and LIKELY_PARENT_AGES[0] <= age <= LIKELY_PARENT_AGES[1]):
        return "likely_parent"
    return "other_adult"


def _fee_rank(band: Optional[str]) -> float:
    """Sort key for an annual fee band: its lower bound in rand, unpaid lowest."""
    if not band or band == "No fees":
        return 0.0
    digits = "".join(ch if ch.isdigit() else " " for ch in band.replace(",", "")
                     .replace(" ", "")).split()
    return float(digits[0]) if digits else 0.5


def _top_fee(bands: List[str]) -> Optional[str]:
    return max(bands, key=_fee_rank) if bands else None


# ── Matching ─────────────────────────────────────────────────────────────────

def match_pool(df: pd.DataFrame, persona: Dict) -> Tuple[pd.DataFrame, str]:
    for quality, keys in _RUNGS:
        pool = df
        if "province" in keys:
            pool = pool[pool["province"] == persona.get("province")]
        if "geotype" in keys:
            pool = pool[pool["geo"] == persona.get("geotype")]
        if "race" in keys:
            pool = pool[pool["race"] == persona.get("race")]
        if "gender" in keys:
            pool = pool[pool["gender"] == persona.get("gender")]
        if "age" in keys:
            age = persona.get("age") or 0
            pool = pool[pool["age"].between(age - 5, age + 5)]
        if len(pool) >= MIN_POOL:
            return pool, quality
    return df, "population"


def spread(pool: pd.DataFrame, column: str) -> Dict[str, float]:
    sub = pool.dropna(subset=[column])
    weights = sub.groupby(column, observed=True)["person_wgt"].sum()
    total = float(weights.sum())
    return {str(k): float(v) / total for k, v in weights.items()} if total else {}


def quotas(target: Dict[str, float], n: int) -> Dict[str, int]:
    """Largest-remainder seats; they always sum to n."""
    if n <= 0 or not target:
        return {}
    exact = {v: s * n for v, s in target.items()}
    seats = {v: int(c) for v, c in exact.items()}
    left = n - sum(seats.values())
    for v in sorted(exact, key=lambda v: (-(exact[v] - seats[v]), v))[:left]:
        seats[v] += 1
    return {v: c for v, c in seats.items() if c}


def _weighted_pick(pool: pd.DataFrame, rng: random.Random) -> pd.Series:
    total = float(pool["person_wgt"].sum())
    cut = rng.random() * total
    running = 0.0
    for _, row in pool.sort_values(["uqnr", "age"]).iterrows():
        running += float(row["person_wgt"])
        if cut <= running:
            return row
    return pool.iloc[-1]


def assign(personas: List[Dict], df: pd.DataFrame) -> List[Optional[Dict]]:
    """One donor per persona, with the pool facts needed to grade what they carry.

    Seats are set per (sex, age band, geotype) from the MEAN of the members' own pool
    spreads — what those particular people are expected to look like — so a
    stratum of mostly-young personas is not handed the parent share of an
    older real population.
    """
    matched = [match_pool(df, p) for p in personas]
    out: List[Optional[Dict]] = [None] * len(personas)

    groups: Dict[Tuple, List[int]] = collections.defaultdict(list)
    for i, p in enumerate(personas):
        groups[_stratum(p)].append(i)

    for key, members in sorted(groups.items(), key=lambda kv: str(kv[0])):
        rng = random.Random("household|" + "|".join(str(k) for k in key))
        spreads = [spread(matched[i][0], "learner_relation") for i in members]
        target: Dict[str, float] = collections.defaultdict(float)
        for s in spreads:
            for v, share in s.items():
                target[v] += share / len(members)
        left = quotas(dict(target), len(members))

        order = sorted(range(len(members)),
                       key=lambda j: (len([v for v in spreads[j] if v in left]),
                                      str(personas[members[j]].get("id"))))
        for j in order:
            i = members[j]
            own = {v: s for v, s in spreads[j].items() if left.get(v, 0) > 0}
            if own:
                total = sum(own.values())
                cut, running = rng.random() * total, 0.0
                for relation in sorted(own, key=lambda v: (-own[v], v)):
                    running += own[relation]
                    if cut <= running:
                        break
            else:
                relation = max(left, key=lambda v: (left[v], v))
            left[relation] -= 1
            if not left[relation]:
                del left[relation]

            pool, quality = matched[i]
            candidates = pool[pool["learner_relation"] == relation]
            if candidates.empty:  # the seat came from the stratum, not this pool
                candidates = df[df["learner_relation"] == relation]
            donor = _weighted_pick(candidates, rng)
            out[i] = {
                "donor": donor,
                "quality": quality,
                "pool": len(pool),
                "relation_share": round(spreads[j].get(relation, 0.0), 3),
                "medical_share": spread(pool, "medical_aid"),
            }
    return out


def _age_band(age) -> str:
    age = age or 0
    for top, band in ((24, "18-24"), (34, "25-34"), (49, "35-49"), (64, "50-64")):
        if age <= top:
            return band
    return "65+"


def _stratum(persona: Dict) -> Tuple:
    """Who shares a pot of seats. Sex and age band, not province: whether someone
    lives with learners turns on those two, and balancing seats by province let
    men 25-34 run ten points high and women 65+ ten points low in validation."""
    return (persona.get("gender"), _age_band(persona.get("age")), persona.get("geotype"))


def _grade(quality: str, share: float, relation: Optional[str] = None) -> str:
    if relation == "likely_parent":
        return "weak"
    return "strong" if quality in _STRONG_RUNGS and share >= STRONG_SHARE else "weak"


def rows_for(persona: Dict, result: Optional[Dict]) -> List[Dict]:
    """The circumstances rows this persona gains. Never overwrites a measured field."""
    if not result:
        return []
    donor, quality, pool = result["donor"], result["quality"], result["pool"]
    rel_share = result["relation_share"]
    relation = donor["learner_relation"]
    base = {"source": SOURCE, "match_quality": quality, "pool": pool}
    rows = []

    if persona.get("learners_in_household") in (None, "", []):
        rows.append({**base, "field": "learners_in_household", "value": donor["learners"],
                     "share": rel_share, "grade": _grade(quality, rel_share, relation)})
        role = _RELATION_ROLE.get(relation)
        if role and not persona.get("ghs_role"):
            rows.append({**base, "field": "ghs_role", "value": role,
                         "share": rel_share, "grade": _grade(quality, rel_share, relation)})
        if donor["fee_band"] and not persona.get("learner_fee_bands"):
            rows.append({**base, "field": "learner_fee_bands", "value": donor["fee_band"],
                         "share": rel_share, "grade": _grade(quality, rel_share, relation)})

    if persona.get("medical_aid") is None and donor["medical_aid"] is not None:
        value = str(bool(donor["medical_aid"]))
        share = round(result["medical_share"].get(str(donor["medical_aid"]), 0.0), 3)
        rows.append({**base, "field": "medical_aid", "value": value,
                     "share": share, "grade": _grade(quality, share)})
    return rows


def _targets(personas: List[Dict]) -> List[Dict]:
    """Adults with at least one of the two facts missing. Learners are skipped: they
    are the child in the household, and this pass describes the adults."""
    return [p for p in personas
            if (p.get("age") or 0) >= ADULT_AGE and p.get("ghs_role") != "learner"
            and (p.get("learners_in_household") in (None, "", [])
                 or p.get("medical_aid") is None)]


# ── Validation ───────────────────────────────────────────────────────────────

def validate(df: pd.DataFrame, n: int = 3000, seed: int = 11) -> None:
    """Hide real GHS adults' answers, impute them from the other half, compare.

    Split by HOUSEHOLD, not by person, so a test person's own spouse can never be
    their donor and leak the answer.
    """
    rng = random.Random(seed)
    households = sorted(df["uqnr"].unique())
    rng.shuffle(households)
    test_hh = set(households[: len(households) // 2])
    donors = df[~df["uqnr"].isin(test_hh)].reset_index(drop=True)
    test = df[df["uqnr"].isin(test_hh)].sample(n=min(n, len(test_hh)), random_state=seed)

    fake = [{"id": f"t{i}", "age": int(r["age"]), "gender": r["gender"], "race": r["race"],
             "province": r["province"], "geotype": r["geo"]}
            for i, (_, r) in enumerate(test.iterrows())]
    results = assign(fake, donors)

    def has_learner(v): return v != "none"
    def is_parent(v): return v in ("parent", "likely_parent")
    def is_gogo(v): return v == "grandparent"

    truth = list(test["learner_relation"])
    drawn = [r["donor"]["learner_relation"] for r in results]
    grades = [_grade(r["quality"], r["relation_share"], r["donor"]["learner_relation"])
              for r in results]
    weights = list(test["person_wgt"])
    w_total = sum(weights)

    print(f"\nVALIDATION — {len(test)} real GHS adults, answers hidden, "
          f"donors from the other half of households\n")
    print(f"{'fact':<30}{'real share':>11}{'imputed':>9}{'person-level':>14}{'base-rate guess':>17}")
    for name, test_fn in (("lives with a learner", has_learner),
                          ("parent (incl. likely)", is_parent),
                          ("grandparent guardian", is_gogo)):
        real = sum(w for w, t in zip(weights, truth) if test_fn(t)) / w_total
        got = sum(w for w, d in zip(weights, drawn) if test_fn(d)) / w_total
        right = sum(w for w, t, d in zip(weights, truth, drawn)
                    if test_fn(t) == test_fn(d)) / w_total
        # What an independent draw at the true base rate would score: p^2 + (1-p)^2.
        chance = real ** 2 + (1 - real) ** 2
        print(f"{name:<30}{real:>10.1%}{got:>9.1%}{right:>13.1%}{chance:>16.1%}")

    med_truth = list(test["medical_aid"])
    med_drawn = [r["donor"]["medical_aid"] for r in results]
    pairs = [(w, t, d) for w, t, d in zip(weights, med_truth, med_drawn)
             if t is not None and d is not None]
    if pairs:
        tw = sum(w for w, _, _ in pairs)
        real = sum(w for w, t, _ in pairs if t) / tw
        got = sum(w for w, _, d in pairs if d) / tw
        right = sum(w for w, t, d in pairs if t == d) / tw
        chance = real ** 2 + (1 - real) ** 2
        print(f"{'medical aid':<30}{real:>10.1%}{got:>9.1%}{right:>13.1%}{chance:>16.1%}")

    print("\nBY GRADE — lives with a learner, person-level")
    for grade in ("strong", "weak"):
        idx = [i for i, gr in enumerate(grades) if gr == grade]
        if not idx:
            continue
        gw = sum(weights[i] for i in idx)
        right = sum(weights[i] for i in idx if has_learner(truth[i]) == has_learner(drawn[i])) / gw
        print(f"  {grade:<7} {len(idx):5d} people   {right:6.1%} right")

    print("\nBY GROUP — share living with a learner, real vs imputed (the number a room shows)")
    frame = pd.DataFrame({"g": test["gender"].values, "age": test["age"].values,
                          "w": weights, "t": [has_learner(t) for t in truth],
                          "d": [has_learner(d) for d in drawn]})
    frame["band"] = pd.cut(frame["age"], [17, 24, 34, 49, 64, 200],
                           labels=["18-24", "25-34", "35-49", "50-64", "65+"])
    worst = 0.0
    for (sex, band), part in frame.groupby(["g", "band"], observed=True):
        if part["w"].sum() == 0 or len(part) < 40:
            continue
        real = (part["w"] * part["t"]).sum() / part["w"].sum()
        got = (part["w"] * part["d"]).sum() / part["w"].sum()
        worst = max(worst, abs(real - got))
        print(f"  {sex:<7}{band:<7} n={len(part):4d}   real {real:6.1%}   imputed {got:6.1%}")
    print(f"  largest group gap: {worst:.1%}")


# ── Report + write ───────────────────────────────────────────────────────────

def _sanity(personas: List[Dict], rows: List[List[Dict]]) -> List[str]:
    problems = []
    for p, rs in zip(personas, rows):
        f = {r["field"]: r["value"] for r in rs}
        age = p.get("age") or 0
        if f.get("ghs_role") == "gogo_guardian" and age < 35:
            problems.append(f"{p.get('name')}: grandparent guardian at {age}")
        if f.get("ghs_role") == "guardian_parent" and age > 75:
            problems.append(f"{p.get('name')}: parent of a learner at {age}")
        if f.get("ghs_role") and f.get("learners_in_household") == "0":
            problems.append(f"{p.get('name')}: guardian with no learners")
    return problems


def _report(targets: List[Dict], rows: List[List[Dict]], results: List[Optional[Dict]]) -> None:
    print(f"\nPersonas filled: {len(targets)}")
    q = collections.Counter(r["quality"] for r in results if r)
    print("MATCH QUALITY")
    for name, count in q.most_common():
        print(f"  {count:4d}  {name}")

    rel = collections.Counter(r["donor"]["learner_relation"] for r in results if r)
    print("\nLEARNER RELATION (drawn)")
    for name, count in rel.most_common():
        print(f"  {count:4d}  {count / len(targets):5.1%}  {name}")

    for field in ("learners_in_household", "ghs_role", "medical_aid"):
        c = collections.Counter(r["value"] for rs in rows for r in rs if r["field"] == field)
        grades = collections.Counter(r["grade"] for rs in rows for r in rs if r["field"] == field)
        print(f"\n{field.upper()}  ({grades.get('strong', 0)} strong, {grades.get('weak', 0)} weak)")
        for value, count in c.most_common():
            print(f"  {count:4d}  {value}")

    problems = _sanity(targets, rows)
    print(f"\nSANITY: {len(problems)} problem(s)")
    for line in problems[:10]:
        print("  " + line)

    print("\nSAMPLE")
    for p, rs in list(zip(targets, rows))[:10]:
        summary = "  ".join(f"{r['field']}={r['value']}({r['grade'][0]})" for r in rs)
        print(f"  {str(p.get('name'))[:22]:<23}{p.get('age'):>3} {p.get('gender', ''):<7}{summary}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--validate", action="store_true", help="accuracy test on GHS itself")
    ap.add_argument("--write", action="store_true", help="back up the library and apply")
    args = ap.parse_args()

    df = load_ghs()
    print(f"GHS adults: {len(df):,}")

    if args.validate:
        validate(df)
        return 0

    with open(LIBRARY, encoding="utf-8") as fh:
        library = json.load(fh)
    personas = library["personas"] if isinstance(library, dict) else library
    targets = _targets(personas)
    results = assign(targets, df)
    rows = [rows_for(p, r) for p, r in zip(targets, results)]
    _report(targets, rows, results)

    if _sanity(targets, rows):
        print("\nSanity problems found. Nothing written.")
        return 1
    if not args.write:
        print("\nDry run. Nothing written. Re-run with --write to apply.")
        return 0

    # Only the first run backs up. A second --write would otherwise save the already
    # filled library over the one worth going back to.
    if os.path.exists(BACKUP):
        print(f"\nKept the existing {os.path.basename(BACKUP)} (the library before any fill)")
    else:
        with open(BACKUP, "w", encoding="utf-8") as fh:
            json.dump(library, fh, ensure_ascii=False, indent=1)
        print(f"\nBacked up to {os.path.basename(BACKUP)}")
    for p, rs in zip(targets, rows):
        kept = [r for r in p.get("circumstances") or [] if r.get("source") != SOURCE]
        p["circumstances"] = kept + rs
    with open(LIBRARY, "w", encoding="utf-8") as fh:
        json.dump(library, fh, ensure_ascii=False, indent=1)
    print(f"Wrote {sum(len(r) for r in rows)} rows onto {len(targets)} personas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
