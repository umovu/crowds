# How a persona forms an opinion

How the system builds a South African persona, where every attribute comes
from, how income enters, and where the language model is allowed to act.

The rule underneath everything: **real data decides who someone is and what
they already believe. The model only puts that into words and reacts to the
room.**

---

## 1. The pipeline, end to end

```
QLFS / GHS microdata   ->  identity skeleton      (real survey row, weighted)
        v
archetype_mapper       ->  behaviour type          (rules, no model)
        v
attitude_fuser         ->  measured attitudes      (Afrobarometer donor match)
        v
income_seeder / GHS    ->  income + affordability  (published + surveyed rands)
        v
texture_generator      ->  name, voice, story      (model, ONCE, offline)
        v
personas.json          ->  the curated library
        v
run time               ->  one model call per agent per round
        v
position_clustering    ->  distinct positions
        v
convergence_detector   ->  stop on coverage saturation
```

Stages 1 to 4 are deterministic and testable with the model switched off.
Stage 5 is the only place the model writes anything that sticks.

---

## 2. Where the body comes from

`backend/scripts/persona_sampler.py`

- Source: Stats SA Quarterly Labour Force Survey (QLFS) microdata, licensed,
  gitignored.
- Whole survey **rows** are drawn with replacement, weighted by the survey
  weight.
- Whole-row sampling is the point. Drawing each field on its own would produce
  impossible people (a 19-year-old professor on R90k). A whole row is a
  combination that actually co-occurred in a real respondent.
- Because rows are weighted, the sampled set reproduces national marginals.
- Under-15s are dropped: QLFS only asks labour questions of 15+, and that is
  also the simulation's universe.

A second body source, `backend/scripts/ghs_adapter.py`, draws from the General
Household Survey. It is used for education personas (learners, guardians,
gogo-guardians) and affluent personas, and it is the source that carries **real
reported household income in rand**.

### Attributes taken from QLFS

| Field | Meaning |
|---|---|
| `age` | exact years |
| `gender` | Female / Male |
| `province` | one of the nine, verbatim label |
| `education` | education status ladder |
| `occupation` | grouped occupation label |
| `employment_status` | Employed / Unemployed / Not economically active |
| `informal` | in informal employment or not |
| `industry` | industry of work |
| `marriage_status` | marital status |
| `is_neet` | not in employment, education or training |
| `race` | normalised to the shared four-category vocabulary |
| `geotype` | Urban / Traditional / Farms |

### Extra attributes taken from GHS

| Field | Meaning |
|---|---|
| `monthly_household_income_rand` | real reported net household income |
| `income_provenance` | `ghs_2025_reported` |
| `home_language` | household language |
| `internet_at_home` | fixed or mobile |
| `computer_in_home` | asset flag |
| `receives_grant` | social grant in the household |
| `ghs_role` | learner / guardian_parent / gogo_guardian |
| `current_grade`, `edu_institution` | for learners |
| `fees_band`, `time_to_school`, `guardian_type` | school reality |
| `learners_in_household`, `learner_fee_bands` | for guardians |
| `farm_market_orientation`, `farm_products` | for farmer builds |

### Health attributes (GHS, only loaded when the scenario is health-adjacent)

| Field | Meaning |
|---|---|
| `medical_aid` | covered or not |
| `self_rated_health` | own rating of own health |
| `has_disability` | reported disability |
| `usual_health_facility` | the clinic or hospital actually used |
| `health_facility_sector` | public or private |
| `transport_to_health_facility` | how they get there |
| `time_to_health_facility` | how long it takes |
| `health_provenance` | `ghs_2025_reported` |

Missing answers stay missing. Nothing here is imputed or guessed.

---

## 3. Behaviour type (archetype)

`backend/scripts/archetype_mapper.py`

- Assigns an `actor_archetype` from the skeleton, using seeded rules. No model.
- The archetype is not cosmetic. It drives how often the agent speaks, which
  events target them, who they hear from in the feed, and their closing voice
  instruction.
- Only archetypes that census fields honestly imply are assigned: livelihood
  and civic types.
- Behavioural-edge types (agitator, looter, conspiracy spreader) are **never**
  inferred from demographics. There is no survey field for "incites violence",
  and a rule like "young plus unemployed plus male equals agitator" is
  stereotyping. Those slots are filled from the user's own scenario instead.
- Without this stage the library would be 200 identical moderates, useless for
  stress-testing.

---

## 4. Where the attitudes come from

`backend/scripts/attitude_fuser.py` and `attitude_donor_adapter.py`

QLFS has no attitude questions, and the attitude survey interviewed different
people. There is no join key. The honest technique is **donor matching**.

- Donors: Afrobarometer Round 9 South Africa, 1,384 real respondents, survey
  weighted.
