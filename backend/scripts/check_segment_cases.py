"""check_segment_cases — score the beachhead suggester against the answer sheet.

For each pitch: who does the tool say the first customer is, and is that right?
Two suggesters scored side by side on `tests/data/segment_cases.json`:

  keyword   panel_service.suggest_segments, as shipped
  typed     one Choice question over the 'who' segments (TypeSafe/Jev)

Only `who` segments are candidates. The attitude axis is a separate question the
product already asks separately (`suggest_narrowing`), and mixing a 226-person
attitude group into "who is the customer" makes the question incoherent.

Run:  python scripts/check_segment_cases.py
"""
import json
import os
import sys

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")
BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND)

_ENV = os.path.join(BACKEND, "..", ".env")
if os.path.exists(_ENV):
    for line in open(_ENV, encoding="utf-8"):
        line = line.strip()
        if line.startswith("TYPESAFE_") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)

CASES = os.path.join(BACKEND, "tests", "data", "segment_cases.json")
# Below this the answer is a spread, not a pick — the honest reply is "we cannot
# tell", which the UI already has a state for.
MIN_CONFIDENCE = 0.5


def who_options():
    from app.services.panel_service import SEGMENTS, segment_sizes
    sizes = segment_sizes()
    return {k: f"{v['label']} — {v['description']}"
            for k, v in SEGMENTS.items()
            if v.get("kind") == "who" and k != "everyone" and sizes.get(k, 0) > 0}


def main():
    from app.services.panel_service import SEGMENTS, suggest_segments
    from app.utils import typesafe_client as ts

    if not ts.enabled():
        print("TYPESAFE_API_KEY not set.")
        return 1

    options = who_options()
    question = {"beachhead": ts.choice_question(
        "Which single group of South Africans is the best FIRST customer for this — "
        "the group that feels the problem most sharply and would take it up earliest?",
        options)}

    cases = json.load(open(CASES, encoding="utf-8"))["cases"]
    tally = {"kw_top1": 0, "kw_any": 0, "ts_top1": 0, "ts_any": 0,
             "kw_none": 0, "ts_unsure": 0, "kw_reject": 0, "ts_reject": 0}
    blind = {"n": 0, "kw_top1": 0, "ts_top1": 0}
    rows = []

    for case in cases:
        accept, reject = set(case["accept"]), set(case.get("reject", []))

        kw = [s for s in suggest_segments(case["pitch"], cap=3)
              if SEGMENTS.get(s, {}).get("kind") == "who"]
        answers = ts.ask(case["pitch"], question)
        answer = (answers or {}).get("beachhead") or {}
        confidence = answer.get("confidence") or 0.0
        ranked = sorted((answer.get("probabilities") or {}).items(), key=lambda kv: -kv[1])
        ts_pick = ranked[0][0] if ranked and confidence >= MIN_CONFIDENCE else None
        ts_top3 = [k for k, _ in ranked[:3]]

        tally["kw_top1"] += bool(kw) and kw[0] in accept
        tally["kw_any"] += any(s in accept for s in kw)
        tally["kw_none"] += not kw
        tally["kw_reject"] += any(s in reject for s in kw[:1])
        tally["ts_top1"] += ts_pick in accept
        tally["ts_any"] += any(s in accept for s in ts_top3)
        tally["ts_unsure"] += ts_pick is None
        tally["ts_reject"] += ts_pick in reject
        if case.get("blind"):
            blind["n"] += 1
            blind["kw_top1"] += bool(kw) and kw[0] in accept
            blind["ts_top1"] += ts_pick in accept

        rows.append((case["id"], bool(case.get("blind")),
                     kw[0] if kw else None, ts_pick, confidence, accept))

    n = len(cases)
    print(f"\n{'case':38} {'kw':>20} {'jev':>22}")
    for cid, is_blind, kw1, ts1, conf, accept in rows:
        mark = lambda s: ("OK " if s in accept else "   ") + (s or "-")
        print(f"{('* ' if is_blind else '  ') + cid:38} {mark(kw1):>20} "
              f"{mark(ts1) + f' {conf:.2f}':>22}")
    print("  (* = a pitch the keyword table matches nothing on)")

    print(f"\n                       keyword   jev")
    print(f"  first pick right     {tally['kw_top1']:>7} {tally['ts_top1']:>5}   of {n}")
    print(f"  right in top 3       {tally['kw_any']:>7} {tally['ts_any']:>5}   of {n}")
    print(f"  named a wrong group  {tally['kw_reject']:>7} {tally['ts_reject']:>5}")
    print(f"  said nothing         {tally['kw_none']:>7} {tally['ts_unsure']:>5}")
    print(f"\n  on the {blind['n']} keyword-blind pitches: "
          f"keyword {blind['kw_top1']}, jev {blind['ts_top1']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
