# Claude Code project guidance — crowds

Notes Claude should follow when working in this repo.

## What this project is

A multi-agent policy simulation. Users describe a scenario, the system
generates a synthetic SA population grounded in real socio-economic
context, and runs the scenario through them — letting policy makers
test announcements / events before committing them in real life.

## Where things live

- `backend/app/api/` — Flask routes (most logic is in `simulation.py`)
- `backend/app/services/` — sim engine, persona library, research
- `backend/scripts/run_simulation_as.py` — the sim subprocess (runs in
  its own process, talks to Flask via file-based IPC)
- `frontend/src/views/` — routed pages
- `frontend/src/components/Step{1..5}*.vue` — the workflow steps
- `frontend/src/components/PersonaLibraryDrawer.vue` — global personas drawer

## Conventions worth knowing

- **LLM split:** `LLM_*` env vars = research/personas (Plus tier);
  `SIM_LLM_*` = simulation runtime (Flash/cheap tier). Keep them split.
- **No LLM-generated personas (hard rule):** WHO populates a room is the
  curated library first, custom agents second — never LLM-authored. The
  cast is assembled in `simulation_manager.prepare_simulation` (library via
  `select_for_query` + `panel_service._build_profile`, guarded by
  `assert_library_cast`); panels use the same path. The LLM only produces
  runtime STANCE/economics (`mode_specs.build_economic_lens`), never identity.
  Don't reintroduce a persona-generation path or a `/generate-profiles` route.
- **Pause/intervene:** lives in `simulation_runner.pause_simulation` and
  IPC commands routed through `simulation_ipc.py`. Env-status accepts
  `alive` / `running` / `paused` — don't tighten this back.
- **LadybugDB WAL:** auto-recovers from corruption at startup
  (`ladybug_storage.__init__` quarantines bad files). Don't force-kill
  the backend — use Ctrl+C.

## Product-mode economy (hard rules)

The product-sim economic lens must keep "wants it" and "can afford it" strictly
separate. When touching anything economic:

- **Affordability comes from real persona data, never the LLM.** The affordability
  number is computed from the persona's real income/budget. If the LLM can write
  or change a budget figure, that's a bug — fix it, don't work around it.
- **"Wants it" vs "can afford it" are separate fields. Never merge them.**
  "Wants it" is qualitative LLM output (objections, willingness, conditions).
  "Can afford it" is computed from real data. They do not collapse into one number.
- **Never emit a "% who would buy" or any validation score.** An affordability
  share computed from real income is allowed; a purchase *probability* is not.
- **Every economic change must be testable with the LLM switched off.** If a piece
  of economic logic can't be asserted without calling a model, it's in the wrong
  layer.

## Style

- Don't add new abstractions speculatively; keep the simplification
  pass intact.
- Don't reintroduce orange theme colours — accent is `#1E9E5A` (green).
- Avoid adding orphan files; if it's not referenced, delete it.
</content>
</invoke>