- For each skeleton, find the donors whose demographics are nearest, then
  import one of their **measured** attitude vectors.
- Match on: `gender`, `province`, `education_band`, `employment_status`,
  `age_band`, `race`.
- The pick is a weighted draw seeded from the skeleton hash, so the same
  persona always gets the same attitudes.
- If the exact six-key cell has no donor, keys drop in a fixed order until
  donors exist. How coarse the match had to be is stored as `match_quality`,
  so every attitude is auditable.
- One donor supplies the **whole** vector, so a persona's outlook, assets and
  hardship stay internally coherent. A real person held all of them at once.
- `race` was added as a sixth key after held-out evaluation. It roughly halved
  distribution error for Indian/Asian (14.0 to 7.0), White (12.7 to 7.8) and
  Coloured (6.7 to 3.9) personas. The measured cost: exact matches fell from
  about 85% to about 76%.

### Attitudes imported (the stance vocabulary)

Core:
- `gov_trust` - low / mid / high
- `economic_optimism` - pessimistic / neutral / optimistic
- `service_satisfaction` - dissatisfied / mixed / satisfied
- `crime_fear` - low / mid / high
- `education_satisfaction` - dissatisfied / mixed / satisfied

Health:
- `health_service_satisfaction`
- `health_authority_trust`

Policy mode:
- `councillor_responsiveness` - does raising it with a councillor achieve anything
- `official_responsiveness`
- `crime_handling`
- `immigration_priority`

Product mode:
- `pays_for_quality` - willingness to pay more for better service
- `business_trust` - how much proof a pitch needs
- `social_trust` - whether word of mouth is plausible
- `environment_priority` - how near environmental harm already sits in this life

`pays_for_quality` is a measured attitude on purpose. It never becomes a
"% who would buy".

### Circumstances imported (facts, deliberately NOT attitudes)

These ride the same donor match but live in a separate vocabulary, because
"owns no car" is a fact about a life, not an opinion. The model may restate an
attitude in its own words. It must not contradict a circumstance.

- `lived_poverty` - Afrobarometer Lived Poverty Index, none to high
- `went_without_care` - gone without medical care
- `owns_vehicle`, `owns_computer`, `owns_bank_account`, `owns_television` - none / household / own
- `internet_use` - never to daily
- `electricity_reliability` - never to always
- `money_decision` - self / joint / other / none, who can actually authorise a purchase
- `news_radio`, `news_tv`, `news_internet`, `news_social` - which channels actually reach this person

---

## 5. Where income comes in

Income enters at four separate points, each with its own provenance, and the
more real source always wins.

**1. Real reported household income (strongest for spending power)**
GHS `fin_reqinc`, net rand per month, carried as
`monthly_household_income_rand` with `income_provenance: ghs_2025_reported`.
Sentinel and missing values become `None`, never a guess.

**2. Published grant amounts (highest integrity)**
`backend/app/services/income_seeder.py`. About a third of South Africa lives on
a grant, which breaks any occupation-to-income model: the grant *is* the
income, and its amount is published policy, a known number rather than an
estimate. Detection uses only signals already on the persona (archetype,
occupation, background story, the `safety_economic` need). Provenance is
`grant_schedule`, read from `backend/data/sa_grant_amounts.json`.

**3. Assets, as a living-standard proxy**
`backend/app/services/lsm_proxy.py`. Real LSM is an asset checklist, not an
income measure, and the personas already carry those assets, so they are scored
directly. Eight signals: vehicle, computer, bank account, television, internet
use, geotype, electricity reliability, plus a lived-poverty brake. Bands run
Band 1 "Going without" to Band 4 "Comfortable". Missing values score zero and
are never guessed. It is called a proxy everywhere it surfaces, because it
approximates official LSM from 8 signals rather than reproducing its 14.

**4. Affordability tier at run time**
`backend/app/services/mode_specs.py`, `budget_tier()`. This is the only income
figure the simulation acts on, and it is computed, never written by the model.

Precedence inside `budget_tier`:
1. Real surveyed household income in rand overrides everything.
2. Otherwise a real grant amount sets the tier. Even the largest grant, the old
   age grant, never reaches "loose" discretionary income.
3. Otherwise the tier is inferred from role and economic-security signals.

Learners have no income of their own. A gogo household carries real household
income, and that overrides the role path entirely.

**The hard rule.** In product mode "wants it" and "can afford it" are separate
fields and never merge. "Wants it" is qualitative model output: objections,
conditions, willingness. "Can afford it" is `budget_tier`, computed from real
data. If the model can write or change a budget figure, that is a bug. The
system never emits a purchase probability.

---

## 6. Where the model is allowed to act

