"""Map Afrobarometer R9 South Africa variables to their R10 counterparts.

R10 renumbered many questions (R9's Q6A and Q46I have no R10 code, and the
country-specific block moved from `Q80C_SAF` to `Q80C-SAF`), so the backtest
cannot assume codes line up. This builds the crosswalk once, from two signals:

1. the answer-option set must match (strong, but shared across scale-mates), and
2. the R9 variable label must overlap the R10 question wording (the tie-breaker).

Output must be reviewed by hand before use — `confident` is a heuristic, not proof of semantic equivalence.

Usage:
    python backend/scripts/build_r10_crosswalk.py [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pyreadstat

_ROOT = Path(__file__).resolve().parents[1]
_R9 = _ROOT / "data" / "microdata" / "attitudes" / "afrobarometer_r9_sa.sav"
_R10 = _ROOT / "data" / "microdata" / "attitudes" / "afrobarometer_r10_sa_toplines.json"
_OUT = _ROOT / "data" / "microdata" / "attitudes" / "r9_r10_crosswalk.json"

# Codes that carry no opinion: dropped before comparing option sets.
_NON_SUBSTANTIVE = {
    "missing",
    "refused",
    "refused to answer",
    "other",
    "not asked in this country",
}
_STOP = {
    "the", "a", "an", "of", "to", "in", "this", "that", "is", "are", "you",
    "your", "how", "what", "do", "does", "or", "and", "for", "it", "with",
    "would", "say", "about", "on", "be", "if", "have", "has", "any", "at",
    "not", "no", "yes", "please", "following", "each", "them", "their",
}


# A floor only: short labels such as Performance: President score 0.5.
_WORDING_FLOOR = 0.30


def _norm(text: str) -> str:
    text = text.replace("�", "'").replace("’", "'").lower().strip()
    return re.sub(r"[^a-z0-9' ]+", " ", text).strip()


def _is_dk(label: str) -> bool:
    n = _norm(label)
    return n in _NON_SUBSTANTIVE or n.startswith("don't know") or n.startswith("dont know")


def _options(labels: list[str]) -> tuple[str, ...]:
    return tuple(sorted({_norm(x) for x in labels if not _is_dk(x)}))


def _words(text: str) -> set[str]:
    return {w for w in _norm(text).split() if w not in _STOP and len(w) > 2}


def _overlap(a: set[str], b: set[str]) -> float:
    if not a:
        return 0.0
    return len(a & b) / len(a)


def build() -> dict:
    _, meta = pyreadstat.read_sav(str(_R9), metadataonly=True)
    r10 = json.loads(_R10.read_text(encoding="utf-8"))["questions"]

    r10_index = [
        (code, _options(list(q["rows"])), _words(q["text"]))
        for code, q in r10.items()
    ]

    rows = []
    for code in meta.column_names:
        value_labels = meta.variable_value_labels.get(code)
        if not value_labels:
            continue
        r9_opts = _options([str(v) for v in value_labels.values()])
        if len(r9_opts) < 2:
            continue
        label = meta.column_names_to_labels.get(code) or code
        # strip the leading "Q4a. " restatement of the code
        label_words = _words(re.sub(r"^q\d+[a-z0-9_]*\.\s*", "", label, flags=re.I))

        scored = [
            (round(_overlap(label_words, text_words), 3), r10_code)
            for r10_code, opts, text_words in r10_index
            if opts == r9_opts
        ]
        scored.sort(reverse=True)
        best = scored[0] if scored else None
        runner = scored[1][0] if len(scored) > 1 else 0.0
        rows.append(
            {
                "r9": code,
                "r9_label": label,
                "r10": best[1] if best else None,
                "score": best[0] if best else 0.0,
                "wording_overlap": best[0] if best else 0.0,
                "wording_floor": _WORDING_FLOOR,
                "candidates": len(scored),
                # unique option-set match, or a clear win over the runner-up
                "confident": bool(best) and best[0] >= _WORDING_FLOOR
                and (len(scored) == 1 or best[0] - runner >= 0.25),
                "alternates": [c for _, c in scored[1:6]],
            }
        )
    return {
        "note": "R9 .sav variables mapped to R10 summary-of-results codes. Review non-confident rows by hand.",
        "mappings": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=_OUT)
    args = ap.parse_args()
    before = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else None
    payload = build()
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    rows = payload["mappings"]
    if before:
        old = {r["r9"]: r for r in before["mappings"]}
        changed = [{"r9": r["r9"], "r10": r["r10"],
                    "before": old[r["r9"]]["confident"], "after": r["confident"],
                    "wording_overlap": r["wording_overlap"], "r9_label": r["r9_label"]}
                   for r in rows if r["r9"] in old and old[r["r9"]]["confident"] != r["confident"]]
        audit = {"before_confident": sum(r["confident"] for r in old.values()),
                 "after_confident": sum(r["confident"] for r in rows), "changed": changed}
        audit_path = _ROOT / "scripts" / "out" / "r10_crosswalk_changes.json"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        # Preserve the original before/after evidence on subsequent identical builds.
        if changed or not audit_path.exists():
            audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
        print(json.dumps(audit, indent=2))
    matched = [r for r in rows if r["r10"]]
    confident = [r for r in matched if r["confident"]]
    print(f"{len(rows)} R9 variables | {len(matched)} matched | {len(confident)} confident -> {args.out}")


if __name__ == "__main__":
    main()
