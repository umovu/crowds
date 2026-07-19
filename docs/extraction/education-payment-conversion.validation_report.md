# Validation report: education-payment-conversion

**Verdict: NEEDS HUMAN REVIEW**

> Automated pre-screen, not a substitute for reading the source paper.
> AUTO-APPROVED means nothing detectable was wrong, not that it is
> definitely correct.

## Deterministic checks

- Contamination lint: passed
- Passage faithfulness: 35/35 passages fuzzy-matched a source file (threshold 0.55)
- Vocabulary NOT found verbatim in any source: ['learner-teacher ratios']

## LLM second-opinion review

- Summary: All five mechanisms are tightly grounded in their respective chains with no identity violations, unsupported inferences, or confidence overstatements; card is production-ready.

**Mechanism-chain fit:**
  - mechanism 0: OK — Mechanism accurately reflects C1's progression from perceived public school failure to migration toward limited functional sub-systems based on academic outcomes.
  - mechanism 1: OK — Mechanism correctly synthesizes C2's link between financial/informational scarcity and zoning as a forced constraint; 'override all other attributes' is supported by P16/P17 in the chain.
  - mechanism 2: OK — Mechanism faithfully represents C3's causal path from parental education to active marketplace search using specific informed criteria.
  - mechanism 3: OK — Mechanism is a direct restatement of C4; no drift or overstatement regarding safety threats triggering vigilance/exit.
  - mechanism 4: OK — Mechanism aligns with C5's sequence of traditional norm irrelevance leading to preference-driven choice and trade-offs.

**Confidence honesty:** {'verdict': 'OK', 'note': 'Confidence field appropriately qualifies findings as single-province, small-sample qualitative synthesis with unknown national prevalence, matching the cited sources (Western Gauteng/Centurion focus).'}

## What you still need to do

- [x] No passages flagged — spot-checking optional but recommended
- [ ] Read the LLM judge's concerns (if any) and agree/disagree
- Reviewer: ______  Date: ______  Final sign-off: YES / NO