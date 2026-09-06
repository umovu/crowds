"""Model-free realism diagnostics. Does not fuse, edit, or generate personas.

Usage: python backend/scripts/check_r10_realism.py
Outputs r10_identical_people.json and r10_identical_people.md, consumed by
R10_BACKTEST_RESULTS.md. Full-key in-sample eta-squared is descriptive, not
predictive: singletons can make it equal one for arbitrary answers.
"""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
import pyreadstat
import attitude_donor_adapter as ada
from attitude_fuser import _skeleton_join_view

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scripts" / "out"
KEYS = ("race", "gender", "province", "education_band", "employment_status", "age_band")


def explained_variance(values, weights, groups):
    """Weighted between-group / total sum of squares; undefined if constant."""
    values, weights = np.asarray(values, float), np.asarray(weights, float)
    if not len(values):
        return None
    if not np.all(np.isfinite(values)) or not np.all(np.isfinite(weights)) or np.any(weights <= 0):
        raise ValueError("finite observations and positive weights required")
    mean = np.average(values, weights=weights)
    total = np.sum(weights * (values - mean) ** 2)
    if total < 1e-12:
        return None
    cells = defaultdict(list)
    for i, key in enumerate(groups):
        cells[key].append(i)
    between = sum(weights[ix].sum() * (np.average(values[ix], weights=weights[ix]) - mean) ** 2
                  for ix in cells.values())
    return float(between / total)


def describe(values, weights, groups):
    counts = Counter(groups)
    eta = explained_variance(values, weights, groups)
    repeated = [i for i, key in enumerate(groups) if counts[key] > 1]
    # Fixed seed; shows how much high-cardinality grouping explains by chance.
    # Descriptive sensitivity check, not a survey-design-adjusted significance test.
    rng = np.random.default_rng(20260906)
    nulls = [explained_variance(rng.permutation(values), weights, groups) for _ in range(100)]
    nulls = [v for v in nulls if v is not None]
    return {"n": len(values), "groups": len(counts),
            "singleton_people": sum(n == 1 for n in counts.values()),
            "explained_variance": eta,
            "permuted_mean": float(np.mean(nulls)) if nulls else None,
            "permuted_p95": float(np.quantile(nulls, .95)) if nulls else None,
            "repeated_cell_n": len(repeated),
            "repeated_cell_explained_variance": explained_variance(
                [values[i] for i in repeated], [weights[i] for i in repeated], [groups[i] for i in repeated])}


def r9_view(row, meta):
    age = row.get("Q1")
    return {"race": ada.race_to_canonical(meta.variable_value_labels["Q101"].get(row.get("Q101")), "ab"),
            "gender": {1: "Male", 2: "Female"}.get(row.get("THISINT")),
            "province": ada._AB_REGION_TO_PROVINCE.get(row.get("REGION")),
            "education_band": ada._ab_education_band(row.get("Q94")),
            "employment_status": ada._AB_Q93A_TO_STATUS.get(row.get("Q93A")),
            "age_band": ada.age_to_band(int(age)) if age == age and age >= 15 and age not in ada._AB_MISSING else None}


