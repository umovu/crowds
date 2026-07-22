"""
eval_attitude_match — held-out evaluation of attitude donor-matching ladders.

The question this answers: **does a given backoff ladder actually give a person the
attitudes they really hold?**

Ladder designs were previously compared on in-sample proxies (top-rung counts,
attribute concordance, group-mean R²). Those proxies disagree with each other and
group-mean R² mechanically rewards high-cardinality keys, so they cannot rank the
join keys. This script measures the thing we care about instead.

Method
------
Donors are the only records where we know BOTH the demographics and the true
attitudes. So we hide some:

  1. Split donors into train/test (k-fold, seeded).
  2. Treat each TEST donor as a skeleton — it carries every join key.
  3. Match it against the TRAIN pool only, using the ladder under test. A test
     donor can never match itself; that is the point of the split.
  4. Compare the assigned attitudes to the test donor's real answers.

Scores are averaged over k folds so one lucky split can't decide the design.

Baselines
---------
Two, both required. If a ladder can't beat "give everyone the most common stance",
the matching is not earning its complexity — which is a finding worth having.

Caveat (also printed in the output)
-----------------------------------
Test donors are Afrobarometer respondents, not QLFS skeletons. Their demographic
mix differs (Afrobarometer oversamples Coloured, undersamples White). This measures
LADDER quality, not final library quality.

LLM-free. Deterministic. No network.
"""

from __future__ import annotations

import argparse
import hashlib
import random
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

import attitude_donor_adapter as ada

# Ordinal positions so "how far off" is measurable, not just right/wrong.
_ORDINAL: Dict[str, int] = {
    "low": 0, "mid": 1, "high": 2,
    "pessimistic": 0, "neutral": 1, "optimistic": 2,
    "dissatisfied": 0, "mixed": 1, "satisfied": 2,
}

# The four dimensions every donor carries. education_satisfaction is excluded: it is
# only populated for the education sub-pool, so scoring it here would compare ladders
# on a different, smaller population.
DIMS = ["gov_trust", "economic_optimism", "service_satisfaction", "crime_fear"]

_G = ["gender", "province", "education_band", "employment_status"]

# Candidate ladders. Each is a list of rungs; a rung is the set of keys that must all
# match. The last rung is always [] (whole population) so a match always exists.
LADDERS: Dict[str, List[List[str]]] = {
    # Shipping today.
    "A_current": [
        _G + ["age_band"], _G,
        ["gender", "province", "employment_status"],
        ["gender", "employment_status"], ["employment_status"], [],
    ],
    # Swap the weakest-looking key for race, keeping the key count at 5.
    "B_swap_age_race": [
        _G + ["race"], _G,
        ["gender", "province", "employment_status"],
        ["gender", "employment_status"], ["employment_status"], [],
    ],
    # Add race as a 6th key; race survives to the bottom.
    "C_add_race": [
        _G + ["age_band", "race"], _G + ["race"],
        ["gender", "province", "employment_status", "race"],
        ["gender", "employment_status", "race"],
        ["employment_status", "race"], ["race"], [],
    ],
    # Keep age+race throughout, spend province instead.
    "D_drop_province": [
        _G + ["age_band", "race"],
        ["gender", "education_band", "employment_status", "age_band", "race"],
        ["gender", "employment_status", "age_band", "race"],
        ["gender", "age_band", "race"], ["age_band", "race"], ["race"], [],
    ],
    # Current ladder, with race added only to the lower rungs.
    "E_race_in_backoff": [
        _G + ["age_band"], _G,
        ["gender", "province", "employment_status", "race"],
        ["gender", "employment_status", "race"],
        ["employment_status", "race"], ["race"], [],
    ],
}


def _matching(view: Dict, pool: Sequence[Dict], keys: Sequence[str]) -> List[Dict]:
    """Donors in `pool` equal to `view` on every key. Empty keys → whole pool."""
    if not keys:
        return list(pool)
    return [d for d in pool if all(d.get(k) == view.get(k) for k in keys)]


