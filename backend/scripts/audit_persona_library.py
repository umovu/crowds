"""Audit the persona library against national benchmarks.

Compares the curated library's demographic shape to South Africa's, so we know
where the room is skewed before reading anything into what the room says.

Benchmarks come from the Afrobarometer Round 10 South Africa summary of results
(weighted, n=1,600, fieldwork mid-2025) for gender / location / province /
education / age, and from the R9 microdata for race (R10 reports ethnic group,
not population group).

Usage:
    python backend/scripts/audit_persona_library.py [--out PATH]
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import pyreadstat

_ROOT = Path(__file__).resolve().parents[1]
_LIBRARY = _ROOT / "app" / "data" / "persona_library" / "personas.json"
_R9 = _ROOT / "data" / "microdata" / "attitudes" / "afrobarometer_r9_sa.sav"
_OUT = _ROOT / "scripts" / "out" / "persona_library_audit.md"

# Weighted national shares, R10 summary of results (page 5 and Q1).
NATIONAL = {
    "gender": {"Male": 48.5, "Female": 51.5},
    "location": {"Urban": 71.0, "Rural": 29.0},
    "province": {
        "Eastern Cape": 10.5, "Free State": 5.0, "Gauteng": 27.5,
        "KwaZulu-Natal": 18.5, "Limpopo": 9.2, "Mpumalanga": 8.0,
        "North West": 6.2, "Northern Cape": 2.0, "Western Cape": 13.0,
    },
    "education": {
        "No formal education": 3.3, "Primary": 7.8,
        "Secondary": 52.6, "Post-secondary": 36.1,
    },
    "age": {
        "18-25": 19.1, "26-35": 23.9, "36-45": 27.0,
        "46-55": 15.5, "56-65": 9.8, "65+": 4.7,
    },
}

EDUCATION_MAP = {
    "No schooling": "No formal education",
    "None": "No formal education",
    "Less than primary completed": "Primary",
    "Primary": "Primary",
    "Primary completed": "Primary",
    "Secondary not completed": "Secondary",
    "Secondary completed": "Secondary",
    "Tertiary": "Post-secondary",
}

# The library splits rural into traditional-authority areas and farms; the
# survey reports a single rural share.
LOCATION_MAP = {"Urban": "Urban", "Traditional": "Rural", "Farms": "Rural"}

# The library and Afrobarometer name the same population groups differently.
RACE_MAP = {
    "African/Black": "Black / African",
    "White": "White / European",
    "Coloured": "Coloured / Mixed race",
    "Indian/Asian": "South Asian (Indian, Pakistani, etc.)",
}


def _age_band(age) -> str | None:
    if not isinstance(age, (int, float)):
        return None
    for hi, band in ((25, "18-25"), (35, "26-35"), (45, "36-45"), (55, "46-55"), (65, "56-65")):
        if age <= hi:
            return band
    return "65+"


def _race_benchmark() -> dict[str, float]:
    """Weighted population-group shares from R9 (R10 publishes ethnicity instead)."""
    df, meta = pyreadstat.read_sav(str(_R9))
    labels = meta.variable_value_labels.get("Q101") or {}
    weights = df["withinwt_hh"]
    out: dict[str, float] = {}
    for value, label in labels.items():
        if value in {-1.0, 8.0, 9.0, 98.0, 99.0}:
            continue
        out[str(label).strip()] = float(weights[df["Q101"] == value].sum())
    total = sum(out.values())
    return {k: round(100.0 * v / total, 1) for k, v in out.items() if v}


def _shares(values: list) -> dict[str, float]:
    counts = collections.Counter(v for v in values if v)
    total = sum(counts.values())
    return {k: 100.0 * v / total for k, v in counts.items()}, total


def _table(name: str, observed: dict[str, float], target: dict[str, float], n: int) -> list[str]:
    lines = [f"### {name}", "", f"| Category | Library | Country | Weight | Gap |", "|---|---|---|---|---|"]
    worst = 0.0
    for key in sorted(set(observed) | set(target), key=lambda k: -target.get(k, 0.0)):
        lib = observed.get(key, 0.0)
        nat = target.get(key)
        if nat is None:
            lines.append(f"| {key} | {lib:.1f}% | not benchmarked | - | - |")
            continue
        weight = f"{nat / lib:.2f}" if lib else "n/a"
        gap = nat - lib
        worst = max(worst, abs(gap))
        flag = " **" if abs(gap) >= 5 else ""
        lines.append(f"| {key} | {lib:.1f}% | {nat:.1f}% | {weight} | {gap:+.1f}{flag} |")
    lines += ["", f"_n = {n}. Largest gap {worst:.1f} points._", ""]
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=_OUT)
    args = ap.parse_args()

    data = json.loads(_LIBRARY.read_text(encoding="utf-8"))
    people = data.get("personas", data) if isinstance(data, dict) else data

    axes = {
        "Gender": ([p.get("gender") for p in people], NATIONAL["gender"]),
        "Urban / rural": ([LOCATION_MAP.get(p.get("geotype")) for p in people], NATIONAL["location"]),
        "Province": ([p.get("province") for p in people], NATIONAL["province"]),
        "Education": ([EDUCATION_MAP.get(p.get("education")) for p in people], NATIONAL["education"]),
        "Age": ([_age_band(p.get("age")) for p in people], NATIONAL["age"]),
        "Race": ([RACE_MAP.get(p.get("race")) for p in people], _race_benchmark()),
    }

    lines = [
        "# Persona library audit",
        "",
        f"{len(people)} personas against national benchmarks "
        "(Afrobarometer R10 South Africa, weighted, mid-2025; race from R9 microdata).",
        "",
        "`Weight` is what a persona in that category would have to count for, to bring "
        "the library back to national. Gaps of 5 points or more are flagged.",
        "",
    ]
    for name, (values, target) in axes.items():
        observed, n = _shares(values)
        lines += _table(name, observed, target, n)

    quality = collections.Counter(p.get("attitude_match_quality") for p in people)
    lines += ["### Attitude match quality", "", "| Quality | Count | Share |", "|---|---|---|"]
    for key, count in quality.most_common():
        lines.append(f"| {key} | {count} | {100.0 * count / len(people):.1f}% |")
    lines.append("")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
