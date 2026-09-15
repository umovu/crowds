# crowds — full system map

_How the app is meant to be used, and everything that has to be true underneath
for that use to work. Written to be read top to bottom: the user flow first,
then the machinery that serves it, then the architecture and the honest state
of our engineering practice._

Companion docs: `docs/ARCHITECTURE_OVERVIEW.md` (file-relationship summary),
`docs/PERSONA_PIPELINE.md` (how a survey row becomes a voice), `CLAUDE.md`
(the hard rules).

---

# Part 1 — What the user is trying to do

## The job

Someone is about to put something into the world in South Africa: a price, a
policy, a post, a product, a rumour. They want to know how real South Africans
will take it **before** it is real. Not a number. Not a validation score. The
honest reactions of people who are shaped like the actual population.

Two ways we answer that, deliberately different in cost and depth:

| Tier | What it is | Time | What it answers |
|---|---|---|---|
| **Panel** | A focus group. 12 people, one room, they react to your pitch. | Seconds | "How does this land? What breaks it? Who is it for?" |
| **Simulation** | A society. Personas talk to each other over rounds, opinions move. | Minutes | "What happens to the mood over time? What spreads?" |

Panel is the wedge — clear job, cheap, fast. Simulation is the depth tier and
is never removed. A user can run a panel and then run the deeper sim off the
same pitch.

## The front door

1. Visitor hits `/` while signed out → hard-redirected to `/landing.html`
   (static marketing page in `frontend/public/`).
2. Sign in via `auth.html` → Supabase → back through `/auth/callback`.
3. Not yet approved → `/waitlist.html`. Approval is a flag in the Supabase
   `profiles` table, flipped from a Telegram link that hits `/admin/*`.
4. Approved → the app at `/`, which is [FlowView.vue](frontend/src/views/FlowView.vue).

