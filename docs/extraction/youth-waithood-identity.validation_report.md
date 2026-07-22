# Validation report: youth-waithood-identity

**Verdict: NEEDS HUMAN REVIEW**

> Automated pre-screen, not a substitute for reading the source paper.
> AUTO-APPROVED means nothing detectable was wrong, not that it is
> definitely correct.

## Deterministic checks

- Contamination lint: passed
- Passage faithfulness: 51/51 passages fuzzy-matched a source file (threshold 0.55)
- Vocabulary: all terms found in source text

## LLM second-opinion review

- Summary: Mechanism 1 misrepresents Chain C2 by conflating substance use (a coping behavior) with felt stigma (a downstream perception), requiring correction to preserve causal fidelity; all other elements are sound.

**Mechanism-chain fit:**
  - mechanism 0: OK — Mechanism accurately reflects Chain C1's progression from government betrayal/alienation to nihilism and the perception of education as useless.
  - mechanism 1: CONCERN — Mechanism states substance use is a 'mask for felt stigma,' but Chain C2 positions substance use as a behavior resulting from lost self-esteem/worthlessness, while 'feeling stigmatised' is listed separately as a downstream reading/perception. The mechanism conflates the coping behavior with the social perception, reversing or collapsing the chain's distinct steps.
  - mechanism 2: OK — Mechanism faithfully captures C3's link between deferred education dreams, comparative worthlessness, fear of rejection, and interpreting job requirements as unattainable/personal.
  - mechanism 3: OK — Mechanism correctly maps C4's causal path from family hardship/caregiving to survival-based evaluation of opportunities.

**Confidence honesty:** {'verdict': 'OK', 'note': 'Confidence statement appropriately qualifies the synthesis as multi-source qualitative with unknown magnitudes and regional boundaries, matching the cited mix of theological reflection, psychiatric self-reports, and career-development interviews from limited SA contexts.'}

## What you still need to do

- [x] No passages flagged — spot-checking optional but recommended
- [ ] Read the LLM judge's concerns (if any) and agree/disagree
- Reviewer: ______  Date: ______  Final sign-off: YES / NO