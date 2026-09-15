"""Score a sealed R10 run on ROOM SHAPE and REASONING, not distribution match.

Matching R10's pie chart exactly is the wrong target: R10 respondents are
strangers whose backgrounds we cannot see, so chasing their exact split invites
tuning prompts until the picture fits. These checks ask different questions,
most of which need no survey at all:

  spread        does the room use the range of answers, or pile onto one box
  extremes      does anyone ever pick the strongest option
  separation    do personas with different measured stances answer differently
  echo          do personas repeat an answer we handed them onto a NEW subject
  strength      does someone who said "fairly bad" now claim the worst ever

Only `spread` and `extremes` look at R10 at all, and only as a reference for
what a real population's shape looks like — never per answer.
"""
import argparse, collections, json, sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"

# Items whose subject differs from the primary question we hand the persona, so a
# verbatim repeat is an echo rather than consistency. Q37A (the President) is the
# carried answer; these ask about other institutions on the same scale.
ECHO_ITEMS = {"Q37B_Q37B": "gov_trust", "Q37F_Q37F": "gov_trust",
              "Q37G_Q37G": "gov_trust", "Q37I_Q37I": "gov_trust"}

# Items close enough to a measured dimension that a stance should move the answer.
STANCE_ITEMS = {"Q4A_Q4A": "economic_optimism", "Q5A_Q5A": "economic_optimism",
                "Q37A_Q37A": "gov_trust", "Q37B_Q37B": "gov_trust",
                "Q37F_Q37F": "gov_trust", "Q37G_Q37G": "gov_trust",
                "Q37I_Q37I": "gov_trust"}


def load(seed, base=None):
    d = Path(base) if base else OUT
    man = json.loads((d / f"r10_manifest_{seed}.json").read_bytes())
    res = json.loads((d / f"r10_results_{seed}.json").read_bytes())
    parts = man["participants"]
    parts = parts if isinstance(parts, list) else list(parts.values())
    answers = collections.defaultdict(dict)
    for line in (d / f"r10_run_{seed}.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        got = rec.get("answer") or rec.get("parsed")
        if got and "slot" in rec and "item_id" in rec:
            answers[rec["item_id"]][rec["slot"]] = got
    return man, res, parts, answers


def report(seed, base=None):
    man, res, parts, answers = load(seed, base)
    items = {i["id"]: i for i in man["items"]}
    truth = {r["id"]: r.get("truth") or {} for r in res["results"]}
    stance = {}
    carried = {}
    for p in parts:
        rows = (p.get("profile") or {}).get("attitudes") or []
        stance[p["slot"]] = {r["topic"]: r["stance"] for r in rows}
        carried[p["slot"]] = {r["topic"]: r.get("measured_answer") for r in rows}

    out = {"seed": seed}

    # 1. spread — 1 minus the share on the single most common answer
    ours, real = [], []
    for iid, by in answers.items():
        if len(by) < 10:
            continue
        c = collections.Counter(by.values())
        ours.append(1 - c.most_common(1)[0][1] / len(by))
        t = truth.get(iid) or {}
        if t:
            real.append(1 - max(t.values()))
    out["spread_ours"] = round(sum(ours) / len(ours), 3)
    out["spread_real"] = round(sum(real) / len(real), 3)

    # 2. extremes — share of answers landing on a strongest option
    hit = tot = 0
    real_hit = real_n = 0
    for iid, by in answers.items():
        ext = set(items.get(iid, {}).get("extremes") or [])
        if not ext:
            continue
        hit += sum(1 for a in by.values() if a in ext)
        tot += len(by)
        t = truth.get(iid) or {}
        if t:
            real_hit += sum(v for k, v in t.items() if k in ext)
            real_n += 1
    out["extremes_ours"] = round(hit / tot, 3) if tot else None
    out["extremes_real"] = round(real_hit / real_n, 3) if real_n else None

    # 3. separation — do opposite stances give different answers
    seps = []
    for iid, dim in STANCE_ITEMS.items():
        by = answers.get(iid) or {}
        groups = collections.defaultdict(collections.Counter)
        for slot, ans in by.items():
            groups[stance.get(slot, {}).get(dim)][ans] += 1
        ends = [g for g in groups if g and g not in ("neutral", "mid", "mixed")]
        if len(ends) < 2:
            continue
        a, b = (collections.Counter(groups[e]) for e in ends[:2])
        na, nb = sum(a.values()), sum(b.values())
        if na < 3 or nb < 3:
            continue
        keys = set(a) | set(b)
        seps.append(0.5 * sum(abs(a[k] / na - b[k] / nb) for k in keys))
    out["separation"] = round(sum(seps) / len(seps), 3) if seps else None

    # 4. echo — repeating a handed answer onto a different subject
    ech = n = 0
    for iid, dim in ECHO_ITEMS.items():
        for slot, ans in (answers.get(iid) or {}).items():
            given = carried.get(slot, {}).get(dim)
            if not given:
                continue
            n += 1
            ech += (ans == given)
    out["echo_rate"] = round(ech / n, 3) if n else None

    # 5. strength — someone who answered mildly now claiming the extreme
    over = n2 = 0
    for iid, dim in STANCE_ITEMS.items():
        ext = set(items.get(iid, {}).get("extremes") or [])
        for slot, ans in (answers.get(iid) or {}).items():
            given = (carried.get(slot, {}) or {}).get(dim)
            if not given:
                continue
            mild = given.lower().startswith(("fairly", "somewhat", "just a little"))
            if mild:
                n2 += 1
                over += ans in ext
    out["overclaim_rate"] = round(over / n2, 3) if n2 else None
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("seeds", nargs="+")
    ap.add_argument("--base", default=None)
    args = ap.parse_args()
    for s in args.seeds:
        print(json.dumps(report(s, args.base)))
