# crowds — system architecture, in detail

The machine, layer by layer: what runs where, what talks to what, what is
written to disk, and which rules each boundary exists to protect.

Companion docs: `docs/SYSTEM_MAP.md` (the user's journey and the honest state of
the codebase), `docs/OPINION_FORMATION.md` (how a persona forms an opinion),
`docs/ARCHITECTURE_OVERVIEW.md` (short file-relationship summary), `CLAUDE.md`
(the hard rules).

---

## 1. The shape in one picture

```
  BROWSER
  ├── frontend/public/*.html      static, no app bundle
  │     landing · auth · waitlist · privacy · terms · refunds · contact
  └── frontend/src/  Vue 3 SPA (Vite)
        FlowView.vue        one state machine: home -> building -> results
        api/*.js            one HTTP client per backend blueprint
                │
                │  HTTPS  /api/*   Authorization: Bearer <Supabase JWT>
                v
  FLASK  (backend/app/__init__.py, app factory)
        before_request #1   verify JWT (ES256 / JWKS) -> verify approval
        before_request #2   request logging
        11 blueprints       + /admin + /health
                │
                v
  SERVICES  (backend/app/services/, ~50 plain Python modules)
        │            │                │                  │
        v            v                v                  v
   persona       InterviewService  simulation_runner   storage/
   library       (in-process LLM)  (spawns an OS       ladybug graph DB
   personas.json                    process)           SQLite + files
   (built offline)                       │
                                  file-based JSON IPC
                                         v
                          backend/scripts/run_simulation_as.py
                          wraps agentsociety2 (the engine)

  OFFLINE, NEVER AT RUNTIME
  backend/scripts/  build_library.py pipeline -> personas.json
  backend/data/microdata/  QLFS 2026-Q1 · GHS 2025 · Afrobarometer R9

  EXTERNAL
  Supabase (auth, profiles, entitlements) · Paystack (payments)
  LLM providers (two tiers) · Serper / Firecrawl / Jina (web research)
```

Four processes matter: the browser, the Flask worker, the simulation
subprocess, and the offline build. Only the first three exist in production.

---

## 2. Presentation layer

### Two front doors, on purpose

**Static HTML** in `frontend/public/` serves everything a signed-out visitor
sees: `landing.html`, `auth.html`, `waitlist.html`, and the legal pages. These
load without booting the Vue bundle, which is why the marketing page is fast and
why an auth failure cannot leave a blank app.

**The SPA** in `frontend/src/` is the product. `FlowView.vue` is the main
screen and holds a three-state machine, `home -> building -> results`. Nothing
navigates away; overlays rise over a dimmed home, browser Back collapses the
overlay, and the open view is written to `localStorage` so a refresh restores
where you were, including a half-finished build.

Flow components: `FlowHome.vue`, `FlowBuilding.vue`, `FlowResults.vue`,
`DashboardPanel.vue`, `ProfileModal.vue`, `LensIcon.vue`.

Other routed views exist for the deeper simulation surface:
`SimulationView.vue`, `SimulationRunView.vue`, `InteractionView.vue`,
`ReportView.vue`, `MainView.vue`, `AuthCallbackView.vue`,
`PasswordResetView.vue`.

### API clients

`frontend/src/api/` holds one module per backend blueprint: `billing.js`,
`context.js`, `graph.js`, `panel.js`, `report.js`, `research.js`,
`simulation.js`, with `index.js` as the shared axios/fetch wrapper that attaches
the Supabase JWT.

### Auth is enforced twice

- The Vue router guard (`router/index.js`) so a signed-out user never sees a
  blank app. This is **UX only**.
- The Flask `before_request` hook (`app/__init__.py`) so the API is actually
  safe. This is **the security boundary**.

Never rely on the first.

---

## 3. API layer

Flask app factory in `backend/app/__init__.py`. Dependency injection through
`app.extensions` (notably `graph_storage` and `graph_backend`). Blueprints are
mounted under `/api/<name>`.

