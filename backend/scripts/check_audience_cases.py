"""check_audience_cases — does audience_reader pick the right facts for a founder's words?

Scores tests/data/audience_cases.json, written by hand:
  added     facts or provinces picked that the answer sheet does not have (precision)
  missed    facts or provinces on the answer sheet that were not picked (recall)
  unmatched each "can't match this part" the sheet expects, reported in plain words
A case passes when nothing is added, nothing is missed and every expected "can't
match" is said.

    python check_audience_cases.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, BACKEND)
os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "audience-check")
CASES = os.path.join(BACKEND, "tests", "data", "audience_cases.json")


def score(read) -> dict:
    with open(CASES, encoding="utf-8") as fh:
        cases = json.load(fh)["cases"]
    rows, picked_total, right_total, expected_total = [], 0, 0, 0
    for case in cases:
        got = read(case["text"])
        want = set(case["facts"]) | {f"@{p}" for p in case["provinces"]}
        have = set(got["facts"]) | {f"@{p}" for p in got["provinces"]}
        said = " | ".join(got["unmatched"]).lower()
        unsaid = [u for u in case["unmatched"] if u.lower() not in said]
        extra_unmatched = len(got["unmatched"]) - len(case["unmatched"]) > 0
        added, missed = sorted(have - want), sorted(want - have)
        picked_total += len(have)
        right_total += len(have & want)
        expected_total += len(want)
        rows.append({"id": case["id"], "held_out": bool(case.get("held_out")), "added": added, "missed": missed, "unsaid": unsaid,
                     "extra_unmatched": extra_unmatched,
                     "ok": not added and not missed and not unsaid and not extra_unmatched})
    return {
        "rows": rows,
        "passed": sum(r["ok"] for r in rows),
        "held_out_passed": sum(r["ok"] for r in rows if r["held_out"]),
        "held_out_total": sum(r["held_out"] for r in rows),
        "total": len(rows),
        "precision": right_total / picked_total if picked_total else 1.0,
        "recall": right_total / expected_total if expected_total else 1.0,
    }


def main() -> int:
    from app.services import audience_reader
    out = score(audience_reader.read)
    for r in out["rows"]:
        if not r["ok"]:
            bits = [f"added {r['added']}" if r["added"] else "", f"missed {r['missed']}" if r["missed"] else "",
                    f"didn't say {r['unsaid']}" if r["unsaid"] else "",
                    "said a 'can't match' that wasn't there" if r["extra_unmatched"] else ""]
            print(f"  FAIL {r['id']}: " + "; ".join(b for b in bits if b))
    print(f"\nprecision (nothing wrong added): {out['precision']:.0%}")
    print(f"recall (nothing missed):         {out['recall']:.0%}")
    print(f"Score: {out['passed']} of {out['total']} cases passed "
          f"(held out: {out['held_out_passed']} of {out['held_out_total']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
