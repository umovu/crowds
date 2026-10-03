"""shadow_objections — score the keyword objection reader against a typed one.

Reads every stored panel answer, labels it twice, and reports where the two
disagree:

  keyword  objections.classify — substring match over objection_vocab.json cues
  typed    one Noul per objection type (TypeSafe/Jev), same 17 labels

Nothing is changed. The mention layer is pinned by
`tests/test_classifier_reproduction.py`, so this only produces evidence: which
cue words misfire, and which complaints the vocabulary cannot see at all.

Run:  python scripts/shadow_objections.py [--limit N]
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")
BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND)
for line in open(os.path.join(BACKEND, "..", ".env"), encoding="utf-8"):
    line = line.strip()
    if line.startswith("TYPESAFE_") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)

OUT = os.path.join(BACKEND, "scripts", "out", "objection_shadow.json")
# A Noul above this counts as "the typed reader says yes".
YES = 0.6


def answers():
    """Every stored panel answer, with the session and persona it came from."""
    base = os.path.join(BACKEND, "uploads", "panel_sessions")
    rows = []
    for d in sorted(os.listdir(base)):
        rdir = os.path.join(base, d, "rounds")
        if not os.path.isdir(rdir):
            continue
        for rf in sorted(os.listdir(rdir)):
            try:
                j = json.load(open(os.path.join(rdir, rf), encoding="utf-8"))
            except Exception:
                continue
            for x in (j.get("result") or {}).get("results") or []:
                t = (x.get("response") or "").strip()
                if len(t) > 40 and t != "I have no comment on that.":
                    rows.append({"session": d, "name": x.get("agent_name"), "text": t})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    from app.services import objections as ob
    from app.utils import typesafe_client as ts

    if not ts.enabled():
        print("TYPESAFE_API_KEY not set.")
        return 1

    rows = answers()
    if args.limit:
        rows = rows[:args.limit]
    print(f"{len(rows)} stored answers, {len(ob.OBJECTION_TYPES)} objection types\n")

    # The label alone is ambiguous — "costs something just to reach it" reads as
    # "costs something" and swallows every affordability complaint. Each wall's
    # `definition` block (what / not_for / examples) is what separates them, so
    # send that, structured, exactly as the vocabulary file states it.
    defs = ob.DEFINITIONS
    questions = {}
    for o in ob.OBJECTION_TYPES:
        d = defs.get(o) or {}
        questions[o] = ts.noul_question(
            {"question": f"Does the speaker raise this as a problem with the offer: "
                         f"{ob.LABELS[o]}?",
             "what_counts": d.get("what", ob.LABELS[o]),
             "what_does_not_count": d.get("not_for", ""),
             "examples_that_count": d.get("examples", [])})

    def label(row):
        a = ts.ask(row["text"], questions)
        if a is None:
            return None
        row["typed"] = {o: (a.get(o) or {}).get("noul", 0.0) for o in ob.OBJECTION_TYPES}
        row["keyword"] = ob.classify(row["text"])
        return row

    with ThreadPoolExecutor(max_workers=8) as pool:
        done = [r for r in pool.map(label, rows) if r]
    print(f"labelled {len(done)} of {len(rows)}\n")

    agree = Counter()
    # For a false alarm, which cue word fired — that is the actionable part.
    misfire = defaultdict(Counter)
    missed = Counter()
    for r in done:
        low = r["text"].lower()
        for o in ob.OBJECTION_TYPES:
            kw = o in r["keyword"]
            tp = r["typed"][o] >= YES
            agree[(kw, tp)] += 1
            if kw and not tp:
                for w in ob.VOCAB[o]:
                    if w in low:
                        misfire[o][w] += 1
            if tp and not kw:
                missed[o] += 1

    tot = sum(agree.values())
    print("PER LABEL DECISION (17 labels x every answer)")
    print(f"  both say yes      {agree[(True, True)]:6}")
    print(f"  both say no       {agree[(False, False)]:6}")
    print(f"  keyword only      {agree[(True, False)]:6}   <- false alarms")
    print(f"  typed only        {agree[(False, True)]:6}   <- vocabulary blind spots")
    print(f"  total             {tot:6}")

    print("\nCUE WORDS THAT FIRED WHEN THE TYPED READER SAID NO")
    flat = sorted(((c, o, w) for o, ws in misfire.items() for w, c in ws.items()),
                  reverse=True)
    for c, o, w in flat[:20]:
        print(f"  {c:4}x  {w!r:22} -> {ob.LABELS[o]}")

    print("\nLABELS THE VOCABULARY MISSES MOST")
    for o, c in missed.most_common(10):
        print(f"  {c:4}x  {ob.LABELS[o]}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(done, open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"\nfull per-answer detail -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
