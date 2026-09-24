"""sameness_benchmark — do a panel's answers sound like one person or like twelve?

Every change aimed at group-think so far was judged on one run of one room, and one
run cannot tell a real change from the model's own variation. This runs a fixed set
of pitches over a fixed set of rooms, measures how alike each room's answers are,
and reports the mean with its uncertainty, so two versions can be compared.

What is measured, per room of 12:

  overlap        mean pairwise share of content words two answers have in common,
                 counting only words the pitch itself does not use — echoing the
                 pitch ("R150 a visit") is the pitch talking, not the room
  shared         phrases (3 words, again not from the pitch) said by at least a
                 quarter of the room, per answer
  opening        share of answers that start with the room's most common first
                 three words ("I'd try it")
  stance_spread  how evenly the room splits across support/neutral/oppose, 0 when
                 everyone lands in one place, 1 when evenly split

Lower overlap, shared and opening, and higher stance_spread, mean a less uniform
room. None of these says the answers are right; only that they are not one voice.

Calibrated by running the same setup twice (2026-09-23): stance_spread, shared and
opening read "no clear change", as they should; overlap read a false +0.012. So treat
an overlap change under about 0.02 as noise, or run each version twice.

First use: rewording the decision question from "What would you do about it?" to
"What do you make of it, for your own life?" made rooms MORE alike on three of the
four measures (opening +0.18, shared +0.39, overlap +0.016). The sameness moved
rather than went: answers opened by repeating the price ("R80 a month", 22 times
against 13). The wording was not changed.

Rooms are chosen by seed, so every version sees the same people. Sessions are
written to a temporary folder, never to uploads/. One sim-tier call per persona:
4 pitches x 3 rooms x 12 = 144 calls a run.

Usage:
    python sameness_benchmark.py run --label baseline           # writes out/sameness_baseline.json
    FLAG=1 python sameness_benchmark.py run --label variant
    python sameness_benchmark.py compare baseline variant       # the difference, with intervals
    python sameness_benchmark.py run --label x --segment employed --seeds 9   # more, targeted rooms
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import math
import os
import re
import statistics
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(HERE, "out")

PITCHES = {
    "clinic": ("A private clinic chain wants to launch a R150 pay-per-visit nurse service. "
               "You book on WhatsApp and see a nurse the same day, with no queue and no "
               "medical aid needed."),
    "parent_app": ("An app that shows parents how much effort their child puts into "
                   "schoolwork each day, so they can reward it. R60 a month."),
    "solar": ("A small solar and battery kit rented for R299 a month that keeps your "
              "lights, fridge and phone going when the power is out."),
    "funeral": ("Funeral cover for R80 a month that pays out within 48 hours, signed up "
                "on your phone with no paperwork and no medical questions."),
}
SEEDS = (101, 202, 303)
ROOM = 12

# Flags that change what a panel is asked or shown. Recorded with every run, so a
# comparison can say what differed.
FLAGS = ("PANEL_DECISION_QUESTION", "FUB_TYPED_CARDS", "FUB_TYPED_SUBJECTS",
         "RESEARCH_CONTEXT_ENABLED", "RESEARCH_CONTEXT_RENDERED", "EVIDENCE_AWARE_PROMPTS",
         "SIM_LLM_MODEL")

_STOP = set("""a an the and or but if then so to of in on at for with from by as is are
was were be been it its this that these those i me my we our you your he she they them
their would will can could should not no do does did have has had just about what which
who how when where there here than too very also into out up down over only own same more
most some such any all both each few other i'd i'm it's don't that's i'll can't won't
isn't""".split())


def _words(text: str):
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def _content(text: str, pitch_words: set) -> set:
    return {w for w in _words(text) if w not in _STOP and w not in pitch_words and len(w) > 2}


def _trigrams(text: str) -> set:
    w = _words(text)
    return {" ".join(w[i:i + 3]) for i in range(len(w) - 2)}


def room_measures(answers, stances, pitch: str) -> dict:
    """The four sameness measures for one room. Pure; no model."""
    answers = [a for a in answers if a and a.strip() and "no comment" not in a.lower()]
    n = len(answers)
    pitch_words = set(_words(pitch))
    pitch_tri = _trigrams(pitch)

    sets = [_content(a, pitch_words) for a in answers]
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    overlap = (sum(len(sets[i] & sets[j]) / max(1, len(sets[i] | sets[j])) for i, j in pairs)
               / len(pairs)) if pairs else 0.0

    counts = collections.Counter(g for a in answers for g in _trigrams(a) - pitch_tri)
    floor = max(2, math.ceil(n / 4))
    shared = sum(1 for c in counts.values() if c >= floor) / n if n else 0.0

    openings = collections.Counter(" ".join(_words(a)[:3]) for a in answers)
    opening = (openings.most_common(1)[0][1] / n) if n else 0.0

    tally = collections.Counter(s or "neutral" for s in stances)
    total = sum(tally.values())
    if total and len(tally) > 1:
        entropy = -sum((c / total) * math.log(c / total) for c in tally.values())
        spread = entropy / math.log(3)
    else:
        spread = 0.0

    return {"answered": n, "overlap": round(overlap, 4), "shared": round(shared, 4),
            "opening": round(opening, 4), "stance_spread": round(spread, 4)}


def _summary(values):
    """Mean and a 95% interval half-width across rooms."""
    if not values:
        return {"mean": None, "ci": None}
    mean = statistics.fmean(values)
    ci = 1.96 * statistics.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else None
    return {"mean": round(mean, 4), "ci": round(ci, 4) if ci is not None else None}


