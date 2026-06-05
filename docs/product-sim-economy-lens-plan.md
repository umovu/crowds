# Plan: Economic-reasoning lens for product sims

Status: **implemented** on branch `coverage-sim-stop-metric-feed` (uncommitted).
Scope chosen: per-agent economic reasoning only (no dashboard aggregate this pass).
Pitch source chosen: auto-extracted from the document at startup, free-text fallback.

---

## Why

Product mode already *frames* personas economically — SA market segments, rands,
data/load-shedding reasoning, archetypes like `budget_holder` / `skeptic`
([mode_specs.py](../backend/app/services/mode_specs.py), product anchors in
[opinion_block.py](../backend/app/services/opinion_block.py)). The honesty
constraint (reactions/objections, never a "% would buy") is enforced.

What was **missing**: agents carried no economic *state* across rounds. There was
no willingness-to-pay, no perceived cost, no objection that shifts as an agent is
exposed to the pitch and to each other. That made product runs a static poll
rather than a simulation. The two genuinely absent pieces were:

1. **A structured pitch object** — the "thing" agents react to had no schema.
2. **Evolving per-agent economic state** — reactions that *move* across rounds.

## Key architectural fact

The sim does **not** run agentsociety2's spatial environment. There is no
`EnvironmentStarter`, no `EconomySpace`, no currency ledger, no `buy_product()` /
`find_job()` world. It runs `PersonAgent.acompletion()` against one custom skill,
`OpinionCaptureSkill`, over a social-feed environment — **one LLM call per agent
per round**, emitting one of 5 actions (express / respond / search / observe /
nothing).

Therefore the agentsociety2 `economic-reasoning` contrib SKILL could **not** be
"embedded" directly — it is written against `EconomySpace` tools that do not
exist in this runtime, and a literal buy/sell world would violate the
"reactions, not a sales forecast" honesty rule.

## Design principle

A **mode-gated economic-reasoning lens** layered onto the existing
one-call-per-round skill, plus lightweight per-agent economic state.

- No `EconomySpace`, no currency ledger, no new subprocess.
- No second per-round LLM call (preserves the ~94% sim-token-saving discipline).
- Policy mode stays byte-identical — same separation discipline as `mode_specs.py`.
- Honesty constraint holds: qualitative reasoning, **never** a buy-%/validation score.

---

## The two missing pieces, concretely

### A. The pitch object
Derived once at startup from the document context (already extracted for the
founder-label logic). Shape:

```json
{
  "what_it_is": "...",
  "pricing": "... in rands if stated, else 'not stated'",
  "problem_solved": "...",
  "status_quo_alternative": "how SAns solve this today without it"
}
```

One cheap LLM call at init, cached, injected into every product-mode prompt.
Any failure → empty pitch and the lens degrades to generic phrasing.

### B. Per-agent economic state
Carried on `agent.skill_state` (key `product_economy`). Seeded from the agent's
market archetype on first encounter, then **updated each round** from what the
agent just reasoned:

- `perceived_cost` — what they think it really costs (incl. data / load-shedding / time)
- `willingness_band` — qualitative ceiling (NOT a committed price)
- `primary_objection` — current blocker (price / trust / fit / friction / awareness)
- `reconsider_condition` — what would move them ("if it worked offline")

These shift as the agent reads the homophily feed — a vouch from someone similar
lowers a blocker; a hidden cost someone raises lifts it. **That** is the
simulation vs. a static poll.

---

## Implementation steps

| # | File | Change |
|---|------|--------|
| 1 | `mode_specs.py` | `build_economic_lens()`, `seed_willingness_band()` + `PRODUCT_SEED_WILLINGNESS_BANDS`, `build_pitch_extraction_prompt()` + `PRODUCT_PITCH_EXTRACTION_SYSTEM`. All product-side; policy untouched. |
| 2 | `agentsociety_opinion_block.py` | Nullable `economic_reasoning TEXT` column on `opinion` + additive `ALTER TABLE` migration; `add_opinion()` accepts + persists it (None in policy). |
| 3 | `opinion_block.py` | `OpinionCaptureSkill.__init__` takes `mode="policy"` + `pitch=None`. Econ-state seed/merge helpers. When `mode=="product"`: inject lens + pitch + current state into the prompt; parse optional `economic` JSON block; update `skill_state`; thread `economic_reasoning` JSON into `add_opinion` + express/respond output dicts. Gated so policy path is identical. |
| 4 | `run_simulation_as.py` | At skill construction: in product mode, one-shot pitch extraction (best-effort, graceful fallback); pass `mode=sim_mode, pitch=pitch`. |

(Steps were listed as 6 in conversation; 5 and 6 — econ-state seeding and output-dict
threading — were folded into the `opinion_block.py` edits above.)

---

## Output (honesty-safe)

Each expressed opinion record gets a qualitative `economic_reasoning` JSON block.
**No aggregate buy-rate.** A future dashboard view (where objections cluster /
conditions to reconsider) is explicitly out of scope for this pass and would be
framed as "where objections cluster", never "X% would buy".

## Deliberately NOT done

- No `EconomySpace` / currency ledger / `buy_product()` — wrong fit, huge detour,
  and a literal purchase world *is* a sales forecast (violates the constraint).
- No second per-round LLM call.
- No changes to policy mode.

## Cost / risk

- +1 LLM call total at startup (pitch extraction); **0** extra per round.
- Product-mode prompt grows ~10–15 lines; negligible vs. the persona block.
- DB migration is additive/nullable — safe on existing sims.

---

## Verification performed

- `py_compile` on all four changed files — pass.
- `mode_specs` helpers: lens renders specifics with a pitch, falls back to
  generic phrasing when empty, includes the honesty ban ("NEVER state a purchase
  probability", "% would buy"); seed bands non-empty incl. fallback; pitch prompt
  asks for all four fields.
- Policy path inert: `_mode="policy"`, `_pitch={}`, economic section empty, no
  `economic_reasoning` key; product path carries the pitch.
- DB migration: `economic_reasoning` column present; product opinion stores JSON,
  policy opinion stores `NULL`.

## Known limits / follow-ups

- Not yet run end-to-end against a live LLM in a real product-mode project — the
  per-round prompt→parse→state-update loop is verified structurally and by gating
  logic only. A single real product-mode run is the recommended next check.
- The runner reads `self.config.get("simulation_requirement", "")` for the pitch
  prompt; that key may not exist (extraction still works from `document_context`
  alone). If a requirement field exists under another name, wire it in.
- Responses surface `economic_reasoning` on the output dict but only **expressed
  opinions** persist it to a column (responses live in a separate table).
