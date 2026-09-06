# Realism test repair: proof of work

## Important data-reader finding

A follow-up metadata check found a definite bug in the existing education reader.
R9 code 8 means **University completed** (141 people), and code 9 means
**Post-graduate** (36 people). The generic missing-value list contains 8 and 9,
so `_ab_education_band` rejects all **177** valid qualifications. The evidence
is now in `education_decode_audit` in the JSON and the terminal record below.

The reported five warnings apply only to the sample the current reader kept.
**Fix this education decoder and rerun the same fixed method before using those
warnings to justify persona changes.** The test calculation is repaired, but
its source reader still restricts the comparison. The decoder and existing
persona data were left unchanged in this task; no results were quietly replaced
with a different sample. The audit was added after the initial run, and the
method, warning thresholds and all 15 calculated results remain unchanged.

## Findings in plain words

The test is repaired and has run. **Five attitudes need closer review:** government
trust, satisfaction with basic services, fear of crime, satisfaction with health
services, and views on immigration. They differ from the real-person comparison
under the warning rules written before the run. This does not prove they are wrong.

Most demographic predictions still did worse than using the overall answer mix.
Only basic-service satisfaction and fear of crime beat that simple baseline in
the balanced library. A warning can therefore mean "less hard to predict than
real people", even when the prediction itself is weak. It does not mean we can
accurately predict a person's views from their background.

Room balance matters. For example, the result for official responsiveness moved
from +9.82% error reduction to -3.46% after balancing. The adjustments leave 344
usable personas with a weighted effective size of about 160; uneven weights
reduce how much information that room carries. This is a limit, not a change to
the actual number of personas.

There were 163 stored attitude entries tagged `population_draw`, out of 5,625
entries across the library (2.90%). The 344 included personas had no missing
attitude bands, while real respondents did. The stored tags show recorded
filling; they do not reveal exactly which original answers were refusals.

**Next useful work:** repair the education decoder, rerun this same method,
then inspect donor reuse and missing-answer filling where warnings persist. Do not rebuild personas based on these flags alone. The paid R10
answer test remains unrun, and no overall accuracy claim is supported.

## What changed

The repaired test hides each person's answer and predicts its category using other people only.
It compares the same stored attitude bands on both sides. A tiny group cannot predict itself.
This measures how strongly attitudes follow demographics, not whether simulated answers are accurate.

## Rules fixed before results

Method SHA256: `9491eb81b555eab97039d1a2ce63d46bdea5600d1fcbc8621e2650bbb8748c21`.
See [REALISM_REPAIR_METHOD.json](REALISM_REPAIR_METHOD.json) for the full predeclared method.
At least five other observed people and effective training size three are required for a demographic group.
Otherwise the test tries the next shipping matching rung, ultimately falling back to the other-person population.
Both the group prediction and population baseline exclude the person being tested.
Error is the sum of squared differences between predicted category probabilities and the actual category (Brier loss).
The table shows percentage error reduction versus the population baseline; negative values mean worse predictions.
A warning needs a balanced-library reduction at least 10 points above the size-matched real median, above its 95th percentile,
and above the shuffled-library 95th percentile. It also needs 50% nonpopulation prediction coverage and effective sample size 25% of the library.
These are predeclared investigation rules, not a validated safety threshold or significance test.

## What was measured

Real: 1580 total, 1382 with usable keys. Library: 375 total, 344 with usable keys.
Excluded-key counts: `{"real": {"education_band": 182, "employment_status": 4, "education_band + employment_status": 8, "race + education_band": 2, "race": 2}, "library": {"employment_status": 31}}`.
All 15 existing attitude dimensions were included; none was dropped because of its result.
R9 uses its survey weights. Raw library uses equal weights. Balanced library matches the six R9 demographic margins.
Each dimension also uses 50 same-size R9 subsets drawn uniformly without replacement, keeping their survey weights.
Subset ranges describe sensitivity to sample size and selection; they are not confidence intervals.
These targets describe complete-key R9 respondents, not the entire country or R10.
Weight fitting: **converged**. Effective library size: 160.0027151674767.

