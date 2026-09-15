# Customer Sim Scorecard — how our system scores

Assessment of the Crowds panel/sim against the eight-line Customer Sim Scorecard
(`customer_sim_scorecard_1.md`). Scored 0 / 1 / 2 per line.

**Total: 11 / 16.** Middle band — "useful but has a hidden failure mode."

We know exactly which line is low and exactly what it is. That is written up
below with the evidence behind every score.

---

## The evidence base

Four studies back this assessment. Nothing here is scored from opinion.

| # | Study | What it was | File |
|---|---|---|---|
| **CS-1** | **Eskom privatisation backtest** | 30 library personas vs held-out Afrobarometer Q80A, survey-weighted. Policy mode. Exact ground truth computed locally. | `BACKTEST_RESULTS_2026-07-23.md` |
| **CS-2** | **TymeBank pre-launch backtest** | 25 personas, product mode, full panel path, pitched the bank as it existed before Feb 2019. Real outcome sealed first: ~10M customers by 2025, strongest in low-income. | `TYMEBANK_PANEL_BACKTEST.md` |
| **CS-3** | **Segment-contrast experiment** | The identical TymeBank pitch put to three homogeneous casts (tight / loose / grant recipients). 54 interviews, 54 successful. Objections classified by a deterministic keyword classifier, no LLM in the scoring path. | `SEGMENT_CONTRAST_REPORT.md` |
| **CS-4** | **Stage 6 card validation** | Mechanism cards run cards-on vs cards-off on scenarios the source papers never discussed, repeated. | `docs/EXTRACTION_PROTOCOL.md` Stage 6, `backend/scripts/stage6_validate.py` |

A fifth asset exists but is mostly unrun: `SA_BENCHMARK_CASES.md` holds eight
real SA cases with documented outcomes, four business and four policy, four of
which have exact ground truth computable from our own Afrobarometer file. Only
two have been run. That gap is the single biggest reason line 1 is not a 2.

---

## The scores

### 1. Tethered to reality — **1 / 2**

*Has it been checked, cold, against real cases where the outcome is known?*

**What we have.** Two cold backtests where the outcome was sealed before the
run. CS-1 used a held-out survey column, so the benchmark is a number we derive
locally rather than one recalled from memory. CS-2 used a documented commercial
outcome. CS-4 is a genuine cards-on vs cards-off comparison, which is the second
half of what a 2 requires.

**Why not a 2.** One run each. No variance estimate on either. Six of the eight
benchmark cases in `SA_BENCHMARK_CASES.md` are unrun. The scorecard asks for
*regular* reality-checks; we have done it twice.

**What the checks found.** Both failed on direction.

CS-1, Eskom privatisation:

| answer | panel | real | diff |
|---|---|---|---|
| agree | 26.7% | **62.9%** | **-36.2** |
| disagree | 36.7% | 26.5% | +10.2 |
| neither | **36.7%** | 10.6% | **+26.1** |

Real South Africans supported privatising Eskom 63/27. The panel opposed it
27/37. This was deliberately chosen as a counter-stereotype case, and the panel
produced the stereotype. It also hedged: 36.7% picked "neither" against a real
10.6%, more than three times the real fence-sitting rate.

CS-2, TymeBank:

| check | result |
|---|---|
| Direction — does it show interest? | **FAIL** — 24/25 concerned, 1 neutral, 0 support |
| Right reasons cited? | **PASS** — interest/savings 20/25, kiosk convenience 10/25, no fees 7/25 |
| Right friction surfaced? | **PASS** — trust / no branches 19/25 |
| Do tight-budget personas engage? | **FAIL** — 17 concerned, 1 neutral, 0 support |

