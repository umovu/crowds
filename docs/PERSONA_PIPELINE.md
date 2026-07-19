# Persona pipeline — how a seed record becomes a voice in the room

End-to-end trace of the five diagnostic pieces: **(1)** the persona-generation
prompt, **(2)** the seeding/sampling code, **(3)** the schema, **(4)** the
segment/recruiting logic, **(5)** one generated persona vs. its seed. Written
because two tester complaints (the edtech "everyone" run; Tumelo's
communal-vs-absentee farmer mis-slice) traced to the same upstream layers, and
this doc is the reference for fixing them.

The hard rule that bounds everything (CLAUDE.md): the LLM never authors
identity. Surveys author identity; the LLM only styles. This doc shows where
that boundary actually sits in the code, and where the tester-visible drift
enters despite it.

## The pipeline in one diagram

```
(1) Sampling         (2) Archetype + attitudes    (3) Texture (ONE LLM layer)
D:\Fub-agentsociety\  D:\Fub-agentsociety\          D:\Fub-agentsociety\
backend\data\         backend\scripts\              backend\scripts\
microdata\            archetype_mapper.py +         texture_generator.py
qlfs-2026-q1-v1.dta   attitude_fuser.py             (writes texture only;
                      persona_sampler.py             identity already fixed)
 (whole-row,
  weights=Weight)
        │                        │                          │
        └────────────┬───────────┴──────────────────────────┘
                     ▼
  D:\Fub-agentsociety\backend\app\data\persona_library\personas.json  (269 entries)
                     │
                     ▼
  (4) Retrieval + segments + provenance guard
  D:\Fub-agentsociety\backend\app\services\panel_service.py
  D:\Fub-agentsociety\backend\app\services\simulation_manager.py
  D:\Fub-agentsociety\backend\app\services\persona_retrieval.py
   segment predicate → select_for_query → _build_profile → assert_library_cast
                     │
                     ▼
           sim cast / panel roster
```

Three LLM-free stages fix identity. One LLM stage writes the human surface.
Retrieval is LLM-free. The texture stage is the only place the model can inject
its prior — and it is where the "NGO-poor" drift enters.

---

## (1) The persona-generation prompt

There is no standalone "persona generator." The LLM touches the pipeline in
exactly one stage: **texture generation** at build time. Everything else
(skeleton, attitudes, archetype, name, retrieval) is LLM-free.

### Relevant files

| File | Role |
|---|---|
| `D:\Fub-agentsociety\backend\scripts\texture_generator.py` | The LLM texture stage. `_SYSTEM` (line 98), `_prompt` (line 154), `generate_texture` (line 201). The only LLM call in the build. |
| `D:\Fub-agentsociety\backend\scripts\attitude_fuser.py` | Fuses measured Afrobarometer R9 stances onto each skeleton *before* texture, so attitudes are part of the fixed identity the LLM only expresses. |
| `D:\Fub-agentsociety\backend\app\api\research.py` | The *runtime* `/people` route (line 961) does LLM-author personas — but `assert_library_cast` (`D:\Fub-agentsociety\backend\app\services\panel_service.py:198`) bars that path from any sim cast. It's a custom-agent UX path, not the sim-cast path. |

### How seed attributes reach the model

**As a terse JSON blob, not woven into instructions.**
`D:\Fub-agentsociety\backend\scripts\texture_generator.py` `_prompt` (line 154-189) dumps the frozen fields with
`json.dumps(facts, ensure_ascii=False, indent=2)` at line 167 under the header
`FIXED FACTS (do not change, contradict, or invent around — write texture
consistent with exactly these):`. The model gets a flat dict, not a narrative
briefing. Fields the model has no positive value for (income, assets) are
simply absent — absence is where the prior fills the gap.

### Stereotype-inviting language

The user prompt opens (`D:\Fub-agentsociety\backend\scripts\texture_generator.py:163`): `"Write English-only persona texture for
this South African individual."` The phrase "South African individual" fires
the model's training prior. There is **no counter-signal** — nothing tells the
model this person may be affluent, or that it must reflect their actual
economic position rather than defaulting to hardship. The system prompt
(`D:\Fub-agentsociety\backend\scripts\texture_generator.py:98-109`) constrains *language* (English only) and *attitudes* (express
the fused survey stances) but is silent on economic-position fidelity.

### Affluent attributes: absent, not stated positively