**Once, offline, at library build.** `texture_generator.py` writes the human
surface only: `persona` sentence, `background_story` (45 to 60 words, first
person), `voice_guide` (how they speak in English), `behavioral_tendencies`
(what they do in a group), `group_affiliation`, `interested_topics`.

The name is deliberately **not** model output. Asked hundreds of times in
isolation for "a realistic SA name", the model collapsed onto a few prototypes;
about 55 library personas ended up as "Thabo Mokoena", which breaks a feed and
merges people in the UI. Names now come from the curated pool in
`backend/scripts/sa_names.py`, assigned uniquely against a running used-set,
guided by home language then province.

Because texture is expensive and offline, the hosted app just reads
`personas.json` and never pays that cost per user.

Every persona gets a stable id: a hash of its frozen skeleton plus the build
seed. Texture is excluded from the hash, so a rebuild keeps the same id even if
the model rephrases the story.

---

## 7. What the agent sees each round

`backend/app/services/opinion_block.py`, one model call per agent per round.

The prompt is assembled in this order:

1. Document context, then general South African context, which is mode-aware:
   policy mode gets the unrest priming, product and custom casts do not.
2. Who they are, from `character_context` in `opinion_agent.py`: archetype,
   group, persona line, age, gender, occupation, education, marital status,
   province, current stance, radicalism level, background story.
3. **The measured attitudes**, rendered as fixed facts under the heading
   "WHAT YOU HOLD TO BE TRUE - measured survey data about people like you, not
   opinions to be argued out of". The model may express them in its own words
   but must not contradict or invent one.
4. Voice instructions and behavioural pattern.
5. The health block, only when the scenario is health-adjacent, so unrelated
   runs pay zero extra tokens.
6. The economic lens, in product mode only: the pitch plus this agent's current
   budget tier and evolving stance.
7. A topic banner, repeated in **every** prompt, not just round one.
8. The last five feed posts, and one specific post to reply to.

In fast mode the full context is sent on first encounter only; later rounds get
an abbreviated header.

### Choosing what to do

Each agent picks one of five actions: `EXPRESS_OPINION`, `RESPOND_TO_OPINION`,
`SEARCH_TOPIC`, `OBSERVE`, `DO_NOTHING`.

- Loud archetypes are forced to speak while the conversation is active. Quiet
  ones may stay silent. That is how the room gets a shape rather than 40 people
  all talking.
- The reply target is not simply the newest post. Recent posts are scored by
  word overlap with the topic and the most on-topic one is handed over, so the
  thread pulls back toward the subject instead of compounding drift. Pure
  lexical scoring, no model.
- `interested_topics` is deliberately **not** used as a topic fallback. It used
  to be, and it ordered whole rooms to stay on one randomly chosen personal
  interest.

### Who they hear from

The feed is homophily-biased, in `agentsociety_opinion_block.py`. Similarity is
registered per agent as archetype, group, and **current** stance, held by
reference so the live stance is read each round rather than a cached one.
People hear more from people like themselves, which is what makes positions
harden rather than average out.

### What moves

Each agent carries a stance on a five-point scale - support, neutral,
concerned, oppose, resist - and a radicalism level from 1 to 5. Product mode
reuses the same machinery relabelled as a reaction ladder. Stance change is
read from the agent's own self-reported line at interview time, with a keyword
heuristic as fallback, and every change is recorded as a delta with the before
and after.

---

## 8. How a run ends

`convergence_detector.py` and `position_clustering.py`

This is a **coverage** simulator. It stops when the room has run out of new
things to say, never because people agree.

- `PositionRegistry` counts genuinely distinct positions **cumulatively** across
  the whole run. A per-round count is blind to swaps: three new objections
  replacing three old ones leaves the count flat.
- Clustering is **stance-first**. A general embedder groups by subject, so
  "this tax punishes poor families" and "good, junk food should cost more"
  would merge despite being opposites. Posts are bucketed by stance, then
  clustered only within a bucket.
- When no new position has appeared for four rounds, the run stops.
- The older "sentiment has stabilised" rule still runs, but shadow-logged only.
  It stopped runs too early.
- Embeddings come from the existing Ollama service. If unreachable it falls
  back to word-overlap clustering. The two are not comparable, so a mid-run
  flip logs a warning and resets the saturation baseline.

---

## 9. The lines the system does not cross

- No model-generated personas. The cast is the curated library first, custom
  agents second, never model-authored.
- The model never sets identity, never sets a budget figure, never picks a name.
- Web research supplies world facts and context only. It never writes a person.
- Attitudes are measured and imported, never invented.
- Archetypes are never inferred from demographics where doing so would be
  stereotyping.
- No "% who would buy" and no validation score is ever emitted.
- Every economic rule must be assertable with the model switched off. If it
  cannot be, it is in the wrong layer.