| Blueprint | Prefix | What it owns |
|---|---|---|
| `simulation` | `/api/simulation` | the whole sim lifecycle, interviews, interventions |
| `panel` | `/api/panel` | panel sessions, segments, rounds, posters |
| `research` | `/api/research` | web + local research, deep research, seeding |
| `graph` | `/api/graph` | knowledge-graph projects, ontology, build tasks |
| `report` | `/api/report` | report generation, sections, streaming logs |
| `billing` | `/api/billing` | Paystack checkout, status, cancel, webhook |
| `account` | `/api/account` | account status |
| `config` | `/api/config` | backend config surface |
| `context` | `/api/context` | operator context (business description) |
| `waitlist` | `/api/waitlist` | access requests, password reset |
| `admin` | `/admin` | approval flips, hit from a Telegram link |
| — | `/health` | liveness |

### The simulation blueprint, in full

This is the largest surface, and it is worth reading as four groups.

**Setup**
`/create`, `/prepare`, `/prepare/status`, `/custom-agents/parse`,
`/<id>/profiles`, `/<id>/profiles/realtime`, `/<id>/enrichment`,
`/<id>/config`, `/<id>/config/realtime`, `/<id>/config/download`,
`/<id>/research/rerun`, `/<id>/cost`, `/entities/<graph_id>` and its variants.

**Run control**
`/start`, `/stop`, `/<id>/run-status`, `/<id>/run-status/detail`,
`/<id>/pause`, `/<id>/resume`, `/<id>/fork`, `/env-status`, `/close-env`.

**Reading the run**
`/<id>/actions`, `/<id>/timeline`, `/<id>/posts`, `/<id>/comments`,
`/<id>/agent-stats`, `/list`, `/history`, `/<id>` (GET and DELETE),
`/<id>/export/states`, `/<id>/export/impact`.

**Talking to agents**
`/interview`, `/interview/batch`, `/interview/all`, `/interview/history`,
`/interview/post-simulation`, `/interview/impact`,
`/<id>/agents`, `/<id>/agents/<agent_id>/interview`,
`/<id>/agents/batch-interview`,
`/<id>/agents/<agent_id>/intervene`,
`/<id>/agents/<agent_id>/intervene-live`,
`/<id>/broadcast-intervention`.

### The panel blueprint

`/segments`, `/segments/suggest`, `/attitudes/<dim>`, `/affordability`,
`/pointers`, `/read`, `/sessions` (list and create),
`/sessions/<id>` (get and delete), `/sessions/<id>/pitch`,
`/sessions/<id>/segments`, `/sessions/<id>/coverage-gap`,
`/sessions/<id>/rounds`, `/sessions/<id>/agents/<agent_id>/ask`,
`/posters`, `/posters/<poster_id>`.

`/sessions/<id>/segments` is the "add personas to a live room" path: a second
segment can be appended into an existing room for contrast, without re-running.

### Cross-cutting request handling

- **Auth.** `require_supabase_auth` verifies the ES256 JWT against Supabase
  JWKS, then checks the approval flag on the `profiles` row. `AUTH_DISABLED`
  is the local-dev escape hatch. The Paystack webhook is exempt from JWT and
  verified by HMAC signature instead.
- **Quota.** Checked *before* work starts (`check_panel_quota`), incremented
  only after success. Free plan: capped panels, cast capped at 12, simulations
  are paid-only.
- **Thinking suppression.** `_disable_thinking_on_litellm` wraps
  `litellm.acompletion` inside the Flask process, and `run_simulation_as.py`
  does the same in the subprocess. Both are needed.
- **Boot-time storage probe.** `_log_storage_persistence` logs loudly whether
  `DATA_ROOT` points at a real mounted volume. On Railway, if it does not,
  every panel, sim and graph is wiped on redeploy.

---

## 4. Service layer