## Results

| Attitude | Real full % | Real same-size median % | Real subset 5th-95th % | Library raw % | Library balanced % | Warning |
|---|---:|---:|---:|---:|---:|---|
| gov_trust | -10.92 | -12.62 | -18.37 to -8.23 | -0.23 | -2.45 | investigate |
| economic_optimism | -13.57 | -11.91 | -16.71 to -6.95 | -1.84 | -8.05 | below warning rule |
| service_satisfaction | -9.29 | -10.39 | -16.48 to -3.82 | 5.16 | 1.53 | investigate |
| crime_fear | -8.88 | -10.46 | -17.55 to -4.64 | 2.97 | 1.35 | investigate |
| education_satisfaction | -11.95 | -14.16 | -17.85 to -6.59 | 0.69 | -6.39 | below warning rule |
| health_service_satisfaction | -12.28 | -14.63 | -18.94 to -9.46 | -0.29 | -3.32 | investigate |
| health_authority_trust | -12.59 | -14.11 | -19.82 to -9.45 | -0.17 | -5.30 | below warning rule |
| councillor_responsiveness | -15.06 | -11.50 | -17.54 to -6.41 | -6.76 | -6.92 | below warning rule |
| official_responsiveness | -7.76 | -10.00 | -15.26 to -3.64 | 9.82 | -3.46 | below warning rule |
| crime_handling | -13.93 | -14.51 | -19.16 to -7.61 | -4.17 | -7.11 | below warning rule |
| immigration_priority | -13.28 | -13.58 | -21.30 to -7.04 | 1.69 | -2.20 | investigate |
| pays_for_quality | -12.16 | -12.67 | -19.94 to -7.53 | -3.40 | -9.85 | below warning rule |
| business_trust | -11.13 | -11.52 | -16.83 to -7.15 | -0.73 | -5.01 | below warning rule |
| social_trust | -12.20 | -12.70 | -18.43 to -6.43 | -3.10 | -8.29 | below warning rule |
| environment_priority | -8.30 | -12.67 | -17.17 to -8.15 | -2.83 | -7.19 | below warning rule |

**5 of 15 dimensions met the warning rule; 0 were inconclusive.**

Below the warning rule is not proof of realism. A warning does not identify which mechanism caused the pattern.

## Missing opinions

Stored attitude source-quality tags across all personas: `{"exact": 3510, "population_draw": 163, "age_backoff": 1010, "race_only": 683, "education_backoff": 214, "province_backoff": 45}`.
Per-dimension missing-band counts and real weighted missing rates are in the results JSON.
Population-draw/fallback tags show recorded filling, but cannot recover each original refusal or don't-know response.
Some composites remain populated when one source answer is missing; missing-band rates are not raw refusal rates.

## Limits and next step

The repair removes self-prediction and the singleton inflation mechanism. Tests cover singleton-only data and true group patterns.
It uses the shipping matching ladder, which was previously tuned on R9; these results are not a fresh external validation.
Raking fixes marginal balance only, not all demographic combinations, omitted traits, or shared-donor dependence.
Repeated donor use may make persona answers dependent; stable donor identifiers are not available here to split by donor.
Shuffled references are sensitivity checks, not formal multiple-comparison-adjusted significance tests.
Missing demographic keys limit coverage. No population-wide claim is made for excluded people.
Investigate flagged dimensions and stored matching provenance before changing donor assignments. No automatic fixes were applied.
No paid model call is authorised by this diagnostic; the frozen R10 questions remain a separate, unrun answer test.

## Evidence