Auth is enforced twice on purpose: the router guard in
[router/index.js](frontend/src/router/index.js#L99) so signed-out users never see a
blank app, and the Flask `before_request` hook in
[app/__init__.py](backend/app/__init__.py#L223) so the API is actually safe. The
router guard is UX; the backend guard is security. Never rely on the first.

## The main screen

One page, one state machine: `home → building → results`. Nothing navigates
away; overlays rise over a dimmed home. Browser Back collapses the overlay.
The open view is written to `localStorage` so a refresh puts you back where you
were, including a half-finished build.

Left sidebar: **New test**, **Personas** (browse the library), **How it
works**, previous panels, previous sims, profile.

First visit gets a welcome card and an optional guided tour.

## Flow A — the panel (the common path)

1. **Pick a pointer**, or just type. A pointer is the job you want done,
   defined in [pointers.py](backend/app/services/pointers.py):
   - `land` — How does this land? The honest first read.
   - `breaks` — What breaks it? Blockers only, no praise.
   - `fit` — Which of six buyer segments does this fit best?
   - `ab` — Two versions of the same message, one room, side by side.
2. **Fill the slots.** Each pointer has an ordered scaffold ("What are you
   putting out?", "Who is it for?", "What changes for them?", "What are you
   worried about?"). Required slots are enforced server-side before we spend a
   run on a junk seed.
3. **Pick your crowd**, or leave it. Segments are named, real slices:
   Unemployed, Grant recipients, Informal traders, Small business owners,
   Professionals, Guardians, Youth — or "Everyone (representative SA)".
4. **Submit** → `POST /api/panel/sessions`. A cast is assembled and the results
   room opens immediately.
5. **Read the room.** Avatars per persona, grouped by stance. Hover for the
   reaction, click for a full chat.
6. **Ask follow-ups.** `POST .../agents/<id>/ask`. The chat remembers that
   persona's reaction and earlier follow-ups.
7. **Test a variant.** Re-pitch different text at the *same* cast. Rounds are
   stored, so versions stay comparable.
8. Optionally **upload a poster** instead of typing. One vision call reads the
   image into a text brief; the cast only ever sees text.

Deliberate design choices here, each of which is a rule elsewhere in the code:

- No mode toggle. Product vs policy is auto-detected from the seed by
  `mode_detector` (keyword-only, no LLM).
- The `worry` slot never enters the seed. If it did, the room would react to
  your worry instead of your thing. It only shapes the summary.
- `fit` refuses to auto-route segments — picking the segment *is* the answer,
  so we cannot pre-pick it.

## Flow B — the simulation (the depth path)

Same box, "run the deeper sim" instead. Then an overlay narrates a real
pipeline, step by step, in [FlowBuilding.vue](frontend/src/components/flow/FlowBuilding.vue):

1. Generate an ontology from the seed.
2. Build the knowledge graph (background task, polled).
3. Create the simulation.
4. Prepare it — this is where the cast is assembled and the economic lens built.
5. Start it, with a depth preset: **quick** (6 rounds), **balanced** (12), or
   **deep**, from [sim_presets.py](backend/app/services/sim_presets.py).

Then the results room streams: agents act, opinions move, the feed fills. Mid-run
the user can **pause**, **intervene** with one agent or broadcast to all, then
**resume**. At the end they can generate a markdown report, export states, or
fork the run.

## What the user never sees, on purpose

- A "% who would buy" figure, or any validation score. Banned by `CLAUDE.md`.
- A persona invented by a language model.
- "Wants it" and "can afford it" merged into one number.

---

# Part 2 — What makes that work

## The whole picture

```
frontend/ (Vue 3 SPA, Vite)                 frontend/public/ (static)
   FlowView state machine                     landing.html, auth.html,
   api/*.js one client per blueprint          waitlist.html, legal pages
            │  HTTP /api/*  (Supabase JWT in the header)
            ▼
backend/ Flask app factory
   before_request: verify JWT → verify approval → route
   9 blueprints: simulation, research, graph, report, panel,
                 billing, account, config, waitlist  (+ /admin, /health)
            │
   services/ (~45 modules — the real logic)
            │
   ┌────────┴──────────┬──────────────────┬────────────────────┐
   ▼                   ▼                  ▼                    ▼
persona library    InterviewService   simulation_runner    storage/
(personas.json,    (in-process LLM,   (spawns a separate   (LadybugDB graph,
 built offline      panels + Q&A)      OS process)          SQLite, files)
 from microdata)                            │
                                    file-based JSON IPC
                                            ▼
                          scripts/run_simulation_as.py
                          (wraps agentsociety2 == the engine)
```

Everything persistent lives under `Config.DATA_ROOT`. On Railway that **must**
point at a mounted volume or every panel, sim and graph is wiped on redeploy.
The app factory probes and logs this at boot, loudly.

## The persona library — the thing the whole product rests on

The hard rule: **surveys author identity, the LLM only styles it.** Built
offline, before any user ever touches it, by `backend/scripts/`:

1. **Sample** whole rows from real microdata — QLFS 2026-Q1, GHS 2025 — with
   survey weights. A person is a real respondent's row, not a made-up combo.
2. **Fuse attitudes** — measured Afrobarometer R9 SA stances (1,384 donors)
   matched onto each skeleton by demographic donor matching.
3. **Map archetypes** — grant-dependent survivor, informal trader, small
   business owner, professional, and so on.
4. **Texture** — the *only* LLM stage in the build. It writes the human
   surface (voice, daily detail) onto an identity that is already fixed.

Output: `backend/app/data/persona_library/personas.json` (~269 people).

At runtime, retrieval is LLM-free:
`select_for_query` (representative + relevance tilt) → `_build_profile`
→ `assert_library_cast`, a guard that raises if anything not from the library
ended up in a cast. Panels and sims both go through this same path, which is why
a panel session directory is byte-compatible with a simulation directory: a
panel is a sim dir without a sim, and the whole interview stack runs on both
unchanged.

## The economics — separate on purpose

`mode_specs.py` keeps two things apart and never merges them:

- **"Can afford it"** — `budget_tier()`, computed from the persona's real
  income and grant data. Deterministic. Assertable with the LLM switched off.
- **"Wants it"** — impulse, objections, conditions. LLM output, qualitative.

They combine only into a `disposition` label, never a purchase probability.
`build_economic_lens()` renders the real numbers into the prompt so a persona
argues from their actual budget rather than a vibe.

## Two LLM tiers, on purpose

| Env prefix | Used for | Tier |
|---|---|---|
| `LLM_*` | Research, grounding, reports | Plus / capable |
| `SIM_LLM_*` | Simulation runtime, panel interviews | Flash / cheap |

Reasoning "thinking" is force-disabled on both paths — the sim subprocess wraps
`litellm.acompletion` and so does the Flask process
([`_disable_thinking_on_litellm`](backend/app/__init__.py#L42)). This was a
correctness bug as well as a cost one: DeepSeek returns the answer in
`reasoning_content` with empty `content`, which surfaced as a whole panel saying
"I have no comment on that." Provider flag shapes differ (Qwen vs DeepSeek) and
sending the wrong one 400s.

## Grounding

The world the personas live in is refreshed, not frozen: `sa_context.py` pulls
live web search results daily so nobody is still citing a crisis that ended.
`deep_research_service`, `firecrawl_service`, `serper_service`, `jina_service`
and `literature_service` feed the research tier. Mechanism cards
(`app/data/mechanism_cards/*.json`) are hand-extracted behavioural findings
bound to segments.

Crucial boundary: **web research produces world facts and context. It never
writes a persona.** Raw web text is bound to SA segment types first.

## The simulation subprocess

`simulation_runner.start_simulation` spawns `scripts/run_simulation_as.py` as
its own OS process. Flask talks to it by writing and polling JSON files in the
sim directory (`simulation_ipc.py`): interview, batch interview, pause, resume,
apply intervention, broadcast, close env. Env status accepts `alive`,
`running` and `paused` — deliberately loose; tightening it breaks
pause/intervene.

Why a subprocess at all: the engine is heavyweight and can wedge; isolating it
means a bad run cannot take the API down, and it can be terminated cleanly.

## Billing and quota

Supabase holds entitlement rows. Free plan: capped panels (`FREE_PANEL_LIMIT`),
cast capped at 12, sims paid-only. Paystack handles payment; the webhook is
exempt from JWT auth and verified by HMAC signature instead. Quota is checked
*before* work starts (`check_panel_quota`) and incremented after success.

## Storage

- `ladybug_storage.py` — the live graph DB. Auto-quarantines a corrupt WAL at
  startup and recovers. Do not force-kill the backend; use Ctrl+C.
- `neo4j_storage.py`, `kglite_storage.py` — alternative backends, effectively
  legacy.
- Panels, sims, reports — files plus SQLite under `DATA_ROOT`.

---

# Part 3 — Architecture and practice

## The shape

A conventional three-tier app with one unusual limb:

- **Presentation** — Vue 3 SPA, plus static HTML for everything a signed-out
  visitor sees. Splitting those two was right: the marketing and auth pages
  load without booting the app bundle.
- **API** — Flask app factory, blueprints per domain, DI through
  `app.extensions`.
- **Domain** — `services/`, plain Python modules with module-level functions.
  No ORM, no framework coupling. This is the healthiest layer.
- **The limb** — a separate simulation process driven by file IPC.

## What we do well

**Data provenance is enforced in code, not just documented.**
`assert_library_cast` is the single best decision in the codebase. A rule that
only lives in a doc gets broken; this one raises.

**The LLM-free boundary is real and testable.** Cast selection, segments, grant
detection, budget tiers, mode detection, pointers and presets are all pure
functions. The rule "every economic change must be testable with the LLM
switched off" is stated in `CLAUDE.md` and actually holds.

**Cost is treated as an engineering concern.** The two-tier LLM split, the
thinking-flag wrap, and depth presets are deliberate, measured decisions.

**Operational self-diagnosis.** The app factory prints where data lands,
whether it is writable, whether it survives redeploys, and whether auth is
configured — turning "nothing loads" into an obvious log line instead of a
dashboard hunt.

**Failure is designed for.** WAL quarantine and recovery, subprocess isolation,
graceful degradation (a failed LLM summary leaves the deterministic summary
standing), restorable half-built sims.

**Comments explain *why*, not *what*.** Unusually good throughout. Most
non-obvious decisions carry the reason and often the bug that caused them.

## Where we fall short

**1. `api/simulation.py` is a ~4,000-line, 49-route god module.** The single
biggest maintainability risk. `report_agent.py` (~2,600) and `research.py`
(~1,800) are the same smell. Routes contain orchestration that belongs in
services.

**2. Two parallel frontends.** `/` (Flow) and `/classic` (Home + `Step2..5`
components + a dozen analysis panels) duplicate the same concepts. The router
comment admits classic is merely "kept, fully reachable." One of them should be
canonical; the other should go.

**3. The test suite does not match the codebase.** Six test files in
`backend/tests/` against 40k+ lines of services. The `validate_*.py` scripts
in `backend/scripts/` are ad-hoc validators, not regression tests — they prove
something worked once, not that it still works. There is no frontend test at
all and no CI gate running any of it.

**4. No API schema or input validation layer.** Routes hand-parse
`request.get_json()` and hand-check fields. No pydantic, no marshmallow, no
OpenAPI. The IPC protocol is likewise schema-free beyond `to_dict/from_dict`.

**5. File-based IPC and file-based state.** Workable and debuggable on one
node; it cannot scale horizontally, has race windows, and is hard to test.
Single-process is currently a hard requirement (LadybugDB holds a file lock).

**6. Config bridged by env-var side effects in two places** — `run.py` and
`_setup_agentsociety2_env`. Order-dependent (must run before the engine
imports), duplicated, easy to end up half-configured.

**7. Inconsistent error handling.** Most routes are wrapped in a broad
`except Exception` that returns 500 with a stack trace in the JSON body. That
leaks internals to the client and flattens genuinely different failures into
one status code.

**8. Orphans and clutter.** Root-level handoff artifacts
(`IMPLEMENTATION_COMPLETE.md`, `CUSTOM_AGENT_WEB_RESEARCH_IMPLEMENTATION.md`,
`EDUCATION_PERSONAS_HANDOFF.md`), `.bak` persona files, quarantine files in the
working tree, three graph backends where one is live, a `/debug/library` route
marked TEMP. `CLAUDE.md` says "avoid adding orphan files"; we add them.

**9. Secrets and CORS.** `CORS(origins="*")` on `/api/*` is wide open — safe
only because every route requires a JWT, so it is one mistake away from being a
real hole. Auth can be disabled entirely by `AUTH_DISABLED=true`, which is
correct for local dev and catastrophic if it ever ships set.

**10. No migrations, no versioning.** Persisted session and sim JSON has no
schema version. An old panel session and a new one are distinguished by
`.get()` defaults scattered through the readers.

## If we fixed three things

1. Split `api/simulation.py` into route modules that call services, and move
   the orchestration out of the routes.
2. Delete `/classic` and the components only it uses.
3. Put the pure functions under real tests and run them in CI — cast selection,
   budget tiers, segments, pointers, presets, mode detection. They are already
   LLM-free; there is no excuse.

---

## Origin, briefly

The repo began as a fork of a MiroFish/AgentSociety derivative in March 2026 —
19 commits providing the Flask + Vue skeleton and the step-workflow shape. From
April 2026 onward it was rebuilt: the engine was swapped, and the persona
pipeline, panels, economics, grounding, auth and billing were written from
scratch. Roughly 75,000 lines added against a ~14,000-line starting point. The
engine itself is now a pip dependency (`agentsociety2`), not vendored source.