`backend/app/services/`, plain Python modules with module-level functions. No
ORM, no framework coupling. This is the healthiest layer in the codebase.

**Cast assembly and personas**
`persona_library.py`, `persona_retrieval.py`, `panel_service.py`,
`agent_profile_generator.py`, `agent_sampler.py`, `agent_enricher.py`,
`custom_agent_parser.py`.
The guard `assert_library_cast` lives in `panel_service.py` and raises if
anything not from the library ends up in a cast.

**Modes and economics**
`mode_detector.py` (auto-detect policy vs product from the seed),
`mode_specs.py` (`budget_tier`, `disposition`, `build_economic_lens`,
`build_health_block`), `income_seeder.py`, `lsm_proxy.py`, `objections.py`,
`sim_presets.py`, `prompt_reframer.py`.

**Simulation runtime**
`simulation_manager.py` (prepare), `simulation_runner.py` (spawn, monitor,
read logs, pause/resume/stop), `simulation_ipc.py` (the file protocol),
`simulation_config_generator.py`, `opinion_agent.py`, `opinion_block.py`,
`agentsociety_opinion_block.py`, `agentsociety_output_writer.py`,
`event_rule_engine.py`, `convergence_detector.py`, `position_clustering.py`,
`replay_storage.py`, `interview_service.py`.

**Grounding and research**
`sa_context.py` (daily-refreshed live SA context), `world_facts.py`,
`deep_research_service.py`, `serper_service.py`, `firecrawl_service.py`,
`jina_service.py`, `literature_service.py`, `study_reader.py`,
`document_context_engine.py`, `topic_extractor.py`, `mechanism_card_service.py`,
`pointers.py`, `operator_context.py`.

**Graph**
`graph_builder.py`, `graph_memory_updater.py`, `graph_tools.py`,
`ontology_generator.py`, `entity_reader.py`.

**Output**
`report_agent.py`, `data_exporter.py`, `poster_service.py`, `judge_service.py`,
`usage_ledger.py`, `text_processor.py`.

**Utilities** (`backend/app/utils/`)
`llm_client.py` (the tier split), `token_counter.py`, `retry.py`,
`file_parser.py`, `entity_resolver.py`, `logger.py`.

**Vendored skills** (`backend/app/skills/`)
`fub_literature`, `fub_opinion_capture`, `fub_web_research`.

---

## 5. The two product tiers

| | Panel | Simulation |
|---|---|---|
| Shape | a focus group, 12 people, one room | a society, rounds, opinions move |
| Time | seconds | minutes |
| Process | in-process, `InterviewService` | separate OS process |
| Answers | how does this land, what breaks it | what happens to the mood over time |
| Plan | free tier gets a capped number | paid only |

Panel is the wedge. Simulation is the depth tier and is never removed.

The two share the same cast-assembly path, which is why **a panel session
directory is byte-compatible with a simulation directory**. A panel is a sim
directory without a sim, so the whole interview stack runs on both unchanged.

---

## 6. Request lifecycles

### A panel

```
POST /api/panel/sessions   { pitch, segments, cast size }
  -> check_panel_quota
  -> suggest_segments / list_segments        (LLM-free filters over the library)
  -> select_for_query -> _build_profile -> assert_library_cast
  -> derive_budget_tiers(pitch)              (price parsed from the pitch text)
  -> write session dir + panel_session.json
  -> frame_pitch(...)                        (adds operator context, probes)
  -> InterviewService: one SIM_LLM call per persona, in-process
  -> save_round -> rounds on disk
  -> increment quota
GET  /api/panel/sessions/<id>                 read back
POST /api/panel/sessions/<id>/agents/<n>/ask  follow-up question to one person
POST /api/panel/sessions/<id>/segments        append a contrast segment, live
```

### A simulation

