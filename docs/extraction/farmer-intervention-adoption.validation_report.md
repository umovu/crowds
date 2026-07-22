# Validation report: farmer-intervention-adoption

**Verdict: NEEDS HUMAN REVIEW**

> Automated pre-screen, not a substitute for reading the source paper.
> AUTO-APPROVED means nothing detectable was wrong, not that it is
> definitely correct.

## Deterministic checks

- Contamination lint: passed
- Passage faithfulness: 30/30 passages fuzzy-matched a source file (threshold 0.55)
- Vocabulary NOT found verbatim in any source: ['uncoordinated extension services']

## LLM second-opinion review

- Summary: All five mechanisms are well-grounded in their cited chains with no overstatement, identity violations, or confidence inflation; card is internally consistent and ready for production.

**Mechanism-chain fit:**
  - mechanism 0: OK — Mechanism accurately reflects Chain C1's causal sequence from low income/tenure insecurity to financial infeasibility and subsidy dependence.
  - mechanism 1: OK — Mechanism correctly maps Chain C2's link between education/youth/awareness and positive evaluation/adoption of new practices.
  - mechanism 2: OK — Mechanism faithfully represents Chain C3's progression from connectivity/literacy/trust deficits to perceived risk and rejection of digital tools.
  - mechanism 3: OK — Mechanism aligns with Chain C4's logic that lack of training/extension increases complexity and leads to avoidance or sub-optimal use.
  - mechanism 4: OK — Mechanism properly captures Chain C5's connection between cultural embeddedness/social inequality and scepticism toward external interventions.

**Confidence honesty:** {'verdict': 'OK', 'note': 'Confidence statement appropriately qualifies findings as qualitative, regionally bounded (Eastern Cape/Limpopo), temporally scoped (2018-2020), and explicitly notes unknown magnitudes despite multi-source basis.'}

## What you still need to do

- [x] No passages flagged — spot-checking optional but recommended
- [ ] Read the LLM judge's concerns (if any) and agree/disagree
- Reviewer: ______  Date: ______  Final sign-off: YES / NO