`FROZEN_FIELDS` (`D:\Fub-agentsociety\backend\scripts\texture_generator.py:85-96`) for a civic QLFS persona carries: `age, gender,
province, education, occupation, employment_status, informal, industry,
marriage_status, is_neet, actor_archetype`. **No income, no assets, no car, no
medical aid, no LSM, no tenure, no income source mix.** `monthly_household_income_rand`
is in `FROZEN_FIELDS` but only populated for GHS education personas
(`D:\Fub-agentsociety\backend\scripts\build_library.py:50`, `sample_education_skeletons`). For the 113 civic QLFS
personas — the bulk of any "everyone" room — the model gets e.g.
`occupation="Legislators; senior officials and managers"` and nothing else
telling it this person is affluent. The model then writes a precarious
small-business owner one setback from ruin (see §5, Naledi). That is the
prior backfill, in the shipped data.

### What the LLM is allowed to write

`TEXTURE_FIELDS` (`D:\Fub-agentsociety\backend\scripts\texture_generator.py:78-82`): `persona, background_story, voice_guide,
behavioral_tendencies, group_affiliation, interested_topics`. Name is **not**
in this list — names come from a curated pool (`D:\Fub-agentsociety\backend\scripts\sa_names.pick_unique_name`,
`D:\Fub-agentsociety\backend\scripts\texture_generator.py:241`) assigned after texture, because independent LLM name generation
mode-collapses onto a few prototypes (the "55 Thabo Mokoenas" bug).

---

## (2) The seeding/sampling code

### Relevant files

| File | Role |
|---|---|
| `D:\Fub-agentsociety\backend\scripts\persona_sampler.py` | Stage 1. Whole-row sampling from QLFS microdata, weighted by survey `Weight`. LLM-free, deterministic. |
| `D:\Fub-agentsociety\backend\scripts\build_library.py` | Orchestrates the build: `sample_skeletons → fuse_attitudes → map_skeletons → generate_texture → stable id → personas.json`. |
| `D:\Fub-agentsociety\backend\app\services\persona_retrieval.py` | Retrieval at sim time. `select_for_query` (line 81): representative base + bounded relevance tilt. LLM-free. |
| `D:\Fub-agentsociety\backend\app\services\persona_library.py` | Read access to `personas.json`. `sample` (line 148) is uniform; `select_for_query` is the representative path. |

### Whole-record sampling, weights= in the call

`D:\Fub-agentsociety\backend\scripts\persona_sampler.py` `sample_skeletons` (line 135-150):

```python
df = _load(dta_path)
drawn = df.sample(n=n, replace=True, weights=df["Weight"], random_state=seed)
return [_row_to_skeleton(row) for _, row in drawn.iterrows()]
```

`weights=df["Weight"]` **is** in the sample call. Every skeleton is a real,
population-weighted co-occurrence — a 19-year-old professor earning R90k is
impossible because the fields co-occurred in one surveyed person. The docstring
(`D:\Fub-agentsociety\backend\scripts\persona_sampler.py:12-16`) calls out *why* whole-row: independent field-sampling would
produce demographically impossible people.

The library is built once offline; the hosted app reads `personas.json` via
`PersonaLibrary` (`D:\Fub-agentsociety\backend\app\services\persona_library.py:1-14`) and never pays texture cost per user.

### The "everyone" path — where the edtech experience comes from

`D:\Fub-agentsociety\backend\app\services\panel_service.py` `create_session` (line 339-418):

```python
seg_list = ... or ["everyone"]
if seg_list == ["everyone"]:
    cast = select_for_query(n, pitch, province=province, seed=seed, library=library)
```

`select_for_query` (`D:\Fub-agentsociety\backend\app\services\persona_retrieval.py:81-176`) gives every persona a
**baseline weight of 1.0** (line 114), multiplied only by a keyword tilt from
`derive_tilt(query)` (line 64-78). `_KEYWORD_ARCHETYPES`
(`D:\Fub-agentsociety\backend\app\services\persona_retrieval.py:44-56`) matches:
`taxi, spaza, informal, unemploy, youth, grant, pension, small business,
entrepreneur, community, service delivery`. **An edtech pitch matches none of
these** → `derive_tilt` returns `{}` → every persona weight 1.0 → **uniform
sampling over the library**.

The library is population-weighted (QLFS weights at build), so it is
demographically *honest* that it is poverty-skewed — SA is. The 269-persona
library breaks down: 49 grant_dependent_survivor, 30 disillusioned_dropout,
22 unemployed_youth, 53 civic_moderate (many poor), 21 informal_trader, vs
**8 small_business_owner + 10 institutional_loyalist = 18 affluent-ish =
6.7%**. So "everyone" = ~7% affluent. That is the edtech tester's experience,
and it is not a sampler bug — it is the correct representative answer to a
question he didn't mean to ask. "Everyone" means "representative SA," not
"everyone in my market." There is no ticket-size gate on the "everyone"
segment.

