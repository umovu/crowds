"""dedupe_library_names — repair duplicate or race-mismatched names in an existing library.

The library was built with LLM-authored names, which mode-collapsed: ~55 personas
named "Thabo Mokoena", etc. This rewrites duplicate names from the curated pool
(sa_names), keeping the FIRST occurrence of each name and reassigning the rest to
unique, plausible names based on each persona's gender / home language / province.
With --race it also renames anyone whose name does not fit their recorded race
(sa_names.name_fits): names were once picked by province alone, so a Black Western
Cape resident could be "Morné Pietersen". A renamed persona's own prose is updated
to the new name. Everything else (attitudes, demographics, ids) is left untouched.

Usage:
    python backend/scripts/dedupe_library_names.py [--path PATH] [--seed N] [--race] [--dry-run]

Defaults to the in-repo library path; pass --path for the volume copy. Writes a
.bak alongside the file before overwriting (unless --dry-run).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
from sa_names import name_fits, pick_unique_name  # noqa: E402

_DEFAULT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "app", "data", "persona_library", "personas.json")
)


# Text written about the persona that can carry their name.
_PROSE = ("persona", "background_story", "voice_guide", "behavioral_tendencies", "beliefs")


def _norm(name) -> str:
    return (name or "").strip().lower()


def _swap_name(value, old: str, new: str):
    """The persona's own prose, with its old name (full, then first) swapped for the new."""
    if isinstance(value, str):
        value = value.replace(old, new)
        return re.sub(rf"{re.escape(old.split()[0])}", new.split()[0], value)
    if isinstance(value, list):
        return [_swap_name(v, old, new) for v in value]
    if isinstance(value, dict):
        return {k: _swap_name(v, old, new) for k, v in value.items()}
    return value


def repair(path: str, seed: int = 1, dry_run: bool = False, race: bool = False) -> int:
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
    # The first fitting holder of each name keeps it; a later holder, or one whose
    # name does not fit their race (--race), is reassigned.
    keep = [bool(_norm(p.get("name"))) and (not race or name_fits(p["name"], p.get("race")))
            for p in personas]
    used.update(_norm(p.get("name")) for p in personas)  # never reissue a name still held
    seen: set = set()
    for p, ok in zip(personas, keep):
        nm = _norm(p.get("name"))
        if ok and nm not in seen:
            seen.add(nm)
            continue
        # Duplicate, blank or misfit → assign a fresh unique name from the pool.
        new = pick_unique_name(
            used,
            gender=p.get("gender"),
            home_language=p.get("home_language"),
            province=p.get("province"),
            race=p.get("race"),
            rng=rng,
        )
        old = p.get("name") or ""
        if old:
            for k in _PROSE:
                if k in p:
                    p[k] = _swap_name(p[k], old, new)
        print(f"  {old or '(blank)'} -> {new}  [{p.get('race')}, {p.get('province')}]")
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
    ap.add_argument("--race", action="store_true", help="also rename names that do not fit race")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(args.path):
        print(f"Library not found: {args.path}", file=sys.stderr)
        return 1
    repair(args.path, seed=args.seed, dry_run=args.dry_run, race=args.race)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
