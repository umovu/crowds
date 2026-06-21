"""
promote_fact — review sim fact-gaps and promote a fact into the curated layer.

The closing step of the world-facts loop: agents flag costs they needed but
weren't given (logged to a sim's fact_gaps.jsonl by run_simulation_as.py). You
review those gaps and promote the real value into app/data/sa_world_facts.json
in ONE command — the only path that writes a 'curated' (authoritative) fact.
Nothing enters the curated layer without this deliberate step, and the value is
validated (number + unit) before it is written.

Usage:
  # List the fact-gaps recorded in a sim's output dir (deduped, with counts):
  python -m scripts.promote_fact --gaps <sim_output_dir>

  # Promote a fact (adds/replaces by item, provenance=curated):
  python -m scripts.promote_fact --item petrol --value 22 --unit "R/litre" \\
      --source "AA fuel price" --as-of 2026-06 \\
      --derived "R100 buys ~4.5 L — nowhere near a full tank."
"""

import argparse
import json
import os
import sys
from collections import Counter

# Allow running as a script from backend/.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.world_facts import promote_fact, load_facts


def _list_gaps(sim_dir: str) -> None:
    path = os.path.join(sim_dir, "opinion_space", "fact_gaps.jsonl")
    if not os.path.exists(path):
        # Fall back to the dir itself in case a full output path was given.
        alt = os.path.join(sim_dir, "fact_gaps.jsonl")
        path = alt if os.path.exists(alt) else path
    if not os.path.exists(path):
        print(f"No fact_gaps.jsonl found under {sim_dir}")
        return
    counts: Counter = Counter()
    total = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            counts[(rec.get("needed_fact") or "").strip().lower()] += 1
            total += 1
    if not counts:
        print(f"fact_gaps.jsonl is empty ({path})")
        return
    print(f"Fact-gaps in {path} — {total} request(s), {len(counts)} distinct:\n")
    for fact, n in counts.most_common():
        print(f"  {n:>3}×  {fact}")
    print("\nPromote one with: --item <name> --value <num> --unit <unit> [--source ... --derived ...]")


def main() -> None:
    ap = argparse.ArgumentParser(description="Review fact-gaps / promote a curated world-fact.")
    ap.add_argument("--gaps", metavar="SIM_DIR", help="List fact-gaps recorded in a sim output dir")
    ap.add_argument("--item", help="Fact key, e.g. 'petrol'")
    ap.add_argument("--value", type=float, help="Numeric value")
    ap.add_argument("--unit", help="Unit, e.g. 'R/litre'")
    ap.add_argument("--source", default="", help="Where the value comes from")
    ap.add_argument("--derived", default="", help="Human-readable consequence shown to agents")
    ap.add_argument("--as-of", dest="as_of", default="", help="YYYY-MM the value is current as of")
    ap.add_argument("--provenance", default="curated", choices=["curated", "web", "discovered"])
    args = ap.parse_args()

    if args.gaps:
        _list_gaps(args.gaps)
        return

    if not (args.item and args.value is not None and args.unit):
        ap.error("promotion requires --item, --value and --unit (or use --gaps to review)")

    fact = promote_fact(
        item=args.item, value=args.value, unit=args.unit,
        source=args.source, derived=args.derived, as_of=args.as_of,
        provenance=args.provenance,
    )
    print(f"Promoted: {fact['item']} = R{fact['value']} {fact['unit']} ({fact['provenance']})")
    print(f"Curated layer now holds {len(load_facts())} valid fact(s).")


if __name__ == "__main__":
    main()
