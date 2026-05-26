# Claude Code project guidance — fub-sandbox

Notes Claude should follow when working in this repo.

## What this project is

A multi-agent policy simulation. Users describe a scenario, the system
generates a synthetic SA population grounded in real socio-economic
context, and runs the scenario through them — letting policy makers
test announcements / events before committing them in real life.

## Where things live

- `backend/app/api/` — Flask routes (most logic is in `simulation.py`)
- `backend/app/services/` — sim engine, persona generation, research
- `backend/scripts/run_simulation_as.py` — the sim subprocess (runs in
  its own process, talks to Flask via file-based IPC)
- `backend/uploads/persona_cache/` — on-disk persona cache (gitignored)
- `frontend/src/views/` — routed pages
- `frontend/src/components/Step{1..5}*.vue` — the workflow steps
- `frontend/src/components/PersonaLibraryDrawer.vue` — global personas drawer

## Conventions worth knowing

- **LLM split:** `LLM_*` env vars = research/personas (Plus tier);
  `SIM_LLM_*` = simulation runtime (Flash/cheap tier). Keep them split.
- **Persona cache:** `agent_profile_generator._generate_profile_with_llm`
  short-circuits via `persona_cache` (exact + archetype keys). If you
  change the prompt template, bump the `v:` byte in `persona_cache.make_key`.
- **Pause/intervene:** lives in `simulation_runner.pause_simulation` and
  IPC commands routed through `simulation_ipc.py`. Env-status accepts
  `alive` / `running` / `paused` — don't tighten this back.
- **LadybugDB WAL:** auto-recovers from corruption at startup
  (`ladybug_storage.__init__` quarantines bad files). Don't force-kill
  the backend — use Ctrl+C.

## Style

- Don't add new abstractions speculatively; keep the simplification
  pass intact.
- Don't reintroduce orange theme colours — accent is `#1E9E5A` (green).
- Avoid adding orphan files; if it's not referenced, delete it.
</content>
</invoke>