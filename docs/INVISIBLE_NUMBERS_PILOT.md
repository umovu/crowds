# Invisible-numbers pilot spec

Frozen before any experiment code. Lexicons, metrics, and the stats protocol
below are the fixed target; they do not change after B/C/D output exists.

## The claim under test

A persona's surveyed economics must shape its reaction **without the persona
citing the figures**. The income band is the independent variable; the reaction
is the dependent variable. A response that restates the IV ("R50 is negligible
compared to my R18,000 fees") is an echo of the conditioning variable, not a
model of a person.

Success = tier is inferable from **digit-stripped** text. Failure = tier is
inferable only when figures are quoted.

## Calibration basis (production language, frozen)

Markers were curated from 23 valid production responses to the Thuto pitch
(panel_07eb044c9c55 round 1, panel_39692ef06a7c round 1) with recorded
`budget_tier` ground truth. Empirical findings:

- **Tier-neutral (useless):** "cannot justify", "skeptical", "proof/evidence",
  "trust" — appear in all three tiers.
- **Tight-correlated:** impossibility language ("impossible", "out of the
  question", "too expensive"), basics-coverage ("barely", "just to get by",
  "struggling to cover"), concrete displacement ("electricity token money",
  "days of taxi fare").
- **Moderate-correlated:** stretch language ("stretch", "every rand",
  "every cent", "watching every"), guarantee-seeking ("guaranteed",
  "can't risk").
- **Loose-correlated:** price-dismissal ("negligible", "not the issue",
  "isn't the barrier"), commitment-conditional ("before I commit").

Known ground-truth noise: Nolwandle Makhaphela (recorded loose) speaks
constrained ("feels like too much"). The classifier ceiling is below 100%;
that is accepted and applies equally to all conditions.

## Conditions

Same 12 personas (panel_07eb044c9c55 cast), same Thuto pitch, same
deterministic card binding, same STANCE/ECONOMIC tail, temperature 0.7,
`__ERROR__` on LLM failure (never a synthetic quote).

| Cond | Tier gloss shown? | REAL NUMBERS shown? | Situation block? | Ask |
|---|---|---|---|---|
| A_control | yes | yes | no | "justify the spend" |
| B_block_only | no | no | yes | "justify the spend" |
| C_full | no | no | yes | open reaction |
| D_rule_only | yes | yes | no + "never cite own income/fees figures" rule | "justify the spend" |

**Known limitation — missing cell:** "situation block + REAL NUMBERS, no rule"
is not run (call budget). If D fails and B succeeds, the missing cell leaves
mechanism ambiguity (does removal or block-presence do the work?). Accepted;
follow-up run if that pattern materializes.

In B/C the tier label and its gloss ("LOOSE — budget is not the main
obstacle") are removed along with the figures: the gloss is a tier-named
decision-style instruction, itself a leak channel. Tier survives only as
(a) hidden ground truth for scoring, (b) the deterministic affordability
computation (unchanged, LLM-off, per the hard rules).

## The situation compiler (Phase 1)

`backend/scripts/situation_compiler.py` — pure function, no LLM anywhere.

- **Input:** the persona record (`budget_tier`, `monthly_household_income_rand`,
  `fees_band` / `learner_fee_bands`, `receives_grant`, `internet_at_home`,
  `computer_in_home`, `actor_archetype`).
- **Output:** 1–3 sentences of lived circumstance under a neutral header
  (no provenance annotations — the persona must not know its data is
  "surveyed"; that framing invites citation).
- **Situation only, never decision style.** The compiler renders money rhythm
  (when the month is tight) and obligations (what the money stands on). It
  never states how the persona weighs a new cost — that inference is the
  behaviour under observation. (Production's tier glosses — "a new cost must
  displace an existing essential" — are exactly what is excluded.)
- **Number-free.** No numeric tokens, no rand figures, no digit words-as-numbers.
  The price lives only in the pitch text; mapping R50 onto one's life is the
  behaviour being measured. Tested: no `\d` in output for all 12 cast records.
- **Referent licensing.** Obligation lines are drawn only from licensed fields:
  `receives_grant` → grant line; `internet_at_home`/`computer_in_home` →
  digital-access line; any paid fee band → "school things" referent
  (mojibake-tolerant: only the literal "No fees" marker is compared).
  Food/transport universals are allowed but can never carry prices
  (compiler-side: no numeric tokens; response-side: leak metric).
  `geotype` is deliberately unused in v1 (texture-invention risk).
- **Role-aware.** `guardian_parent`/`gogo_guardian` → guardian templates;
  `learner` → learner templates (learners experience household money, they
  don't sign debit orders). Unknown archetype raises.
- **Tier source.** `budget_tier` from the record is ground truth. A test
  asserts naive income banding (<5 000 / 5 000–19 999 / >=20 000) reproduces
  all 12 recorded tiers — it does today; disagreement in a future cast means
  "look at it", not silent failure.

## Lexicon disjointness (anti-circularity 1)

Two frozen lexicons in `situation_compiler.py`:

- `COMPILER_LEXICON` — every normalized token the compiler can emit
  (templates are fixed, so the vocabulary is enumerable).
- `CLASSIFIER_MARKERS` — tier → marker phrases, curated only from the
  production calibration above.

Test (LLM-off): no normalized marker appears as a substring of any normalized
template/obligations line, and vice versa. This test failing blocks the pilot.

## Paraphrase-leak metric (anti-circularity 2)

Lexical disjointness does not catch close paraphrase. So, per response:

1. Normalize (lowercase, digits stripped, punctuation to space, spaces
   collapsed). Compute 4-gram **containment** of the response in the persona's
   own injected block (A/D: the REAL NUMBERS + gloss text; B/C: the compiled
   block). Report per condition.
2. **Echo-robust accuracy** (the primary statistic): mask every response
   n-gram that overlaps the injected block, then classify. Tier separation
   that survives masking is not echo.

## Number-leak metric

Scan responses for R-prefixed figures. Whitelist: `{50} ∪ {50×k, k = 2..36}`
(pitch figure + its legitimate arithmetic out to three years). Anything else
is a leak — including the persona's own income or fee figures, which are
*allowed* today and become leaks under the new rule. Only R-prefixed figures
count, so "my 3 children" never fires.

## Classifier

Deterministic, LLM-off. Per digit-stripped response: count marker hits per
tier on normalized text (multi-word markers as substrings, single-word markers
as word matches). Predict argmax; ties or zero hits → abstain. Abstentions
count as incorrect in balanced accuracy (conservative).

## Stats protocol

- **Statistic:** balanced accuracy (mean per-tier recall; cast is tight 3 /
  moderate 7 / loose 2, so raw accuracy would reward majority-class laziness).
- **Inference:** cluster permutation test — permute the 12 persona→tier
  assignments as whole clusters (repeats within a persona stay together),
  10 000 permutations, p = share of null ≥ observed.
- **Gated contrasts (two, stated up front, no fishing):**
  1. C vs chance — p < 0.05 on echo-robust balanced accuracy.
  2. C vs A — persona-cluster bootstrap 95% CI on the difference; lower
     bound ≥ 0 (non-inferior).
- **Secondary, ungated:** B vs A, D vs A, paraphrase-leak containment per
  condition, plus the carried-over metrics from `score_prompt_shape.py`
  (template collapse, opener entropy, card surfacing, voice fidelity,
  unlicensed texture, STANCE/ECONOMIC discipline, invented figures).
- **Power ceiling (recorded):** 12 personas × 3 repeats; per-tier persona
  counts are 2–7. Only large effects are detectable; the loose tier rests on
  2 personas (one known-noisy). A null result does not distinguish "no effect"
  from "underpowered" — stated honestly in the report.
- **Same instrument everywhere:** every condition, including A, is scored on
  digit-stripped text with the same classifier. If A separates only via quoted
  figures, A scores ~chance on this instrument — that is the finding, not a
  rigged baseline.

## Economics-retained check

The ECONOMIC JSON's `willingness_band` / `primary_objection` must still
correlate with recorded tier under B/C (deterministic check: distribution of
objection classes × tier). We are removing the citation, not the economics.

## Run protocol

3 repeats (pilot rule: single runs at temperature 0.7 are noise). 48 sim-tier
calls per repeat, 144 total. Incremental flush after every call. Qualitative
read of 2–3 transcripts per tier per condition afterwards — metrics alone
miss things (cf. the "Thandi" mode-collapse, found only by reading).

**Blocker:** SIM-tier quota was exhausted during `prompt_shape_pilot`
(128/144 calls 403'd). Phase 4 waits on quota; Phases 0–3 do not need it.

---

## Addendum — run 2 protocol (frozen 2026-07-17, before run-2 output exists)

Run 1 (qwen3.7-max-2026-05-17, 144/144 valid) failed both gates; findings in
`docs/INVISIBLE_NUMBERS_RESULTS.md`. Run 2 tests block v2 + lexicon v2, and
replicates D (which was ported to production after run 1 — the run-2 D cell
is now a production replication check).

**Lexicon v2 (`CLASSIFIER_MARKERS_V2` in `situation_compiler.py`).** v1
markers retained verbatim. Additions curated ONLY from run-1's A-condition
(production channel, 36 responses; B/C/D outputs never inspected for
calibration) under the rule: a phrase enters iff it appears >=2 times within
one tier AND 0 times in the other tiers. Additions: moderate += {"no sense",
"gamble", "upfront", "risk"}; loose += {"easily afford", "easily affordable",
"gimmick", "gimmicky", "bribe", "bribing", "gamify", "gamified", "gamifying"};
tight unchanged (v1 already fires: recall 0.89). Rejected by the rule despite
face validity: "pocket change", "a drop in the ocean" (single occurrence =
single-persona idiolect risk). Disjointness vs all compiler templates (v1+v2)
is tested LLM-off and passing.

**Block v2 (`RHYTHM_V2_OVERRIDES`).** ONLY the loose rhythm is rewritten
(run 1: loose did not differentiate; tight/moderate worked and stay frozen).
Surplus is shown concretely — things replaced before they break, school
chosen for fit — instead of the abstract "does not watch the calendar".

**Conditions:** A_control (internal control), B2_block_v2 (v2 block, justify
ask), C2_full_v2 (v2 block, open ask), D_rule_only (production replication).
144 calls, 3 repeats, temperature 0.7, same cast/pitch/tail.

**Gates (unchanged from run 1):** (1) C2 vs chance, p < 0.05 on echo-robust
balanced accuracy with the v2 lexicon; (2) C2 vs A, persona-cluster bootstrap
95% CI lower bound >= 0. Sensitivity check (ungated): re-score run 1 with
lexicon v2 — legitimate only for B/C/D cells, which were never used for
calibration; A-cell rescoring is calibration-contaminated and reported as
such.