def _pick(pool: Sequence[Dict], ident: str, seed: int) -> Dict:
    """Survey-weighted pick, deterministic for (ident, seed).

    Mirrors attitude_fuser._seeded_weighted_pick. It is re-implemented rather than
    imported because that function hashes QLFS skeleton fields ('age', 'education',
    'occupation') which a donor-as-skeleton does not carry — every test donor would
    hash identically and share one RNG.
    """
    if len(pool) == 1:
        return pool[0]
    h = int(hashlib.sha256(ident.encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed ^ h)
    weights = [float(d.get("weight", 1.0)) for d in pool]
    return rng.choices(list(pool), weights=weights, k=1)[0]


def _modal(pool: Sequence[Dict]) -> Dict[str, str]:
    """Survey-weighted most common stance per dimension."""
    acc: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for d in pool:
        w = float(d.get("weight", 1.0))
        for dim, stance in d["attitudes"].items():
            acc[dim][stance] += w
    return {dim: max(s.items(), key=lambda kv: kv[1])[0] for dim, s in acc.items()}


def _marginals(pool: Sequence[Dict]) -> Dict[str, Tuple[List[str], List[float]]]:
    """Weighted stance distribution per dimension, for the random baseline."""
    acc: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for d in pool:
        w = float(d.get("weight", 1.0))
        for dim, stance in d["attitudes"].items():
            acc[dim][stance] += w
    return {dim: (list(s.keys()), list(s.values())) for dim, s in acc.items()}


def _folds(donors: List[Dict], k: int, seed: int) -> List[Tuple[List[Dict], List[Dict]]]:
    """k disjoint test sets covering the pool, with the complement as train."""
    idx = list(range(len(donors)))
    random.Random(seed).shuffle(idx)
    out = []
    for f in range(k):
        test_ix = set(idx[f::k])
        out.append(
            ([donors[i] for i in idx if i not in test_ix],
             [donors[i] for i in sorted(test_ix)])
        )
    return out


# Subgroups the assigned distribution must be right WITHIN. An overall-population match
# is easy and uninformative — the modal baseline gets that badly wrong only because it
# has no spread at all. What distinguishes ladders is whether *White rural* or
# *unemployed youth* hold opinions in the right proportions.
GROUPINGS = ["race", "age_band", "province", "education_band", "employment_status"]


class Score:
    """Accumulates the real objective (subgroup distribution fidelity) plus
    per-person accuracy, which is kept only as a diagnostic — see module docstring.

    Objective = total variation distance between the ASSIGNED stance distribution and
    the TRUE stance distribution, computed within each subgroup and averaged weighted by
    subgroup size. TVD is half the sum of absolute differences across stances: 0 means
    the distributions match exactly, 1 means no overlap. Reported in points (x100).
    """

    def __init__(self) -> None:
        self.hits = 0.0
        self.n = 0
        self.abserr = 0.0
        self.by_dim: Dict[str, List[float]] = defaultdict(lambda: [0.0, 0.0])
        self.rungs: Counter = Counter()
        # (grouping, group value, dimension) -> {stance: count} for assigned and true
        self.pred_dist: Dict[Tuple[str, str, str], Counter] = defaultdict(Counter)
        self.true_dist: Dict[Tuple[str, str, str], Counter] = defaultdict(Counter)

    def add(self, truth: str, pred: Optional[str], dim: str, donor: Dict) -> None:
        hit = 1.0 if pred == truth else 0.0
        self.hits += hit
        self.n += 1
        if truth in _ORDINAL and pred in _ORDINAL:
            self.abserr += abs(_ORDINAL[truth] - _ORDINAL[pred])
        self.by_dim[dim][0] += hit
        self.by_dim[dim][1] += 1
        for grouping in GROUPINGS:
            key = (grouping, str(donor.get(grouping)), dim)
            self.true_dist[key][truth] += 1
            if pred is not None:
                self.pred_dist[key][pred] += 1

    def tvd(self, grouping: Optional[str] = None, min_n: int = 20) -> float:
        """Size-weighted mean TVD, in points. `grouping=None` averages over all
        groupings. Cells smaller than `min_n` are skipped — their empirical 'true'
        distribution is itself too noisy to be a target."""
        total_w = 0.0
        acc = 0.0
        for key, truth in self.true_dist.items():
            if grouping is not None and key[0] != grouping:
                continue
            n = sum(truth.values())
            if n < min_n:
                continue
            pred = self.pred_dist.get(key, Counter())
            m = sum(pred.values()) or 1
            stances = set(truth) | set(pred)
            d = 0.5 * sum(abs(truth[s] / n - pred[s] / m) for s in stances)
            acc += d * n
            total_w += n
        return acc / total_w * 100 if total_w else float("nan")

    @property
    def acc(self) -> float:
        return self.hits / self.n * 100 if self.n else 0.0

    @property
    def mae(self) -> float:
        return self.abserr / self.n if self.n else 0.0


def evaluate(donors: List[Dict], ladder: List[List[str]], k: int, seed: int) -> Score:
    s = Score()
    for fold, (train, test) in enumerate(_folds(donors, k, seed)):
        modal = _modal(train)
        train_ids = {id(d) for d in train}
        for i, t in enumerate(test):
            assert id(t) not in train_ids, "test donor leaked into train pool"
            for rung, keys in enumerate(ladder):
                pool = _matching(t, train, keys)
                if pool:
                    donor = _pick(pool, f"{fold}:{i}", seed)
                    s.rungs[rung] += 1
                    break
            else:  # pragma: no cover - last rung is [] so always matches
                raise RuntimeError("no rung matched")
            for dim in DIMS:
                truth = t["attitudes"].get(dim)
                if truth is None:
                    continue  # respondent refused; nothing to score against
                pred = donor["attitudes"].get(dim, modal.get(dim))
                s.add(truth, pred, dim, t)
    return s


def evaluate_baseline(donors: List[Dict], kind: str, k: int, seed: int) -> Score:
    s = Score()
    for fold, (train, test) in enumerate(_folds(donors, k, seed)):
        modal = _modal(train)
        marg = _marginals(train)
        rng = random.Random(seed + fold)
        for t in test:
            for dim in DIMS:
                truth = t["attitudes"].get(dim)
                if truth is None:
                    continue
                if kind == "modal":
                    pred = modal.get(dim)
                else:
                    opts, wts = marg[dim]
                    pred = rng.choices(opts, weights=wts, k=1)[0]
                s.add(truth, pred, dim, t)
    return s


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--by-group", action="store_true",
                    help="also print per-race and per-age-band accuracy")
    args = ap.parse_args()

    donors = ada.load_afrobarometer(ada._AFROBAROMETER_PATH)
    print(f"donors: {len(donors)}   folds: {args.folds}   seed: {args.seed}")
    print("scoring dimensions:", ", ".join(DIMS))
    print()

    results: Dict[str, Score] = {}
    for name in ("BASE_modal", "BASE_random"):
        results[name] = evaluate_baseline(
            donors, "modal" if name.endswith("modal") else "random",
            args.folds, args.seed)
    for name, ladder in LADDERS.items():
        results[name] = evaluate(donors, ladder, args.folds, args.seed)

    print("OBJECTIVE — subgroup distribution fidelity (TVD, points; LOWER IS BETTER)")
    print(f"{'ladder':22} {'TVD':>7}   " + " ".join(f"{g[:11]:>12}" for g in GROUPINGS))
    print("-" * 88)
    ranked = sorted(results.items(), key=lambda kv: kv[1].tvd())
    for name, s in ranked:
        cells = " ".join(f"{s.tvd(g):12.1f}" for g in GROUPINGS)
        print(f"{name:22} {s.tvd():7.1f}   {cells}")

    best = ranked[0][0]
    print(f"\nbest on the objective: {best}")

    print("\nDIAGNOSTIC ONLY — per-person accuracy. NOT the objective: assigning every")
    print("persona the modal stance maximises this while giving the whole library one")
    print("identical opinion. Reported to show that trade-off, not to rank ladders.")
    print(f"{'ladder':22} {'accuracy':>9} {'MAE':>7}   top-rung share")
    for name, s in ranked:
        top = f"{s.rungs[0] / sum(s.rungs.values()) * 100:.0f}%" if s.rungs else "-"
        print(f"{name:22} {s.acc:8.1f}% {s.mae:7.3f}   {top}")

    if args.by_group:
        print("\nTVD by race  (the 24% non-African/Black is what race-matching is for)")
        keys = sorted({k[1] for s in results.values() for k in s.true_dist
                       if k[0] == "race"})
        print(f"{'ladder':22} " + " ".join(f"{k[:14]:>16}" for k in keys))
        for name, s in ranked:
            cells = []
            for kk in keys:
                tot = 0.0
                w = 0.0
                for key, truth in s.true_dist.items():
                    if key[0] != "race" or key[1] != kk:
                        continue
                    n = sum(truth.values())
                    if n < 20:
                        continue
                    pred = s.pred_dist.get(key, Counter())
                    m = sum(pred.values()) or 1
                    stances = set(truth) | set(pred)
                    tot += 0.5 * sum(abs(truth[x] / n - pred[x] / m) for x in stances) * n
                    w += n
                cells.append(f"{tot / w * 100:16.1f}" if w else f"{'-':>16}")
            print(f"{name:22} " + " ".join(cells))

    print("\nCAVEAT: test donors are Afrobarometer respondents, not QLFS skeletons — "
          "their demographic mix differs from the library's. This ranks LADDERS, "
          "not final library quality.")


if __name__ == "__main__":
    main()
