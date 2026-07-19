# Validation report: farmer-stock-theft-exposure

**Verdict: NEEDS HUMAN REVIEW**

> Automated pre-screen, not a substitute for reading the source paper.
> AUTO-APPROVED means nothing detectable was wrong, not that it is
> definitely correct.

## Deterministic checks

- Contamination lint: passed
- Passage faithfulness: 25/25 passages fuzzy-matched a source file (threshold 0.55)
- Vocabulary NOT found verbatim in any source: ['lifetime imprisonment']

## LLM second-opinion review

- Summary: All mechanisms are well-grounded in their cited chains and passages, inferred policy links are reasonable extensions of identified problems, and confidence is appropriately calibrated to the qualitative, perception-based evidence base.

**Mechanism-chain fit:**
  - mechanism 0: OK — Mechanism accurately reflects C1's rational choice framing and the high-value/movable nature of livestock cited in passages.
  - mechanism 1: OK — Mechanism faithfully captures C2's link between unaffordable herding labour, distant grazing camps, and increased theft vulnerability.
  - mechanism 2: OK — Mechanism correctly represents C3 as a perception-based deterrent logic (leniency signals state indifference) rather than an objective fact about sentencing efficacy.
  - mechanism 3: OK — Mechanism aligns with C4's causal chain linking cultural demand, lack of ownership proof, and theft surges around events.
  - mechanism 4: OK — Mechanism matches C5's connection between weak identification practices and difficulty in detection/recovery.

**Inferred-link verdicts:**
  - APPROVE: therefore new policy must increase guardianship, reduce accessibility, or raise penalties to alter cost-benefit calculus [inferred] — Reasonable inference from C1's rational choice framework; directly follows from the need to alter offender calculus.
  - APPROVE: therefore new policy must provide subsidized herding, improved fencing, or community monitoring [inferred] — Logical extension of C2's resource constraint problem; solutions map directly to stated barriers.
  - APPROVE: therefore new policy must incorporate stricter sentencing and visible enforcement [inferred] — Follows from C3's farmer advocacy for lifetime imprisonment and perceived government inadequacy.
  - APPROVE: therefore new policy must regulate informal livestock sales and require proof of ownership [inferred] — Directly addresses C4's identified gap in unregulated markets and missing ownership certificates.
  - APPROVE: therefore new policy must expand mandatory identification programs and seasonal patrols [inferred] — Appropriate response to C5's dual problems of weak branding and winter darkness vulnerability.

**Confidence honesty:** {'verdict': 'OK', 'note': 'Confidence field accurately qualifies claims as perception-based from two Eastern Cape communal area studies, explicitly noting lack of quantified magnitudes. Matches the qualitative claim_type and regional scope.'}

## What you still need to do

- [x] No passages flagged — spot-checking optional but recommended
- [ ] Read the LLM judge's concerns (if any) and agree/disagree
- Reviewer: ______  Date: ______  Final sign-off: YES / NO