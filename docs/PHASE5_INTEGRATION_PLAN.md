# Phase 5 — wiring mechanism cards into production (IMPLEMENTED 2026-07-14)

Status: implemented as specified below with reviewer-approved defaults
(cap=2, flag default ON, citations attached now). Tests: 6 new unit tests in
backend/tests/test_mechanism_cards.py, all passing; existing 27
test_library_cast.py tests still pass. One deviation from draft: the digit
guard on the rendered block scopes to content lines only — citation lines
legitimately carry publication years.
Scope: 1 new file + 2 edited files in the MAIN repo (D:/Fub-agentsociety), plus tests.
Rollback: env flag off = identical behavior to today; or revert the 3 files.

## What changes, exactly

### A. New file: `backend/app/services/mechanism_card_service.py`

Deterministic, LLM-free card store + binding + rendering. Public surface:

```python
def load_cards() -> list[dict]:
    """Read backend/app/data/mechanism_cards/*.json once (module-level cache)."""

def cards_for_archetype(archetype: str, cap: int = 2) -> list[dict]:
    """All cards whose segment_tags contain `archetype`, ranked by tag
    specificity (fewer segment_tags = more specific = first), capped.
    Deterministic: ties broken by card id (alphabetical)."""

def render_research_context(cards: list[dict]) -> str:
    """The pilot-validated prompt block:
    '# Research-grounded context for people like you (reason through this;
    do not quote it verbatim)' + per-card citation line + mechanisms +
    vocabulary. Same rendering Stage 6 validated, PLUS a closing precedence
    line: 'These are documented patterns for people in your situation —
    where they conflict with your own stated outlook and beliefs, your own
    outlook prevails.' This resolves the group-vs-individual conflict: a
    persona whose MEASURED fused attitude is optimistic must not be
    overridden by a card's group-level pattern (e.g. waithood nihilism).
    Measured survey data about THIS person always outranks documented
    patterns about people LIKE this person."""

def citations_for(cards: list[dict]) -> list[dict]:
    """[{card_id, citation, confidence}] — provenance for the run record /
    future hover-for-source UI."""
```

Notes:
- Cap default 2 (config-overridable) because broad archetypes bind up to 5
  cards (~25 mechanisms) — too much for the sim-tier prompt on thousands of
  calls. Specificity ranking means a communal_farmer gets the cattle +
  stock-theft cards, not the broad fintech card.
- Reads the flag `RESEARCH_CONTEXT_ENABLED` (env, default "1"). When "0",
  `cards_for_archetype` returns [] — every downstream step becomes a no-op.

### B. Edit: `backend/app/services/simulation_manager.py` (~line 482)

Current:

```python
library_profiles = [_build_profile(p, i, mode) for i, p in enumerate(cast)]
assert_library_cast(library_profiles)
```

Becomes:

```python
library_profiles = [_build_profile(p, i, mode) for i, p in enumerate(cast)]
for p in library_profiles:
    bound = mechanism_card_service.cards_for_archetype(p.get("actor_archetype", ""))
    if bound:
        p["research_context"] = mechanism_card_service.render_research_context(bound)
        p["research_citations"] = mechanism_card_service.citations_for(bound)
assert_library_cast(library_profiles)
```

- Insertion is BEFORE the guard so the guard still sees/validates the final
  profiles (guard checks name/source_entity_type only; extra keys pass).
- Coverage honesty preserved: no bound cards → no keys → prompt unchanged.

### C. Edit: `backend/app/services/opinion_agent.py` — `character_context()` (~line 511)

`character_context()` builds the sim-feed prompt from a WHITELIST of profile
fields; unknown keys are silently dropped. Add one section at the end of the
existing field assembly:

```python
research = profile.get("research_context")
if research:
    sections.append(research)
```

(Exact splice point to match the function's existing list/format idiom —
final form follows the surrounding code style at implementation time.)

- The interview/panel path (`_build_external_question_context`) already passes
  the full profile dict as JSON — cards flow there with NO edit.
- `opinion_block.py` / `agentsociety_opinion_block.py` are dead code paths
  (per PILOT_README) — deliberately NOT touched.

## What does NOT change

- Persona identity, attitude fusion, affordability/economic lens, stats path.
- Binding is archetype-tag lookup only — no LLM anywhere in the new code.
- Cards data files (already shipped + validated; this only reads them).
- Panels: `_build_profile` itself untouched, so panel casts get cards only
  if/when we later add the same 3 lines to the panel path (out of scope now;
  noted as follow-up).

## Tests (LLM-off, in the main repo's test layout)

1. `cards_for_archetype("communal_farmer")` returns exactly
   [communal-cattle-asset-logic, farmer-stock-theft-exposure] (specificity
   order), and `("civic_moderate")` returns [middle-class-status-identity]
   (only card ≤cap that binds).
2. `cards_for_archetype("economic_migrant")` (no cards) → [] and profile
   gains no keys — coverage honesty.
3. Flag off → [] for every archetype.
4. `render_research_context` output contains no digits (contamination guard
   at the prompt boundary, mirroring the card lint).
5. Integration: run `prepare_simulation`'s cast-assembly section against the
   real library and assert a farmer profile carries `research_context` and
   `research_citations`, and `assert_library_cast` still passes.

## Verification after merge

1. Unit tests above.
2. One real sim through the app, same scenario, flag on vs flag off; diff one
   agent's utterances — expect mechanism-flavored reasoning under ON (the
   production replica of Stage 6's baseline-vs-cards result).
3. Inspect `agentsociety_profiles.json` written by prepare_simulation for the
   new keys.

## Open questions for reviewer (you)

1. Cap=2 per persona OK? (Alternative: 1 for sim-feed, all for interviews.)
2. Flag default ON or OFF for the first tester sessions? ON gives Tumelo/
   Nkosinathi the new behavior immediately; OFF lets you A/B deliberately.
3. `research_citations` on the profile now (inert, UI later) or leave
   citations out entirely until the UI exists?

## Token-cost note (sim tier)

Rendered block for 2 cards ≈ 250–450 tokens per agent per call. On a
50-agent, multi-round sim that is a real but modest increase (~10-20% of a
typical system prompt). The cap and flag are the safety valves.
