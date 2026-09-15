"""Write app/data/model/<name>.json from the Python data models in app/model.

The classes are the source of truth; the JSON is their reviewable, LLM-free-loadable
form. Run after changing a class:

    python backend/scripts/export_data_models.py          # rewrite the files
    python backend/scripts/export_data_models.py --check  # exit 1 if any file is stale
"""

from __future__ import annotations

import argparse
import json
import os
import sys

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND)
os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "export-placeholder")

MODEL_DIR = os.path.join(BACKEND, "app", "data", "model")


def rendered(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def stale() -> list:
    from app.model import EXPORTS
    out = []
    for name, export in EXPORTS.items():
        path = os.path.join(MODEL_DIR, f"{name}.json")
        current = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if current != rendered(export()):
            out.append(name)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report stale files instead of writing")
    args = ap.parse_args()
    from app.model import EXPORTS
    names = stale()
    if args.check:
        for name in names:
            print(f"stale: app/data/model/{name}.json (run scripts/export_data_models.py)")
        return 1 if names else 0
    for name, export in EXPORTS.items():
        with open(os.path.join(MODEL_DIR, f"{name}.json"), "w", encoding="utf-8") as fh:
            fh.write(rendered(export()))
    print(f"wrote {len(EXPORTS)} model file(s); {len(names)} had changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
