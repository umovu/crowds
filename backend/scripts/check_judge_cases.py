"""
check_judge_cases — score the SA-context judge against a hand-marked answer sheet.

The question this answers: **does the judge catch a bad current-realities block?**
The block goes into every persona prompt for the day, so a bad one that slips through
poisons every run that day.

tests/data/sa_context_cases.json holds one day's real search snippets plus blocks
written from them: a few real ones (marked by hand) and broken ones written on
purpose — unsupported bullets, invented numbers, revived crises, wrong shape.

Two numbers matter, and missing a bad block is the worse error:
  caught   — bad blocks the judge failed (want high)
  wrong    — good blocks the judge failed (want low)

Costs one Plus-tier call per case. Run:  python scripts/check_judge_cases.py
"""

import json
import os
import sys

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")
os.environ["JUDGE_ENABLED"] = "true"

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND)

CASES = os.path.join(BACKEND, "tests", "data", "sa_context_cases.json")


def score(verbose=False):
    """(caught, bad total, wrongly failed, good total). Unmarked cases are skipped."""
    from app.services.judge_service import get_judge_service

    with open(CASES, encoding="utf-8") as fh:
        sheet = json.load(fh)
    snippets, svc = sheet["snippets"], get_judge_service()

    caught = bad_total = wrong = good_total = 0
    for case in sheet["cases"]:
        verdict = case.get("verdict")
        if verdict is None:
            if verbose:
                print(f"SKIP  {case['id']} — not marked yet")
            continue
        result = svc.judge_sa_context(case["block"], snippets)
        if result.errored:
            print(f"ERROR {case['id']} — judge call failed: {result.reasoning[:120]}")
            continue
        should_pass = verdict == "fine"
        right = result.pass_ == should_pass
        if should_pass:
            good_total += 1
            wrong += not right
        else:
            bad_total += 1
            caught += right
        if verbose and not right:
            print(f"MISS  {case['id']} ({verdict}) scored {result.score}: "
                  f"{result.reasoning[:160]}")
        elif verbose:
            print(f"ok    {case['id']} ({verdict}) scored {result.score}")
    return caught, bad_total, wrong, good_total


if __name__ == "__main__":
    caught, bad_total, wrong, good_total = score(verbose=True)
    print(f"\nCaught {caught} of {bad_total} bad blocks")
    print(f"Wrongly failed {wrong} of {good_total} good blocks")
