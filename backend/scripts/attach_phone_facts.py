"""Attach the phone facts (Q90F own phone, Q90G phone gets online, Q90H phone use) to the
EXISTING persona library, from each persona's own survey respondent.

No rebuild and no model calls. A persona gets them only when its recorded
survey_respondent still gives every circumstance it already carries (population draws
aside). Where that fails the persona is left without phone facts and counted: a phone
fact from a different person would contradict the rest of the record.

Dry run by default; --apply writes the library after backing it up.
"""
import argparse
import collections
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pyreadstat  # noqa: E402
import attitude_donor_adapter as ada  # noqa: E402

NEW_FIELDS = ("owns_phone", "phone_internet", "phone_use")


def measured_by_respondent(sav_path):
    df, _meta = pyreadstat.read_sav(sav_path)
    return {str(row.get("RESPNO") or ""): ada._decode_ab_circumstances(row) for _, row in df.iterrows()}


def attach(person, measured, stats):
    rows = person.get("circumstances") or []
    if any(r.get("field") in NEW_FIELDS for r in rows):
        stats["already_has_phone_facts"] += 1
        return
    if not measured:
        stats["respondent_not_found"] += 1
        return
    kept = [r for r in rows if r.get("match_quality") != "population_draw"]
    if not kept or any(measured.get(r["field"]) != r["value"] for r in kept):
        stats["respondent_disagrees_left_alone"] += 1
        return
    like = kept[0]
    added = 0
    for field in NEW_FIELDS:
        if measured.get(field) is None:
            stats[f"{field}_not_answered"] += 1
            continue
        rows.append({"field": field, "value": measured[field],
                     "source": like["source"], "match_quality": like["match_quality"]})
        added += 1
    stats["personas_given_phone_facts" if added else "personas_nothing_to_add"] += 1


def without_phone_facts(payload):
    p = copy.deepcopy(payload)
    for person in p["personas"]:
        if isinstance(person.get("circumstances"), list):
            person["circumstances"] = [r for r in person["circumstances"] if r.get("field") not in NEW_FIELDS]
    return json.dumps(p, sort_keys=True, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    library = root / "app/data/persona_library/personas.json"
    raw = library.read_bytes()
    data = json.loads(raw)
    by_id = measured_by_respondent(ada._AFROBAROMETER_PATH)
    new = copy.deepcopy(data)
    stats = collections.Counter()
    for person in new["personas"]:
        attach(person, by_id.get(person.get("survey_respondent") or ""), stats)
    assert without_phone_facts(data) == without_phone_facts(new), "something other than phone facts changed"
    print(json.dumps({"applied": args.apply, "model_calls": 0,
                      "personas": len(new["personas"]), **stats}, indent=2))
    if args.apply:
        backup = library.with_name("personas.backup-pre-phone-facts.json")
        if backup.exists():
            raise SystemExit(f"{backup.name} already exists; refusing to overwrite it")
        backup.write_bytes(raw)
        library.write_bytes((json.dumps(new, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
