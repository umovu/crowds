# Validation report: youth-mobile-airtime-economy

**Verdict: NEEDS HUMAN REVIEW**

> Automated pre-screen, not a substitute for reading the source paper.
> AUTO-APPROVED means nothing detectable was wrong, not that it is
> definitely correct.

## Deterministic checks

- Contamination lint: passed
- Passage faithfulness: 17/17 passages fuzzy-matched a source file (threshold 0.55)
- Vocabulary: all terms found in source text

## LLM second-opinion review

- Summary: Mechanism 0 overstates provenance by introducing 'styling' and 'fear of lower status' not present in Chain C1; all other mechanisms, inferred links, and confidence statements are well-supported.

**Mechanism-chain fit:**
  - mechanism 0: CONCERN — Mechanism claims 'fear of being seen as lower-status drives a preference for functionality and styling over price.' Chain C1 states adolescents 'prioritise functionality and multimedia' due to social inclusion, but does not mention 'styling' or explicitly frame the driver as 'fear of being seen as lower-status' (vs. desire for inclusion). 'Styling' appears unsupported by the cited chain; 'over price' is also not established in C1.
  - mechanism 1: OK — Mechanism accurately reflects C2: airtime scarcity and privacy concerns lead to missed calls/narrow definitions of use, making direct questions unreliable.
  - mechanism 2: OK — Mechanism aligns with C3: aspirations for tertiary education create willingness to pay for mobile services viewed as advancement tools.
  - mechanism 3: OK — Mechanism correctly captures C4: gendered routines dictate availability and context for mobile interactions.

**Inferred-link verdicts:**
  - APPROVE: therefore mobile phone ownership is a marker of social inclusion [inferred] — Reasonable inference from 'adolescents without a mobile phone feel socially isolated and perceive lower social status' in C1.
  - APPROVE: therefore they engage in cost-reducing behaviours like missed calls and narrow definitions of 'use' [inferred] — Directly supported by C2's premise about lacking airtime leading to these specific behaviors.
  - APPROVE: therefore they see mobile phones as tools for advancement [inferred] — Logical bridge between 'aspirations for tertiary education/willingness to pay' and 'receptive to educational services' in C3.
  - APPROVE: therefore they are receptive to educational or informational services on mobile phones [inferred] — Follows reasonably from seeing phones as advancement tools plus existing willingness to pay in C3.
  - APPROVE: therefore evaluative rules about appropriate activities differ by gender [inferred] — Reasonable sociological inference from observed gendered time-use patterns (household vs. public) in C4.
  - APPROVE: therefore boys and girls have different availability and contexts for mobile phone use [inferred] — Direct logical consequence of differing routines and evaluative rules stated in C4.

**Confidence honesty:** {'verdict': 'OK', 'note': 'Confidence statement appropriately qualifies findings as cohort-specific with unknown generalisability, matching the cited South African adolescent samples and mixed-methods scope.'}

## What you still need to do

- [x] No passages flagged — spot-checking optional but recommended
- [ ] Read the LLM judge's concerns (if any) and agree/disagree
- Reviewer: ______  Date: ______  Final sign-off: YES / NO