Note: the QLFS survey weight is used at **build** time, not at **retrieval**
time. Retrieval is uniform over the already-weighted library. So the weighting
is correct; the poverty skew is structural to SA, not a sampling error.

---

## (3) The persona schema / data model

### Relevant files

| File | Role |
|---|---|
| `D:\Fub-agentsociety\backend\app\services\agent_profile_generator.py` | `AgentProfile` dataclass — the profile shape consumed by `OpinionAgent` / `run_simulation_as.py`. Note at line 4: "LLM-based persona *generation* has been removed." |
| `D:\Fub-agentsociety\backend\scripts\texture_generator.py` | `FROZEN_FIELDS` (line 85) and `TEXTURE_FIELDS` (line 78) — the effective schema for a library persona. |
| `D:\Fub-agentsociety\backend\app\services\panel_service.py` | `_build_profile` (line 221) attaches product-mode economic fields at sim time. |
| `D:\Fub-agentsociety\backend\app\services\mode_specs.py` | `budget_tier` — deterministic affordability, computed from real data only. |

### What a civic persona carries

Skeleton fields (from QLFS, fixed before the LLM — see
`D:\Fub-agentsociety\backend\scripts\persona_sampler.py:_row_to_skeleton` line 110-132): `age, gender, province,
education, occupation, employment_status, informal, industry, marriage_status,
is_neet, actor_archetype`. Plus fused Afrobarometer attitudes (4 dims:
gov_trust, economic_optimism, service_satisfaction, crime_fear — see
`D:\Fub-agentsociety\backend\scripts\attitude_fuser.py`) and beliefs.

Texture fields (the LLM writes — `D:\Fub-agentsociety\backend\scripts\texture_generator.py:78-82`):
`persona, background_story, voice_guide,
behavioral_tendencies, group_affiliation, interested_topics`. Plus `name` from
the curated pool (`D:\Fub-agentsociety\backend\scripts\sa_names.py`), `id` (sha256 of skeleton+seed —
`D:\Fub-agentsociety\backend\scripts\build_library.py:54-61`), `source_entity_type =
"library_persona"`.

### What a civic persona does NOT carry

**No income, no assets, no car, no medical aid, no LSM, no population group,
no land tenure, no income source mix, no smartphone, no children-in-household,
no geotype.** This is the upstream cause of the tester-visible problems:

- **Naledi** (§5) is a senior corporate manager the model wrote as a
  precarious spaza-supplier, because the seed had no income/asset field to be
  faithful to. The schema has no affluent signal → the prompt can't state it
  positively → the prior fills the gap.
- **Tumelo** (§5) is one of 6 farmers in the library, all `Elementary
  Occupation` (farm labourers). There is no `Skilled agricultural` occupation,
  no farm-owner, no communal smallholder, no absentee landlord. The schema has
  no `land_tenure`, `farm_role`, or `income_source_mix` field — even if a
  commercial farmer were sampled, nothing in the record could distinguish
  communal from absentee from wage-labour. The flat-farmer problem is a schema
  problem before it is a prompt problem.

### Product-mode economic fields (attached later, not in the seed)

`D:\Fub-agentsociety\backend\app\services\panel_service.py` `_build_profile` (line 221-262) attaches, in product mode only:
`is_grant_dependent`, `grant_type`, `monthly_income_rand`, `income_provenance`,
`budget_tier`. These come from `detect_grant` + `D:\Fub-agentsociety\backend\app\services\mode_specs.py` `budget_tier` —
**computed from archetype/occupation heuristics and GHS household income, not
from the seed record the LLM saw.** The affluent civic persona never gets a
positive affordability stamp at texture time. "Wants it" / "can afford it"
separation is enforced in *product* mode, but the *identity* layer the LLM
textured has no affluence signal to be faithful to.

---

## (4) The segment / recruiting logic

### Relevant files

| File | Role |
|---|---|
| `D:\Fub-agentsociety\backend\app\services\panel_service.py` | `SEGMENTS` dict (line 53-124) — the taxonomy a user picks from. `create_session` (line 339) routes the pick. |
| `D:\Fub-agentsociety\backend\app\services\persona_retrieval.py` | `select_for_query` (line 81) — the "everyone" path; `derive_tilt` (line 64) — keyword→archetype tilt. |
| `D:\Fub-agentsociety\backend\app\services\simulation_manager.py` | `prepare_simulation` (line 479-484) — the sim-cast path, same `select_for_query → _build_profile → assert_library_cast` chain. |

### The segment taxonomy

