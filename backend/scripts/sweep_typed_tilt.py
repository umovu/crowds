"""sweep_typed_tilt — tune the tilt rule against the answer sheet, offline.

Reads cached answers (scripts/cache_typed_tilt.py) so no model is called. Scores
every rule on the same 26 cases x 5 seeds the shipped picker is scored on.
"""
import json
import os
import sys
from itertools import product

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")
BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND)

from check_cast_cases import CASES, SEEDS, room_problems  # noqa: E402
from shadow_typed_tilt import _room  # noqa: E402

ANSWERS = os.path.join(BACKEND, "scripts", "out", "typed_tilt_answers.json")


def stake(answer, from_level):
    probs = answer.get("probabilities") or {}
    return sum(float(v) for k, v in probs.items() if int(k) >= from_level)


def weights_for(answers, *, from_level, min_stake, top_k, max_tilt):
    scored = []
    for arch, answer in answers.items():
        if arch.startswith("_"):
            continue
        s = stake(answer, from_level)
        if s >= min_stake:
            scored.append((arch, s))
    scored.sort(key=lambda kv: -kv[1])
    if top_k:
        scored = scored[:top_k]
    if not scored:
        return {}
    # Normalise so the strongest archetype always earns the full cap; a rule that
    # boosts eight groups equally is the same as boosting none.
    best = scored[0][1]
    return {a: 1.0 + (s / best) * (max_tilt - 1.0) for a, s in scored}


def main():
    cached = json.load(open(ANSWERS, encoding="utf-8"))
    sheet = json.load(open(CASES, encoding="utf-8"))
    n, groups, cases = sheet["room_size"], sheet["groups"], sheet["cases"]
    from app.services.persona_retrieval import MAX_TILT

    def score(rule):
        passed, detail = 0, {}
        for case in cases:
            answers = cached.get(case["id"])
            if answers is None:
                continue
            w = weights_for(answers, max_tilt=MAX_TILT, **rule)
            prov = (answers.get("_province") or {})
            province = prov.get("choice")
            if province == "not_stated" or (prov.get("confidence") or 0) < 0.5:
                province = None
            good = sum(1 for s in SEEDS
                       if not room_problems(case, _room(case["pitch"], n, s, w, province), groups))
            ok = good > len(SEEDS) // 2
            passed += ok
            detail[case["id"]] = good
        return passed, detail

    print(f"cases: {len(cases)}   baseline (keyword): 20\n")
    results = []
    for from_level, min_stake, top_k in product((2, 3), (0.4, 0.5, 0.6, 0.7), (None, 3, 4, 5)):
        rule = {"from_level": from_level, "min_stake": min_stake, "top_k": top_k}
        passed, detail = score(rule)
        results.append((passed, rule, detail))
        print(f"  level>={from_level}  stake>={min_stake}  top_k={str(top_k):4}  ->  {passed}")

    results.sort(key=lambda r: -r[0])
    best_n, best_rule, best_detail = results[0]
    print(f"\nbest: {best_rule} -> {best_n} of {len(cases)}")
    fails = [cid for cid, good in best_detail.items() if good <= len(SEEDS) // 2]
    print("still failing: " + (", ".join(fails) or "none"))


if __name__ == "__main__":
    main()
