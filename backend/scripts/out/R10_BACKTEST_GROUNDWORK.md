# R10 realism validation: groundwork and failed readiness gate

## Outcome

Items 1-3 are implemented and verified. Item 4 was measured where the data exists,
but cannot deliver its promised held-out library comparison. The requested raw
group statistic is also inflated by small cells. It does not establish whether
the library is a stereotype machine. The paid run is paused; no model calls,
no token spend, no accuracy claim, and no persona changes.

The supplied path resolved to `local-plans/REALISM_VALIDATION_PLAN.md`.
The review found issues that must be settled before spending on Item 5.

## Method and limits

- Real data: local R9 SAV, 1,580 respondents; `withinwt_hh` survey weights.
- R10: existing parsed national and subgroup percentages, 266 questions; the
  source PDF is 2,309,705 bytes. Its JSON and PDF are retained for inspection.
- Library: 375 stored personas, read only. Missing grouping keys exclude 31;
  missing R9 keys/weights exclude 198. These are not whole-population results.
- Six grouping keys come from the shipping fuser: race, gender, province,
  education band, employment status, age band. Existing employment
  canonicalisation changes were included and tested; no fusion was run.
- Weighted between-cell variance / total variance is reported exactly as asked.
  Numeric survey codes retain the original ordinal order; don't-know/refusal
  and other missing codes are excluded from that variance, and reported apart.
- For like-for-like library comparisons, real R9 answers are decoded into the
  same 15 stored attitude bands using the existing adapter. Library observations
  have equal weight. These comparisons are separate from held-out-item accuracy.
- A fixed-seed 100-permutation sensitivity check reveals how large the raw group
  statistic can be with unrelated answers. It is not a survey-adjusted p-value
  or a replacement for cross-validation. Repeated-cell results are in the JSON.

## Item 1: crosswalk

The wording floor is 0.30, alongside the existing option-set/ranking rule.
All candidate rows remain visible, with `wording_overlap` and `wording_floor`.
A confident flag remains a heuristic; hand review is still required.

Before: 102 confident rows. After: 98. Every changed row:

| R9 | R10 | Overlap | Before | After |
|---|---|---:|---|---|
| Q22C | Q21A | 0.25 | confident | review |
| Q85A | Q63A | 0.25 | confident | review |
| Q93A | Q94A | 0.00 | confident | review |
| Q106C | Q56 | 0.25 | confident | review |

The false Q85A/Q63A shift is removed from the shortlist. Known-good police trust,
police corruption, China influence, and President performance pairs survive.
Demotion does not mean all four are wrong: short labels can need manual review.
The rebuilt shortlist has 83 comparable candidates: 61 held-out and 22 seen
when `--top 100` is used. The old 40 held-out count was a display cap.

Full change evidence: [r10_crosswalk_changes.json](r10_crosswalk_changes.json).

## Item 2: frozen questions

[r10_item_list.json](r10_item_list.json) contains 12 held-out items and 3 seen
controls. Four held-out items have a substantive option with an urban/rural gap
of at least 5 points. All held-out items have movement TVD >=5 points and are
absent from `_IMPORTED`. No selected R10 question is flagged suspect.

| Set | R9 codes |
|---|---|
| Held-out | Q38E, Q38F, Q38G, Q37F, Q37I, Q37B, Q46E, Q46B, Q9A, Q5A, Q47A, Q37G |
| Seen controls | Q37A, Q4A, Q46F |

Each row includes the R9 label, R10 full wording, every answer option, R9
substantive codes, movement, national/subgroup truth, rationale, and one
preselected substantive subgroup endpoint. The full R9 questionnaire wording
was not independently verified; metadata labels and all coded options were.

Git attributes preserve the exact bytes of the two frozen inputs across platforms.
The immutable hashes are in [r10_item_lock.json](r10_item_lock.json).
[r10_ask_scenarios.json](r10_ask_scenarios.json) carries the same questions and
options without truth, movement, or rationales. No ask/reveal runner exists yet:
this separation is groundwork, not a claim that a blind ritual was performed.

## Item 3: spread

`backtest_panel.spread` reuses `score` and keeps the full option distribution.
It reports total variation distance, extreme-option mass, and maximum option
share. Empty rooms and invalid options cannot pass.

Frozen pass conditions: absolute tail-mass difference <=10 points, and modal
pile-up <=15 points above truth. Synthetic exact, flat, and concentrated rooms
have the expected error ranking for the explicitly fixed test distribution.
No universal ranking exists independently of the truth distribution.

## Item 4: findings

Full figures: [r10_identical_people.md](r10_identical_people.md) and
[r10_identical_people.json](r10_identical_people.json).

Government trust gives R9 explained variance **48.05%**, library **81.81%**,
a **+33.76-point** gap. Across all 15 shared bands, raw gaps range from
**+25.22 to +36.54 points**. Those are warning signals, not a validated verdict.

