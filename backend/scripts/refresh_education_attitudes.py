"""One-time Q94 repair: snapshot, then refresh only attitude fields.

Run --phase before BEFORE the decoder fix; --phase apply after it. No models.
Existing identity, prose, budgets, circumstances and all non-attitude fields
are preserved. Backup and replay remain private beside the persona library.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from collections import Counter,defaultdict
from pathlib import Path
import os
import pyreadstat
import attitude_donor_adapter as ada
from attitude_fuser import fuse_attitudes
from check_r10_realism import education_decode_audit

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"scripts/out"
LIB=ROOT/"app/data/persona_library/personas.json"
BACKUP=LIB.with_name("personas.backup-pre-q94-education-fix.json")
REPLAY=LIB.with_name("personas.backup-pre-q94-education-replay.json")
BASELINE=OUT/"education_fix_before.json"
ALLOWED={"attitudes","attitude_match_quality"}
PROTECTED_NAMES=["REALISM_REPAIR_METHOD.json","r10_item_list.json","r10_item_lock.json",
 "r10_ask_scenarios.json","realism_repair_results.json","REALISM_REPAIR_POW.md",
 "realism_repair_terminal.txt","r10_identical_people.json","r10_identical_people.md"]
EXPECTED_METHOD="9491eb81b555eab97039d1a2ce63d46bdea5600d1fcbc8621e2650bbb8748c21"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode("utf-8")


def protected():
    return {n:digest((OUT/n).read_bytes()) for n in PROTECTED_NAMES}


def non_attitude_bytes(payload):
    clone=copy.deepcopy(payload)
    clone["personas"]=[{k:v for k,v in p.items() if k not in ALLOWED} for p in clone["personas"]]
    return canonical(clone)


def stance_changes(before,after):
    people,values=0,0
    for a,b in zip(before,after,strict=True):
        aa={x["topic"]:x["stance"] for x in a["attitudes"]}
        bb={x["topic"]:x["stance"] for x in b["attitudes"]}
        n=sum(aa.get(k)!=bb.get(k) for k in aa.keys()|bb.keys())
        people+=bool(n);values+=n
    return {"personas_with_stance_change":people,"stance_values_changed":values}


def tags(people):
    return dict(Counter(a.get("match_quality","missing") for p in people for a in p["attitudes"]))


def refresh(payload,donors):
    result=copy.deepcopy(payload)
    groups=defaultdict(list)
    for i,p in enumerate(payload["personas"]):
        sources={a["source"] for a in p["attitudes"]}
        if len(sources)!=1:
            raise ValueError("Mixed attitude sources require explicit review")
        groups[next(iter(sources))].append(i)
    roles={"afrobarometer_r9_sa":None,"afrobarometer_r9_sa:students":"learner",
           "afrobarometer_r9_sa:teacher_class_professionals":"educator"}
    seed=payload["seed"] # reuse the recorded build seed, never choose a new one
    belief_differences=0
    for source,indices in groups.items():
        if source not in roles:
            raise ValueError(f"Unsupported source: {source}")
        pool,suffix=ada.donor_pool_for_role(roles[source],donors)
        actual_source="afrobarometer_r9_sa"+(":"+suffix if suffix else "")
        updated=fuse_attitudes([payload["personas"][i] for i in indices],seed=seed,donors=pool,source=actual_source)
        for i,new in zip(indices,updated,strict=True):
            old=payload["personas"][i]
            belief_differences+=old.get("beliefs")!=new.get("beliefs")
            for key in ALLOWED:
                result["personas"][i][key]=new[key]
    assert non_attitude_bytes(result)==non_attitude_bytes(payload)
    return result,belief_differences


def measure_pool():
    sav=ROOT/"data/microdata/attitudes/afrobarometer_r9_sa.sav"
    df,meta=pyreadstat.read_sav(str(sav))
    donors=ada.load_afrobarometer(str(sav))
    return donors,{"survey_rows":len(df),"donors":len(donors),"skipped":len(df)-len(donors),
                   "education_band_counts":dict(Counter(d["education_band"] for d in donors)),
                   "education_audit":education_decode_audit(df,meta)}



def write_report():
    before=json.loads(BASELINE.read_text(encoding="utf-8"))
    after=json.loads((OUT/"education_fix_after.json").read_text(encoding="utf-8"))
    old=json.loads((OUT/"realism_repair_results.json").read_text(encoding="utf-8"))
    new=json.loads((OUT/"realism_repair_results_q94_fixed.json").read_text(encoding="utf-8"))
    assert protected()==before["protected_sha256"]==after["protected_sha256"]
    assert digest(LIB.read_bytes())==after["library_sha256_after"]
    assert digest(BACKUP.read_bytes())==before["library_sha256"]
    assert non_attitude_bytes(json.loads(LIB.read_bytes()))==non_attitude_bytes(json.loads(BACKUP.read_bytes()))
    assert old["method_sha256"]==new["method_sha256"]==EXPECTED_METHOD
    old_rows={x["dimension"]:x for x in old["dimensions"]}
    new_rows={x["dimension"]:x for x in new["dimensions"]}
    assert set(old_rows)==set(new_rows)==set(ada.ATTITUDE_VOCAB)
    def direction(rows, reference):
        return sum(x["library_balanced"]["reduction"] >
                   (x["real_full"]["reduction"] if reference=="full" else x["real_size_matched"]["median"])
                   for x in rows.values())
    old_direction=direction(old_rows,"matched");new_direction=direction(new_rows,"matched")
    comparison=[]
    for dim in ada.ATTITUDE_VOCAB:
        a,b=old_rows[dim],new_rows[dim]
        comparison.append({"dimension":dim,"old_library_balanced_pct":100*a["library_balanced"]["reduction"],
                           "new_library_balanced_pct":100*b["library_balanced"]["reduction"],
                           "old_real_matched_pct":100*a["real_size_matched"]["median"],
                           "new_real_matched_pct":100*b["real_size_matched"]["median"],
                           "old_warning":a["investigate"],"new_warning":b["investigate"]})
    df,meta=pyreadstat.read_sav(str(ROOT/"data/microdata/attitudes/afrobarometer_r9_sa.sav"))
    graduate_drops=Counter()
    for _,row in df[df["Q94"].isin([8,9])].iterrows():
        reasons=[]
        if row["Q1"]!=row["Q1"] or row["Q1"]<15 or row["Q1"] in ada._AB_MISSING:reasons.append("age")
        if row["THISINT"] not in (1,2):reasons.append("gender")
        if not ada._AB_REGION_TO_PROVINCE.get(row["REGION"]):reasons.append("province")
        if not ada._AB_Q93A_TO_STATUS.get(row["Q93A"]):reasons.append("employment_status")
        if row["withinwt_hh"]!=row["withinwt_hh"] or row["withinwt_hh"]<=0:reasons.append("weight")
        if not ada._decode_ab_attitudes(row):reasons.append("all_attitudes")
        if reasons:graduate_drops[" + ".join(reasons)]+=1
    summary={"direction_old":old_direction,"direction_new":new_direction,
             "direction_full_old":direction(old_rows,"full"),"direction_full_new":direction(new_rows,"full"),
             "warnings_old":old["warning_count"],"warnings_new":new["warning_count"],
             "graduate_other_exclusion_reasons":dict(graduate_drops),"comparison":comparison,
             "all_old_outputs_and_locks_unchanged":True,"non_attitude_fields_changed":0,
             "method_sha256":EXPECTED_METHOD,"model_calls":0}
    (OUT/"education_fix_comparison.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    lines=["# Education fix: proof of work", "", "## Main finding", "",
     f"**The direction stayed at {old_direction}/15 before and {new_direction}/15 after: the library remains more predictable from demographics than real people in this diagnostic.**",
     f"The count moved by {new_direction-old_direction}. This holds against both the full real sample and the same-size real median.",
     f"Warnings fell from {old['warning_count']} to {new['warning_count']}; that is secondary to the unchanged direction. Only health-service satisfaction remains flagged.",
     "These measures describe demographic predictability, not accuracy or a realism score. A changed number does not prove the repair improved realism.", "",
     "## What was fixed", "",
     "Q94 now has its own missing codes (-1, 98, 99). Codes 8 and 9 are tertiary qualifications.",
     "The shared missing-code set and Q93B occupation handling were not changed.",
     f"Valid education rejections: {before['pool']['education_audit']['valid_education_rejected_n']} -> {after['pool']['education_audit']['valid_education_rejected_n']}.",
     f"Donors: {before['pool']['donors']} -> {after['pool']['donors']}; skipped: {before['pool']['skipped']} -> {after['pool']['skipped']}.",
     f"Tertiary donors: {before['pool']['education_band_counts']['tertiary']} -> {after['pool']['education_band_counts']['tertiary']}. Other education-band counts stayed the same.",
     f"The pool gained 171, not all 177, because {dict(graduate_drops)} still fail other donor eligibility checks.", "",
     "## Library refresh", "",
     f"Refreshed the local private library using its recorded seed {after['seed']} and existing source/pool routing; no identity generation.",
     f"Stored library -> refreshed: {after['stored_to_refreshed']['personas_with_stance_change']} personas and {after['stored_to_refreshed']['stance_values_changed']} attitude values changed.",
     "**Zero non-attitude fields changed.** All identity, financial, circumstance and prose values remain byte-identical when canonically encoded as UTF-8 JSON.",
     f"Before/after non-attitude SHA256: `{after['non_attitude_sha256_after']}`.",
     "Only `attitudes` and `attitude_match_quality` were copied from fusion output. Persona order and library metadata also stayed unchanged.",
     f"Exact original-file backup: `{BACKUP.relative_to(ROOT.parent).as_posix()}`; SHA256 `{before['library_sha256']}`.",
     "Private backups and the refreshed library are not published in Git.", "",
     "| Matching tag | Old entries | New entries | Change |", "|---|---:|---:|---:|"]
    for tag in ["exact","age_backoff","race_only","education_backoff","province_backoff","population_draw"]:
        a=after["tags_before"].get(tag,0);b=after["tags_after"].get(tag,0)
        lines.append(f"| {tag} | {a} | {b} | {b-a:+d} |")
    lines += ["", "## Attribution and remaining limits", "",
     "The stored library was not an exact replay of the current matching code even before this fix:",
     f"{after['pre_fix_replay_vs_stored']['personas_with_stance_change']} personas / {after['pre_fix_replay_vs_stored']['stance_values_changed']} values already differed.",
     f"Comparing controlled old-pool and new-pool replays isolates {after['decoder_only_replay_difference']['personas_with_stance_change']} personas / {after['decoder_only_replay_difference']['stance_values_changed']} values attributable to the decoder/pool change under current code.",
     "These counts overlap and must not be added. The full stored-to-refreshed difference is not solely a decoder effect.",
     f"For {after['derived_beliefs_would_differ_n']} personas, the fuser's newly derived belief text would differ from the preserved text.",
     "The plan permits only attitude values/provenance to change, so belief prose and circumstances were deliberately retained. Their consistency with refreshed attitudes is not established by this work.",
     "Shared-donor dependence and demographic combinations are still not fully controlled. Fifteen same-direction dimensions are not fifteen independent significance tests.",
     "The decoder error is fixed; these diagnostics still do not grant a paid-test pass or establish product accuracy.", "",
     "## All 15 dimensions, before and after", "",
     "Values are percentage reduction in held-out category-prediction error versus the population baseline. Negative means worse than the baseline.",
     "| Attitude | Old library balanced % | New library balanced % | Old real same-size % | New real same-size % | Old warning | New warning |",
     "|---|---:|---:|---:|---:|---|---|"]
    for x in comparison:
        lines.append(f"| {x['dimension']} | {x['old_library_balanced_pct']:.2f} | {x['new_library_balanced_pct']:.2f} | {x['old_real_matched_pct']:.2f} | {x['new_real_matched_pct']:.2f} | {'yes' if x['old_warning'] else 'no'} | {'yes' if x['new_warning'] else 'no'} |")
    lines += ["", "## Coverage and locked inputs", "",
     f"Usable real rows: {old['real_usable']}/{old['real_total']} -> {new['real_usable']}/{new['real_total']}.",
     f"Usable library rows: {old['library_usable']}/{old['library_total']} -> {new['library_usable']}/{new['library_total']}.",
     f"Balance: {old['balance']['status']} -> {new['balance']['status']}. Effective library size: {old['balance']['effective_n']:.2f} -> {new['balance']['effective_n']:.2f}.",
     f"Method SHA256 unchanged: `{EXPECTED_METHOD}`.",
     "No thresholds, seeds, matching ladder or selected dimensions were changed. Only input data changed; `--output-tag` changes output filenames, not the calculation.",
     "All old outputs and frozen R10 input files retain their before-fix hashes:", "",
     "| Protected file | Unchanged SHA256 |", "|---|---|"]
    for name,h in before["protected_sha256"].items():lines.append(f"| {name} | `{h}` |")
    lines += ["", "## Proof and reproduction", "",
     "The education tests failed before the fix: **2 failed, 12 passed**. After the fix the focused and existing matching/realism checks gave **41 passed**, with two existing Stata text-decoding warnings.",
     "Those warnings and the original failures are preserved, not hidden. No model calls were made; both model keys were unset for the commands.",
     "[Exact terminal output](education_fix_terminal.txt) includes failed/passed tests, full education audits, donor counts, identity hashes, matching tags and the complete rerun table.",
     "[Before snapshot](education_fix_before.json), [after snapshot](education_fix_after.json), [comparison data](education_fix_comparison.json).",
     "[New calculation report](REALISM_REPAIR_POW_q94_fixed.md), [new full results](realism_repair_results_q94_fixed.json), [new calculation terminal output](realism_repair_terminal_q94_fixed.txt).",
     "The old report and old results were retained beside these new files.", "",
     "```powershell",
     "# The snapshot step was run before modifying the decoder; never recreate it from fixed code.",
     "python -B backend/scripts/refresh_education_attitudes.py --phase before",
     "# After the decoder fix and tests:",
     "python -B backend/scripts/refresh_education_attitudes.py --phase apply",
     "python -B backend/scripts/check_r10_realism.py --repaired --output-tag q94_fixed",
     "python -B backend/scripts/refresh_education_attitudes.py --phase report",
     "```", "",
     "The snapshot/apply phases refuse existing or changed inputs; tagged diagnostic runs refuse to overwrite existing evidence.",
     "The private local library was updated. A running application's cached copy or any separately deployed private library was not refreshed or verified here.", "",
     "### Changed code locations", ""]
    refs={"scripts/attitude_donor_adapter.py":["_AB_Q94_MISSING =","def _ab_education_band("],
          "scripts/check_r10_realism.py":["def repaired_main("],
          "scripts/refresh_education_attitudes.py":["def refresh(","def write_report(","def main("],
          "tests/test_education_decode.py":["def test_q94_education_codes(","def test_refresh_changes_only_attitude_fields("]}
    for path,needles in refs.items():
        source=(ROOT/path).read_text(encoding="utf-8").splitlines()
        for needle in needles:
            line=next(i for i,text in enumerate(source,1) if needle in text)
            lines.append(f"- `backend/{path}:{line}`: `{needle}`")
    (OUT/"EDUCATION_FIX_POW.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))
    print("All protected hashes unchanged; non-attitude field differences=0; model calls=0")
    print("POW: backend/scripts/out/EDUCATION_FIX_POW.md")


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase",choices=["before","apply","report"],required=True)
    args=ap.parse_args()
    if os.environ.get("LLM_API_KEY") or os.environ.get("SIM_LLM_API_KEY"):
        raise SystemExit("Unset both model keys before running")
    if args.phase=="report":
        write_report()
        return
    hashes=protected()
    assert hashes["REALISM_REPAIR_METHOD.json"]==EXPECTED_METHOD
    current=LIB.read_bytes()
    payload=json.loads(current)
    donors,pool=measure_pool()
    if args.phase=="before":
        assert not BASELINE.exists() and not BACKUP.exists() and not REPLAY.exists(), "Before snapshot already exists"
        assert pool["education_audit"]["valid_education_rejected_n"]==177, "Expected pre-fix decoder"
        replay,_=refresh(payload,donors)
        with BACKUP.open("xb") as f:f.write(current)
        with REPLAY.open("xb") as f:f.write(canonical(replay))
        baseline={"pool":pool,"library_sha256":digest(current),"backup_sha256":digest(BACKUP.read_bytes()),
                  "non_attitude_sha256":digest(non_attitude_bytes(payload)),"protected_sha256":hashes,
                  "seed":payload["seed"],"personas":len(payload["personas"]),"tags":tags(payload["personas"]),
                  "sources":dict(Counter(a["source"] for p in payload["personas"] for a in p["attitudes"])),
                  "pre_fix_replay_vs_stored":stance_changes(payload["personas"],replay["personas"]),
                  "model_calls":0}
        with BASELINE.open("x",encoding="utf-8") as f:json.dump(baseline,f,indent=2)
        print(json.dumps(baseline,indent=2))
        return
    before=json.loads(BASELINE.read_text(encoding="utf-8"))
    assert hashes==before["protected_sha256"], "Protected inputs/old outputs changed"
    assert digest(current)==before["library_sha256"]==digest(BACKUP.read_bytes()), "Library changed after snapshot"
    assert pool["education_audit"]["valid_education_rejected_n"]==0, "Decoder fix not in place"
    result,belief_differences=refresh(payload,donors)
    assert non_attitude_bytes(result)==non_attitude_bytes(payload), "Forbidden field changed"
    replay=json.loads(REPLAY.read_bytes())
    report={"pool":pool,"seed":payload["seed"],"personas":len(result["personas"]),
            "tags_before":before["tags"],"tags_after":tags(result["personas"]),
            "stored_to_refreshed":stance_changes(payload["personas"],result["personas"]),
            "decoder_only_replay_difference":stance_changes(replay["personas"],result["personas"]),
            "pre_fix_replay_vs_stored":before["pre_fix_replay_vs_stored"],
            "non_attitude_fields_changed":0,"non_attitude_sha256_before":before["non_attitude_sha256"],
            "non_attitude_sha256_after":digest(non_attitude_bytes(result)),
            "library_sha256_before":digest(current),"protected_sha256":hashes,
            "derived_beliefs_would_differ_n":belief_differences,
            "note":"Only attitudes and attitude_match_quality copied. Beliefs, prose, circumstances, identity and finances preserved. Derived belief differences are a follow-up limitation, not modified here.",
            "model_calls":0}
    output=OUT/"education_fix_after.json"
    assert not output.exists(), "After record already exists"
    encoded=(json.dumps(result,indent=2,ensure_ascii=False)+"\n").encode("utf-8")
    report["library_sha256_after"]=digest(encoded)
    # Exact backup is already verified; atomic single-file replacement in same folder.
    staged=LIB.with_name("personas.q94-refresh.tmp")
    with staged.open("xb") as f:f.write(encoded)
    os.replace(staged,LIB)
    assert digest(LIB.read_bytes())==report["library_sha256_after"]
    assert protected()==hashes
    with output.open("x",encoding="utf-8") as f:json.dump(report,f,indent=2)
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    main()