def main():
    df, meta = pyreadstat.read_sav(str(ROOT / "data/microdata/attitudes/afrobarometer_r9_sa.sav"))
    payload = json.loads((ROOT / "app/data/persona_library/personas.json").read_text(encoding="utf-8"))
    people = payload["personas"] if isinstance(payload, dict) else payload
    items = json.loads((OUT / "r10_item_list.json").read_text(encoding="utf-8"))["items"]
    real, excluded = [], 0
    for _, row in df.iterrows():
        view = r9_view(row, meta)
        w = row.get("withinwt_hh")
        if any(view[k] is None for k in KEYS) or not np.isfinite(w) or w <= 0:
            excluded += 1
            continue
        real.append((row, tuple(view[k] for k in KEYS), float(w)))
    library = []
    for person in people:
        view = _skeleton_join_view(person)
        if any(view[k] is None for k in KEYS):
            continue
        library.append((person, tuple(view[k] for k in KEYS)))
    item_rows = []
    for item in items:
        code = item["r9"]
        substantive = {float(k): v for k, v in item["r9_substantive_codes"].items()}
        observations = [(float(row[code]), w, key) for row, key, w in real if row[code] in substantive]
        values, weights, groups = zip(*observations) if observations else ([], [], [])
        labels = meta.variable_value_labels[code]
        dk_codes = {c for c, label in labels.items() if "know" in label.lower() or "refus" in label.lower()}
        total_weight = float(df["withinwt_hh"].sum())
        dk_weight = float(df.loc[df[code].isin(dk_codes), "withinwt_hh"].sum())
        missing_weight = float(df.loc[~df[code].isin(set(substantive) | dk_codes), "withinwt_hh"].sum())
        item_rows.append({"r9": code, "bucket": item["bucket"],
                          "real": describe(list(values), list(weights), list(groups)),
                          "library": None, "gap": None,
                          "library_reason": "Raw survey item not stored; fused bands/composites cannot reconstruct it.",
                          "r9_dont_know_refusal_pct": dk_weight / total_weight * 100,
                          "r9_other_missing_pct": missing_weight / total_weight * 100})
    shared = []
    decoded = [(ada._decode_ab_attitudes(row) or {}, key, w) for row, key, w in real]
    for dim, vocab in ada.ATTITUDE_VOCAB.items():
        real_obs = [(vocab.index(a[dim]), w, key) for a, key, w in decoded if a.get(dim) in vocab]
        lib_obs = []
        missing = 0
        for p, key in library:
            attitudes = {a["topic"]: a["stance"] for a in p.get("attitudes", [])}
            if attitudes.get(dim) in vocab:
                lib_obs.append((vocab.index(attitudes[dim]), 1.0, key))
            else:
                missing += 1
        a = describe(*[list(v) for v in zip(*real_obs)])
        b = describe(*[list(v) for v in zip(*lib_obs)])
        gap = b["explained_variance"] - a["explained_variance"] if a["explained_variance"] is not None and b["explained_variance"] is not None else None
        shared.append({"dimension": dim, "real": a, "library": b, "gap": gap,
                       "library_missing_pct": 100 * missing / len(library)})
    result = {"r9_total": len(df), "r9_demographic_excluded": excluded,
              "library_total": len(people), "library_demographic_excluded": len(people)-len(library),
              "keys": KEYS, "items": item_rows, "shared_dimensions": shared,
              "status": "INCONCLUSIVE: held-out library answers absent; raw group statistic is inflated by sparse cells",
              "paid_run_ready": False,
              "notes": ["Shared dimensions compare the same decoded bands; not held-out-item results.",
                        "R9 uses withinwt_hh; stored library uses equal weights for this descriptive diagnostic.",
                        "Missing fused attitudes are not a measured refusal rate; fusion fills missing donor answers.",
                        "Existing _footer forces closest option and old scenarios omit opt-outs. It has not been changed.",
                        "R10 frozen scenarios preserve all published options including opt-outs; this differs from the older scenarios.",
                        "Permutation sensitivity is not cross-validation or a survey-design significance test."]}
    (OUT / "r10_identical_people.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = ["# Identical-people diagnostic", "", result["status"], "",
             f"R9: {len(df)} respondents, {excluded} excluded for missing group keys/weight. Library: {len(people)}, {len(people)-len(library)} excluded.",
             "", "Raw group variance is descriptive. Sparse cells explain variation even after answers are shuffled.",
             "The shared dimensions below are a separate comparison; they cannot fill the absent held-out answers.", "",
             "| Shared dimension | R9 explained % | Library explained % | Gap pp | R9 shuffled % | Library shuffled % | R9 singleton people | Library singleton people |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for x in shared:
        a,b=x["real"],x["library"]
        lines.append(f"| {x['dimension']} | {100*a['explained_variance']:.2f} | {100*b['explained_variance']:.2f} | {100*x['gap']:+.2f} | {100*a['permuted_mean']:.2f} | {100*b['permuted_mean']:.2f} | {a['singleton_people']} | {b['singleton_people']} |")
    lines += ["", "| Item | Set | R9 explained % | R9 don't-know/refusal % | Library / gap |", "|---|---|---:|---:|---|"]
    for x in item_rows:
        lines.append(f"| {x['r9']} | {x['bucket']} | {100*x['real']['explained_variance']:.2f} | {x['r9_dont_know_refusal_pct']:.2f} | unavailable |")
    lines += ["", *["- " + n for n in result["notes"]], "", "Paid run held: this diagnostic cannot certify the plan's gate. No personas changed."]
    text = "\n".join(lines) + "\n"
    (OUT / "r10_identical_people.md").write_text(text, encoding="utf-8")
    print(text)



def prediction_weights(views, weights, ladder, min_peers=5, min_effective=3):
    """LOO demographic mean operator. Diagonal is zero, including the baseline.

    Rungs depend only on demographics, response availability and weights, never
    answer values. Tiny cells back off instead of predicting themselves.
    """
    weights = np.asarray(weights, float)
    n = len(views)
    if n < 2 or len(weights) != n or not np.all(np.isfinite(weights)) or np.any(weights <= 0):
        raise ValueError("At least two people and finite positive aligned weights required")
    if not ladder or ladder[-1] != [] or min_peers < 1 or min_effective < 1:
        raise ValueError("Require a population fallback and positive peer thresholds")
    matrix = np.zeros((n, n), float)
    baseline = np.tile(weights, (n, 1))
    np.fill_diagonal(baseline, 0)
    baseline /= baseline.sum(axis=1, keepdims=True)
    rungs = np.full(n, len(ladder)-1, int)
    unresolved = set(range(n))
    for rung, keys in enumerate(ladder[:-1]):
        groups = defaultdict(list)
        for i, view in enumerate(views):
            groups[tuple(view[k] for k in keys)].append(i)
        for members in groups.values():
            if len(members)-1 < min_peers:
                continue
            for i in members:
                if i not in unresolved:
                    continue
                others = np.array([j for j in members if j != i])
                w = weights[others]
                if w.sum()**2 / np.dot(w, w) < min_effective:
                    continue
                matrix[i, others] = w / w.sum()
                rungs[i] = rung
                unresolved.remove(i)
    for i in unresolved:
        matrix[i] = baseline[i]
    return matrix, baseline, rungs


def heldout_reduction(values, weights, model, baseline, categories):
    """Brier error reduction against the same held-out population baseline.

    This is a diagnostic of demographic predictability, not overall realism.
    Negative reduction means demographics predict worse than the baseline.
    """
    values = np.asarray(values)
    weights = np.asarray(weights, float)
    if (len(values) != len(weights) or model.shape != (len(values), len(values))
            or baseline.shape != model.shape or np.any(values < 0)
            or np.any(values >= categories) or np.any(values != values.astype(int))):
        raise ValueError("Aligned categorical observations and operators required")
    truth = np.eye(categories)[values.astype(int)]
    predictions = model @ truth
    base_predictions = baseline @ truth
    loss = float(np.average(np.sum((truth-predictions)**2, axis=1), weights=weights))
    base_loss = float(np.average(np.sum((truth-base_predictions)**2, axis=1), weights=weights))
    return {"reduction": 1-loss/base_loss if base_loss > 1e-12 else None,
            "brier_loss": loss, "baseline_loss": base_loss}


def balance_weights(library_views, real_views, real_weights, keys, tolerance=1e-7, iterations=1000):
    """Rake marginal demographics only; fail clearly on absent support.

    These are diagnostic complete-case R9 targets, not national R10 weights.
    """
    w = np.ones(len(library_views), float)
    rw = np.asarray(real_weights, float)
    targets = {}
    masks = {}
    unsupported = []
    for key in keys:
        targets[key] = {}
        for category in sorted({v[key] for v in real_views} | {v[key] for v in library_views}):
            target = float(rw[[v[key] == category for v in real_views]].sum() / rw.sum())
            mask = np.array([v[key] == category for v in library_views])
            if target > 0 and not mask.any():
                unsupported.append({"key": key, "category": category, "target": target})
            if mask.any() and target == 0:
                unsupported.append({"key": key, "category": category, "target": 0,
                                    "reason": "Library-only category would get zero weight"})
            targets[key][category] = target
            masks[key, category] = mask
    if unsupported:
        return None, {"status": "unsupported categories", "unsupported": unsupported}
    error = float("inf")
    for iteration in range(iterations):
        for key in keys:
            for category, target in targets[key].items():
                mask = masks[key, category]
                if target:
                    current = w[mask].sum()/w.sum()
                    w[mask] *= target/current
            w *= len(w)/w.sum()
        error = max(abs(w[masks[k,c]].sum()/w.sum()-target)
                    for k in keys for c,target in targets[k].items())
        if error <= tolerance:
            return w, {"status": "converged", "iterations": iteration+1, "max_marginal_error": error,
                       "effective_n": float(w.sum()**2/np.dot(w,w)), "min_weight": float(w.min()),
                       "max_weight": float(w.max()), "targets": targets}
    return None, {"status": "did not converge", "iterations": iterations, "max_marginal_error": error}


def repaired_main():
    import hashlib
    import sys
    from attitude_fuser import _BACKOFF_LADDER
    method_path = OUT / "REALISM_REPAIR_METHOD.json"
    method = json.loads(method_path.read_text(encoding="utf-8"))
    sav = ROOT / "data/microdata/attitudes/afrobarometer_r9_sa.sav"
    lib_path = ROOT / "app/data/persona_library/personas.json"
    locked = [OUT / "r10_item_list.json", OUT / "r10_ask_scenarios.json"]
    inputs = [method_path, sav, lib_path, *locked]
    before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    df, meta = pyreadstat.read_sav(str(sav))
    payload = json.loads(lib_path.read_text(encoding="utf-8"))
    people = payload["personas"] if isinstance(payload, dict) else payload
    real, library = [], []
    exclusions = {"real": Counter(), "library": Counter()}
    provenance = Counter()
    for _, row in df.iterrows():
        view = r9_view(row, meta)
        missing = [k for k in KEYS if view[k] is None]
        if not np.isfinite(row["withinwt_hh"]) or row["withinwt_hh"] <= 0:
            missing.append("weight")
        if missing:
            exclusions["real"][" + ".join(missing)] += 1
            continue
        real.append((view, ada._decode_ab_attitudes(row) or {}, float(row["withinwt_hh"])))
    for person in people:
        view = _skeleton_join_view(person)
        missing = [k for k in KEYS if view[k] is None]
        for a in person.get("attitudes", []):
            provenance[a.get("match_quality", "unrecorded")] += 1
        if missing:
            exclusions["library"][" + ".join(missing)] += 1
            continue
        library.append((view, {a["topic"]: a["stance"] for a in person.get("attitudes", [])}, 1.0))
    adjusted, balance = balance_weights([x[0] for x in library], [x[0] for x in real],
                                         [x[2] for x in real], KEYS,
                                         method["balance_tolerance"], method["balance_max_iterations"])
    def operators(views, weights):
        return prediction_weights(views, weights, _BACKOFF_LADDER,
                                  method["minimum_other_people"], method["minimum_training_effective_n"])
    rows = []
    for dim_index, (dim, vocab) in enumerate(ada.ATTITUDE_VOCAB.items()):
        rr = [x for x in real if x[1].get(dim) in vocab]
        ll = [(i,x) for i,x in enumerate(library) if x[1].get(dim) in vocab]
        rv, ry, rw = [x[0] for x in rr], [vocab.index(x[1][dim]) for x in rr], np.array([x[2] for x in rr])
        lv, ly = [x[0] for _,x in ll], [vocab.index(x[1][dim]) for _,x in ll]
        if len(ly) < 2 or len(ry) < len(ly):
            rows.append({"dimension":dim, "status":"insufficient sample"})
            continue
        rm, rb, _ = operators(rv, rw)
        real_result = heldout_reduction(ry, rw, rm, rb, len(vocab))
        del rm, rb
        raw_weights = np.ones(len(ly))
        lm, lb, rung = operators(lv, raw_weights)
        raw = heldout_reduction(ly, raw_weights, lm, lb, len(vocab))
        rng = np.random.default_rng(method["seed"]+dim_index)
        reference = []
        for _ in range(method["size_matched_repeats"]):
            ix = rng.choice(len(ry), len(ly), replace=False)
            sm, sb, _ = operators([rv[i] for i in ix], rw[ix])
            score = heldout_reduction(np.asarray(ry)[ix], rw[ix], sm, sb, len(vocab))["reduction"]
            if score is not None:
                reference.append(score)
        sensitivity = {"n":len(reference), "median":float(np.median(reference)),
                       "p05":float(np.quantile(reference,.05)), "p95":float(np.quantile(reference,.95))} if reference else None
        aw = adjusted[[i for i,_ in ll]] if adjusted is not None else None
        adj, null, coverage, effective, rung_counts = None, [], None, None, None
        if aw is not None:
            am, ab, ar = operators(lv, aw)
            adj = heldout_reduction(ly, aw, am, ab, len(vocab))
            coverage = float(aw[ar < len(_BACKOFF_LADDER)-1].sum()/aw.sum())
            effective = float(aw.sum()**2/np.dot(aw,aw))
            rung_counts = dict(Counter(map(int,ar)))
            for _ in range(method["shuffle_repeats"]):
                score = heldout_reduction(rng.permutation(ly), aw, am, ab, len(vocab))["reduction"]
                if score is not None:
                    null.append(score)
        warning = None
        if adj is not None and adj["reduction"] is not None and sensitivity and null:
            rule = method["warning_rule"]
            adequate = coverage >= rule["minimum_nonpopulation_weighted_share"] and effective/len(ly) >= rule["minimum_adjusted_effective_n_share"]
            warning = bool(adj["reduction"]-sensitivity["median"] >= rule["adjusted_excess_over_size_matched_real_median_pp"]/100
                           and adj["reduction"] > sensitivity["p95"]
                           and adj["reduction"] > np.quantile(null,.95)) if adequate else None
        rows.append({"dimension": dim, "real_n":len(ry), "library_n":len(ly),
                     "real_missing_band_n":len(real)-len(ry), "library_missing_band_n":len(library)-len(ly),
                     "real_missing_band_weighted_pct":100*(1-rw.sum()/sum(x[2] for x in real)),
                     "real_full":real_result, "library_raw":raw, "library_balanced":adj,
                     "real_size_matched":sensitivity, "balanced_shuffled_p95":float(np.quantile(null,.95)) if null else None,
                     "nonpopulation_weighted_share":coverage, "balanced_effective_n":effective,
                     "balanced_rung_counts":rung_counts, "investigate":warning})
    after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    assert before == after, "An input changed during this run"
    result = {"method_sha256":before[str(method_path.relative_to(ROOT))], "input_sha256":before,
              "inputs_unchanged":True, "real_total":len(df), "library_total":len(people),
              "real_usable":len(real), "library_usable":len(library), "exclusions":exclusions,
              "balance":balance, "stored_attitude_provenance_counts_all_personas":provenance,
              "ladder":_BACKOFF_LADDER, "dimensions":rows, "model_calls":0,
              "warning_count":sum(x.get("investigate") is True for x in rows),
              "inconclusive_count":sum(x.get("investigate") is None for x in rows),
              "interpretation":"Exploratory demographic-predictability warning, not accuracy or proof of stereotyping. No paid-run gate granted."}
    (OUT / "realism_repair_results.json").write_text(json.dumps(result, indent=2),encoding="utf-8")
    def pp(value):
        return "n/a" if value is None else f"{100*value:.2f}"
    lines = ["# Realism test repair: proof of work", "",
             "## What changed", "",
             "The repaired test hides each person's answer and predicts its category using other people only.",
             "It compares the same stored attitude bands on both sides. A tiny group cannot predict itself.",
             "This measures how strongly attitudes follow demographics, not whether simulated answers are accurate.", "",
             "## Rules fixed before results", "",
             f"Method SHA256: `{result['method_sha256']}`.",
             "See [REALISM_REPAIR_METHOD.json](REALISM_REPAIR_METHOD.json) for the full predeclared method.",
             "At least five other observed people and effective training size three are required for a demographic group.",
             "Otherwise the test tries the next shipping matching rung, ultimately falling back to the other-person population.",
             "Both the group prediction and population baseline exclude the person being tested.",
             "Error is the sum of squared differences between predicted category probabilities and the actual category (Brier loss).",
             "The table shows percentage error reduction versus the population baseline; negative values mean worse predictions.",
             "A warning needs a balanced-library reduction at least 10 points above the size-matched real median, above its 95th percentile,",
             "and above the shuffled-library 95th percentile. It also needs 50% nonpopulation prediction coverage and effective sample size 25% of the library.",
             "These are predeclared investigation rules, not a validated safety threshold or significance test.", "",
             "## What was measured", "",
             f"Real: {len(df)} total, {len(real)} with usable keys. Library: {len(people)} total, {len(library)} with usable keys.",
             f"Excluded-key counts: `{json.dumps(exclusions)}`.",
             "All 15 existing attitude dimensions were included; none was dropped because of its result.",
             "R9 uses its survey weights. Raw library uses equal weights. Balanced library matches the six R9 demographic margins.",
             "Each dimension also uses 50 same-size R9 subsets drawn uniformly without replacement, keeping their survey weights.",
             "Subset ranges describe sensitivity to sample size and selection; they are not confidence intervals.",
             "These targets describe complete-key R9 respondents, not the entire country or R10.",
             f"Weight fitting: **{balance['status']}**. Effective library size: {balance.get('effective_n', 'n/a')}.", "",
             "## Results", "",
             "| Attitude | Real full % | Real same-size median % | Real subset 5th-95th % | Library raw % | Library balanced % | Warning |",
             "|---|---:|---:|---:|---:|---:|---|"]
    for x in rows:
        if "real_full" not in x:
            lines.append(f"| {x['dimension']} | n/a | n/a | n/a | n/a | n/a | insufficient data |")
            continue
        ref=x["real_size_matched"]
        lines.append(f"| {x['dimension']} | {pp(x['real_full']['reduction'])} | {pp(ref['median']) if ref else 'n/a'} | {pp(ref['p05'])+' to '+pp(ref['p95']) if ref else 'n/a'} | {pp(x['library_raw']['reduction'])} | {pp(x['library_balanced']['reduction']) if x['library_balanced'] else 'n/a'} | {'investigate' if x['investigate'] else 'inconclusive' if x['investigate'] is None else 'below warning rule'} |")
    lines += ["", f"**{result['warning_count']} of {len(rows)} dimensions met the warning rule; {result['inconclusive_count']} were inconclusive.**", "",
              "Below the warning rule is not proof of realism. A warning does not identify which mechanism caused the pattern.",
              "## Missing opinions", "",
              f"Stored attitude source-quality tags across all personas: `{json.dumps(provenance)}`.",
              "Per-dimension missing-band counts and real weighted missing rates are in the results JSON.",
              "Population-draw/fallback tags show recorded filling, but cannot recover each original refusal or don't-know response.",
              "Some composites remain populated when one source answer is missing; missing-band rates are not raw refusal rates.", "",
              "## Limits and next step", "",
              "The repair removes self-prediction and the singleton inflation mechanism. Tests cover singleton-only data and true group patterns.",
              "It uses the shipping matching ladder, which was previously tuned on R9; these results are not a fresh external validation.",
              "Raking fixes marginal balance only, not all demographic combinations, omitted traits, or shared-donor dependence.",
              "Repeated donor use may make persona answers dependent; stable donor identifiers are not available here to split by donor.",
              "Shuffled references are sensitivity checks, not formal multiple-comparison-adjusted significance tests.",
              "Missing demographic keys limit coverage. No population-wide claim is made for excluded people.",
              "Investigate flagged dimensions and stored matching provenance before changing donor assignments. No automatic fixes were applied.",
              "No paid model call is authorised by this diagnostic; the frozen R10 questions remain a separate, unrun answer test.", "",
              "## Evidence", "",
              "[Full machine-readable results](realism_repair_results.json), including input hashes, coverage, missingness and sample weights.",
              "[Exact commands and terminal output](realism_repair_terminal.txt). Tests and source line references are appended after verification.",
              "Input hashes were compared before/after: persona library, survey file, frozen question files and method were unchanged.",
              "Old r10_identical_people outputs were preserved. Model calls: **0**. No personas generated, edited, or re-fused."]
    (OUT / "REALISM_REPAIR_POW.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines[lines.index("## Results"):lines.index("## Missing opinions")]))
    print(f"Method SHA256: {result['method_sha256']}")
    print(f"Usable rows: real={len(real)}/{len(df)}, library={len(library)}/{len(people)}; balance={balance['status']}")
    print("Input hashes unchanged; model calls=0")
    print("POW: backend/scripts/out/REALISM_REPAIR_POW.md")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repaired", action="store_true", help="Run the predeclared held-out-band diagnostic; preserve original outputs")
    args = parser.parse_args()
    repaired_main() if args.repaired else main()
