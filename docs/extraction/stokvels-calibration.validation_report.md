# Validation report: stokvels-calibration

**Verdict: NEEDS HUMAN REVIEW**

> Automated pre-screen, not a substitute for reading the source paper.
> AUTO-APPROVED means nothing detectable was wrong, not that it is
> definitely correct.

## Deterministic checks

- Contamination lint: passed
- Passage faithfulness: 20/20 passages fuzzy-matched a source file (threshold 0.55)
- Vocabulary: all terms found in source text

## LLM second-opinion review

- Summary: Mechanism 3 overstates lending exclusivity by omitting 'trusted outsiders' explicitly mentioned in Chain C4; all other elements are well-supported and confidence is honestly stated.

**Mechanism-chain fit:**
  - mechanism 0: OK — Mechanism accurately reflects C1's logic of separating grocery spending from other claims to smooth consumption.
  - mechanism 1: OK — Mechanism faithfully captures C2's causal link between witnessing funeral hardship and pooling resources for equipment/labour.
  - mechanism 2: OK — Mechanism correctly describes C3's forced-savings logic converting regular contributions into lump sums for assets/bills.
  - mechanism 3: CONCERN — Mechanism states lending is 'confined to a trusted circle,' but Chain C4 explicitly includes 'lending to members and trusted outsiders.' The mechanism overstates exclusivity by omitting the 'trusted outsiders' component present in the chain.
  - mechanism 4: OK — Mechanism aligns with C5's description of uniforms and networks signaling accessible entry rules.

**Confidence honesty:** {'verdict': 'OK', 'note': 'Confidence field accurately discloses single-township qualitative case study with unspecified fieldwork dates and unknown magnitudes.'}

## What you still need to do

- [x] No passages flagged — spot-checking optional but recommended
- [ ] Read the LLM judge's concerns (if any) and agree/disagree
- Reviewer: ______  Date: ______  Final sign-off: YES / NO