[Full machine-readable results](realism_repair_results.json), including input hashes, coverage, missingness and sample weights.
[Exact commands and terminal output](realism_repair_terminal.txt). Tests and source line references are appended after verification.
Input hashes were compared before/after: persona library, survey file, frozen question files and method were unchanged.
Old r10_identical_people outputs were preserved. Model calls: **0**. No personas generated, edited, or re-fused.

## Files and verification

- `backend/scripts/check_r10_realism.py:154`: `prediction_weights`.
- `backend/scripts/check_r10_realism.py:194`: `heldout_reduction`.
- `backend/scripts/check_r10_realism.py:215`: `balance_weights`.
- `backend/scripts/check_r10_realism.py:273`: `repaired_main`.
- `backend/tests/test_realism_repair.py:11`: `test_singletons_`.
- `backend/tests/test_realism_repair.py:20`: `test_own_answer_`.
- `backend/tests/test_realism_repair.py:29`: `test_real_group_`.
- `backend/tests/test_realism_repair.py:37`: `test_small_or_`.
- `backend/tests/test_realism_repair.py:53`: `test_balance_matches_`.
- `backend/tests/test_realism_repair.py:63`: `test_balance_does_not_`.

The test script covers nine new tests: singleton fallback, self-answer
exclusion, recoverable true group signal, rejection of balanced noise, tiny and
weight-dominated groups, undefined constant-answer results, demographic weight
fitting, and unsupported categories. Bad input weights are also rejected.

**15 tests passed**, including the six existing R10 regression tests. Both model
keys were unset. Method digest and unchanged input digests are recorded in the
results JSON. The old report and frozen R10 question list were not regenerated.

The run used this command:

```powershell
& backend/.venv/Scripts/python.exe -B backend/scripts/check_r10_realism.py --repaired
```

The code regenerates the calculation report; this final POW adds the reviewed
plain-language interpretation and terminal evidence. Keep this dated evidence
with the saved results when running a future method version.

## Exact terminal evidence

