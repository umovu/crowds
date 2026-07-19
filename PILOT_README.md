# Context-grounding pilot worktree

Separate git worktree (branch `context-grounding-pilot`, checked out at
`D:/fub-agentsociety-context-pilot`) for validating whether research papers +
real statistics shape persona responses. Nothing here touches the main repo
(`D:/Fub-agentsociety`) or the live app.

## Context for coding agents working in this worktree

Read this section first — it is the project state you need.

**The product** (main repo): a multi-agent SA policy/product simulation.
Users describe a scenario; the system runs it through synthetic personas
built from REAL survey microdata (QLFS skeletons + Afrobarometer attitude
fusion). Hard rules from the main repo's CLAUDE.md apply here too:

- **No LLM-authored personas, ever.** Surveys author identity; the LLM only
  styles voice. Personas come from
  `D:/Fub-agentsociety/backend/app/data/persona_library/personas.json` (269
  records) — load them, never invent them.
- **Numbers never come from the LLM or from memory.** Real figures live in
  `backend/app/data/sa_world_facts.json` and
  `backend/data/sa_grant_amounts.json` (main repo). Papers contribute
  qualitative mechanisms only (`claim_type: qualitative`) — never carry a
  statistic out of a paper into a card.
- **Everything must be testable with the LLM off** — card→persona binding is
  a deterministic archetype-tag lookup, not an LLM match.

**What this worktree is for**: piloting the "academic grounding" design
(full design: `docs/ACADEMIC_GROUNDING.md` in the MAIN repo — it is
untracked there, plans stay local). The idea: pre-selected papers are
distilled offline into human-reviewed **mechanism cards** (JSON: citation,
segment_tags, mechanisms, vocabulary, objection_patterns); at runtime cards
bind to personas by archetype and inject documented reasoning patterns into
the system prompt, with citations surfaced in the UI later.

Card extraction follows `docs/EXTRACTION_PROTOCOL.md` (six-stage pipeline:
harvest → chain → scope → formalize → gate → validate), one worksheet per
card from `docs/extraction/WORKSHEET_TEMPLATE.md`. Stages 1-4 run
programmatically via `backend/scripts/extract_card.py` (paper text in, draft
worksheet + card JSON out, deterministic lint included); the human's job is
proofreading the draft and signing off Stage 5.

**What has been established so far** (details:
`docs/CONTEXT_GROUNDING_PILOT_REPORT.md` in this worktree):

