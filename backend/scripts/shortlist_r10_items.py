"""Shortlist candidate items for the R9 -> R10 backtest.

Ranks every confidently-crosswalked question by how much South Africa actually
moved between 2022 (R9 microdata, weighted) and 2025 (R10 toplines). Flat
questions are useless as a test: a rock scores well on them.

Each candidate is tagged:
  seen      - the question feeds an attitude dimension already fused onto
              personas, so answering it is recall, not prediction
  held_out  - no imported dimension uses it. This is the real test.

Output is a shortlist for human sign-off, not the final item list.

Usage:
    python backend/scripts/shortlist_r10_items.py [--top N] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pyreadstat

_ROOT = Path(__file__).resolve().parents[1]
_DIR = _ROOT / "data" / "microdata" / "attitudes"
_R9 = _DIR / "afrobarometer_r9_sa.sav"
_R10 = _DIR / "afrobarometer_r10_sa_toplines.json"
_CROSSWALK = _DIR / "r9_r10_crosswalk.json"
_OUT = _ROOT / "scripts" / "out" / "r10_shortlist.json"

_WEIGHT = "withinwt_hh"
_MISSING = {-1.0, 8.0, 9.0, 98.0, 99.0, 998.0, 999.0}

# R9 columns consumed by attitude/circumstance fusion
# (attitude_donor_adapter._decode_ab_attitudes / _decode_ab_circumstances).
_IMPORTED = {
    "Q37A", "Q37D", "Q4A", "Q4B", "Q46I", "Q46L", "Q7A", "Q7B", "Q46H", "Q46G",
    "Q37O_SAF", "Q34B", "Q36A", "Q46F", "Q82C_SAF", "Q80C_SAF", "Q38J", "Q86A",
    "Q67A", "Q72A", "Q72D",
    "Q6A", "Q6B", "Q6C", "Q6D", "Q6E",
    "Q90B", "Q90C", "Q90D", "Q90E", "Q90I", "Q92B", "Q93C",
    "Q74A", "Q74B", "Q74D", "Q74E",
}


def _norm(text: str) -> str:
    text = str(text).replace("�", "'").replace("’", "'").lower().strip()
    return re.sub(r"[^a-z0-9' ]+", " ", text).strip()


def _r9_distribution(df, meta, code: str) -> dict[str, float]:
    """Weighted percentage per substantive answer label, renormalised to 100."""
    labels = meta.variable_value_labels[code]
    weights = df[_WEIGHT]
    out: dict[str, float] = {}
    for value, label in labels.items():
        if value in _MISSING:
            continue
        mask = df[code] == value
        out[_norm(label)] = float(weights[mask].sum())
    total = sum(out.values())
    if total <= 0:
        return {}
    return {k: round(100.0 * v / total, 2) for k, v in out.items()}


def _r10_distribution(question: dict) -> dict[str, float]:
    i = question["columns"].index("Total")
    raw = {
        _norm(label): (cells[i] or 0.0)
        for label, cells in question["rows"].items()
        if not _norm(label).startswith("don't know")
        and _norm(label) not in {"refused", "refused to answer", "missing"}
    }
    total = sum(raw.values())
    if total <= 0:
        return {}
    return {k: round(100.0 * v / total, 2) for k, v in raw.items()}


def _tvd(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) | set(b)
    return round(sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys) / 2.0, 2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--out", type=Path, default=_OUT)
    args = ap.parse_args()

    df, meta = pyreadstat.read_sav(str(_R9))
    r10 = json.loads(_R10.read_text(encoding="utf-8"))["questions"]
    crosswalk = json.loads(_CROSSWALK.read_text(encoding="utf-8"))["mappings"]

    candidates = []
    for row in crosswalk:
        if not row["confident"] or not row["r10"]:
            continue
        question = r10[row["r10"]]
        if question["suspect"]:
            continue
        r9_dist = _r9_distribution(df, meta, row["r9"])
        r10_dist = _r10_distribution(question)
        if not r9_dist or not r10_dist:
            continue
        # option sets were matched on normalised labels, so keys should align
        if set(r9_dist) != set(r10_dist):
            continue
        candidates.append(
            {
                "r9": row["r9"],
                "r10": row["r10"],
                "bucket": "seen" if row["r9"] in _IMPORTED else "held_out",
                "question": question["text"],
                "movement_tvd": _tvd(r9_dist, r10_dist),
                "r9_truth": r9_dist,
                "r10_truth": r10_dist,
            }
        )

    # Several R9 variables can land on the same R10 code (scale-mates the
    # tie-breaker could not separate). Only one of them is the real match, and
    # we cannot tell which, so drop the whole collision rather than guess.
    seen_r10: dict[str, int] = {}
    for c in candidates:
        seen_r10[c["r10"]] = seen_r10.get(c["r10"], 0) + 1
    collisions = {code for code, n in seen_r10.items() if n > 1}
    if collisions:
        print(f"dropping {len(collisions)} ambiguous R10 codes claimed by several R9 variables: {', '.join(sorted(collisions))}")
    candidates = [c for c in candidates if c["r10"] not in collisions]

    candidates.sort(key=lambda c: c["movement_tvd"], reverse=True)
    held_out = [c for c in candidates if c["bucket"] == "held_out"][: args.top]
    seen = [c for c in candidates if c["bucket"] == "seen"][: args.top]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "note": "Ranked by how far the country actually moved 2022 -> 2025. Shortlist only; the final item list must be committed before any model call.",
                "counts": {"all": len(candidates), "held_out": len(held_out), "seen": len(seen)},
                "held_out": held_out,
                "seen": seen,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"{len(candidates)} comparable questions ({len(held_out)} held_out, {len(seen)} seen) -> {args.out}")
    for c in held_out[:15]:
        print(f"  {c['movement_tvd']:5.1f}  {c['r9']:>10} -> {c['r10']:<10} {c['question'][:70]}")


if __name__ == "__main__":
    main()
