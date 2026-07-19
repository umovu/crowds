# Validation report: edtech-adoption-barriers

**Verdict: NEEDS HUMAN REVIEW**

> Automated pre-screen, not a substitute for reading the source paper.
> AUTO-APPROVED means nothing detectable was wrong, not that it is
> definitely correct.

## Deterministic checks

- Contamination lint: passed
- Passage faithfulness: 26/26 passages fuzzy-matched a source file (threshold 0.55)
- Vocabulary: all terms found in source text

## LLM second-opinion review

- Summary: Mechanism 2 overclaims adoption behavior where the source chain only supports positive valuation/perception; all other mechanisms and metadata are accurate.

**Mechanism-chain fit:**
  - mechanism 0: OK — Mechanism accurately reflects Chain C1. Passages P4 and P7 support the 'binding constraint' framing via the explicit evaluative rule that financial burden negates viability and leads to resource liquidation.
  - mechanism 1: OK — Mechanism aligns with Chain C2. The phrase 'non-negotiable' is supported by the chain's evaluative rule stating a conducive environment is 'necessary,' and the dismissal of e-learning vs. contact classes is explicitly cited in P5.
  - mechanism 2: CONCERN — Mechanism overstates the causal link. Chain C3 states learners 'value' tools for engagement and see them as 'transformative' (P24, P26), but does not support the absolute claim that matching preferences causes them to be 'embraced.' Adoption implies usage/uptake, whereas the chain only confirms positive perception and valuation. Additionally, 'digital-native preferences' is a contested generalization presented here as settled fact.
  - mechanism 3: OK — Mechanism faithfully summarizes Chain C4. The restriction to administrative tasks (P13, P25) directly follows from the instructor's perception of role threat and lack of pedagogical understanding.
  - mechanism 4: OK — Mechanism matches Chain C5. Single-source passage P16 supports the sequence from infrastructure deficits to negative attitudes and reduced engagement.

**Confidence honesty:** {'verdict': 'OK', 'note': 'Confidence field correctly identifies the multi-source qualitative nature and explicitly flags the inability to determine magnitudes or precise regional variation, which aligns with the diverse citation base (schools, universities, special needs).'}

## What you still need to do

- [x] No passages flagged — spot-checking optional but recommended
- [ ] Read the LLM judge's concerns (if any) and agree/disagree
- Reviewer: ______  Date: ______  Final sign-off: YES / NO