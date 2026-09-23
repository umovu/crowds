"""shadow_typed_tilt — score the room picker with the typed tilt beside keywords.

Runs the existing cast-case answer sheet twice: once as shipped (keyword tilt),
once with `derive_tilt_typed`. Prints both scores and every case where they
disagree, so the typed tier is judged on the sheet rather than on a demo.

One typed call per pitch, reused across all seeds.

Run:  python scripts/shadow_typed_tilt.py
"""

import json
import os
import sys
from collections import Counter

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND)

# The key lives in the repo-root .env; this script runs outside Flask's loader.
_ENV = os.path.join(BACKEND, "..", ".env")
if os.path.exists(_ENV):
    with open(_ENV, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("TYPESAFE_") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)

from check_cast_cases import CASES, SEEDS, room_problems  # noqa: E402


def _room(pitch, n, seed, tilt=None, province=None):
    """check_cast_cases.pick_room, with an optional tilt override."""
    from app.services.panel_service import (_economic_fields, _FilteredLibrary,
                                            derive_budget_tiers, get_library)
    from app.services.persona_retrieval import select_for_query

    library = get_library()
    price = derive_budget_tiers(pitch)
    if price:
        library = _FilteredLibrary([p for p in library.all()
                                    if _economic_fields(p)["budget_tier"] in price["tiers"]])
    return select_for_query(n, pitch, library=library, seed=seed,
                            tilt=tilt, province=province)


def _passes(case, n, groups, tilt=None, province=None):
    """(passed, problem lines) over every seed for one case."""
    results = [room_problems(case, _room(case["pitch"], n, s, tilt, province), groups)
               for s in SEEDS]
    good = sum(1 for r in results if not r)
    return good > len(SEEDS) // 2, good, [p for r in results for p in r]


def main():
    from app.services.persona_retrieval import derive_tilt, derive_tilt_typed
    from app.utils import typesafe_client as ts

    if not ts.enabled():
        print("TYPESAFE_API_KEY not set — nothing to shadow.")
        return 1

    with open(CASES, encoding="utf-8") as fh:
        sheet = json.load(fh)
    n, groups, cases = sheet["room_size"], sheet["groups"], sheet["cases"]

    base_pass = typed_pass = 0
    fixed, broke, same = [], [], []
    blind = 0

    for case in cases:
        pitch = case["pitch"]
        kw_weights, _ = derive_tilt(pitch)
        if not kw_weights:
            blind += 1

        b_ok, b_good, _ = _passes(case, n, groups)

        typed = derive_tilt_typed(pitch)
        if typed is None:
            print(f"  (typed call failed for {case['id']} — counted as keyword)")
            t_ok, t_good, t_problems = b_ok, b_good, []
        else:
            tilt, province = typed
            t_ok, t_good, t_problems = _passes(case, n, groups, tilt, province)

        base_pass += b_ok
        typed_pass += t_ok
        row = (case["id"], b_good, t_good, sorted(set(t_problems)),
               sorted(kw_weights), sorted((typed or ({}, None))[0]))
        (fixed if t_ok and not b_ok else broke if b_ok and not t_ok else same).append(row)

    print(f"\nkeyword tilt: {base_pass} of {len(cases)}")
    print(f"typed tilt:   {typed_pass} of {len(cases)}")
    print(f"pitches the keyword table matched nothing on: {blind} of {len(cases)}")

    for label, rows in (("FIXED", fixed), ("BROKE", broke)):
        if not rows:
            continue
        print(f"\n{label}")
        for cid, b, t, problems, kw, tw in rows:
            print(f"  {cid}: {b}/{len(SEEDS)} -> {t}/{len(SEEDS)}")
            print(f"     keyword said: {kw or 'nothing'}")
            print(f"     typed said:   {tw or 'nothing'}")
            for line in problems[:4]:
                print(f"     still: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
