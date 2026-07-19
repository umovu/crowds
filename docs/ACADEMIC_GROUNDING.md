# Academic grounding — mechanism cards from pre-selected papers

Design for grounding simulation context in SA behavioural research, with visible
citations. Motivated by both testers independently (Tumelo: hover-for-paper-refs,
papers as "aggregated surveys with the insights behind them"; Nkosinathi: used
time-use research to make a product decision, assumed personas weren't data-born
because grounding is invisible).

## What we're trying to achieve

Make sim responses reason the way real studies say each segment actually
reasons — a communal farmer talks stock theft and community standing, not
generic hardship — and surface that grounding as citations in the UI. This is
the credibility core of the "market research co-pilot" positioning.

## Hard rules (unchanged, mechanically enforced)

- Papers shape **STANCE/context bound to existing survey-born identities** —
  never author personas, never touch affordability.
- Papers contribute **mechanisms and vocabulary, never numbers**. Quantitative
  attitudes stay with microdata fusion (Afrobarometer/SASAS); headline stats go
  to `sa_reference_stats.json`, not cards.
- Retrieval + binding must run **LLM-off testable** end to end. The LLM only
  styles responses *through* mechanisms; it never invents one.

## Why pre-selection, not live retrieval

The hard problem is extraction, not search: a paper is ~8,000 words wrapped
around five useful sentences. Live retrieval means per-run LLM cost, no review
gate, and bad extractions silently poisoning sims. Pre-selection inverts all
three: extract once, offline, human-reviewed. 30 vetted cards beat 300 scraped
papers.

Existing plumbing to reuse: `literature_service.py` (ArXiv/OpenAlex/CrossRef +
local uploads), `agent_enricher.enrich_from_literature` (currently shallow —
dumps titles only, same string for every archetype; replace with card binding).
OpenAlex is the right live backbone later (free, region/concept filters); arXiv
is near-useless for SA sociology.

## The mechanism card (the schema IS the extraction contract)

Never ask the LLM to "summarise the paper" — ask it to fill this schema. The
fields discipline the output:

```json
{
  "id": "ainslie-2013-cattle",
  "citation": "Ainslie (2013), J. of Southern African Studies",
  "segment_tags": ["communal_farmer", "rural", "livestock_owner"],
  "topic_tags": ["livestock", "savings", "insurance", "status"],
  "mechanisms": [
    "Cattle function as a savings and insurance vehicle; selling is a last resort, not routine income",
    "Herd size signals social standing; decisions weigh community perception, not just economics"
  ],
  "vocabulary": ["lobola", "stock theft", "dipping"],
  "objection_patterns": ["Will this expose my herd/assets to outsiders?"],
  "claim_type": "qualitative",
  "region": "Eastern Cape",
  "year_range": "2008-2012",
  "confidence": "ethnographic, single-region"
}
```

- `mechanisms` — causal reasoning rules ("X because Y"), not findings. The payload.
- `segment_tags` — from the existing archetype/geotype/tier vocabulary → runtime
  binding is a deterministic lookup, no LLM matching.
- `claim_type: qualitative` — the guardrail: extraction is forbidden from
  carrying numbers out of papers.
- `region`/`year_range`/`confidence` — staleness + scope for the judge and
  honest UI citations.
- `vocabulary`/`objection_patterns` — fixes voice (the "stock theft" words).
- One card per **mechanism cluster**, not per paper — e.g. three stock-theft
  studies collapse into one card with three citations.

## Phased flow

1. **Phase 1 — curated corpus (start here).** Hand-pick ~20–40 papers driven by
   the segment list (coverage-driven, not search-driven). Offline script: paper
   → LLM fills schema → **human reviews card** → committed JSON next to
   `sa_world_facts.json` (cards are data, they ship; this doc stays local).
2. **Runtime binding = lookup.** Cast selected → cards matched on segment_tags
   → mechanisms injected alongside the economic lens → citations stored on the
   run. Assertable LLM-off: "communal farmer received the cattle-as-savings card".
3. **Provenance UI** — citation list on run/persona, hover-for-source. Answers
   Tumelo's ask and Nkosinathi's invisibility problem in one stroke.
4. **Phase 2 — live OpenAlex retrieval** only when a scenario hits uncovered
   segments/topics (reuses the coverage-honesty trigger); proposes new cards
   into a **review queue** — never injects unreviewed text into a running sim.

## Starter corpus (~30 works, by segment; ★ = first extraction batch)

Prefer open-access full text (SciELO SA, PMC, university repos) for extraction;
books extract from reviews + key chapters, not 300 pages.

