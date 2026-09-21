"""The poster gate. One command, one truth.

    python backend/tests/poster_gate.py

Runs every model-off poster test and prints one line per test. The exit code
is 0 only when everything passes.

Why this exists: status was being written by hand in the proof-of-work and it
drifted from the code three rounds running. Nothing is "Done" because someone
typed it. It is done when this prints PASS.

The proof-of-work pastes this output raw. It does not summarise it.

No pytest needed — the environment does not have it, and the gate must run
anywhere. No model is called; a placeholder API key is set because an
unrelated package reads one at import time.
"""

import importlib.util
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, ".."))

# An unrelated package reads this at import time. No model is called.
os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "gate-placeholder")
sys.path.insert(0, BACKEND)

# Ordered so the locked findings file runs last and reads as the punchline.
SUITES = [
    ("step 1  brief parsing", "test_poster_brief.py"),
    ("step 2  labels", "test_poster_labels.py"),
    ("step 3  poster round", "test_poster_round.py"),
    ("step 4  scoring", "test_poster_scoring.py"),
    ("step 5  spread cast", "test_poster_spread.py"),
    ("LOCKED  review findings", "test_poster_findings.py"),
]


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    passed = failed = 0
    failures = []

    for title, filename in SUITES:
        path = os.path.join(HERE, filename)
        print(f"\n{title}  ({filename})")
        if not os.path.isfile(path):
            print("  MISSING  file does not exist")
            failed += 1
            failures.append((title, filename, "file missing"))
            continue
        try:
            mod = _load(path, f"gate_{filename[:-3]}")
        except Exception as e:
            print(f"  IMPORT FAIL  {type(e).__name__}: {e}")
            failed += 1
            failures.append((title, filename, f"import: {e}"))
            continue

        for name in sorted(n for n in dir(mod) if n.startswith("test_")):
            try:
                getattr(mod, name)()
                print(f"  PASS  {name}")
                passed += 1
            except Exception as e:
                first = (str(e).strip().splitlines() or [""])[0][:110]
                print(f"  FAIL  {name}  — {type(e).__name__}: {first}")
                failed += 1
                failures.append((title, name, first))

    total = passed + failed
    print("\n" + "=" * 62)
    print(f"GATE: {passed}/{total} pass")
    if failures:
        print("\nOpen findings — these are the work order:")
        for title, name, why in failures:
            print(f"  - [{title}] {name}: {why}")
        print("\nDo not edit tests in test_poster_findings.py to close these.")
    print("=" * 62)
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
