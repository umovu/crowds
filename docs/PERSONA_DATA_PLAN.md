# Persona data plan — sources, gaps, and the build pipeline

Working plan for the persona library rebuild. Motivated by tester feedback
(2026-07-04): the library reads "NGO-poor" — every voice is a hardship story,
and scenarios that turn on non-income attributes (e.g. which parents' kids have
smartphones) can't differentiate. This plan covers: what we have, where it hits
and falls short, the files we build from, environmental context, and how web
research adds depth without ever authoring identity.

Hard rules that bound everything here (see CLAUDE.md):
- **No LLM-authored personas.** Surveys author identity; the LLM only styles.
- **Affordability from real data only**; wants-it and can-afford-it never merge.
- Web research produces **context bound to existing identities**, never people.

## 1. Current library — audit (269 personas, verified 2026-07-06)

### Where it hits
| Dimension | State |
|---|---|
| Employment/education/province/age | Real QLFS skeletons; marginals track StatsSA (37% employed ≈ real EPR) |
| Attitudes | Fused from 1,384 real Afrobarometer R9 SA donors by demographic match |
| Grant economics | Real SASSA amounts via `detect_grant` + `sa_grant_amounts.json` |
| Budget tiers | Deterministic (`mode_specs.budget_tier`), LLM-off testable |
| Household income | Real GHS `fin_reqinc` on 70/269 personas (overrides inference) |

### Where it falls short
| Gap | Evidence | Consequence |
|---|---|---|
| No top end | tiers: 133 tight / 126 moderate / **10 loose (4%)**; zero salaried-professional archetypes | Product rooms have ~1 comfortable buyer; "can afford, won't opt" is anecdotal |
| No population group | 0/269 carry race | Cannot claim SA demographic fidelity; no per-group readouts |
| No assets/connectivity | 0/269 carry smartphone, internet, assets, children-in-household | Scenarios dividing on non-income lines collapse into one voice |
| Geotype unused | in QLFS/GHS data, absent from persona fields | Township / suburb / rural clerk are the same person |
| Hardship-story monotony | 126/269 background stories money/grant/struggle-framed, incl. moderate tier | The middle *talks* like the bottom → the "money chorus" |
| Attitude coverage | Afrobarometer = civic/political only | No consumer/lifestyle attitudes; thin for product mode |
| Name reuse | ~55 "Thabo Mokoena" | Handled at selection (dedupe) but limits cast size |

## 2. File inventory

### Already in repo (`backend/data/microdata/`) — no downloads block the next steps
| File | Carries | Used for |
|---|---|---|
| `qlfs-2026-q1-v1.dta/.csv` | employment, occupation, education, age, province, **popgrp, geotype** | skeletons (today); popgrp/geotype enrichment (next) |
| `ghs-2025-person-v1.dta` | **smartphone/cell ownership**, income categories, all grant types, geotype, metro | attribute enrichment |
| `ghs-2025-household-v1.dta` | **head_popgrp, internet access, `fin_reqinc` (rand income), asset battery (pay-TV, computer, car…), child hunger, income source** | attribute enrichment + income coverage beyond 70 personas |
| `attitudes/afrobarometer_r9_sa.sav` | 1,384 real SA respondents | attitude fusion (live); **reserve a holdout slice before next rebuild** |
| `sa_grant_amounts.json` | published SASSA amounts | grant economics (live) |

### To collect (in need order)
| Dataset | Where | Unlocks | When |
|---|---|---|---|
| SEM segment definitions | ESS/BRC public docs | marketer-recognizable segment labels | now (hours) |
| SASAS or GCRO QoL microdata | HSRC / GCRO, free reg. | held-out attitude questions → benchmark tier 2 | with benchmark harness |
| Curated outcome facts (two-pot uptake, smartphone penetration by age, e-tolls…) | published stats, hand-built JSON | backtesting → benchmark tier 3 | with benchmark harness |
| Time Use Survey | DataFirst | how people actually spend time/money (esp. youth) | texture layer |
| LCS / IES expenditure baskets | DataFirst | what each income decile buys → story realism | texture layer |
| NHTS | DataFirst | commute mode/cost — strong class/voice marker | texture layer |
| Census 2022 10% sample | DataFirst | joint-distribution weighting if QLFS insufficient | benchmark tier 1, if needed |

