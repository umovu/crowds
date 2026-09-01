"""Deterministic objection-type classifier — the scoring path for the benchmark.

Scoring is LLM-free: every case's direction reading goes through this script, so
the comparison is assertable. A thin CLI over app.services.objections, so the
benchmark and the product score objections with one implementation.

Usage:
    python classify_objections.py <session_dir_or_json> [--group-by seg|budget] [--conditions]

Input:
  - a panel session dir: backend/uploads/panel_sessions/<id>, reads
    rounds/round_*.json -> result.results[].response
  - a JSON file: list of {"name", "segment", "response"} records
    (the segment-contrast fixture is one such file)

Output:
  - per-cast percentage raising each objection type (markdown table)
  - with --conditions: per-cast condition-framed vs dealbreaker-framed counts
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional

# Load the classifier BY PATH, not as `app.services.objections`: importing the
# package would run app/services/__init__.py, which pulls AgentSociety2 and dies
# without AGENTSOCIETY_LLM_API_KEY. This script must stay runnable with no key
# and no model — that is the whole point of it being the scoring path.
_OBJECTIONS_PY = os.path.join(
    os.path.dirname(__file__), "..", "app", "services", "objections.py")
_spec = importlib.util.spec_from_file_location(
    "objections_cli", os.path.abspath(_OBJECTIONS_PY))
_objections = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_objections)

OBJECTION_TYPES = _objections.OBJECTION_TYPES
classify_text = _objections.classify
is_condition = _objections.is_condition


def extract_interviews(source: str) -> List[Dict[str, str]]:
    """Read a panel-session dir or a JSON file of interview records.

    Returns records with keys: name, segment, response (+ optional
    reported_objections carried through from fixture files).
    """
    if os.path.isdir(source):
        records: List[Dict[str, str]] = []
        rounds_dir = os.path.join(source, "rounds")
        if not os.path.isdir(rounds_dir):
            raise ValueError(f"no rounds/ dir in {source}")
        for fname in sorted(os.listdir(rounds_dir)):
            if not fname.startswith("round_"):
                continue
            with open(os.path.join(rounds_dir, fname), encoding="utf-8") as fh:
                data = json.load(fh)
            results = ((data.get("result") or {}).get("results")) or []
            for r in results:
                response = r.get("response") or ""
                if not response:
                    continue
                records.append({
                    "name": r.get("agent_name") or str(r.get("agent_id")),
                    "segment": r.get("budget_tier") or "all",
                    "response": response,
                })
        return records
    with open(source, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = list(data.values())
    return [{"name": r.get("name", ""), "segment": r.get("segment") or r.get("budget_tier") or "all",
             "response": r.get("response", ""), **{k: v for k, v in r.items()
             if k in ("reported_objections",)}} for r in data]


def per_cast_percentages(records: List[Dict[str, str]]) -> Dict[str, Dict[str, float]]:
    """% of each cast raising each objection type. Report-table shape."""
    by_cast: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for r in records:
        by_cast[r["segment"]].append(r)
    out: Dict[str, Dict[str, float]] = {}
    for cast, rs in by_cast.items():
        counts = {t: 0 for t in OBJECTION_TYPES}
        for r in rs:
            for t in classify_text(r["response"]):
                counts[t] += 1
        out[cast] = {t: round(counts[t] / len(rs) * 100) for t in OBJECTION_TYPES}
    return out


def condition_split(records: List[Dict[str, str]]) -> Dict[str, Dict[str, int]]:
    """Count people whose objection reads as a satisfiable condition ('if X, I
    would') versus a dealbreaker ('I will not'). The honest product-direction
    signal that stays inside the no-purchase-probability rule."""
    by_cast: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for r in records:
        by_cast[r["segment"]].append(r)
    out: Dict[str, Dict[str, int]] = {}
    for cast, rs in by_cast.items():
        c = d = 0
        for r in rs:
            if is_condition(r["response"]):
                c += 1
            else:
                d += 1
        out[cast] = {"condition": c, "dealbreaker": d}
    return out


def render_table(records: List[Dict[str, str]]) -> str:
    table = per_cast_percentages(records)
    casts = list(table.keys())
    lines = ["| objection type | " + " | ".join(casts) + " |",
             "|---|---" + "---|" * len(casts)]
    for t in OBJECTION_TYPES:
        row = " | ".join(str(table[c][t]) + "%" for c in casts)
        lines.append(f"| {t} | {row} |")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="LLM-free objection-type classifier")
    ap.add_argument("source", help="panel session dir or JSON of interview records")
    ap.add_argument("--conditions", action="store_true",
                    help="also emit the condition-vs-dealbreaker split")
    args = ap.parse_args()

    records = extract_interviews(args.source)
    if not records:
        print("no interviews found", file=sys.stderr)
        return 1
    print(f"n={len(records)}")
    print(render_table(records))
    if args.conditions:
        print("\ncondition vs dealbreaker (per cast):")
        for cast, counts in condition_split(records).items():
            print(f"  {cast}: {counts['condition']} condition, {counts['dealbreaker']} dealbreaker")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())