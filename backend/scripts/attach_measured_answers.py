"""Attach the donor's literal survey answers to an EXISTING persona library.

No rebuild: identities, ids, incomes and stances are untouched. The donor match
is deterministic from (skeleton, seed), so re-running it recovers the SAME donor
that produced each persona's stances. That is verified per persona before any
answer is attached: if a re-matched stance disagrees with what is on file, the
persona is left alone and counted, never patched from a different donor.
"""
import json, sys, copy, argparse, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import attitude_donor_adapter as ada
import attitude_fuser as af

ap = argparse.ArgumentParser()
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--apply", action="store_true")
args = ap.parse_args()

lib = Path(__file__).resolve().parents[1] / "app/data/persona_library/personas.json"
raw = lib.read_bytes()
data = json.loads(raw)
pool = ada.load_donors()

stats = collections.Counter()
new = copy.deepcopy(data)
for person in new["personas"]:
    rows = person.get("attitudes") or []
    on_file = {r["topic"]: r["stance"] for r in rows}
    try:
        donor, _q = af._match_with_backoff(person, pool, args.seed)
    except Exception:
        stats["no_donor"] += 1
        continue
    # Only trust the re-match where the donor's stance agrees with the file.
    answers = donor.get("attitude_answers") or {}
    attached = 0
    for r in rows:
        dim = r["topic"]
        if r.get("match_quality") == "population_draw":
            continue
        if dim not in answers or donor["attitudes"].get(dim) != on_file.get(dim):
            continue
        # Refuse an answer that points the opposite way to the band it sits in.
        if ada.answer_contradicts_band(dim, r["stance"], answers[dim].get("answer_band")):
            stats["contradictions_skipped"] += 1
            continue
        r["measured_answer"] = answers[dim]["answer"]
        r["measured_question"] = answers[dim]["question"]
        r["measured_asked"] = answers[dim]["asked"]
        attached += 1
    stats["personas_touched" if attached else "personas_unchanged"] += 1
    stats["answers_attached"] += attached

# Nothing outside the attitude rows may move.
def strip(payload):
    p = copy.deepcopy(payload)
    for x in p["personas"]:
        for r in (x.get("attitudes") or []):
            for k in ("measured_answer", "measured_question", "measured_asked"):
                r.pop(k, None)
    return json.dumps(p, sort_keys=True, ensure_ascii=False)
assert strip(data) == strip(new), "something other than measured answers changed"

print(json.dumps({"seed": args.seed, "applied": args.apply,
                  "personas": len(new["personas"]), **stats}, indent=2))
if args.apply:
    lib.write_bytes((json.dumps(new, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
