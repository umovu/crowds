# Education fix: proof of work

## Main finding

**The direction stayed at 15/15 before and 15/15 after: the library remains more predictable from demographics than real people in this diagnostic.**
The count moved by 0. This holds against both the full real sample and the same-size real median.
Warnings fell from 5 to 1; that is secondary to the unchanged direction. Only health-service satisfaction remains flagged.
These measures describe demographic predictability, not accuracy or a realism score. A changed number does not prove the repair improved realism.

## What was fixed

Q94 now has its own missing codes (-1, 98, 99). Codes 8 and 9 are tertiary qualifications.
The shared missing-code set and Q93B occupation handling were not changed.
Valid education rejections: 177 -> 0.
Donors: 1384 -> 1555; skipped: 196 -> 25.
Tertiary donors: 239 -> 410. Other education-band counts stayed the same.
The pool gained 171, not all 177, because {'employment_status': 6} still fail other donor eligibility checks.

## Library refresh

Refreshed the local private library using its recorded seed 1 and existing source/pool routing; no identity generation.
Stored library -> refreshed: 87 personas and 745 attitude values changed.
**Zero non-attitude fields changed.** All identity, financial, circumstance and prose values remain byte-identical when canonically encoded as UTF-8 JSON.
Before/after non-attitude SHA256: `374345f7285b5883e9d44c9107f04f03e7694e3e260ba3662577db0d700f4a3b`.
Only `attitudes` and `attitude_match_quality` were copied from fusion output. Persona order and library metadata also stayed unchanged.
Exact original-file backup: `backend/app/data/persona_library/personas.backup-pre-q94-education-fix.json`; SHA256 `71ac42b1ad09c33059b31b10155d4b88596f26b27d21006e91c2dbe980766326`.
Private backups and the refreshed library are not published in Git.

| Matching tag | Old entries | New entries | Change |
|---|---:|---:|---:|
| exact | 3510 | 3872 | +362 |
| age_backoff | 1010 | 964 | -46 |
| race_only | 683 | 457 | -226 |
| education_backoff | 214 | 174 | -40 |
| province_backoff | 45 | 0 | -45 |
| population_draw | 163 | 158 | -5 |

## Attribution and remaining limits

The stored library was not an exact replay of the current matching code even before this fix:
16 personas / 143 values already differed.
Comparing controlled old-pool and new-pool replays isolates 72 personas / 607 values attributable to the decoder/pool change under current code.
These counts overlap and must not be added. The full stored-to-refreshed difference is not solely a decoder effect.
For 86 personas, the fuser's newly derived belief text would differ from the preserved text.
The plan permits only attitude values/provenance to change, so belief prose and circumstances were deliberately retained. Their consistency with refreshed attitudes is not established by this work.
Shared-donor dependence and demographic combinations are still not fully controlled. Fifteen same-direction dimensions are not fifteen independent significance tests.
The decoder error is fixed; these diagnostics still do not grant a paid-test pass or establish product accuracy.

## All 15 dimensions, before and after

Values are percentage reduction in held-out category-prediction error versus the population baseline. Negative means worse than the baseline.
| Attitude | Old library balanced % | New library balanced % | Old real same-size % | New real same-size % | Old warning | New warning |
|---|---:|---:|---:|---:|---|---|
| gov_trust | -2.45 | -3.87 | -12.62 | -12.69 | yes | no |
| economic_optimism | -8.05 | -5.51 | -11.91 | -10.43 | no | no |
| service_satisfaction | 1.53 | -1.93 | -10.39 | -10.65 | yes | no |
| crime_fear | 1.35 | 0.62 | -10.46 | -7.75 | yes | no |
| education_satisfaction | -6.39 | -5.07 | -14.16 | -12.93 | no | no |
| health_service_satisfaction | -3.32 | -2.46 | -14.63 | -14.36 | yes | yes |
| health_authority_trust | -5.30 | -6.76 | -14.11 | -13.98 | no | no |
| councillor_responsiveness | -6.92 | -8.23 | -11.50 | -12.15 | no | no |
| official_responsiveness | -3.46 | -6.67 | -10.00 | -10.45 | no | no |
| crime_handling | -7.11 | -4.08 | -14.51 | -13.19 | no | no |
| immigration_priority | -2.20 | -5.03 | -13.58 | -14.28 | yes | no |
| pays_for_quality | -9.85 | -12.08 | -12.67 | -14.20 | no | no |
| business_trust | -5.01 | -3.91 | -11.52 | -12.06 | no | no |
| social_trust | -8.29 | -6.10 | -12.70 | -12.60 | no | no |
| environment_priority | -7.19 | -5.45 | -12.67 | -11.94 | no | no |

