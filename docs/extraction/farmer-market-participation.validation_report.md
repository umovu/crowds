# Validation report: farmer-market-participation

**Verdict: NEEDS HUMAN REVIEW**

> Automated pre-screen, not a substitute for reading the source paper.
> AUTO-APPROVED means nothing detectable was wrong, not that it is
> definitely correct.

## Deterministic checks

- Contamination lint: passed
- Passage faithfulness: 35/35 passages fuzzy-matched a source file (threshold 0.55)
- Vocabulary: all terms found in source text

## LLM second-opinion review

- Summary: Mechanism 0 contains an identity claim violation by attributing market exclusion to 'tradition and age' as inherent traits rather than reasoning constraints, and Mechanism 3 over-generalizes a specific HIV-related labour shock into generic sickness, losing critical contextual precision from the cited passages.

**Mechanism-chain fit:**
  - mechanism 0: CONCERN — Mechanism attributes risk aversion to 'tradition and age' as a psychological lock. Chain C1 cites P10/P11 linking 'old, illiterate, rely on traditions' to risk aversion, but the mechanism overstates this as an identity-based refusal ('treated as a threat') rather than a capability or information constraint. The chain supports reluctance due to lack of modern tech adoption, not necessarily that informal networks are preferred because formal ones are perceived as threats.
  - mechanism 1: OK — Mechanism accurately reflects Chain C2: lack of info/grades/contracts leads to inability to make selling decisions and price-taking behavior. Passages P2, P3, P5, P6, P22, P27 fully support this causal sequence.
  - mechanism 2: OK — Mechanism correctly captures Chain C3's logic: small surplus + consumption priority -> insufficient volume for formal markets -> reliance on local/informal outlets. Passages P1, P3, P8, P20, P23 align with this volume-constraint mechanism.
  - mechanism 3: CONCERN — Mechanism generalizes to 'sickness withdraws a family worker' as a single point of failure. Chain C4 specifically cites HIV-positive household members (P4, P15, P29) as the labour shock. The mechanism strips the specific health context (HIV/AIDS) which is central to the cited passages in this South African context, potentially misrepresenting the nature of the labour constraint as generic illness rather than a specific epidemiological factor documented in the source.
  - mechanism 4: OK — Mechanism faithfully represents Chain C5: remoteness/poor roads -> high transaction costs -> default to informal/non-participation. Passages P7, P14, P19, P33 support the fixed-cost/margin-erosion logic.

**Identity-claim violations flagged:** ['Risk aversion rooted in tradition and age locks out formal markets']

**Confidence honesty:** {'verdict': 'OK', 'note': 'Confidence field appropriately qualifies findings as robust for the specific smallholder typology in Limpopo/Mpumalanga while acknowledging unknown national prevalence and magnitude. This matches the two-study, region-specific provenance.'}

## What you still need to do

- [x] No passages flagged — spot-checking optional but recommended
- [ ] Read the LLM judge's concerns (if any) and agree/disagree
- Reviewer: ______  Date: ______  Final sign-off: YES / NO