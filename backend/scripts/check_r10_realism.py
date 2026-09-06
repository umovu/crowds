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


if __name__ == "__main__":
    main()