## Coverage and locked inputs

Usable real rows: 1382/1580 -> 1551/1580.
Usable library rows: 344/375 -> 344/375.
Balance: converged -> converged. Effective library size: 160.00 -> 170.94.
Method SHA256 unchanged: `9491eb81b555eab97039d1a2ce63d46bdea5600d1fcbc8621e2650bbb8748c21`.
No thresholds, seeds, matching ladder or selected dimensions were changed. Only input data changed; `--output-tag` changes output filenames, not the calculation.
All old outputs and frozen R10 input files retain their before-fix hashes:

| Protected file | Unchanged SHA256 |
|---|---|
| REALISM_REPAIR_METHOD.json | `9491eb81b555eab97039d1a2ce63d46bdea5600d1fcbc8621e2650bbb8748c21` |
| r10_item_list.json | `d8aa93d6c8ca2028bd99d234a7b2f49fc1b8e13f10d0377460dc350df5267898` |
| r10_item_lock.json | `c238879e07515624515892e6157860683fa146488b9eaf88e1e2044ed3c80841` |
| r10_ask_scenarios.json | `48b85cd6bd7e99a641593b0bd10407fa2486b526694eebbc7f0842cd87f04e20` |
| realism_repair_results.json | `423ffd67d9926e55a915b643e7faf9d1fc5393b735853639654b56a5d2401ee5` |
| REALISM_REPAIR_POW.md | `52f80ebf49914d38b95d5c5fee97bec09d92f042b0fc7aabb6a9f27445cc6439` |
| realism_repair_terminal.txt | `6f25dc1d8cd5cb029d15375024c563874a54ffbd591b94766b1340cc9be09519` |
| r10_identical_people.json | `ab320316e999f4b66301b24ff7badbe0f84e500a7b5814607d0bf27e1ac25058` |
| r10_identical_people.md | `27669d4212082d3598140c3b9e071f356031e6cdedfcfc4ae93c3e8daa13bd2b` |

## Proof and reproduction

The education tests failed before the fix: **2 failed, 12 passed**. After the fix the focused and existing matching/realism checks gave **41 passed**, with two existing Stata text-decoding warnings.
Those warnings and the original failures are preserved, not hidden. No model calls were made; both model keys were unset for the commands.
[Exact terminal output](education_fix_terminal.txt) includes failed/passed tests, full education audits, donor counts, identity hashes, matching tags and the complete rerun table.
[Before snapshot](education_fix_before.json), [after snapshot](education_fix_after.json), [comparison data](education_fix_comparison.json).
[New calculation report](REALISM_REPAIR_POW_q94_fixed.md), [new full results](realism_repair_results_q94_fixed.json), [new calculation terminal output](realism_repair_terminal_q94_fixed.txt).
The old report and old results were retained beside these new files.

```powershell
# The snapshot step was run before modifying the decoder; never recreate it from fixed code.
python -B backend/scripts/refresh_education_attitudes.py --phase before
# After the decoder fix and tests:
python -B backend/scripts/refresh_education_attitudes.py --phase apply
python -B backend/scripts/check_r10_realism.py --repaired --output-tag q94_fixed
python -B backend/scripts/refresh_education_attitudes.py --phase report
```

The snapshot/apply phases refuse existing or changed inputs; tagged diagnostic runs refuse to overwrite existing evidence.
The private local library was updated. A running application's cached copy or any separately deployed private library was not refreshed or verified here.

### Changed code locations

- `backend/scripts/attitude_donor_adapter.py:380`: `_AB_Q94_MISSING =`
- `backend/scripts/attitude_donor_adapter.py:383`: `def _ab_education_band(`
- `backend/scripts/check_r10_realism.py:273`: `def repaired_main(`
- `backend/scripts/refresh_education_attitudes.py:65`: `def refresh(`
- `backend/scripts/refresh_education_attitudes.py:102`: `def write_report(`
- `backend/scripts/refresh_education_attitudes.py:214`: `def main(`
- `backend/tests/test_education_decode.py:11`: `def test_q94_education_codes(`
- `backend/tests/test_education_decode.py:24`: `def test_refresh_changes_only_attitude_fields(`