```text

$ D:\Fub-agentsociety\backend\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider backend/tests/test_realism_repair.py backend/tests/test_r10_validation.py
LLM_API_KEY and SIM_LLM_API_KEY unset
..............                                                           [100%]
14 passed in 1.41s

exit_code=0

$ D:\Fub-agentsociety\backend\.venv\Scripts\python.exe -B backend/scripts/check_r10_realism.py --repaired
LLM_API_KEY and SIM_LLM_API_KEY unset
## Results

| Attitude | Real full % | Real same-size median % | Real subset 5th-95th % | Library raw % | Library balanced % | Warning |
|---|---:|---:|---:|---:|---:|---|
| gov_trust | -10.92 | -12.62 | -18.37 to -8.23 | -0.23 | -2.45 | investigate |
| economic_optimism | -13.57 | -11.91 | -16.71 to -6.95 | -1.84 | -8.05 | below warning rule |
| service_satisfaction | -9.29 | -10.39 | -16.48 to -3.82 | 5.16 | 1.53 | investigate |
| crime_fear | -8.88 | -10.46 | -17.55 to -4.64 | 2.97 | 1.35 | investigate |
| education_satisfaction | -11.95 | -14.16 | -17.85 to -6.59 | 0.69 | -6.39 | below warning rule |
| health_service_satisfaction | -12.28 | -14.63 | -18.94 to -9.46 | -0.29 | -3.32 | investigate |
| health_authority_trust | -12.59 | -14.11 | -19.82 to -9.45 | -0.17 | -5.30 | below warning rule |
| councillor_responsiveness | -15.06 | -11.50 | -17.54 to -6.41 | -6.76 | -6.92 | below warning rule |
| official_responsiveness | -7.76 | -10.00 | -15.26 to -3.64 | 9.82 | -3.46 | below warning rule |
| crime_handling | -13.93 | -14.51 | -19.16 to -7.61 | -4.17 | -7.11 | below warning rule |
| immigration_priority | -13.28 | -13.58 | -21.30 to -7.04 | 1.69 | -2.20 | investigate |
| pays_for_quality | -12.16 | -12.67 | -19.94 to -7.53 | -3.40 | -9.85 | below warning rule |
| business_trust | -11.13 | -11.52 | -16.83 to -7.15 | -0.73 | -5.01 | below warning rule |
| social_trust | -12.20 | -12.70 | -18.43 to -6.43 | -3.10 | -8.29 | below warning rule |
| environment_priority | -8.30 | -12.67 | -17.17 to -8.15 | -2.83 | -7.19 | below warning rule |

**5 of 15 dimensions met the warning rule; 0 were inconclusive.**

Below the warning rule is not proof of realism. A warning does not identify which mechanism caused the pattern.
Method SHA256: 9491eb81b555eab97039d1a2ce63d46bdea5600d1fcbc8621e2650bbb8748c21
Usable rows: real=1382/1580, library=344/375; balance=converged
Input hashes unchanged; model calls=0
POW: backend/scripts/out/REALISM_REPAIR_POW.md

exit_code=0

Post-run education metadata audit:
$ D:\Fub-agentsociety\backend\.venv\Scripts\python.exe -B -c "import sys; sys.path.insert(0,'backend/scripts'); import pyreadstat,json; from check_r10_realism import education_decode_audit; df,meta=pyreadstat.read_sav('backend/data/microdata/attitudes/afrobarometer_r9_sa.sav',usecols=['Q94']); print(json.dumps(education_decode_audit(df,meta),indent=2))"
{
  "rows": [
    {
      "code": -1.0,
      "label": "Missing",
      "n": 0,
      "decoded": null,
      "valid_education_rejected": false
    },
    {
      "code": 0.0,
      "label": "No formal schooling",
      "n": 43,
      "decoded": "none",
      "valid_education_rejected": false
    },
    {
      "code": 1.0,
      "label": "Informal schooling only (including Koranic schooling)",
      "n": 7,
      "decoded": "none",
      "valid_education_rejected": false
    },
    {
      "code": 2.0,
      "label": "Some primary schooling",
      "n": 55,
      "decoded": "primary",
      "valid_education_rejected": false
    },
    {
      "code": 3.0,
      "label": "Primary school completed",
      "n": 126,
      "decoded": "primary",
      "valid_education_rejected": false
    },
    {
      "code": 4.0,
      "label": "Intermediate school or Some secondary school / high school",
      "n": 360,
      "decoded": "secondary",
      "valid_education_rejected": false
    },
    {
      "code": 5.0,
      "label": "Secondary school / high school completed",
      "n": 555,
      "decoded": "secondary",
      "valid_education_rejected": false
    },
    {
      "code": 6.0,
      "label": "Post-secondary qualifications, other than university e.g. a diploma or degree from a polytechnic or college",
      "n": 184,
      "decoded": "tertiary",
      "valid_education_rejected": false
    },
    {
      "code": 7.0,
      "label": "Some university",
      "n": 58,
      "decoded": "tertiary",
      "valid_education_rejected": false
    },
    {
      "code": 8.0,
      "label": "University completed",
      "n": 141,
      "decoded": null,
      "valid_education_rejected": true
    },
    {
      "code": 9.0,
      "label": "Post-graduate",
      "n": 36,
      "decoded": null,
      "valid_education_rejected": true
    },
    {
      "code": 98.0,
      "label": "Refused",
      "n": 11,
      "decoded": null,
      "valid_education_rejected": false
    },
    {
      "code": 99.0,
      "label": "Don\u2019t know",
      "n": 4,
      "decoded": null,
      "valid_education_rejected": false
    }
  ],
  "valid_education_rejected_n": 177
}

exit_code=0

$ D:\Fub-agentsociety\backend\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider backend/tests/test_realism_repair.py backend/tests/test_r10_validation.py
LLM_API_KEY and SIM_LLM_API_KEY unset
...............                                                          [100%]
15 passed in 1.65s

exit_code=0

```
