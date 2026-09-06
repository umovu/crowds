# Realism test repair: proof of work

## Data-reader limitation

The existing education reader rejects 0 respondents with valid Q94 education codes. See education_decode_audit in the JSON.
No valid education qualifications rejected. Remaining demographic exclusions and diagnostic limitations still apply.

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

Real: 1580 total, 1551 with usable keys. Library: 375 total, 344 with usable keys.
Excluded-key counts: `{"real": {"education_band": 13, "employment_status": 10, "education_band + employment_status": 2, "race": 4}, "library": {"employment_status": 31}}`.
All 15 existing attitude dimensions were included; none was dropped because of its result.
R9 uses its survey weights. Raw library uses equal weights. Balanced library matches the six R9 demographic margins.
Each dimension also uses 50 same-size R9 subsets drawn uniformly without replacement, keeping their survey weights.
Subset ranges describe sensitivity to sample size and selection; they are not confidence intervals.
These targets describe complete-key R9 respondents, not the entire country or R10.
Weight fitting: **converged**. Effective library size: 170.9406282392709.

## Results

| Attitude | Real full % | Real same-size median % | Real subset 5th-95th % | Library raw % | Library balanced % | Warning |
|---|---:|---:|---:|---:|---:|---|
| gov_trust | -9.98 | -12.69 | -16.88 to -5.76 | 2.27 | -3.87 | below warning rule |
| economic_optimism | -11.38 | -10.43 | -15.45 to -4.96 | -3.75 | -5.51 | below warning rule |
| service_satisfaction | -11.53 | -10.65 | -18.10 to -3.03 | 1.70 | -1.93 | below warning rule |
| crime_fear | -7.84 | -7.75 | -15.73 to -2.42 | 4.31 | 0.62 | below warning rule |
| education_satisfaction | -12.30 | -12.93 | -19.77 to -4.13 | -1.56 | -5.07 | below warning rule |
| health_service_satisfaction | -11.94 | -14.36 | -18.63 to -9.18 | -2.44 | -2.46 | investigate |
| health_authority_trust | -14.14 | -13.98 | -19.31 to -6.68 | -2.84 | -6.76 | below warning rule |
| councillor_responsiveness | -14.33 | -12.15 | -18.20 to -6.50 | -4.97 | -8.23 | below warning rule |
| official_responsiveness | -10.04 | -10.45 | -17.96 to -6.42 | 4.39 | -6.67 | below warning rule |
| crime_handling | -12.62 | -13.19 | -19.22 to -7.44 | -3.33 | -4.08 | below warning rule |
| immigration_priority | -13.68 | -14.28 | -23.03 to -6.87 | 1.17 | -5.03 | below warning rule |
| pays_for_quality | -12.28 | -14.20 | -21.44 to -5.91 | -6.04 | -12.08 | below warning rule |
| business_trust | -11.10 | -12.06 | -21.20 to -7.20 | 5.25 | -3.91 | below warning rule |
| social_trust | -12.79 | -12.60 | -17.17 to -6.27 | -0.90 | -6.10 | below warning rule |
| environment_priority | -7.30 | -11.94 | -18.68 to -6.16 | 0.04 | -5.45 | below warning rule |

**1 of 15 dimensions met the warning rule; 0 were inconclusive.**

Below the warning rule is not proof of realism. A warning does not identify which mechanism caused the pattern.
## Missing opinions

Stored attitude source-quality tags across all personas: `{"exact": 3872, "population_draw": 158, "age_backoff": 964, "education_backoff": 174, "race_only": 457}`.
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

[Full machine-readable results](realism_repair_results_q94_fixed.json), including input hashes, coverage, missingness and sample weights.
[Exact commands and terminal output](realism_repair_terminal_q94_fixed.txt). Tests and source line references are appended after verification.
Input hashes were compared before/after: persona library, survey file, frozen question files and method were unchanged.
Old r10_identical_people outputs were preserved. Model calls during this diagnostic: **0**. No input files changed during this invocation. The preceding attitude refresh is documented in [EDUCATION_FIX_POW.md](EDUCATION_FIX_POW.md).
