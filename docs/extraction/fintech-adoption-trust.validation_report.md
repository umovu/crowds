# Validation report: middle-class-fintech-trust

**Verdict: NEEDS HUMAN REVIEW**

> Automated pre-screen, not a substitute for reading the source paper.
> AUTO-APPROVED means nothing detectable was wrong, not that it is
> definitely correct.

## Deterministic checks

- Contamination lint: passed
- Passage faithfulness: 45/45 passages fuzzy-matched a source file (threshold 0.55)
- Vocabulary: all terms found in source text

## LLM second-opinion review

- Summary: All five mechanisms use identical absolute language ('the binding constraint... only when') that overstates the exclusivity of each factor relative to the others; the underlying chains support these as concurrent evaluative rules or prerequisites, not mutually exclusive binding constraints. Confidence and identity claims are fine.

**Mechanism-chain fit:**
  - mechanism 0: CONCERN — Mechanism states cost is 'the binding constraint' and adoption occurs 'only when' cheaper. Chain C1 supports cost as *an* evaluative rule and a factor in switching behavior, but does not establish it as the singular, exclusive binding constraint overriding all other factors (e.g., trust or convenience). The 'only when' phrasing overstates the exclusivity supported by the chain.
  - mechanism 1: CONCERN — Same issue as M0. Chain C2 presents convenience as a driver and evaluative rule, but not as the sole 'binding constraint.' The mechanism's absolute framing ('only when') contradicts the multi-factor nature of the source chains.
  - mechanism 2: CONCERN — Chain C3 supports trust/security as a critical gatekeeper and preference for human interaction when absent. However, labeling it 'the binding constraint' implies it universally supersedes cost or convenience, which the chain does not prove. It is a necessary condition in specific contexts, not necessarily the universal binding constraint.
  - mechanism 3: CONCERN — Chain C4 identifies self-efficacy/infrastructure as a prerequisite ('adopt only if skills... sufficient'). While this functions more like a true constraint than M0-M2, the label 'the binding constraint' still falsely implies exclusivity against the other four mechanisms listed in the same card.
  - mechanism 4: CONCERN — Chain C5 describes social proof and youth identity as influential factors driving trial. Calling this 'the binding constraint' significantly overstates the evidence; social proof is rarely a hard prerequisite comparable to infrastructure (M3) or trust (M2), yet the mechanism text grants it equal absolute status via the 'only when' formulation.

**Confidence honesty:** {'verdict': 'OK', 'note': 'The confidence field accurately reflects the qualitative, multi-source, single-country nature of the evidence and correctly notes that magnitudes are unknown. It does not overstate certainty.'}

## What you still need to do

- [x] No passages flagged — spot-checking optional but recommended
- [ ] Read the LLM judge's concerns (if any) and agree/disagree
- Reviewer: ______  Date: ______  Final sign-off: YES / NO