`SEGMENTS` (`D:\Fub-agentsociety\backend\app\services\panel_service.py:53-124`): `everyone, unemployed,
grant_recipients, informal_traders, small_business, youth, employed, learners,
guardians, gogo_guardians, educators, fee_paying, no_fee_school`. Each has a
`predicate` over persona fields.

### Where Tumelo's mis-slice lives

`grant_recipients` predicate (`D:\Fub-agentsociety\backend\app\services\panel_service.py:64-68`):

```python
"grant_recipients": {
    "predicate": lambda p: p.get("actor_archetype") == "grant_dependent_survivor",
}
```

This is a single archetype the mapper assigns to over-60s not-economically-active
and the long-term withdrawn (`D:\Fub-agentsociety\backend\scripts\archetype_mapper.py:101-108`). It does **not**
include child-support-grant households where adults work — a household
receiving the CSG but with an employed parent is in `civic_moderate` or
`employed`, not `grant_dependent_survivor`. The `receives_grant` GHS field
exists on education personas but the `grant_recipients` predicate ignores it.
So "grant recipients" as a segment under-counts working grant households —
Tumelo's mis-slice.

### How far from ticket-size-based recruiting

Closest thing: `fee_paying` / `no_fee_school` (`D:\Fub-agentsociety\backend\app\services\panel_service.py:114-123`), education-only,
predicated on GHS fee bands. There is **no income-tier segment for the civic
population** — no `loose_budget`, `moderate_budget`, `tight_budget` chip, no
LSM gate, no household-income-decile filter. Outside education, recruiting is
archetype-based, and the archetype taxonomy has no affluent-non-small-business
category (see §3). You are nowhere near ticket-size-based recruiting for the
civic population.

### How a user's selection maps to filters

- **"everyone"** → `select_for_query(n, pitch)` with keyword tilt only (`D:\Fub-agentsociety\backend\app\services\panel_service.py:373-374`).
- **one named segment** → `_mixed_cast` with that segment's predicate filtering the library (`D:\Fub-agentsociety\backend\app\services\panel_service.py:377`).
- **multiple named segments** → `_mixed_cast` round-robin, even seat allocation across segment pools (`D:\Fub-agentsociety\backend\app\services\panel_service.py:276-317`).
- **"everyone" + anything** → rejected (`D:\Fub-agentsociety\backend\app\services\panel_service.py:360-361`): "everyone is already the full mix."

All paths end in `_build_profile → assert_library_cast` (`D:\Fub-agentsociety\backend\app\services\panel_service.py:378-381`), which
refuses any non-library identity — so the runtime `/people` LLM-author path
(`D:\Fub-agentsociety\backend\app\api\research.py:961`) can never leak into a sim cast.

---

## (5) One persona vs. its seed, side by side

The single most diagnostic artifact. Two records, pulled from
`D:\Fub-agentsociety\backend\app\data\persona_library\personas.json`.

### High-LSM: Naledi Motaung — proves the prompt drift

**Seed (QLFS skeleton, the `FROZEN_FIELDS` the model was given):**

```
age: 42, gender: Female, province: Gauteng
education: Secondary completed
occupation: "Legislators; senior officials and managers"
employment_status: Employed, informal: false
industry: "Wholesale and retail trade"
marriage_status: Never married, is_neet: false
actor_archetype: small_business_owner   ← D:\Fub-agentsociety\backend\scripts\archetype_mapper.py:128
attitudes: gov_trust=low, economic_optimism=pessimistic,
           service_satisfaction=mixed, crime_fear=mid
           (fused via D:\Fub-agentsociety\backend\scripts\attitude_fuser.py)
```

**What the LLM wrote (texture fields):**

- `persona`: *"A pragmatic wholesale distributor operating out of a warehouse
  in Johannesburg South, she manages a lean team… a self-made manager who
  relies on personal networks rather than state support…"*
- `background_story`: *"runs her own small distribution business, supplying
  independent spaza shops… if the business fails, there is nothing else… She
  lives in a secure complex, acutely aware that her hard-earned assets make
  her a target."*
- `voice_guide`: *"avoiding political jargon or optimistic slogans…
  preferring to discuss tangible risks and immediate survival strategies."*

**The drift:** the seed said "Legislators; senior officials and managers" in
wholesale/retail — a senior corporate manager. The archetype mapper collapsed
that to `small_business_owner` (`D:\Fub-agentsociety\backend\scripts\archetype_mapper.py:128`: managers → 50%
small_business_owner, 25% community_leader, 25% institutional_loyalist —
there is no `corporate_executive` archetype). The LLM then wrote a
spaza-shop supplier one setback from ruin. No income figure was in the seed,
so the model invented "no safety net," "if the business fails there is
nothing," "hard-earned assets make her a target" — the affluent persona is
written as precarious. That is the prior backfill, in the shipped data.
Affluence was never stated positively, so it didn't survive.

