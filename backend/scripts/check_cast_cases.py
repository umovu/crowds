"""
check_cast_cases — score the room picker against a hand-written answer sheet.

The question this answers: **for a pitch, does an 'Everyone' panel put the right
people in the room?** Each case in tests/data/cast_cases.json says who must get a seat, who
should barely appear, and how many well-off or struggling seats are allowed.

The picker is partly random, so every pitch runs on several seeds. A case passes
when most of its rooms pass. LLM-free: runs on the real library, no model calls.

Run:  python scripts/check_cast_cases.py
"""

import json
import os
import sys
from collections import Counter

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND)

CASES = os.path.join(BACKEND, "tests", "data", "cast_cases.json")
SEEDS = range(5)


def room_problems(case, room, groups):
    """What is wrong with one room, as plain lines. Empty means it passes."""
    seats = Counter(p.get("actor_archetype") for p in room)
    problems = []
    for want in case.get("want", []):
        if not any(seats[a] for a in want):
            problems.append(f"no seat for any of {want}")
    for a in case.get("avoid", []):
        if seats[a] > 1:
            problems.append(f"{a} took {seats[a]} seats (max 1)")
    well_off = sum(seats[a] for a in groups["well_off"])
    struggling = sum(seats[a] for a in groups["struggling"])
    if well_off < case.get("well_off_min", 0):
        problems.append(f"well-off {well_off} (min {case['well_off_min']})")
    if "struggling_max" in case and struggling > case["struggling_max"]:
        problems.append(f"struggling {struggling} (max {case['struggling_max']})")
    return problems


def pick_room(pitch, n, seed):
    """The room an 'Everyone' panel gets: the price filter create_session runs on
    the pitch, then select_for_query on whoever is left."""
    from app.services.panel_service import (_economic_fields, _FilteredLibrary,
                                            derive_budget_tiers, get_library)
    from app.services.persona_retrieval import select_for_query

    library = get_library()
    price = derive_budget_tiers(pitch)
    if price:
        library = _FilteredLibrary([p for p in library.all()
                                    if _economic_fields(p)["budget_tier"] in price["tiers"]])
    return select_for_query(n, pitch, library=library, seed=seed)


def score(verbose=False):
    """(cases passed, cases total). tests/test_cast_cases.py guards the number."""
    with open(CASES, encoding="utf-8") as fh:
        sheet = json.load(fh)
    n, groups, cases = sheet["room_size"], sheet["groups"], sheet["cases"]

    passed = 0
    for case in cases:
        rooms = [pick_room(case["pitch"], n, s) for s in SEEDS]
        results = [room_problems(case, room, groups) for room in rooms]
        good = sum(1 for r in results if not r)
        ok = good > len(SEEDS) // 2
        passed += ok
        if not verbose:
            continue
        print(f"{'PASS' if ok else 'FAIL'}  {good}/{len(SEEDS)} rooms  {case['id']}")
        if not ok:
            for line, count in Counter(p for r in results for p in r).most_common():
                print(f"        {count}x {line}")
            mix = Counter(p.get("actor_archetype") for room in rooms for p in room)
            print("        typical room: " + ", ".join(
                f"{a} {c / len(SEEDS):.1f}" for a, c in mix.most_common(6)))
    return passed, len(cases)


if __name__ == "__main__":
    passed, total = score(verbose=True)
    print(f"\nScore: {passed} of {total} cases passed")