### Grants & low-income household economics (largest segment)
- ★ Zembe-Mkabile et al. — CSG spending/allocation studies.
  https://pmc.ncbi.nlm.nih.gov/articles/PMC4727456/
  Mechanisms: grant money is allocated, not just spent — uniforms, transport,
  social-capital spend compete with food; meals rationed to protect education.
- ★ Deborah James, *Money from Nothing: Indebtedness and Aspiration in South
  Africa* (Stanford UP, 2015); OA companion article "Mediating Indebtedness":
  https://www.tandfonline.com/doi/full/10.1080/00141844.2017.1362450
  Mechanisms: credit is status/aspiration-bound; ~30k mashonisas; borrowing is
  aspirational, not just survivalist. Key for "wants it but stretched".
- Black Sash, *Social Grants: Challenging Reckless Lending*:
  https://blacksash.org.za/wp-content/uploads/2023/09/Social_Grants_Challenging_Reckless_Lending.pdf
  Objection pattern: "will this take money off my card?"

### Informal savings & financial life
- ★ Stokvel cluster — Verhoef (women & stokvels 1930–1998):
  https://www.researchgate.net/publication/30963582
  Orange Farm case: https://www.scielo.org.za/scielo.php?script=sci_arttext&pid=S0037-80542014000400004
  Festive-season retail stokvels: https://www.researchgate.net/publication/336198924
  Mechanisms: trust/kin-based; lump-sum thinking vs monthly budgets; women-led.
  Needed for any savings/fintech/subscription sim.
- Burial societies / funeral economics (Case & Menendez "Paying the piper";
  Roth) — funerals as largest discretionary spend event; insurance attitudes.

### Communal & emerging farmers (Tumelo's segment)
- ★ Ainslie — *Keeping Cattle?* / Eastern Cape communal cattle studies:
  https://www.researchgate.net/publication/242580473
  Peddie District: https://centaur.reading.ac.uk/82831/
  Mechanisms: cattle as savings/insurance/status; selling last resort; herd
  decisions weigh community perception.
- ★ Stock theft cluster — PLOS One farmers' perceptions (2024):
  https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0310881
  Nyandeni welfare impact: https://www.scielo.org.za/scielo.php?pid=S0301-603X2025000300004&script=sci_arttext
  Mechanisms: syndicate-driven theft; police distrust; theft risk shapes
  willingness to adopt anything exposing assets. The "rural safety" card.
- Nguni project literature (interventions landing with communal farmers):
  https://www.researchgate.net/publication/261877544
- Remote emerging farmer: literature thin — search OpenAlex (absentee livestock
  ownership / telefarming SA); no card until a solid source exists.

### Township consumers & spaza economy (product mode)
- ★ Spaza customer experience (JEBS 2022):
  https://ojs.amhinternational.com/index.php/jebs/article/view/3304
  Spaza coopetition (SAJBM): https://sajbm.org/index.php/sajbm/article/view/1295/1385
  Mechanisms: shop credit is normal; proximity/relationship beat price.
- Township brand research (industry, mark confidence accordingly):
  https://africanmarketingconfederation.org/brand-loyalty-and-purchasing-decisions-of-township-residents-examined/
  Mechanism: low income ≠ low brand aspiration; premium local brands desirable.

### Tech adoption & connectivity
- ★ GSMA smartphone affordability (mechanisms only; numbers →
  sa_reference_stats.json):
  https://african.business/2026/01/technology-information/cheaper-smartphones-can-close-africas-digital-divide-says-gsma
  Mechanisms: device cost as % of income is the adoption wall; strong appetite
  for device financing.
- Mobile money & financial inclusion SSA:
  https://www.sciencedirect.com/science/article/abs/pii/S0167624523000495
  Mechanisms: why SA lags Kenya (banked population, distribution); data-cost
  sensitivity as standing objection.

### Youth
- ★ Honwana, *The Time of Youth* ("waithood"):
  https://www.academia.edu/12629968
  Mechanisms: suspended between school and work; improvised income; agency
  without structure.
- UCT township youth perceptions of poverty/unemployment:
  https://open.uct.ac.za/handle/11427/3842
  Mechanisms: expect to out-do parents but expect environment to block them;
  job search runs on social networks because search itself costs money.

### Cross-cutting
- SEM/LSM segmentation papers (ESS/BRC — already on plan's to-collect list).
- Ubuntu/collectivism in consumer decisions (OpenAlex) — the "is this aligned
  with my community" reasoning, beyond farming.

### Known gap
Top-end/professional segment has almost no card coverage — deliberate: those
personas don't exist yet (plan step 2). Add middle-class debt/aspiration cards
(James partially covers) when that batch lands.

## Sequencing vs the persona data plan

Cards slot in after GHS enrichment gives personas the segment fields
(geotype, assets) that cards bind on — extraction of the ★ batch can start
anytime (it's offline), but runtime binding lands with/after step 1.
