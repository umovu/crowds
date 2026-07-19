# Worksheet: <card-id>

Sources (cluster rule: all papers feeding this card):
- <citation 1> — <link/DOI>
- <citation 2> — <link/DOI>

## Stage 0 — Eligibility

- Verdict: PASS / REJECT
- Reason (one line):
- Target segment(s):

## Stage 1 — Harvested passages

| ID | Passage (paraphrase or quote) | Voice | Source, page/section |
|----|-------------------------------|-------|----------------------|
| P1 |  | participant / author-interpretation |  |
| P2 |  |  |  |

## Stage 2 — Chains (max 5)

### C1 (from P_, P_)
situation → evaluative rule → behaviour → how a new product/policy gets read

> <chain here; mark unsupported links `[inferred]`>

## Stage 3 — CMO scope

- C1: For <segment>, in <context>, <chain>, producing <outcome pattern>.
- segment_tags (closed vocab only):
- Negative scope (does NOT apply to):
- region / year_range:

## Stage 4 — Draft card

- Runnability test per mechanism: PASS/FAIL + unseen-scenario example
- COM-B coverage: capability __ / opportunity __ / motivation __
  (record gaps; never invent)

```json
{
  "id": "<card-id>",
  "citation": "",
  "segment_tags": [],
  "mechanisms": [],
  "evaluative_rules": [],
  "vocabulary": [],
  "objection_patterns": [],
  "claim_type": "qualitative",
  "region": "",
  "year_range": "",
  "confidence": ""
}
```

Mechanism → chain → passages map:
- M1 ← C1 ← P1, P2

Evaluative rule → chain → passages map (rules = the "therefore evaluative
rule" link of a chain, restated as a decision heuristic; max 5):
- R1 ← C1 ← P1, P2

## Stage 5 — Gate

- [ ] No number carried out of the paper
- [ ] No identity claims
- [ ] Tags in closed vocabulary, 1:1 with persona fields
- [ ] Vocabulary attested in paper
- [ ] Every mechanism traceable to passage IDs
- [ ] Every evaluative rule is a weighing/filtering heuristic (never identity),
      traceable to its chain's passages
- Confidence per mechanism (CERQual: limitations / relevance / coherence / adequacy):
  - M1:
- Reviewer: <name> — Date: — Sign-off: YES/NO + notes

## Stage 6 — Validation

- Unseen scenario used:
- Runs: <n repeats> × baseline/cards/cards+stats — output files:
- Straw-in-the-wind: | Hoop: | Smoking gun: | Doubly decisive:
- Verdict: SHIP / PROVENANCE-ONLY / BACK TO STAGE 4