(Aside: the background starts *"Thandiwe completed her secondary education"*
but the persona's name is Naledi. Names come from a curated pool assigned
*after* texture — `pick_unique_name` at `D:\Fub-agentsociety\backend\scripts\texture_generator.py:241`
(impl in `D:\Fub-agentsociety\backend\scripts\sa_names.py`) — so the LLM
improvised "Thandiwe" in prose and the curated name overwrote the label but
not the body. Minor, but it shows how loosely the "FIXED FACTS" constraint
actually binds the prose.)

### Farmer: Tumelo Ramavhoya — proves the schema gap

**Seed:**

```
age: 26, gender: Male, province: Limpopo
education: Secondary completed
occupation: "Elementary Occupation"   ← QLFS grouping = farm labourer
employment_status: Employed, informal: false
industry: "Agriculture; hunting; forestry and fishing"
actor_archetype: civic_moderate        ← D:\Fub-agentsociety\backend\scripts\archetype_mapper.py:136 default
```

**LLM wrote:** *"general laborer on a commercial citrus farm… steady but
modest income… lives with his parents… wages eroding monthly."* Honest to the
seed.

But this is the **only** kind of farmer the library can hold. All 6
agriculture personas in the 269-entry library are `Elementary Occupation`
(farm labourers), except one `Legislators; senior officials and managers
(informal)`. There is no `Skilled agricultural and fishery` occupation, no
farm-owner, no communal smallholder, no absentee landlord. The schema has no
`land_tenure`, `farm_role`, or `income_source_mix` field — even if a
commercial farmer were sampled, nothing in the record could distinguish
communal from absentee from wage-labour. `D:\Fub-agentsociety\backend\scripts\archetype_mapper.py`
`_candidates` (line 117-137) routes every employed-non-informal farmer through the default
`civic_moderate 0.7` branch — there is no farmer archetype at all. Tumelo's
communal-vs-absentee distinction is unrepresentable at three layers: QLFS
occupation grouping (in `D:\Fub-agentsociety\backend\scripts\persona_sampler.py`) → archetype taxonomy
(`D:\Fub-agentsociety\backend\scripts\archetype_mapper.py`) → persona schema (`D:\Fub-agentsociety\backend\scripts\texture_generator.py` FROZEN_FIELDS).

---

## Where the drift enters — summary

| Layer | File:line | LLM? | What goes wrong |
|---|---|---|---|
| Sampling | `D:\Fub-agentsociety\backend\scripts\persona_sampler.py:149` | no | Correct — whole-row, weighted. Poverty skew is structural to SA, not a bug. |
| Archetype mapping | `D:\Fub-agentsociety\backend\scripts\archetype_mapper.py:128,136` | no | Managers collapse to `small_business_owner`; no farmer archetype; no affluent-salaried archetype. |
| Schema | `D:\Fub-agentsociety\backend\scripts\texture_generator.py:85` (FROZEN_FIELDS) | no | No income/assets/LSM/tenure on civic personas → no affluent signal for the LLM to be faithful to. |
| **Texture prompt** | **`D:\Fub-agentsociety\backend\scripts\texture_generator.py:154-189`** | **yes** | Terse JSON blob; "South African individual" language; no positive affluence statement → prior backfills hardship. **This is where Naledi's drift enters.** |
| Retrieval | `D:\Fub-agentsociety\backend\app\services\persona_retrieval.py:81` | no | Uniform over the (correctly poverty-skewed) library when no keyword tilt matches → the edtech "everyone" experience. |
| Segments | `D:\Fub-agentsociety\backend\app\services\panel_service.py:64` | no | `grant_recipients` = one archetype, misses working CSG households → Tumelo's mis-slice. No income-tier segment for civic population. |
| Library data | `D:\Fub-agentsociety\backend\app\data\persona_library\personas.json` | no | 269 personas; ~7% affluent. The shipped artefact the above layers produced. |

The texture stage is the only LLM layer, and it is the only place the model
can inject its prior — but it drifts *because the schema and archetype layers
upstream give it nothing affluent to be faithful to.* The fix order is:
schema (add asset/income/tenure from a survey that carries them — NIDS or
IES, since QLFS doesn't) → archetype taxonomy (add a farmer split and an
affluent-salaried archetype) → then the prompt can be told to state
affluence positively and forbid the precarious-by-default framing. The
prompt alone cannot fix Naledi, because the seed she was built from had no
affluence field to defend.