For government trust, shuffled answers still give **44.10%** in R9 and
**63.44%** in the library. There are **157 singleton people** in the 344 usable
library records. Grouping alone inflates the statistic. The plan's expectation
that the real ceiling should be low is not supported by this estimator.

All 12 held-out raw answers are absent from the library by design. Even the
three seen controls are stored as bands or composites rather than original
individual response codes. Item 4.2 cannot be computed for these raw items;
the result records `null`, not an invented value. It does not copy donor
answers onto personas or pretend a fused composite is the original answer.

R9 don't-know/refusal rates for the frozen questions range from **0.51% to
11.79%**, not a universal 5-20%. Stored missing attitude bands cannot establish
a library refusal rate, because fusion fills missing donor answers.

The existing `_footer` and old scenarios require a closest-option choice and
usually omit opt-outs. They were not changed. R10 full-option scenarios do
include the published opt-outs, as Item 3.1 requires; that is a different
question format from the old benchmark and must be acknowledged in comparisons.

## Why Item 5 is paused

The plan says to measure before spending, and to stop if Item 4 exposes a
realism problem. The measurements expose a risk, but also a problem in the
proposed test. We cannot honestly mark the gate green or call it a definitive
stereotype failure. The user chose to stop at these findings on 2026-09-06. No redesign or paid run
is authorised as a continuation of this task. A possible future repair is to
use shared stored bands for the data-layer check, choose a held-out or
matched-cell comparison with a declared failure threshold, and reserve the
raw held-out-item comparison for actual model answers.

Other review limits to retain:

- Held-out from the fused columns does not prove the model has never seen R10.
  Model training contents and persona narrative leakage were not audited.
- Selecting large historical shifts yields a stress test, not an unbiased
  estimate of accuracy over all possible questions or commercial scenarios.
- Seen items are banded/composite inputs and target a later survey; they are
  useful controls but are not guaranteed to outperform every held-out item.
- Separate ask/reveal invocations must use the truth-free file for ask.
  Loading the full item list and then ignoring its truth would break Rule 3.
- R10 `null` cells are preserved. Their meaning must be verified before grading;
  the earlier shortlist normalises substantive responses only.
- The existing answer parser accepts one-word/underscore labels. The future
  R10 runner must explicitly support full printed answer labels and test them.
- `backtest_panel` attaches existing research context; it does not demonstrate
  a paired live-web grounding intervention. Movement cannot be attributed to
  that layer without testing it.
- Audit weights are marginal ratios, not one ready-to-use joint weight. National
  reporting needs a declared weighting method and coverage check. The existing
  audit also shows education/province gaps larger than those cited in the plan.

No smoke/full answer files, reveal results, subgroup accuracy, weighted national
accuracy, or answer-level variance exist. Tokens spent: **0**. Items 5 and 4.4
remain unimplemented. No headline accuracy number can be written.

## Honest outside paragraph

We prepared 12 survey questions not imported into our persona attitudes and
three controls, but have not yet measured their simulated answers against the
national results. Our preliminary checks found that the proposed realism test
is distorted by small demographic groups and cannot compare held-out answers
that the library does not store. We paused before spending on model calls or
claiming an accuracy figure.

## Verification and proof

Exact commands, terminal output, and exit codes are retained in
[r10_proof_of_work.txt](r10_proof_of_work.txt). Tests run with `LLM_API_KEY` and
`SIM_LLM_API_KEY` unset, without importing application config or calling models.
Final local checks: **11 passed**; the six new tests also passed on the isolated
branch from main. The whitespace check excludes only the verbatim terminal
transcript, whose original trailing spaces are retained as evidence. Local checks had with two existing Stata text-encoding warnings
from the donor-ladder fixture reads; their string decoding was not independently
verified in this task. File/line references are in [r10_file_references.json](r10_file_references.json).
The delivery manifest hashes use LF-normalised text (raw bytes for the PDF);
frozen-list hashes retain exact bytes. The delivery files and hashes are in [r10_delivery_manifest.json](r10_delivery_manifest.json).

Reproduce with the local survey files and Python packages `pyreadstat`, `numpy`,
`pypdf`, and `pytest` available:

```powershell
& backend/.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider backend/tests/test_r10_validation.py
& backend/.venv/Scripts/python.exe -B backend/scripts/check_r10_realism.py
```

Do not regenerate the frozen item list after any model answers exist. The SAV
and private persona library stay uncommitted. Raw model outputs do not exist.
The R10 PDF is modest (2.31 MB); only that public summary and derived aggregate
JSON/crosswalk are included as survey assets, not respondent microdata.

## Delivery

This is a partial implementation with an explicit failed readiness gate, not a
completed validation. The user chose to stop at the findings. Any test-method repair and paid run
are future work, not part of this delivery.
