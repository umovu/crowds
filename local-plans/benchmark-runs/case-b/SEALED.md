# Case B — Prepaid airtime + electricity · SEALED OUTCOME

**Case role:** CONTROL · run first. Sealed before any run. This file is the
pre-registered expectation; hindsight must not edit it.

---

## What we are testing

The floor. Can the sim say a confident **yes** to something obvious and
quantitatively true about the SA mass market?

- If this case fails AND Case A also fails → the sim is simply negative, and
  nothing else it says can be trusted.
- If this case fails and A passes → the bug is counter-stereotype-specific.
- If this case passes → the sim can still read an obvious win when the persona
  data supports it.

## The real outcome (sealed)

**Overwhelming adoption in exactly these segments — tight and moderate tiers.**

Prepaid is how the mass market buys airtime and electricity. It is not a niche
choice; it is the default mechanism for a large share of the population.

**Documented reason:** prepaid gives the buyer **control over irregular income**.
A person whose earnings or grant arrive unevenly cannot absorb a surprise bill or
a locked contract. Pay-per-use, load-only-what-you-can afford, nothing billed
later, no credit check, no termination penalty. The cost-per-unit premium over a
contract is the accepted price of that control. This is why the mechanism is the
floor: the "win" is not a new behaviour — it is an endorsement of an existing one.

**Edge filter:** none needed. This is pure customer reasoning — a person deciding
how they prefer to pay. Distribution, marketing, price wars and timing are not in
play.

## Pass condition (sealed)

Score with the objection classifier + condition split (Phase 0). The case passes
iff:

1. **Objection profile** is dominated by **satisfiable conditions**, not
   dealbreakers — the condition-vs-dealbreaker split must show a condition
   majority in the cast.
2. `fee_sensitivity` and `cost_of_access` may appear but must **not be blocking**
   (i.e. they must co-occur with conditional phrasing, not hard refusals).
3. Stance distribution is recorded for continuity but is **never the pass/fail**.

## Fail signal (sealed)

A room of `concerned` with dealbreaker phrasing ("I will not", "not for me").
That is the floor collapsing: the sim rejecting the mechanism the mass market
already uses every day. If that happens, report it as the sim being
indiscriminately negative — the strongest negative finding in the whole set.

## Contamination

**MEDIUM-LOW.** Prepaid's popularity is common knowledge, so a trained model can
echo it from priors. That is fine — this case tests endorsement of an existing
norm, not prediction of a new one. The element that must NOT come from priors is
the *reason*: control over irregular income. If the room endorses prepaid but the
dominant objection-type profile is `fee_sensitivity`/`cost_of_access` blocking,
the sim endorses without understanding, and we record that as a load-bearing
reason failure.

## Cast plan

- **n=20.** Tight + moderate tiers only (the mass market), mixed archetypes
  (informal trader, grant-dependent, domestic worker, small business, etc.).
- No loose tier — the floor claim is about the mass market, not the affluent.
- Tier 0 grounding coverage recorded in `CAST.md` before scoring: % with exact
  attitude-donor match, % with real household income, % with bound cards.

## Run protocol

- Cold pitch: no company name, no brand, no year, no outcome hint.
- Minimum 3 runs, different seeds. Report spread, not the mean.
- Score four things separately: direction · load-bearing reason · source
  (grounded vs naked) · cards-off delta (n/a here unless cards bind).
- If the "no comment" signature appears (every interview identical/empty), the
  run is void and must be re-run, not scored.

## Dated signature

Sealed before the first run of Case B. Any change to this file after runs begin
invalidates the case.
