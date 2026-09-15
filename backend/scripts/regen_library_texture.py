"""regen_library_texture — rewrite the texture of an EXISTING library in place.

Not a rebuild. `build_library.py` resamples skeletons and produces different people;
this keeps every person exactly as they are — same id, same name, same demographics,
same fused attitudes and circumstances — and rewrites only the LLM-authored surface
(persona, background_story, voice_guide, behavioral_tendencies, group_affiliation,
interested_topics) under the current prompt and provenance gate.

Why it exists: the texture prompt used to hand the model `load-shedding` as an example
and ask it to "pick the two or three facts that most shape this person's life". 363 of
375 personas repeated the example and the rest reached for hardship, so the library read
far more negative than the survey data behind it. Fixing the prompt fixes new personas;
this fixes the ones already built.

Safety: writes to a side file and never touches the live library. Checkpoints every
persona, so an interrupted run resumes instead of re-spending. Verify the output with
texture_provenance_audit.py before swapping it in.

Usage:
    python regen_library_texture.py [--workers 6] [--limit N] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _HERE)

# The build scripts read config from the environment; the repo keeps it in a root .env
# that nothing in scripts/ loads on its own.
_ENV = os.path.join(_ROOT, ".env")
if os.path.exists(_ENV):
    with open(_ENV, encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if raw and not raw.startswith("#") and "=" in raw:
                key, value = raw.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

import texture_generator as tg  # noqa: E402
from app.utils.llm_client import LLMClient  # noqa: E402

LIBRARY = os.path.join(_HERE, "..", "app", "data", "persona_library", "personas.json")

_lock = threading.Lock()


def regen_one(person: dict, client: LLMClient) -> dict:
    """New texture for one person, with their identity restored verbatim.

    `generate_texture` assigns a name from the pool. That is right for a fresh build and
    wrong here: a renamed persona breaks every saved sim, panel and report that refers to
    them. The original name and id win.
    """
    fresh = tg.generate_texture(dict(person), client=client, used_names=set())
    fresh["name"] = person["name"]
    if person.get("id"):
        fresh["id"] = person["id"]
    return fresh


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0, help="regenerate only the first N")
    ap.add_argument("--out", default=os.path.join(
        _HERE, "..", "app", "data", "persona_library", "personas.regen.json"))
    args = ap.parse_args()

    with open(LIBRARY, encoding="utf-8") as fh:
        payload = json.load(fh)
    people = payload["personas"] if isinstance(payload, dict) else payload
    if args.limit:
        people = people[:args.limit]

    checkpoint = args.out + ".checkpoint.jsonl"
    done: dict = {}
    if os.path.exists(checkpoint):
        with open(checkpoint, encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except Exception:  # noqa: BLE001 — a truncated last line is expected
                    continue
                done[row["name"]] = row
        print(f"resuming: {len(done)} already regenerated", flush=True)

    todo = [p for p in people if p["name"] not in done]
    print(f"{len(todo)} to regenerate, {args.workers} workers", flush=True)

    client = LLMClient()
    failures: list = []
    handle = open(checkpoint, "a", encoding="utf-8")

    def work(person):
        return person, regen_one(person, client)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(work, p) for p in todo]
        for i, fut in enumerate(as_completed(futures), 1):
            try:
                person, fresh = fut.result()
            except Exception as exc:  # noqa: BLE001 — one failure must not lose the run
                failures.append(str(exc)[:200])
                continue
            with _lock:
                done[person["name"]] = fresh
                handle.write(json.dumps(fresh, ensure_ascii=False) + "\n")
                handle.flush()
            if i % 25 == 0:
                print(f"  {i}/{len(todo)} done, {len(failures)} failed", flush=True)
    handle.close()

    out_people = [done.get(p["name"], p) for p in people]
    result = dict(payload) if isinstance(payload, dict) else {}
    if isinstance(payload, dict):
        result["personas"] = out_people
    else:
        result = out_people
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    regenerated = sum(1 for p in people if p["name"] in done)
    print(f"\nwrote {args.out}")
    print(f"regenerated {regenerated}/{len(people)}; {len(failures)} failures")
    for f in failures[:5]:
        print("  !", f)


if __name__ == "__main__":
    main()