```
POST /api/simulation/create        allocate id + directory
POST /api/simulation/prepare       (async, polled by /prepare/status)
       read entities from the graph
       detect mode from the seed          (mode_detector)
       assemble the cast from the library (same path as panel)
       generate run config                (simulation_config_generator)
       write simulation_config.json, agentsociety_profiles.json,
             document_context.json, enrichment.json, state.json
       copy the runner script into the sim dir
POST /api/simulation/start
       simulation_runner.start_simulation spawns run_simulation_as.py
       a monitor thread tails actions.jsonl and updates run_state.json
   ... rounds run: one LLM call per agent per round ...
       PositionRegistry counts distinct positions
       ConvergenceDetector stops on coverage saturation
GET  /api/simulation/<id>/run-status | /actions | /timeline | /posts
POST /api/simulation/<id>/pause | /resume | /agents/<n>/intervene-live
POST /api/simulation/interview     talk to an agent mid-run or after
POST /api/simulation/close-env     tear the environment down
```

---

## 7. The simulation subprocess and its IPC

### Why a separate process

The engine (`agentsociety2`) is heavyweight and can wedge. Isolating it means a
bad run cannot take the API down, and it can be terminated cleanly.

### The protocol

`simulation_ipc.py` defines `IPCCommand` and `IPCResponse` and two ends: the
Flask-side client and the subprocess-side server. Transport is **files inside
the simulation directory**, not sockets.

```
<sim_dir>/
  commands/<command_id>.json     Flask writes, subprocess polls and deletes
  responses/<command_id>.json    subprocess writes, Flask polls
  env_status.json                subprocess heartbeat
```

Commands: `interview`, `batch_interview`, `pause`, `resume`,
`apply_intervention`, `broadcast_intervention`, `close_env`.

`check_env_alive` accepts status `alive`, `running` **and** `paused`. This
looseness is deliberate. Tightening it breaks pause and intervene.

Every call carries a timeout (30s default for control commands) and
`_dead_env_message` produces the human-readable failure when the subprocess is
gone.

`SimulationRunner` also registers cleanup handlers so simulations are terminated
on shutdown rather than orphaned.

---

## 8. What is on disk

Everything persistent lives under `Config.DATA_ROOT`, which defaults to the
backend directory locally and **must** be a mounted volume in production.

```
DATA_ROOT/
  uploads/
    simulations/<simulation_id>/
        state.json                    lifecycle state
        simulation_config.json        rounds, activity, timing
        agentsociety_profiles.json    the cast, fully resolved
        document_context.json         the seed and its grounding
        enrichment.json               research attached to the run
        actions.jsonl                 append-only action log (the run itself)
        run_state.json                monitor-thread view of progress
        env_status.json               subprocess heartbeat
        commands/ responses/          the IPC mailboxes
        opinion.db                    SQLite: opinions, responses, activity
    panel_sessions/<session_id>/
        panel_session.json            pitch, cast, segments, meta
        rounds/                       each round's questions and answers
        coverage_gaps.jsonl           what the room could not answer
        fact_gaps.jsonl               facts the pitch failed to supply
    posters/                          uploaded images, read once by the vision tier
  graph DB files                      LadybugDB
```

`opinion.db` holds three tables: `opinion`, `opinion_response`, and
`agent_round_activity`. The third exists so silence is recorded too: OBSERVE and
DO_NOTHING are data, not absence of data.

Graph backends: `ladybug_storage.py` is live and auto-quarantines a corrupt WAL
at startup so it recovers on its own. Do not force-kill the backend; use Ctrl+C.
`neo4j_storage.py` and `kglite_storage.py` are alternates and effectively
legacy.

---

## 9. The LLM tiers

Three separate tiers, each with its own env prefix, so pointing one at a new
model never silently swaps another.

| Prefix | Used for | Tier |
|---|---|---|
| `LLM_*` | research, grounding, reports, persona texture | Plus / capable |
| `SIM_LLM_*` | simulation runtime, panel interviews | Flash / cheap |
| `VISION_*` | reading uploaded posters into text, once per image | vision, falls back to `LLM_*` |