**One honest caveat on CS-1.** The scenario framing supplied its own
counter-argument ("others say electricity is too important to hand to private
owners chasing profit"), and the answer list made "neither" a first-class
choice. Both may have primed the result. That is a flaw in the test design, not
proven to be a flaw in the product, and it needs a re-run with neutral framing
before the accuracy finding is fully trustworthy.

---

### 2. Honest about blind spots, on the screen — **1 / 2**

*Can the user see which voices are grounded vs improvised?*

**What we have.** The honesty is real and it is computed. Every persona that
binds research carries `research_citations` with card id, citation and
confidence. `attach_research_context` adds **no keys at all** when nothing
binds, so the absent field is itself the honest signal. `docs/GROUNDING_TESTING.md`
Tier 0 requires recording, before trusting any output: percentage of personas
with an exact attitude-donor match, percentage with real household income vs an
inferred tier, and percentage with bound mechanism cards.

**Why not a 2.** None of it reaches the user. A search of `frontend/src` finds
no reference to `research_citations` or citations at all. The provenance UI is
Phase 3 of `docs/ACADEMIC_GROUNDING.md` and is not built. On screen today, a
persona reasoning from two cards and a persona reasoning from nothing look
identical and equally confident.

This is the line both testers independently asked for. One wanted
hover-for-paper-references. The other assumed the personas weren't data-born,
precisely because the grounding is invisible.

---

### 3. Knows what it structurally cannot see — **1 / 2**

*Does it state its own edge?*

**What we have.** The team knows the edge and the rules encode part of it. The
product rules forbid emitting a "% who would buy" or any validation score. An
affordability share computed from real income is allowed; a purchase probability
is not. By that standard CS-2 worked as designed: it produced objections,
conditions and a remedy, not a score.

**Why not a 2.** The tool never states its boundary, and the absence bites. From
CS-2:

> The risk is that `concerned 24 / 25` still **reads as a verdict** to a founder,
> even though no score is computed. A user seeing this would conclude "don't
> launch" about a product that became one of SA's biggest banking successes.

That is the scorecard's line-3 failure exactly: silently taking blame for
something outside customer reasoning. TymeBank's win ran on distribution, kiosk
placement inside retailers, and years of marketing spend. A customer-reasoning
model cannot see any of that, and nothing in the output says so.

---

### 4. Separates can-afford / circumstances-allow / want-to — **2 / 2**

*Or does it mash them into one "probably not"?*

All three are separate, by architecture and by hard rule.

- **Can afford** is `budget_tier`, computed from the persona's real surveyed
  income. Deterministic. The model cannot write it. Product-mode casts are
  filtered by tier *before* selection using the same `_economic_fields`
  computation later stamped on the profile, so the filter and the stamp cannot
  drift apart.
- **Circumstances allow** are measured fields carried per persona, and they
  visibly do the work. CS-2: Oratile Khoza objected because *"I only access the
  internet weekly and do not own a computer"* — her measured `internet_use` and
  `owns_computer` driving the objection, not her wallet.
- **Want to** is qualitative LLM output only. Objections, conditions,
  willingness in words.

CS-3 shows why the split matters commercially. The three barriers separate
cleanly by segment and the *fix differs for each*: grant recipients need the
data-cost problem solved (90% raised it), loose-budget customers need human
recourse (93%), tight-budget customers need biometric reassurance (45%). One
blended verdict would have hidden all three.

---

### 5. Reasons from mechanism, not vibe — **2 / 2**

*Can it travel to a product nobody studied?*

The extraction protocol enforces this mechanically. Stage 4 applies a hard
runnability gate: could a persona apply this rule to a scenario the paper never
discussed? "Cattle are important" fails and dies there. "Cattle function as
savings and insurance, so selling is a last resort rather than routine income"
passes, because it transfers.

Stage 5 requires every mechanism to trace back to numbered passages, and Stage 6
proves transfer empirically on scenarios the source papers never covered. The
rendered block scored **15/15 on the hoop test** — the reasoning appeared with
cards and was rare without them.

The affective rule is part of this line too. Emotional material may enter only
as "X breeds/erodes/triggers Y", never as "people like this ARE Y". The first is
transferable reasoning; the second is a stereotype wearing a citation.

CS-2 shows it working live. Otsile Molefe: *"I'm not handing my fingerprint to a
new outfit just because a kiosk promises me interest. I need to see my actual
mates from the Local Builders Forum pull their cash first."* That is social
proof as a decision rule, and social proof is how TymeBank actually grew.

---

### 6. Resists the echo chamber by design — **1 / 2**

*Is the sceptic in the room, and as well-armed as the enthusiast?*

**Voices: solid.** `persona_retrieval.select_for_query` allocates base seats in
proportion to the library's QLFS-tracked mix, caps the relevance tilt at
`MAX_TILT = 3.0`, and enforces `MIN_DISTINCT_ARCHETYPES = 4`. A taxi query
cannot produce a room of only taxi operators.

**Grounding: tilted.** This is the scorecard's exact level-1 description —
diverse personas, but grounding tilts toward whoever was studied. Our own card
README lists the gaps: no card for `institutional_loyalist` or `community_leader`,
and no coverage at all for the top-end professional segment. The starter corpus
is heavily weighted to grants, informal savings, farmers, township consumers and
youth.

So in CS-2, Otsile the informal trader argued from bound stokvel and fintech
research, while Realeboga the urban professional and Lehlohonolo the
institutional loyalist argued from nothing. The doubter can be the naked one.

Note the design does not fake coverage to hide this: an archetype with no
matching card gets nothing, never a forced bind to the nearest non-match. That
honesty is why the gap is visible at all.

---

### 7. Real data about a person beats patterns about people like them — **1 / 2**

*Is the source hierarchy right way up?*

**The hierarchy is right, and enforced in the prompt.** The research block closes
with: "These are documented patterns for people in your situation — where they
conflict with your own stated outlook and beliefs, your own outlook prevails."
Underneath that sits a stricter rule: numbers computed from real data are never
overridable by anything.

**CS-3 is strong evidence it works.** Grant recipients raised biometric concerns
at **20%**, against 45% for tight-budget and 43% for loose-budget personas — less
than half as worried about handing over a fingerprint. The real-world cause is
obvious once seen: they already give biometrics to SASSA every time they collect.
Nothing in the pitch or the prompt says this. A model reasoning from stereotype
would have made the poorest personas the *most* suspicious of authority-adjacent
data collection, not the least. The persona data beat the stereotype.

**But it leaks, in two documented places.**

1. CS-1 caught the model overriding the persona. Personas repeatedly reasoned
   "I don't care who owns it as long as the lights stay on" — the right instinct,
   matching the real 63% — and then talked themselves out of it on generic price
   fear. The measured data pulled toward reality; something downstream overrode
   it.
2. CS-2 found `internal_state.attitudes` **empty on 25 of 25 agents**. This is a
   dict/list type mismatch at `opinion_agent.py:300`: the code type-checks for a
   dict, the library ships a list. Twelve measured attitudes per persona are
   being discarded into the psychological-state layer. The emotion and needs
   model sits at defaults on every agent, and `impact_metadata.affected_entity`
   is extracting the first capitalised word of the response rather than an
   entity — top values were `Opening`, `However`, `Cutting`, `Walking`.

A hierarchy with three inert layers is a hierarchy that exists on paper.

---

### 8. Cheap and boring enough to run constantly — **2 / 2**

*A ceremony, or a tool you run twenty times while shaping a pitch?*

About R0.95 per balanced run. The simulation runtime uses a separate cheap model
tier from research and personas, and the thinking-token fix cut sim output cost
by roughly 50x.

Everything below the model is deterministic and testable with the LLM switched
off: cast selection, budget tiers, card binding, grant detection. That is what
made CS-3 possible at all — 54 interviews scored by a keyword classifier with no
model in the scoring path, so the comparison is assertable rather than argued.

CS-3 itself is the proof of iteration cost: three full panels on one pitch, run
to answer a single question about whether aggregation was hiding signal.

---

## The one test that matters

The scorecard says line 1 is the test, with four questions over it. We have run
it, twice, and the pattern is identical both times.

| question | CS-1 Eskom | CS-2 TymeBank |
|---|---|---|
| **Direction** — did the room lean the way reality did? | **FAIL** (36.2pt gap, inverted) | **FAIL** (0 support of 25) |
| **Load-bearing reason** — did anyone name what decided it? | **PASS** — "I don't care who owns the wires as long as the lights stay on" is the real 63% instinct | **PASS** — trust, no branches, social proof; and the panel summary named the real remedy |
| **Source** — grounded voice or naked one? | **PASS** — assets, occupation and measured circumstances drove the arguments | **PASS** — measured internet use, device ownership, walking distance |
| **Cards-off delta** — did the answer change? | not run per-case | **PASS** at protocol level (CS-4, 15/15 hoop) |

And the filter over the top: *did this succeed or fail for a customer-reasoning
reason at all?* For TymeBank, partly not. Distribution — kiosks inside stores
people already visit — was central to the win, and distribution is outside the
sim's edge. That miss should not be charged fully to the tool. But zero
enthusiasm across 25 people, including the two with **no bank account at all**,
is too uniform to excuse.

That last detail is the sharpest single finding in the whole assessment. From
CS-2:

> The two personas with **no bank account** — the single clearest target market
> for a free, five-minute account — react exactly like the 21 who already have
> one. In reality that difference is the entire business case.

---

## What the failure actually is

CS-2 concluded that the persona data shapes the words and has no effect on the
verdict. CS-3 revised that, and the revision matters:

> The persona reaches the response, then is **thrown away by the five-point
> stance scale.** Every persona sits somewhere in the middle on a new bank, so an
> intensity axis saturates while the *kind* of hesitation varies a great deal.

The proof is in the same 54 interviews read two ways.

**By intensity — everything collapses:**

| cast | stance distribution |
|---|---|
| tight_budget (n=20) | concerned 14, neutral 5, oppose 1 |
| loose_budget (n=14) | concerned 13, support 1 |
| grant_recipients (n=20) | concerned 17, neutral 1, oppose 2 |

44 of 54 landed on `concerned`. Three structurally different populations, one
headline verdict.

**By objection type — it separates sharply:**

| objection type | tight | loose | grant | spread |
|---|---|---|---|---|
| no_human_support | 50% | 93% | 60% | **43pp** |
| digital_capability | 80% | 50% | 90% | **40pp** |
| identity_biometric | 45% | 43% | 20% | **25pp** |
| fee_sensitivity | 95% | 79% | 90% | 16pp |
| cost_of_access | 30% | 14% | 15% | 16pp |

Two spreads exceed 40 percentage points. Each divergence has an obvious
real-world cause and none of it was prompted. The well-banked object hardest to
losing branches because they currently have branches to lose. Data cost is a
first-order barrier for poor South Africans and a non-issue for the affluent.

So the verdict on the whole assessment is narrower than "the sim is wrong":

> **Segmentation is not impossible with this library. It is impossible with this
> metric.**

---

## What moves the score

Ranked by score gained per unit of work.

**1. Kill or demote the stance scale (line 1, line 3).** The signal already
exists in the text and is being discarded at the last step. CS-3 turned the same
54 interviews into an actual go-to-market table — what to lead with, what to
solve first, what not to mention — purely by reading type instead of intensity.
This is the highest-value change on the list and it needs no new data.

**2. Fix the three inert layers (line 7).** The `attitudes` dict/list mismatch at
`opinion_agent.py:300`, the defaulted emotion/needs model, and the
`affected_entity` parser. Then re-run CS-2 and measure whether variance appears.
Causation is not proven — that these layers are inert *and* the verdict is
uniform is consistent, not conclusive — and a controlled test is the honest way
to settle it.

**3. Surface grounding in the UI (line 2).** `research_citations` and the Tier 0
coverage numbers already exist per persona. Showing them, plus a grounded-vs-naked
marker, moves line 2 from 1 to 2 without touching the engine. It also answers
both testers' original complaint.

**4. State the edge in the output (line 3).** One line on every panel result
naming what the panel cannot see: distribution, pricing power, marketing spend,
timing, regulation. Cheap, and it directly prevents the "don't launch TymeBank"
misread.

**5. Run the remaining six benchmark cases (line 1).** `SA_BENCHMARK_CASES.md`
already has them written, four with locally computable ground truth. Repeats, not
single runs — the extraction protocol's own rule is that single runs are never
evidence.

**6. Fill the card gaps (line 6).** No cards for `institutional_loyalist`,
`community_leader`, or the professional segment. Until then the sceptic in a
middle-class room is arguing without grounding.

**Also worth fixing regardless of score:** CS-2 reproduced the silent-failure bug.
Two attempts returned 25 × "I have no comment on that" and exited 0, with no
error surfaced. A user hitting an expired key sees a full panel of empty answers
and nothing telling them it broke. If every interview in a round fails, the round
should fail loudly.

---

## Summary table

| # | Line | Score | The evidence |
|---|---|---|---|
| 1 | Tethered to reality | **1** | CS-1, CS-2 run cold; CS-4 cards-on/off. Two cases, one run each, six unrun. |
| 2 | Honest about blind spots on screen | **1** | Citations and coverage computed; zero frontend references. |
| 3 | Knows its edge | **1** | No validation score by rule; but "concerned 24/25" reads as a verdict. |
| 4 | Afford / circumstances / want separated | **2** | Deterministic tier, measured circumstances, qualitative want. CS-3 shows different fixes per barrier. |
| 5 | Mechanism not vibe | **2** | Stage 4 runnability gate; 15/15 hoop on unseen scenarios. |
| 6 | Resists echo chamber | **1** | Voices capped and floored; grounding tilted to studied segments. |
| 7 | Person beats pattern | **1** | CS-3 biometric result proves it works; CS-1 override and 25/25 empty attitudes prove it leaks. |
| 8 | Cheap and boring | **2** | ~R0.95/run; deterministic layers made CS-3 assertable. |
| | **Total** | **11 / 16** | Useful, with one known failure mode: the verdict metric. |
