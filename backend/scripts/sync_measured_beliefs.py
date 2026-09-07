"""Repair only deterministic survey belief sentences after an attitude refresh.

No model calls. Unknown prose is retained for separate review. Back up before
applying; refuse to overwrite an existing backup or aggregate report.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from attitude_fuser import _BELIEF_PHRASING


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sync_person(person):
    result = copy.deepcopy(person)
    rows = person.get("attitudes", [])
    topics = [row["topic"] for row in rows]
    if len(topics) != len(set(topics)):
        raise ValueError("Duplicate attitude topics")
    known = {sentence for topic in topics for sentence in _BELIEF_PHRASING.get(topic, {}).values()}
    current = [_BELIEF_PHRASING[row["topic"]][row["stance"]] for row in rows
               if row["stance"] in _BELIEF_PHRASING.get(row["topic"], {})]
    old = person.get("beliefs", [])
    if not isinstance(old, list) or any(not isinstance(b, str) for b in old):
        raise ValueError("Beliefs must be a list of strings")
    # Keep the original order when all statements already agree.
    if set(b for b in old if b in known) == set(current):
        return result
    result["beliefs"] = current + [b for b in old if b not in known]
    return result


def without_beliefs(payload):
    result = copy.deepcopy(payload)
    for person in result["personas"]:
        person.pop("beliefs", None)
    return canonical(result)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    library = root / "app/data/persona_library/personas.json"
    backup = library.with_name("personas.backup-pre-belief-sync.json")
    report = root / "scripts/out/belief_sync_results.json"
    raw = library.read_bytes()
    old = json.loads(raw)
    new = copy.deepcopy(old)
    new["personas"] = [sync_person(p) for p in old["personas"]]
    assert without_beliefs(old) == without_beliefs(new)
    assert all(sync_person(p) == p for p in new["personas"])
    updated = (json.dumps(new, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    sha = lambda data: hashlib.sha256(data).hexdigest()
    result = {"applied": args.apply, "model_calls": 0, "personas": len(old["personas"]),
              "changed_personas": sum(a != b for a,b in zip(old["personas"],new["personas"])),
              "before_sha256": sha(raw), "proposed_after_sha256": sha(updated),
              "non_belief_fields_sha256": sha(without_beliefs(new)),
              "all_other_fields_unchanged": True,
              "remaining_known_sentence_conflicts": 0,
              "limitation": "Custom beliefs and narrative prose are preserved, not semantically validated; live service not refreshed."}
    if args.apply:
        if backup.exists() or report.exists():
            raise SystemExit("Backup or report exists; refusing overwrite")
        with backup.open("xb") as f:
            f.write(raw)
        temporary = library.with_name("personas.belief-sync.tmp")
        with temporary.open("xb") as f:
            f.write(updated)
        if library.read_bytes() != raw:
            raise SystemExit("Library changed during repair; original retained")
        temporary.replace(library)
        result["after_sha256"] = sha(library.read_bytes())
        report.write_text(json.dumps(result,indent=2) + "\n",encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
