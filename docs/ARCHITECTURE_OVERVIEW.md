# Architecture & File Relationship Summary

_A high-level map of the `crowds` / Fub multi-agent policy-simulation codebase._

## What it is

A multi-agent policy/product simulation. A user describes a scenario; the system
assembles a synthetic South African population from a curated persona library
(grounded in real QLFS/GHS microdata + Afrobarometer attitudes), runs the
scenario through them via a forked **AgentSociety2** engine (Tsinghua FIB Lab,
installed as a pip dependency `agentsociety2==2.1.5`), and returns sentiment /
reactions / reports. There is also a lighter **panel** (focus-group) tier.

## Two big pieces

```
┌─────────────────────────┐        HTTP /api/*        ┌──────────────────────────┐
│  frontend/ (Vue 3 SPA)  │  ───────────────────────► │  backend/ (Flask API)    │
│  Vite, vue-router       │  ◄─────────────────────── │  app factory + blueprints│
└─────────────────────────┘        JSON               └────────────┬─────────────┘
                                                                    │ spawns
                                                        file-based IPC (JSON files)
                                                                    ▼
                                              ┌───────────────────────────────────┐
                                              │ scripts/run_simulation_as.py       │
                                              │ (separate OS process = the sim)    │
                                              │ wraps agentsociety2 engine         │
                                              └───────────────────────────────────┘
```

## Entry points

| Layer | File | Role |
|-------|------|------|
| Root CLI | `fub.py` | Thin wrapper → `cd backend` → `run.py` |
| Backend boot | `backend/run.py` | Loads `.env`, bridges config → `AGENTSOCIETY_*` env vars, UTF-8 fix, calls `create_app()` |
| Flask factory | `backend/app/__init__.py` | Builds app, CORS, registers 7 blueprints, storage-persistence logging |
| Sim subprocess | `backend/scripts/run_simulation_as.py` | The actual simulation, runs in its own process, talks to Flask via files |
| Frontend boot | `frontend/src/main.js` → `App.vue` → `router/index.js` | Vue SPA |
| Public front door | `frontend/public/landing.html`, `auth.html` | Static marketing/auth pages (served same-origin, auth-gated) |

## Backend layout (`backend/app/`)

### `api/` — Flask routes (thin-ish controllers), mounted under `/api/<name>`
| Blueprint | Prefix | Notes |
|-----------|--------|-------|
| `simulation.py` | `/api/simulation` | **4,050 LOC — the monolith.** ~45 routes: create/prepare/start/stop, interview, pause/resume/intervene, fork, export |
| `research.py` | `/api/research` | 1,807 LOC. Web-research grounding, document ingest |
| `graph.py` | `/api/graph` | Knowledge-graph / ontology endpoints |
| `report.py` | `/api/report` | Report generation |
| `panel.py` | `/api/panel` | Focus-group panel tier |
| `billing.py` | `/api/billing` | Paystack/Supabase billing |
| `config.py` | `/api/config` | Client config |

### `services/` — the real logic (43 modules). Key clusters:
- **Sim orchestration:** `simulation_manager.py` (assembles cast: library → custom → guarded by `assert_library_cast`), `simulation_runner.py` (spawns/kills subprocess), `simulation_ipc.py` (JSON-file command/response protocol), `simulation_config_generator.py`, `mode_detector.py` + `mode_specs.py` (auto-detect product vs policy; `build_economic_lens`).
- **Personas (no LLM-authored identity — hard rule):** `persona_library.py`, `persona_retrieval.py`, `agent_sampler.py`, `agent_enricher.py`, `agent_profile_generator.py`, `income_seeder.py`.
- **Opinion/agents:** `opinion_agent.py`, `opinion_block.py`, `agentsociety_opinion_block.py`, `convergence_detector.py`, `position_clustering.py`.
- **Research/grounding:** `deep_research_service.py`, `sa_context.py`, `world_facts.py`, `firecrawl_service.py`, `serper_service.py`, `jina_service.py`, `literature_service.py`, `document_context_engine.py`.
- **Post-sim:** `report_agent.py` (2,585 LOC), `interview_service.py`, `judge_service.py`, `data_exporter.py`, `event_rule_engine.py`.
- **Graph:** `graph_builder.py`, `graph_tools.py`, `graph_memory_updater.py`, `ontology_generator.py`.

### `storage/` — persistence backends
- `ladybug_storage.py` — primary graph DB (WAL auto-recovery / quarantine on corruption).
- `neo4j_storage.py`, `kglite_storage.py`, `graph_storage.py` — alternative/legacy graph backends.
- `embedding_service.py`, `search_service.py`, `ner_extractor.py`.

### `utils/` — `llm_client.py` (LLM split: `LLM_*` vs `SIM_LLM_*`), `token_counter.py`, `retry.py`, `file_parser.py`, `entity_resolver.py`, `logger.py`.

### `skills/` — vendored AgentSociety skills: `fub_literature`, `fub_opinion_capture`, `fub_web_research`.

### `scripts/` — data pipeline (offline): `build_library.py`, `attitude_fuser.py`, `attitude_donor_adapter.py`, `ghs_adapter.py`, `archetype_mapper.py`, `persona_sampler.py`, `texture_generator.py`, plus many `validate_*.py` companions. Microdata lives in `backend/data/microdata/` (QLFS 2026-Q1, GHS 2025, attitudes).

## Frontend layout (`frontend/src/`)