def _wire_llm():
    """Same SIM_* -> AGENTSOCIETY_* mapping the backend does at start-up."""
    from dotenv import load_dotenv
    # A worktree has no .env of its own; DOTENV_PATH points at the checkout's.
    for path in (os.environ.get("DOTENV_PATH"), os.path.join(BACKEND, "..", ".env"),
                 os.path.join(BACKEND, ".env")):
        if path:
            load_dotenv(path)
    wanted = {"AGENTSOCIETY_LLM_API_KEY": os.environ.get("SIM_LLM_API_KEY") or os.environ.get("LLM_API_KEY"),
              "AGENTSOCIETY_LLM_API_BASE": os.environ.get("SIM_LLM_BASE_URL") or os.environ.get("LLM_BASE_URL"),
              "AGENTSOCIETY_LLM_MODEL": os.environ.get("SIM_LLM_MODEL") or os.environ.get("LLM_MODEL_NAME")}
    for name, value in wanted.items():
        if not os.environ.get(name) and value:
            os.environ[name] = value
    if not os.environ.get("AGENTSOCIETY_LLM_API_KEY"):
        raise SystemExit("No sim model key found. Set DOTENV_PATH to the .env holding SIM_LLM_*.")
    for tier in ("NANO_LLM", "ANALYSIS_LLM"):
        for key in ("API_KEY", "API_BASE", "MODEL"):
            if not os.environ.get(f"AGENTSOCIETY_{tier}_{key}"):
                os.environ[f"AGENTSOCIETY_{tier}_{key}"] = os.environ.get(f"AGENTSOCIETY_LLM_{key}", "")


def run(label: str, segment: str = "everyone", seeds: int = len(SEEDS)) -> dict:
    sys.path.insert(0, BACKEND)
    os.chdir(BACKEND)
    _wire_llm()
    from app.config import Config
    Config.PANEL_SESSION_DATA_DIR = tempfile.mkdtemp(prefix="sameness_")
    from app.services import panel_service as ps
    from app.services.interview_service import InterviewService

    rooms = []
    for name, pitch in PITCHES.items():
        for seed in [101 * (i + 1) for i in range(seeds)]:
            meta = ps.create_session(pitch=pitch, mode="panel", n=ROOM, seed=seed,
                                     segments=[segment], user_id="sameness-benchmark")
            framed = ps.frame_pitch(pitch, "panel")
            svc = InterviewService(meta["session_id"], base_dir=Config.PANEL_SESSION_DATA_DIR)
            res = asyncio.run(svc.batch_impact_interview(framed, concurrency=6))
            results = res.get("results", res)
            answers = [r.get("response") or "" for r in results]
            stances = [r.get("stance_after") for r in results]
            m = room_measures(answers, stances, pitch)
            rooms.append({"pitch": name, "seed": seed, **m, "answers": answers})
            print(f"  {name:<11} seed {seed}: overlap {m['overlap']:.3f}  shared {m['shared']:.2f}  "
                  f"opening {m['opening']:.2f}  spread {m['stance_spread']:.2f}  ({m['answered']} heard)")

    out = {
        "label": label,
        "segment": segment,
        "flags": {f: os.environ.get(f) for f in FLAGS},
        "rooms": rooms,
        "summary": {k: _summary([r[k] for r in rooms])
                    for k in ("overlap", "shared", "opening", "stance_spread")},
    }
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, f"sameness_{label}.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    return out


def compare(a_label: str, b_label: str) -> None:
    def load(label):
        with open(os.path.join(OUT, f"sameness_{label}.json"), encoding="utf-8") as fh:
            return json.load(fh)
    a, b = load(a_label), load(b_label)
    changed = {f: (a["flags"].get(f), b["flags"].get(f)) for f in FLAGS
               if a["flags"].get(f) != b["flags"].get(f)}
    print(f"{a_label} -> {b_label}   flags changed: {changed or 'none'}\n")
    # Paired by room: the same people answered both, so the per-room difference
    # removes who-was-in-the-room from the comparison.
    by_room = {(r["pitch"], r["seed"]): r for r in a["rooms"]}
    print(f"{'measure':<14}{a_label:>12}{b_label:>12}{'change':>10}{'95% interval':>18}   reads as")
    for key, lower_is_better in (("overlap", True), ("shared", True), ("opening", True),
                                 ("stance_spread", False)):
        diffs = [r[key] - by_room[(r["pitch"], r["seed"])][key]
                 for r in b["rooms"] if (r["pitch"], r["seed"]) in by_room]
        s = _summary(diffs)
        ci = s["ci"] or 0.0
        lo, hi = s["mean"] - ci, s["mean"] + ci
        if lo > 0 or hi < 0:
            better = (s["mean"] < 0) == lower_is_better
            verdict = "less alike" if better else "more alike"
        else:
            verdict = "no clear change"
        print(f"{key:<14}{a['summary'][key]['mean']:>12.3f}{b['summary'][key]['mean']:>12.3f}"
              f"{s['mean']:>+10.3f}{f'[{lo:+.3f}, {hi:+.3f}]':>18}   {verdict}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--label", required=True)
    r.add_argument("--segment", default="everyone", help="panel segment every room is drawn from")
    r.add_argument("--seeds", type=int, default=len(SEEDS), help="rooms per pitch")
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    args = ap.parse_args()
    if args.cmd == "run":
        out = run(args.label, args.segment, args.seeds)
        print("\nSUMMARY (mean, 95% interval across rooms)")
        for key, s in out["summary"].items():
            print(f"  {key:<14} {s['mean']:.3f} ± {s['ci'] or 0:.3f}")
    else:
        compare(args.a, args.b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