1. v1 proved a mechanism card produces a real reasoning shift, not just
   restyled prose (stokvel trust-model appeared unprompted and reframed a
   savings product's lock-in as "bait").
2. The coverage-honesty gate matters: the library has NO farmer/livestock
   archetype, so the stock-theft card had nothing to bind to — confirming a
   tester-reported gap against live data. Never force-bind a card to the
   nearest non-matching persona.
3. `segment_tags` need a closed vocabulary that maps 1:1 onto persona fields
   (archetype today; geotype/assets when the library gains them).
4. One caveat holds over everything: single runs at temperature 0.7 are
   noisy. Only consistency across repeat runs counts as evidence.

**Framework note**: production sims run `OpinionCitizenAgent(PersonAgent)`
(`backend/app/services/opinion_agent.py` + `backend/scripts/run_simulation_as.py`).
`PersonAgent` (from the `agentsociety2` package) is a tool-loop agent whose
`profile` dict is auto-injected into every system prompt — so the eventual
production integration is "add a research_context key to the profile dict",
not a new agent class. `backend/app/services/opinion_block.py` and
`agentsociety_opinion_block.py` are DEAD code paths (never instantiated) —
don't build on them. This pilot intentionally uses bare OpenAI calls instead
of PersonAgent because the only variable under test is prompt context.

**Environment**: no venv or .env in this worktree — scripts borrow the main
repo's (`D:/Fub-agentsociety/backend/.venv/Scripts/python.exe`, root `.env`).
Sim-tier model = `SIM_LLM_*` env vars (cheap tier); do not switch pilots to
the `LLM_*` research-tier model. `uv run` is broken on this machine
(torchvision wheel) — always call the venv python directly.

**Conventions**: keep this pilot self-contained under `backend/scripts/` +
docs; don't touch main-repo services from here. Commit messages terse, no
rationale body. Accent colour `#1E9E5A` if any UI ever appears here.

## How to run

From this directory (`D:/fub-agentsociety-context-pilot`):

```
D:/Fub-agentsociety/backend/.venv/Scripts/python.exe backend/scripts/context_grounding_pilot_v2.py
```

Each run costs ~9 LLM calls on the sim-tier model.

## What v2 does

- Loads 3 REAL personas from the library (one each: grant_dependent_survivor,
  informal_trader, unemployed_youth).
- Binds mechanism cards deterministically: a card attaches only if the
  persona's `actor_archetype` is in the card's `segment_tags`.
- Loads the stats block from the repo's real curated files
  (`sa_world_facts.json`, `sa_grant_amounts.json`).
- Runs each persona through the same scenario under 3 conditions:
  - `baseline`    — identity only
  - `cards`       — identity + paper-derived mechanism cards
  - `cards+stats` — identity + cards + real cost/grant figures
- Each response ends with a self-reported `STANCE:` line (same format the
  production `opinion_agent.py` parses).

## Output

Console shows all 9 responses. Full JSON saved to
`backend/scripts/context_grounding_pilot_v2_output.json` (overwritten each
run — rename to keep a run, e.g. `..._run1.json`). One completed run exists
(2026-07-08): stances were Thandeka `concerned→concerned→oppose`,
Noluthando `concerned→oppose→concerned`, Thabo `concerned` throughout.

## What to look for when validating

1. **baseline vs cards** — does reasoning route through the documented
   mechanism (stokvel trust, budget-displacement, hidden-fee suspicion), or
   is it the same generic response reworded?
2. **cards vs cards+stats** — do real magnitudes appear and get used
   correctly (weighing R15/month against the R560 CSG or R85/GB data), or
   are numbers ignored/invented?
3. **STANCE line** — does grounding shift the stance, or only the prose?
   (Prose-only = texture; stance shift = decision-level effect.)
4. **Vocabulary leakage** — cards should surface organically ("my stokvel",
   "deductions"), NOT verbatim ("according to research..."). Verbatim =
   prompt needs adjusting.
5. **Re-run variance** — run 2-3 times; the mechanism should appear
   consistently under `cards` and rarely under `baseline`. If baseline
   already reaches it often, the card's value is provenance, not behaviour.

## Editing the experiment

All knobs in `backend/scripts/context_grounding_pilot_v2.py`:

- `CARDS` — the 3 mechanism cards (stokvels / CSG allocation / credit &
  aspiration). Edit mechanisms, add cards, change `segment_tags`.
- `scenario` in `main()` — the product/policy tested. The R15/month price is
  in the scenario text on purpose so personas can do real arithmetic.
- `load_personas_by_archetype({...})` — which archetypes, how many.
- `temperature=0.7` in `respond()` — lower for more repeatable runs.

v1 (`context_grounding_pilot.py`) is the single-persona version with the
coverage-honesty check.

## Prompt-hardening pilot (remediation Fix 0/1)

`backend/scripts/prompt_hardening_pilot.py` A/B-tests the texture prompt from
the main repo's persona remediation plan (local doc `PERSONA_REMEDIATION_PLAN.md`):
old prompt vs hardened prompt (specific-person framing, economic-fidelity
clause, invention prohibition, rendered fact briefing) on real QLFS
manager/professional seeds plus poor-seed controls, scoring deterministic
hardship-framing markers and the Fix 1 deterministic consistency checks
(pool-name leak, naming-phrase leak, invented currency).

Run (16 sim-tier calls):

```
D:/Fub-agentsociety/backend/.venv/Scripts/python.exe backend/scripts/prompt_hardening_pilot.py
```

First run (2026-07-09, qwen3.6-plus, single run — repeat before trusting):
affluent hardship markers 4→1, control 4→1. Qualitative read of controls
showed the drop is marker-language softening, not dishonesty (unemployment
and rejection history remain explicit). Two side-findings: (a) the OLD prompt
named both control personas "Thandi" in prose — the name mode-collapse bug
appearing inside prose, invisible to the pool-lexicon check; (b) the hardened
prompt also suppressed specific real place names (Umlazi, Khayelitsha →
"a township in KwaZulu-Natal") — the invention prohibition costs local
texture; may need a "real, province-consistent settings are encouraged"
carve-out.

## Invisible-numbers pilot (economic grounding without citation)

Question: can a persona's surveyed economics shape its reaction WITHOUT the
persona citing the figures? (Income band = independent variable; reaction =
dependent variable. Restating the IV is echo, not grounding.) Trigger:
production panels showed personas reciting injected income/fees verbatim.

Spec (frozen, incl. lexicons + stats protocol):
`docs/INVISIBLE_NUMBERS_PILOT.md`.

- `backend/scripts/situation_compiler.py` — deterministic, LLM-free compiler:
  persona record -> 1-3 sentences of lived circumstance (money rhythm +
  licensed obligations). Number-free by test; situation only, never decision
  style; tier gloss removed along with figures (the gloss is itself a leak
  channel). Also owns both frozen lexicons (compiler vocabulary +
  CLASSIFIER_MARKERS curated from production calibration) so the disjointness
  guarantee is enforced in one place.
- `backend/scripts/test_situation_compiler.py` — 12 LLM-off checks: no
  numeric tokens, classifier/compiler lexicon disjointness, referent
  licensing, income-banding/tier agreement on the cast, template
  distinctness, role mapping, vocabulary self-consistency. All passing
  (2026-07-17).

- `backend/scripts/invisible_numbers_pilot.py` — A/B/C/D runner (48 sim-tier
  calls per repeat). A_control mirrors production's budget-reality + real
  numbers verbatim; B swaps in the compiled situation block; C adds the open
  ask; D is production + a no-cite rule (cheapest patch). Research cards are
  bound + recorded but NOT rendered (economic channel is the only variable).
- `backend/scripts/score_invisible_numbers.py` — LLM-off scorer: post-strip
  balanced accuracy (raw + echo-robust), cluster permutation test (10k),
  persona-cluster bootstrap CI for C−A, paraphrase-leak containment,
  number-leak (whitelist {50}∪{50k}), carried-over shape metrics,
  economics-retained tables. Mechanics verified end-to-end on fabricated
  data (2026-07-17): echo case masks to abstain, own-figure citation flags
  as leak, permutation p-floor behaves as permutations allow.

Run tests / scorer:
```
D:/Fub-agentsociety/backend/.venv/Scripts/python.exe backend/scripts/test_situation_compiler.py
D:/Fub-agentsociety/backend/.venv/Scripts/python.exe backend/scripts/score_invisible_numbers.py
```

Experiment run (DONE 2026-07-17 — on `qwen3.7-max-2026-05-17` after
qwen3.6-plus quota death, 144/144 valid, 0 errors):
```
SIM_LLM_MODEL=qwen3.7-max-2026-05-17  # or restore quota for qwen3.6-plus
D:/Fub-agentsociety/backend/.venv/Scripts/python.exe backend/scripts/invisible_numbers_pilot.py 3
D:/Fub-agentsociety/backend/.venv/Scripts/python.exe backend/scripts/score_invisible_numbers.py
```

**Run 1 verdict (docs/INVISIBLE_NUMBERS_RESULTS.md):** both gates FAIL —
the situation block degraded measurable tier signal under the frozen
instrument (A 0.41 > C 0.24 > B 0.10). But: (a) production cites own figures
in 83% of responses; (b) D (rule-only) kills citation to 0% while keeping
above-chance tier signal (p=0.044) — the evidence-backed production port;
(c) frozen classifier under-measures the substituted model's idiolect
(loose recall 0 in ALL conditions incl. A); (d) persona prose is a second
figure-leak channel. Next: port D; rerun on qwen3.6-plus or pre-register an
extended lexicon on a fresh run; block v2 with stronger loose texture.

## Papers behind the cards

- Matuku & Kaseke (2014), stokvels in Orange Farm — trust/lump-sum/social
  infrastructure mechanisms.
- Zembe-Mkabile et al. (SAMRC, 2015–2023), CSG studies — allocation under
  scarcity, education-first defending, social-capital spend.
- Deborah James (2015), *Money from Nothing* — aspirational credit,
  mashonisa relationality, expected extraction ("where's the hidden fee").

The wider candidate corpus (~30 works by segment) is in the main repo's
`docs/ACADEMIC_GROUNDING.md`.