Two parallel UIs (see Shortfalls):
- **`views/FlowView.vue`** — the current default (`/`), backed by `components/flow/*` (`FlowHome`, `FlowBuilding`, `FlowResults`, `DashboardPanel`, `ProfileModal`) and `components/sim2/PipelineBox.vue`.
- **`views/Home.vue`** — the "classic" rich app at `/classic`, backed by `components/Step2..5*.vue` and the many analysis panels (`SentimentTimeline`, `ArchetypeHeatmap`, `EventImpactCards`, `PolicyComparisonPanel`, `TopicWordCloud`, etc.).
- Other views: `MainView` (`/process/:id`), `SimulationView`, `SimulationRunView`, `ReportView`, `InteractionView`, `AuthCallbackView`.
- `api/*.js` — one client module per backend blueprint (`simulation.js`, `research.js`, `graph.js`, `report.js`, `panel.js`, `billing.js`, `index.js`).
- `composables/` — `useAuth.js`, `useBilling.js`. `store/pendingUpload.js`. Router enforces auth-by-default (only `meta.public` reachable signed-out).

## Request → simulation lifecycle

1. Frontend `POST /api/simulation/create` → `simulation.py` → `simulation_manager.prepare_simulation` assembles the cast (library `select_for_query` + `panel_service._build_profile`, `assert_library_cast` guard).
2. `POST /api/simulation/start` → `simulation_runner` spawns `run_simulation_as.py` as a subprocess.
3. Subprocess drives the `agentsociety2` engine; Flask polls/commands it through `simulation_ipc.py` (JSON files in the sim dir: env-status `alive`/`running`/`paused`, interview, pause, intervene, close).
4. Results persist under `Config.DATA_ROOT` (files + SQLite + LadybugDB). On Railway this must be a mounted volume via `DATA_ROOT` or data is wiped each redeploy.
5. `report.py` / `report_agent.py` produce the report; `interview_service` powers post-sim Q&A.

## Origin

Fork of **AgentSociety2** (Chinese-origin research framework). Fub layered a
SA-specific persona/data pipeline, product/policy economic lens, panels,
Supabase auth, and Paystack billing on top. The engine itself is now a pip
dependency, not vendored source.

---

## Obvious shortfalls / AI-slop / vibe-coding smells

1. **`api/simulation.py` is a 4,050-line, ~45-route god-module.** By far the
   biggest risk to maintainability. `report_agent.py` (2,585) and
   `research.py` (1,807) are similarly oversized. These want decomposition into
   sub-modules/services.

2. **Two parallel frontends (`/` Flow vs `/classic` Home).** The router comment
   admits the classic multi-page flow is "kept here, fully reachable." Dead-ish
   weight — `Step2..5*.vue` + a dozen analysis panels — that duplicates concepts
   in `components/flow/`. Decide which is canonical and retire the other.

3. **Multiple overlapping graph-storage backends** (`ladybug`, `neo4j`,
   `kglite`, `graph_storage`). Almost certainly only one is live; the rest are
   abandoned experiments. Same smell in storage: `search_service`,
   `embedding_service`, `ner_extractor` may be orphaned.

4. **Root-level doc sprawl / handoff artifacts** — `IMPLEMENTATION_COMPLETE.md`,
   `CUSTOM_AGENT_WEB_RESEARCH_IMPLEMENTATION.md`, `EDUCATION_PERSONAS_HANDOFF.md`,
   `frontend/CHINESE_TEXT_INVENTORY.md` (a March scan; the Chinese it inventories
   is now fully translated — **0 CJK chars remain in app/frontend code**, so this
   file is a stale orphan). CLAUDE.md itself says "avoid adding orphan files."

5. **`.bak` clutter checked into the tree** — `personas.json.bak` (currently
   untracked in git status) and a series of `ladybug_data.corrupt-*.bak`
   quarantine files sitting in `backend/`. The corruption-quarantine mechanism
   is intentional, but the artifacts should be gitignored/cleaned, not
   accumulated in the repo working dir.

6. **Config bridged through env-var side effects in two places**
   (`run.py` and `app/__init__._setup_agentsociety2_env`) — the `LLM_*` →
   `AGENTSOCIETY_*` mapping is duplicated and order-dependent (must run before
   engine import). Fragile; easy to get a half-configured process.

7. **File-based IPC over JSON files** for driving the sim subprocess is workable
   but brittle (polling, race windows, no schema enforcement beyond
   `to_dict/from_dict`). Fine for a single-node deploy; will not scale
   horizontally and is hard to test.

8. **Bilingual residue in comments/config** — `config.py` / `__init__.py` still
   carry Chinese-origin comments about `\uXXXX` escaping. Cosmetic, but signals
   the fork was translated in a hurry.

9. **`test_implementation.sh` / `test_implementation_simple.sh` + many
   `validate_*.py` scripts** are ad-hoc validators rather than a real test suite
   (`backend/tests/` exists but is thin relative to 40k+ LOC of services).

### What is genuinely well-kept (not slop)
- The **persona-source and economy hard rules** (no LLM-authored identity;
  "wants it" vs "can afford it" kept separate; economic logic testable with the
  LLM off) are clearly stated in CLAUDE.md and enforced in code
  (`assert_library_cast`, `mode_specs.build_economic_lens`).
- The **LLM tier split** (`LLM_*` research vs `SIM_LLM_*` runtime) is a real
  cost-control decision, not accidental.
- Storage-persistence self-diagnostics in `__init__.py` are thoughtful ops work.
