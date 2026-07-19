# Validation report: communal-cattle-asset-logic

**Verdict: AUTO-APPROVED**

> Automated pre-screen, not a substitute for reading the source paper.
> AUTO-APPROVED means nothing detectable was wrong, not that it is
> definitely correct.

## Deterministic checks

- Contamination lint: passed
- Passage faithfulness: 34/34 passages fuzzy-matched a source file (threshold 0.55)
- Vocabulary: all terms found in source text

## LLM second-opinion review

- Summary: All mechanisms are well-grounded in their cited chains, inferred links are reasonable extensions of the source logic, and confidence is appropriately calibrated to the qualitative, multi-site evidence base.

**Mechanism-chain fit:**
  - mechanism 0: OK — Mechanism accurately reflects Chain C1's logic regarding cattle as liquid assets and the rejection of cash outlays unless income is secured.
  - mechanism 1: OK — Mechanism faithfully captures Chain C2's causal link between youth unemployment/herder shortage and theft, and the resulting evaluative rule for interventions.
  - mechanism 2: OK — Mechanism correctly summarizes Chain C3's rational choice framework where species ownership is determined by comparative utility.
  - mechanism 3: OK — Mechanism aligns with Chain C4's definition of resilience as dependent on resources, networks, and finance, and the corresponding policy evaluation criteria.

**Inferred-link verdicts:**
  - APPROVE: therefore how a new product/policy gets read: policies that support cattle health (e.g., free veterinary services) are embraced, while those requiring cash outlay are rejected unless they secure the income role of cattle. — Reasonable inference from C1's premise that cattle are primary income/liquid assets; follows logically that health support (preserving asset value) is accepted while cash costs are resisted unless ROI is clear.
  - APPROVE: therefore how a new product/policy gets read: policies that create youth employment or provide herding solutions are seen as directly reducing cattle loss. — Directly supported by C2's explicit causal chain linking unemployment/herder shortage to theft.
  - APPROVE: therefore how a new product/policy gets read: a new livestock policy or product is evaluated by whether it enhances the utility of the species a household already prefers, given its socio-economic profile. — Valid inference from C3's rational choice model; if ownership is utility-maximizing, interventions must improve utility of preferred species to be adopted.
  - APPROVE: therefore how a new product/policy gets read: policies that provide financial access, strengthen social networks, or enable diversification are seen as building resilience, while those ignoring these gaps are viewed as inadequate. — Follows directly from C4's definition of resilience dependencies and observed coping behaviors.

**Confidence honesty:** {'verdict': 'OK', 'note': 'Confidence statement accurately reflects mixed-methods, multi-site qualitative sources without overstating generalizability or quantifying effects.'}

## What you still need to do

- [x] No passages flagged — spot-checking optional but recommended
- [ ] Read the LLM judge's concerns (if any) and agree/disagree
- Reviewer: ______  Date: ______  Final sign-off: YES / NO