"""Fill the employment status GHS already recorded, and re-match those personas.

31 personas carry no employment_status because the GHS adapter read only
employ_Status1, whose "Unspecified" code covers every non-worker. employ_Status2
classes all of them "Not economically active". Employment is one of the six
attitude-match keys, so the blank failed every rung and left these personas
matched on race alone — the weakest attitudes in the library.

This fills the field and re-runs the SAME deterministic match for those personas
only. Nothing else is touched, and the before/after match quality is reported.
"""
import argparse, collections, copy, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import attitude_donor_adapter as ada
import attitude_fuser as af

ap = argparse.ArgumentParser()
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--apply", action="store_true")
args = ap.parse_args()

lib = Path(__file__).resolve().parents[1] / "app/data/persona_library/personas.json"
data = json.loads(lib.read_bytes())
new = copy.deepcopy(data)
pool = ada.load_donors()

STATUS = "Other not economically active"
modal = af._population_modal_stances(pool)
dist = af._population_distributions(pool, "attitudes", ada.ATTITUDE_VOCAB)
before, after = collections.Counter(), collections.Counter()
fixed = 0
for person in new["personas"]:
    if person.get("employment_status") is not None:
        continue
    if (person.get("age") or 0) < 15:      # children are a different GHS code
        continue
    before[person.get("attitude_match_quality")] += 1
    person["employment_status"] = STATUS
    person["employment_status_provenance"] = "ghs_2025:employ_Status2"

    donor, quality = af._match_with_backoff(person, pool, args.seed)
    full = dict(donor["attitudes"])
    per_dim = {dim: quality for dim in full}
    for dim in ada.ATTITUDE_VOCAB:
        if dim not in full:
            full[dim] = af._population_draw(dist, dim, person, args.seed) or modal[dim]
            per_dim[dim] = "population_draw"
    rows, beliefs = af._attitudes_to_fields(
        full, "afrobarometer_r9_sa", per_dim, donor.get("attitude_answers") or {})
    person["attitudes"] = rows
    person["beliefs"] = beliefs
    person["attitude_match_quality"] = quality
    after[quality] += 1
    fixed += 1

print(json.dumps({"seed": args.seed, "applied": args.apply, "personas_fixed": fixed,
                  "match_quality_before": dict(before),
                  "match_quality_after": dict(after)}, indent=2))
if args.apply:
    lib.write_bytes((json.dumps(new, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