Embeddings are separate again (`EMBEDDING_*`), local Ollama by default, pinned
to 768 dimensions so vectors stay compatible with stored ones.

**Thinking is force-disabled on every path.** Qwen and DeepSeek are
reasoning-enabled by default and emit hidden thinking tokens that are billed but
invisible. `Config.llm_extra_body` picks the right flag shape per provider —
Qwen takes `enable_thinking`, DeepSeek takes `thinking: {type}` — because
sending the wrong one 400s. Reasoning-only model variants get `{}`, since their
thinking cannot be switched off.

This was a correctness bug as well as a cost one. DeepSeek returns the answer in
`reasoning_content` with empty `content`, which surfaced as an entire panel
saying "I have no comment on that."

`ENABLE_LLM_THINKING=1` re-enables it deliberately, for a research call that
benefits from chain of thought.

`JUDGE_ENABLED` (off by default) turns on an advisory Plus-tier quality scorer.
It scores; it never gates or regenerates.

---

## 10. Grounding boundaries

- `sa_context.py` refreshes South African context from live web search, cached
  daily, so personas stop citing crises that have ended.
- `build_sa_context(mode)` is mode-aware: policy mode gets the unrest priming,
  product and custom casts get core grounding only, with no riot nudge.
- Mechanism cards (`app/data/mechanism_cards/*.json`) are hand-extracted
  behavioural findings, bound to segments.
- **The hard boundary:** web research produces world facts and context. It never
  writes a persona. Raw web text is bound to South African segment types first,
  which is what stopped a foreign product page leaking into a persona's identity.

---

## 11. External systems

| System | Role | Notes |
|---|---|---|
| Supabase | auth, `profiles`, entitlements | ES256 JWT verified against JWKS |
| Paystack | payments | webhook exempt from JWT, HMAC-verified |
| Vercel | frontend hosting | serves the static pages and the SPA |
| Railway | backend hosting | needs a mounted volume for `DATA_ROOT` |
| Serper / Firecrawl / Jina | web research | feed the Plus tier only |
| LLM provider | inference | two tiers plus vision |
| Ollama (local) | embeddings | falls back to lexical clustering if unreachable |

Access is gated: sign up lands on the waitlist, and approval is a flag on the
`profiles` row flipped from an admin link. An invite row must exist before
signup, or the database trigger blocks it.

---

## 12. The invariants this architecture exists to protect

1. **No LLM-generated personas.** The cast comes from the curated library
   first, custom agents second, never from a model. Enforced in code by
   `assert_library_cast`, not by convention.
2. **Surveys author identity; the model only styles it.** The one model stage
   in the build writes texture onto an identity that is already fixed.
3. **"Wants it" and "can afford it" never merge.** Affordability is computed
   from real income data. The model cannot write a budget figure.
4. **No purchase probability, ever.** An affordability share from real income is
   allowed. A "% who would buy" is not.
5. **Every economic rule is testable with the model switched off.** If it
   cannot be asserted without a model call, it is in the wrong layer.
6. **Web research makes context, not people.**
7. **Auth is verified on the server.** The router guard is decoration.
8. **State lives under `DATA_ROOT`.** Anything written elsewhere dies on the
   next deploy.

---

## 13. Known weak points

- **File-based IPC** is simple and debuggable but polls, and its timeouts are
  the failure surface for pause and intervene.
- **`simulation.py` is a large blueprint.** Most of the sim logic that should
  be in services still lives in routes.
- **Two graph backends are dead weight.** Neo4j and kglite are kept but unused.
- **Position clustering silently changes metric** if Ollama is unreachable. It
  logs a warning and resets the saturation baseline, but the two modes are not
  comparable.
- **The library is a build artefact.** Refreshing microdata means rerunning the
  offline pipeline and paying the texture cost again.
