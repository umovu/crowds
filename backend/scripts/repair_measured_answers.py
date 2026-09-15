"""Repair the literal survey answers on the library so each belongs to the persona's own respondent.

The problem: `attach_measured_answers.py` re-matched donors with seed 0, while the
stances had been fused with seed 1. So a persona could carry one real person's stances
and a DIFFERENT real person's literal answers — only 219 of 375 personas had answers and
stances that fit a single respondent. The model is shown those answers as "your own
words in a national survey", so a mismatch is a fabricated measurement.

The fix, per persona, no model:
  * If the persona records `survey_respondent` (set by add_word_of_mouth_attitudes.py
    after a replay that reproduced every stance), look that respondent up and take each
    literal answer from them — only where their band equals the stance on file, the row
    is not a population draw, and the answer does not point the opposite way to the band.
  * Otherwise, try to identify the respondent from the stances and answers already on
    file. Exactly one match: use them, and record `survey_respondent`.
  * Anything else: remove the literal answer. A persona falls back to its belief
    sentence rather than being told words someone else said.

Only `measured_answer` / `measured_question` / `measured_asked` on attitude rows, and
`survey_respondent`, may change. Everything else is asserted byte-identical.

Usage:
    python repair_measured_answers.py            # dry run
    python repair_measured_answers.py --apply    # backs up, then writes
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import attitude_donor_adapter as ada

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "app/data/persona_library/personas.json"
SAV = ROOT / "data/microdata/attitudes/afrobarometer_r9_sa.sav"
BACKUP = LIB.with_name("personas.backup-pre-answer-repair.json")
ANSWER_KEYS = ("measured_answer", "measured_question", "measured_asked")


def repaired_rows(rows: List[Dict], donor: Optional[Dict]) -> Tuple[List[Dict], collections.Counter]:
    """Attitude rows with literal answers taken from `donor`, or removed where unprovable."""
    stats: collections.Counter = collections.Counter()
    out = []
    answers = (donor or {}).get("attitude_answers") or {}
    bands = (donor or {}).get("attitudes") or {}
    for row in rows:
        new = {k: v for k, v in row.items() if k not in ANSWER_KEYS}
        had = bool(row.get("measured_answer"))
        topic, stance = row.get("topic"), row.get("stance")
        ans = answers.get(topic)
        usable = (
            donor is not None
            and ans
            and row.get("match_quality") != "population_draw"
            and bands.get(topic) == stance
            and not ada.answer_contradicts_band(topic, stance, ans.get("answer_band"))
        )
        if usable:
            new["measured_answer"] = ans["answer"]
            new["measured_question"] = ans["question"]
            new["measured_asked"] = ans["asked"]
            if not had:
                stats["answers_added"] += 1
            elif row.get("measured_answer") != ans["answer"]:
                stats["answers_corrected"] += 1
            else:
                stats["answers_confirmed"] += 1
        elif had:
            stats["answers_removed"] += 1
        out.append(new)
    return out, stats


def identify(person: Dict, donors: List[Dict]) -> Optional[Dict]:
    """The one respondent whose bands AND literal answers match what the persona carries."""
    stances = {a["topic"]: a["stance"] for a in person["attitudes"]
               if a.get("match_quality") != "population_draw"}
    answers = {a["topic"]: a["measured_answer"] for a in person["attitudes"]
               if a.get("measured_answer")}
    if not answers:
        return None
    hits = [d for d in donors
            if all(d["attitudes"].get(t) == s for t, s in stances.items())
            and all((d.get("attitude_answers") or {}).get(t, {}).get("answer") == v
                    for t, v in answers.items())]
    return hits[0] if len(hits) == 1 else None


def protected_bytes(payload) -> bytes:
    clone = copy.deepcopy(payload)
    for p in clone["personas"]:
        p.pop("survey_respondent", None)
        p["attitudes"] = [{k: v for k, v in a.items() if k not in ANSWER_KEYS}
                          for a in p.get("attitudes", [])]
    return json.dumps(clone, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    raw = LIB.read_bytes()
    payload = json.loads(raw)
    donors = ada.load_afrobarometer(str(SAV))
    by_id = {d["respondent"]: d for d in donors if d.get("respondent")}

    result = copy.deepcopy(payload)
    totals: collections.Counter = collections.Counter()
    for person in result["personas"]:
        resp = person.get("survey_respondent")
        donor = by_id.get(resp) if resp else None
        if resp and donor is None:
            raise SystemExit(f"{person.get('name')}: respondent {resp} not in the survey file")
        if donor is not None:
            totals["people_by_recorded_respondent"] += 1
        else:
            donor = identify(person, donors)
            if donor is not None:
                person["survey_respondent"] = donor["respondent"]
                totals["people_identified_from_answers"] += 1
            else:
                totals["people_unprovable"] += 1
        person["attitudes"], stats = repaired_rows(person["attitudes"], donor)
        totals.update(stats)
        if any(stats[k] for k in ("answers_corrected", "answers_removed", "answers_added")):
            totals["people_changed"] += 1

    assert protected_bytes(result) == protected_bytes(payload), "a protected field changed"

    report = {"apply": args.apply, "model_calls": 0, "personas": len(payload["personas"]),
              **totals, "before_sha256": hashlib.sha256(raw).hexdigest()}
    if args.apply:
        if BACKUP.exists():
            raise SystemExit(f"{BACKUP.name} already exists; refusing to overwrite")
        BACKUP.write_bytes(raw)
        if LIB.read_bytes() != raw:
            raise SystemExit("library changed during the run; nothing written")
        LIB.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["backup"] = BACKUP.name
        report["after_sha256"] = hashlib.sha256(LIB.read_bytes()).hexdigest()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
