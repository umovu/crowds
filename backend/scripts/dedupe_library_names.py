"""dedupe_library_names — one-time repair for duplicate names in an existing library.

The library was built with LLM-authored names, which mode-collapsed: ~55 personas
named "Thabo Mokoena", etc. This rewrites duplicate names from the curated pool
(sa_names), keeping the FIRST occurrence of each name and reassigning the rest to
unique, plausible names based on each persona's gender / home language / province.
Everything else (attitudes, demographics, ids, texture) is left untouched.

Usage:
    python backend/scripts/dedupe_library_names.py [--path PATH] [--seed N] [--dry-run]

Defaults to the in-repo library path; pass --path for the volume copy. Writes a
.bak alongside the file before overwriting (unless --dry-run).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
from sa_names import pick_unique_name  # noqa: E402

_DEFAULT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "app", "data", "persona_library", "personas.json")
)


def _norm(name) -> str:
    return (name or "").strip().lower()


def repair(path: str, seed: int = 1, dry_run: bool = False) -> int:
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    personas = doc.get("personas", doc if isinstance(doc, list) else [])
    if not personas:
        print(f"No personas found in {path}")
        return 0

    before = Counter(_norm(p.get("name")) for p in personas)
    dup_names = {n for n, c in before.items() if n and c > 1}
    print(f"{len(personas)} personas, {len(before)} unique names, "
          f"{len(dup_names)} names duplicated.")

    rng = random.Random(seed)
    used: set = set()
    renamed = 0
    # First pass: lock in the first occurrence of every name. Second pass would
    # reorder; instead do it in one pass — the first time we see a name it's kept,
    # any later persona carrying an already-used name is reassigned.
    for p in personas:
        nm = _norm(p.get("name"))
        if nm and nm not in used:
            used.add(nm)
            continue
        # Duplicate (or blank) → assign a fresh unique name from the pool.
        new = pick_unique_name(
            used,
            gender=p.get("gender"),
            home_language=p.get("home_language"),
            province=p.get("province"),
            rng=rng,
        )
        p["name"] = new
        renamed += 1

    after = Counter(_norm(p.get("name")) for p in personas)
    still_dup = {n: c for n, c in after.items() if c > 1}
    print(f"Renamed {renamed} personas. "
          f"Now {len(after)} unique names, {len(still_dup)} duplicates remaining.")
    assert not still_dup, f"unexpected residual duplicates: {still_dup}"

    if dry_run:
        print("--dry-run: not writing.")
        return renamed

    bak = path + ".bak"
    shutil.copy2(path, bak)
    if isinstance(doc, dict):
        doc["personas"] = personas
        doc["count"] = len(personas)
        out = doc
    else:
        out = personas
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Backed up -> {bak}\nWrote repaired library -> {path}")
    return renamed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=_DEFAULT_PATH, help="library JSON path")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(args.path):
        print(f"Library not found: {args.path}", file=sys.stderr)
        return 1
    repair(args.path, seed=args.seed, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
