# Mechanism-card extraction protocol

How a research paper becomes a mechanism card. One worksheet per card
(`docs/extraction/<card-id>.worksheet.md`, template in this folder); all six
stages are passes over that single worksheet. Budget: ≤1 day per paper.

Division of labour: thematic synthesis finds it, process tracing shapes it,
CMO scopes it, the card schema makes it executable, the gate keeps it clean,
the evidence tests prove it worked.

Hard rules (from PILOT_README, restated because every stage enforces one):
papers contribute qualitative mechanisms only — never numbers, never identity;
binding stays a deterministic tag lookup; everything testable with the LLM off.

## Stage 0 — Eligibility screen (gate, ~10 min)

The paper must document **segment reasoning** — participant quotes or
interpreted "why" — not just outcomes or correlations.

- Reject: quantitative-only findings ("62% of households own livestock").
  Route useful numbers to `sa_world_facts.json` via the stats path instead.
- Record in worksheet: pass/reject, one-line reason, target segment(s).

## Stage 1 — Harvest (thematic synthesis)

Walk the findings/discussion sections. Copy every passage where the paper
explains *why* the segment acts. For each passage record:

- ID (P1, P2, …), page/section reference
- Voice: `participant` or `author-interpretation`
  (mechanisms resting only on author-interpretation take a confidence
  penalty at Stage 5)

## Stage 2 — Chain (process tracing)

Group related passages; force each group into an explicit entity-activity
chain:

> actor's situation → therefore evaluative rule → therefore behaviour →
> therefore how a new product/policy gets read

- Every link cites its passage IDs. A link with no passage is marked
  `[inferred]` and needs reviewer sign-off at Stage 5 or deletion.
- **Max 5 chains per paper.** More means you are extracting findings, not
  mechanisms — merge or cut.

## Stage 3 — Scope (realist CMO)

For each chain, complete the sentence:

> For [segment], in [context], [chain], producing [outcome pattern].

- The context clause uses **only the closed vocabulary** (persona archetypes
  today; geotype/assets when the library gains them). No free-text tags.
- Write the **negative scope** too: which nearby segments this does NOT
  apply to (e.g. cattle-as-savings applies to `communal_farmer`, NOT
  `smallholder_emerging_farmer`). This enforces coverage honesty at write
  time instead of bind time.
- **Economic class of the studied sample** (`economic_tags`): read what the
  paper says about its population's income/fee level and map it onto the
  product-mode budget tiers — the closed vocabulary `tight` / `moderate` /
  `loose`. Mapping rule of thumb: township, communal, grant-dependent,
  no-fee/low-fee-school samples → `["tight", "moderate"]`; explicit
  middle-class or former-Model-C/private-school samples →
  `["moderate", "loose"]`. **Omit the field entirely when the paper is
  class-blind** — an absent tag means "applies to all tiers", and an honest
  omission beats a guessed tag. At bind time a product-mode persona only
  receives the card if its computed `budget_tier` is in `economic_tags`
  (policy casts have no tier and bind tier-blind). Never tag finer than the
  three tiers.
- Output: `segment_tags`, `economic_tags` (optional), `region`, `year_range`.

## Stage 4 — Formalize (card schema; COM-B as checklist)

1. Compress each chain into one card `mechanism` sentence that **preserves
   the "because"**.
   - **Affective/attitude material is welcome ONLY in conditional form.**
     Papers often document emotional or attitudinal patterns (nihilism,
     status insecurity, shame around debt). These may enter `mechanisms`
     only as circumstance-triggered responses — "X breeds/erodes/triggers
     Y" — never as dispositional traits ("people like this ARE Y"). The
     conditional form describes documented reasoning a persona can apply;
     the dispositional form authors identity, which papers must never do.
     (The Stage-5 identity-claim check polices this.)
   - Where a paper reveals a segment-defining attitude DIMENSION (e.g.
     bank-specific distrust) rather than a mechanism, do not put stance
     values in the card — flag it as a candidate for extending the
     attitude-fusion vocabulary (ATTITUDE_VOCAB), so the value comes from
     survey donors per persona, not from the paper.
2. **Runnability test (hard gate):** could a persona apply this rule to a
   scenario the paper never discussed? Descriptive statements ("cattle are
   important") fail and die here.
3. `vocabulary`: attested terms only, participant-voice preferred.
   `objection_patterns`: the questions the segment actually asks.
   `evaluative_rules` (optional, max 5): the "therefore evaluative rule" link
   of each chain restated as a standalone decision heuristic — how the segment
   weighs/filters a purchase or adoption ("judge by X, not Y"). Must be a rule
   of evaluation, never identity; each rule carries chain + passage provenance
   (`evaluative_rule_provenance`). These feed the need-vs-want elicitation at
   runtime, so only include rules that genuinely gate wanting/choosing.
4. **COM-B pass (coverage check only, never a generator):** does the card
   cover capability, opportunity and motivation mechanisms? Record gaps in
   the worksheet as gaps — never fill one by invention.

Output: draft card JSON; each mechanism annotated with its chain + passage IDs.

## Stage 5 — Gate (contamination checklist + confidence)

Contamination checklist — all must pass:

- [ ] No number carried out of the paper
- [ ] No identity claims (papers shape reasoning, never author who a persona is)
- [ ] All `segment_tags` in the closed vocabulary, 1:1 with persona fields
- [ ] `economic_tags` reflect the paper's actual sample (omitted when class-blind, never guessed)
- [ ] Vocabulary items attested in the paper
- [ ] Every mechanism traceable to passage IDs

Confidence grading — per **mechanism**, not per paper, CERQual components:
methodological limitations · relevance to the SA segment · coherence ·
adequacy of data → one graded line in the card's `confidence` field.

Human review task (defined, not vibes): re-check Stage 2 links against
Stage 1 passages; re-run the checklist. Sign-off recorded in the worksheet.
Only then does the JSON ship.

## Stage 6 — Validate (evidence tests, v2 harness)

Run matching personas × baseline / cards / cards+stats × 2–3 repeats on a
scenario **the paper never discussed** (the v2 pilot pattern). Grade
transcripts:

| Test | Operationalization | Verdict |
|---|---|---|
| Straw-in-the-wind | card vocabulary appears under `cards` | weak — texture only |
| Hoop | mechanism reasoning present under `cards`, rare under `baseline` | card adds behaviour, not just provenance |
| Smoking gun | mechanism applied to the unseen scenario | card causes the reasoning |
| Doubly decisive | hoop + smoking gun consistent across repeats | ship it |

Rules:

- Passes only straw-in-the-wind → ship with a `provenance-only` flag
  (citations in UI, no behavioural claim).
- Fails the hoop test → back to Stage 4 (usually the mechanism was written
  as a finding).
- Single runs are never evidence (temperature noise) — repeats or nothing.

## Cluster rule

One card per **mechanism cluster**, not per paper. Three stock-theft studies
= one card with three citations; the worksheet lists all sources and their
passages together.

## Phase 2 note

When extraction is automated, Stages 1–4 of this document become the LLM
extraction prompt verbatim; Stage 5 stays human; Stage 6 stays scripted.
The dry-run diff (re-extracting Matuku & Kaseke and comparing to the
hand-made stokvel card) is the regression test for extractor quality.
