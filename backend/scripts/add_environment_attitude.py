"""Add `environment_priority` to the existing persona library, in place.

Why not rebuild the library: build_library.py regenerates every persona from
scratch, including the LLM texture pass. That would churn 297 finished, reviewed
identities to gain one measured field. This script instead re-runs the SAME
deterministic donor match each persona already had (same seed, same join keys,
same backoff ladder) and appends only the new dimension.

The match is seeded from (build seed XOR a stable hash of the skeleton), so for
almost every persona it resolves to the identical donor it did at build time —
that donor simply now carries `environment_priority` as well.

A minority do move. The hash is taken over the SKELETON, and a few personas were
relabelled downstream of fusion (archetype mapping, texture), so their hash no
longer reproduces. Measured on the current library: 23 of 297 personas change,
182 of 4158 attitude values (4%). Those 23 still receive a real, demographically
matched donor's vector — just a different real respondent's.

That churn is accepted deliberately, and bounded: this script REFUSES TO WRITE if
more than MAX_DRIFT_FRACTION of the library moves, because a larger number would
mean the match is not reproducing at all rather than a handful of relabels.

The durable fix is to record the chosen donor id on each persona at build time,
so a future dimension can be added with zero churn. Worth doing on the next real
library rebuild.

Run:  python backend/scripts/add_environment_attitude.py [--write]
Without --write it reports what would change and touches nothing.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import attitude_donor_adapter as ada  # noqa: E402
from attitude_fuser import fuse_attitudes  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "app", "data", "persona_library", "personas.json")
SAV = os.path.join(HERE, "..", "data", "microdata", "attitudes",
                   "afrobarometer_r9_sa.sav")
NEW_DIM = "environment_priority"
# A few relabelled personas re-draw (see the module docstring). Anything past this
# means the match is broken, not drifting — stop rather than rewrite the library.
MAX_DRIFT_FRACTION = 0.15


def _attitudes_map(persona: dict) -> dict:
    """Personas store attitudes as a LIST of {topic, stance, ...} rows."""
    out = {}
    for row in persona.get("attitudes") or []:
        if isinstance(row, dict) and row.get("topic"):
            out[row["topic"]] = row.get("stance")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="write the library back (default: dry run)")
    args = ap.parse_args()

    with open(LIB, encoding="utf-8") as fh:
        lib = json.load(fh)
    personas = lib["personas"]
    seed = lib.get("seed", 1)
    print(f"library: {len(personas)} personas, seed={seed}")

    donors = ada.load_afrobarometer(SAV)
    print(f"donors:  {len(donors)}")

    # fuse_attitudes mutates copies of the skeletons it is given; feed it the
    # personas themselves (they carry every join key) so the hash — and therefore
    # the donor — matches the original build.
    refused = fuse_attitudes([dict(p) for p in personas], seed=seed, donors=donors)

    moved_values, moved_people, added = 0, [], collections.Counter()
    for original, again in zip(personas, refused):
        before, after = _attitudes_map(original), _attitudes_map(again)
        changed = [d for d, s in before.items() if after.get(d) != s]
        if changed:
            moved_people.append(original.get("name"))
            moved_values += len(changed)
        added[after.get(NEW_DIM)] += 1

    fraction = len(moved_people) / len(personas)
    print(f"\npersonas re-drawn: {len(moved_people)}/{len(personas)} ({fraction:.1%})")
    print(f"attitude values changed: {moved_values}")
    if moved_people:
        print("  " + ", ".join(moved_people[:6]) + (" …" if len(moved_people) > 6 else ""))

    if fraction > MAX_DRIFT_FRACTION:
        print(f"\nREFUSING TO WRITE — more than {MAX_DRIFT_FRACTION:.0%} of the "
              "library moved. The donor match is not reproducing; investigate "
              "before touching the library.")
        return 1

    print(f"\n{NEW_DIM}: " + ", ".join(f"{k}={v}" for k, v in sorted(
        added.items(), key=lambda kv: (kv[0] is None, kv[0]))))

    if not args.write:
        print("\ndry run — pass --write to apply")
        return 0

    for original, again in zip(personas, refused):
        original["attitudes"] = again.get("attitudes")
        original["beliefs"] = again.get("beliefs")
        original["attitude_match_quality"] = again.get("attitude_match_quality")

    with open(LIB, "w", encoding="utf-8") as fh:
        json.dump(lib, fh, ensure_ascii=False, indent=2)
    print(f"\nwrote {LIB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
