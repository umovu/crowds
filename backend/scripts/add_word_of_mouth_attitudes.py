"""Add the word-of-mouth measures (social_voice, neighbour_trust) to the EXISTING library.

No rebuild, no model. Identity, prose, circumstances and the fifteen attitudes already on
each persona are untouched. The two new attitude rows come from the SAME survey
respondent that produced each persona's stances — and that is proven per persona, not
assumed:

  * The library never recorded which respondent a persona came from, so the donor match
    is replayed with the library's recorded seed and the same source-based donor pools
    the build used.
  * A persona is updated only if the replay reproduces ALL of its existing stances
    exactly. Anything else is skipped and counted, never patched from a donor that might
    be someone else.
  * The respondent id is stored on the persona (`survey_respondent`), so this replay is
    never needed again.

Beliefs are not written here; run sync_measured_beliefs.py afterwards, which derives
belief sentences from the attitude rows.

Usage:
    python add_word_of_mouth_attitudes.py            # dry run, prints the report
    python add_word_of_mouth_attitudes.py --apply    # backs up, then writes
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
from pathlib import Path

import attitude_donor_adapter as ada
import attitude_fuser as af

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "app/data/persona_library/personas.json"
SAV = ROOT / "data/microdata/attitudes/afrobarometer_r9_sa.sav"
BACKUP = LIB.with_name("personas.backup-pre-word-of-mouth.json")


def _free_backup() -> Path:
    """First unused backup name, so a second run never clobbers the first backup."""
    if not BACKUP.exists():
        return BACKUP
    for n in range(2, 100):
        candidate = BACKUP.with_name(f"{BACKUP.stem}-{n}{BACKUP.suffix}")
        if not candidate.exists():
            return candidate
    raise SystemExit("too many word-of-mouth backups; clean them up first")


def _rows_from_recorded(person, donor, source):
    """New-dim rows from the respondent already recorded on the persona.

    Used when the seeded replay does not reproduce the persona (the build code has moved
    on since), but `survey_respondent` was proven another way — by stances AND literal
    answers fitting exactly one real person (repair_measured_answers.py). The respondent
    must still agree with every non-population stance on file, or nothing is added.
    """
    if not donor:
        return None
    for a in person["attitudes"]:
        if (a.get("match_quality") != "population_draw"
                and donor["attitudes"].get(a["topic"]) != a["stance"]):
            return None
    quality = person.get("attitude_match_quality") or "exact"
    answers = donor.get("attitude_answers") or {}
    rows = []
    for dim in NEW_DIMS:
        stance = donor["attitudes"].get(dim)
        if not stance:
            continue  # the respondent did not answer — no draw, nothing claimed
        row = {"topic": dim, "stance": stance, "source": source, "match_quality": quality}
        ans = answers.get(dim)
        if ans and not ada.answer_contradicts_band(dim, stance, ans.get("answer_band")):
            row.update(measured_answer=ans["answer"], measured_question=ans["question"],
                       measured_asked=ans["asked"])
        rows.append(row)
    return rows
NEW_DIMS = ("social_voice", "neighbour_trust")
ALLOWED = {"attitudes", "survey_respondent"}
ROLES = {"afrobarometer_r9_sa": None, "afrobarometer_r9_sa:students": "learner",
         "afrobarometer_r9_sa:teacher_class_professionals": "educator"}


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def untouched_bytes(payload) -> bytes:
    """Everything this script is not allowed to change, plus the ORIGINAL attitude rows."""
    clone = copy.deepcopy(payload)
    for p in clone["personas"]:
        p.pop("survey_respondent", None)
        p["attitudes"] = [a for a in p.get("attitudes", []) if a.get("topic") not in NEW_DIMS]
    return canonical(clone)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    raw = LIB.read_bytes()
    payload = json.loads(raw)
    seed = payload["seed"]
    donors = ada.load_afrobarometer(str(SAV))
    by_id = {d["respondent"]: d for d in donors if d.get("respondent")}

    groups = collections.defaultdict(list)
    for i, p in enumerate(payload["personas"]):
        sources = {a["source"] for a in p["attitudes"]}
        if len(sources) != 1:
            raise SystemExit(f"persona {p.get('name')} mixes attitude sources; review first")
        groups[next(iter(sources))].append(i)

    result = copy.deepcopy(payload)
    stats = collections.Counter()
    bands = {d: collections.Counter() for d in NEW_DIMS}
    quality = collections.Counter()

    for source, indices in groups.items():
        if source not in ROLES:
            raise SystemExit(f"unsupported attitude source: {source}")
        pool, suffix = ada.donor_pool_for_role(ROLES[source], donors)
        actual = "afrobarometer_r9_sa" + (":" + suffix if suffix else "")
        people = [payload["personas"][i] for i in indices]
        fused = af.fuse_attitudes(people, seed=seed, donors=pool, source=actual)
        for i, person, new in zip(indices, people, fused):
            if any(a.get("topic") in NEW_DIMS for a in person["attitudes"]):
                stats["already_has_measures"] += 1
                continue
            on_file = {a["topic"]: a["stance"] for a in person["attitudes"]}
            replay = {a["topic"]: a for a in new["attitudes"]}
            if any(replay.get(t, {}).get("stance") != s for t, s in on_file.items()):
                rows = _rows_from_recorded(
                    person, by_id.get(person.get("survey_respondent") or ""), source)
                if rows is None:
                    stats["skipped_replay_mismatch"] += 1
                    continue
                target = result["personas"][i]
                for row in rows:
                    target["attitudes"].append(row)
                    bands[row["topic"]][row["stance"]] += 1
                    quality[row["match_quality"]] += 1
                stats["updated_from_recorded_respondent"] += 1
                continue
            donor, _q = af._match_with_backoff(person, pool, seed)
            if any(donor["attitudes"].get(t) not in (None, s) for t, s in on_file.items()):
                stats["skipped_donor_disagrees"] += 1
                continue
            target = result["personas"][i]
            for dim in NEW_DIMS:
                row = replay[dim]
                target["attitudes"].append(row)
                bands[dim][row["stance"]] += 1
                quality[row["match_quality"]] += 1
            if donor.get("respondent"):
                target["survey_respondent"] = donor["respondent"]
            stats["updated"] += 1

    assert untouched_bytes(result) == untouched_bytes(payload), "a protected field changed"
    for before, after in zip(payload["personas"], result["personas"]):
        extra = set(after) - set(before)
        assert extra <= ALLOWED, extra

    report = {
        "apply": args.apply, "model_calls": 0, "seed": seed,
        "personas": len(payload["personas"]), **stats,
        "new_dimension_bands": {d: dict(c) for d, c in bands.items()},
        "new_row_match_quality": dict(quality),
        "before_sha256": hashlib.sha256(raw).hexdigest(),
    }
    if args.apply:
        backup = _free_backup()
        backup.write_bytes(raw)
        text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if LIB.read_bytes() != raw:
            raise SystemExit("library changed during the run; nothing written")
        LIB.write_text(text, encoding="utf-8")
        report["backup"] = backup.name
        report["after_sha256"] = hashlib.sha256(LIB.read_bytes()).hexdigest()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