### Derived artifacts (byproducts of the above)
- `sa_reference_stats.json` — ~15 dated headline figures; feeds the personas
  judge (judge upgrade #2) AND benchmark tier 1. One truth, two consumers.

## 3. Build pipeline (order of leverage)

1. **GHS attribute enrichment** — join person↔household GHS records, stamp onto
   skeletons: `population_group`, `geotype`+metro, `has_smartphone`,
   `internet_access`, `children_in_household`, asset flags, `monthly_household_income_rand`
   (raising real-income coverage from 70/269). Deterministic join, no LLM.
2. **Top-end batch** — ~40–60 personas from employed-formal / tertiary / higher
   `fin_reqinc` strata. New archetypes: `salaried_professional`,
   `aspirant_middle_class`, `established_household`. Same pipeline
   (QLFS/GHS body + Afrobarometer attitude donors + LLM voice-styling only).
3. **Story rewrite conditioned on data** — background stories regenerated (styled,
   not authored: every fact in the story must come from the persona's own fields)
   conditioned on tier + geotype + assets, so a moderate-tier suburban clerk talks
   school fees and DSTV, not survival. Kills the money chorus at the middle.
4. **SEM band mapping** — deterministic mapping from assets+income+geotype to a
   SEM band label per persona.
5. **Attitude refresh with holdout** — re-fuse after enrichment (better donor
   matching with popgrp+geotype); reserve the holdout question set FIRST.
6. **Selection/product changes** (parallel): product-mode tier tilt in
   `select_for_query` + afford×interest matrix presentation.

## 4. Environmental context

- `geotype` becomes a first-class persona field (step 1) — settlement type is
  the strongest environment signal in SA after income.
- `sa_context.py` daily block (now judge-checked against its snippets) stays the
  national ambient layer; next step is **conditioning ambient context on the
  persona's setting** — informal-settlement personas hear water/taxi-fare
  context, suburban personas hear rates/school-fees context — instead of one
  national gloom feed for everyone (a contributor to the money chorus).
- `sa_world_facts.json` + grant amounts remain the static fact floor.

## 5. Web research as depth, not authorship

Accepting the distribution problem doesn't mean waiting for the library: web
research can actively close *experienced* gaps per run, within the hard rule
(context bound to identities, never new identities — the WeWALK-fix pattern).

1. **Coverage honesty at /prepare** — deterministic check of the selected cast
   against the query's target segment (tier/archetype/geotype match). Thin
   coverage → say so in the UI ("2 of 20 personas match your target market")
   instead of silently running a mismatched room. Offer custom agents.
2. **Segment context briefs** — when coverage is thin, divert the run's web
   research budget to the target segment: real prices, adoption stats, competitor
   behaviour, segment-specific constraints. The brief is **bound to the nearest
   existing library personas** as runtime STANCE/context (like the economic
   lens), deepening how the closest real identities reason about this scenario.
   Never a new persona.
3. **Library backfill queue** — every thin-coverage event is logged (segment
   asked for, match count). That log is the demand signal that prioritizes which
   strata the next library batch builds — users tell us where the library is
   short by using the product.

What web research must never do (unchanged): author a persona, write a budget
figure, or become identity. Segments in briefs are people-TYPES; personas remain
survey-born.

## 6. Measurement (keeps us honest)

- Benchmark tier 1 (marginals + joints vs StatsSA tables) runs in CI from the
  same reference pack the judge uses.
- Attitude holdout (tier 2) after each fusion rebuild.
- `judge_log.jsonl` trendlines across library rebuilds and prompt changes.
- Rerun the tester's smartphone-ban scenario after step 1 as the acceptance
  test: the room must split parents by real smartphone/children attributes.
