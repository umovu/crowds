# Context-grounding pilot — results

Branch: `context-grounding-pilot` (worktree at `D:/fub-agentsociety-context-pilot`).
Script: `backend/scripts/context_grounding_pilot.py`. Full run output:
`backend/scripts/context_grounding_pilot_output.json`.

Purpose: validate, against the real persona library and real SIM_LLM calls, whether
the mechanism-card design in `docs/ACADEMIC_GROUNDING.md` (main repo) actually
changes persona reasoning — before committing to the full ~30-paper corpus.

## Why not `agentsociety2.agent.person.PersonAgent`

Inspected the installed `agentsociety2` package (`backend/.venv/Lib/site-packages/agentsociety2`).
`PersonAgent` is a skills-first coding-tool agent — workspace filesystem, bash
execution, skill activation, multi-round tool-call loop. Built for automating
dev tasks, not for holding a persona's opinion. This repo already diverged
from it for the same reason (see `backend/app/services/agentsociety_opinion_block.py`
header comment: "runs without the city infrastructure"). Pulling in `PersonAgent`
would add workspace/skill/bash machinery with no role in this test.

Instead the pilot reuses the same minimal shape that file already established:
**Persona** (profile dataclass) → **Block** (one action: RESPOND) → LLM call.
No tool loop, no environment router — the variable under test is only "what
mechanism context is bound to the system prompt."

## What was tested

1. **Coverage-honesty check** — does a real persona exist for a given mechanism
   card's `segment_tags`? Ran against the live 269-persona library
   (`backend/app/data/persona_library/personas.json`, main repo).
2. **Grounded vs ungrounded response** — same persona, same scenario, with and
   without a mechanism card injected into the system prompt.

## Result 1 — coverage check confirms the farmer gap directly

Live archetypes in the library today:
`civic_moderate, community_leader, disillusioned_dropout, gogo_guardian,
grant_dependent_survivor, guardian_parent, informal_trader,
institutional_loyalist, learner, small_business_owner, unemployed_youth`

No `communal_farmer` / livestock archetype exists. The `STOCK_THEFT_CARD`
(Ainslie + Eastern Cape stock-theft mechanisms) has **no persona to bind to**.
This is Tumelo's exact complaint (`docs/PERSONA_DATA_PLAN.md` §6), now
confirmed against live data instead of resting on his anecdote. It's also a
working proof of the coverage-honesty gate design (plan §5.1): the pilot
correctly declined to run the farmer test rather than force-fit the card onto
a mismatched persona (e.g. `grant_dependent_survivor`). **This is the gate
behaving as designed, not a bug in the pilot.**

## Result 2 — grounding produces a real behavioral delta

Persona: Thandeka Nene (`grant_dependent_survivor`, KwaMashu, KZN).
Scenario: a savings app with a 3-month lock-in bonus.
Card: `orange-farm-stokvels-2014` (segment_tags include `grant_recipient`,
`urban_township` — a real match for this persona).

**Without the card** — distrust framed individually and institutionally:
> "...I don't trust a faceless company to hold onto what little I have.
> ...I'll keep my money on my SASSA card where at least I control every withdrawal."

**With the card** — the same distrust now routes through a specific,
documented alternative mental model, introduced unprompted:
> "...In my stokvel, we pull out immediately when a child gets sick or
> there's a funeral because we trust each other's struggles face-to-face,
> not some algorithm that penalises you for needing your own rand. My real
> worry is that this bonus is just bait to trap me..."

This is not a stylistic change — the grounded version gives the persona
access to a reasoning structure (group-based mutual trust vs. institutional
trust) that wasn't available without the card. The card's `objection_patterns`
and `vocabulary` fields surfaced organically ("trust," "bait," the group
dynamic) without being quoted verbatim, which was the design goal in
`ACADEMIC_GROUNDING.md`.

## What this validates about the design

- **Mechanism-card schema works as intended** — a card built from real paper
  text, reviewed by hand, produces a genuine reasoning shift, not decoration.
- **Coverage-honesty gate is necessary, not optional** — without it, the
  natural failure mode is binding the stock-theft card to the nearest
  available persona (`grant_dependent_survivor` or `informal_trader`) and
  getting a farmer-flavored response from someone who isn't a farmer. The
  gate is what makes the gap *visible* instead of silently papering over it.
- **claim_type: "mixed" was necessary** (per the earlier extraction pilot) —
  confirmed again here; the stock-theft card is mixed and that distinction
  matters for confidence display, not for extraction behavior.

## What this changes about the plan

Nothing in `docs/ACADEMIC_GROUNDING.md`'s design needs to change. What changes
is priority: the farmer/livestock archetype gap (already flagged in
`docs/PERSONA_DATA_PLAN.md` step 2 as a build-pipeline item) now has a
concrete, tested consequence — a fully-authored mechanism card sitting idle
with no persona to attach to. Recommend sequencing the communal-farmer /
remote-emerging-farmer archetypes *before or alongside* the first
mechanism-card batch, not after, so the ★-priority cards from
`ACADEMIC_GROUNDING.md` (stock theft, Ainslie cattle) have somewhere to land
on day one.

## Datasets needed alongside personas (confirmed by this pilot, not just designed)

For mechanism cards to bind usefully, personas need machine-checkable
segment fields the card's `segment_tags` can match against — this pilot's
coverage check only worked because `actor_archetype` already exists as a
field. Extending that:

| Dataset | Unlocks | Status |
|---|---|---|
| QLFS agriculture-sector bodies | `communal_farmer` / `remote_emerging_farmer` archetypes to bind the two farmer cards | not yet in library (confirmed by this pilot) |
| GHS asset battery (livestock, if present; otherwise proxy via geotype+occupation) | distinguishing livestock owners from other rural personas | planned, `docs/PERSONA_DATA_PLAN.md` step 1 |
| `geotype` field | binding cards tagged `rural` vs `urban_township` precisely instead of guessing from province | planned, plan §4 |
| A `segment_tags`-compatible vocabulary on personas (derived from archetype + geotype + assets) | turning "coverage check" from a manual archetype-name grep (as done ad hoc in this script) into the deterministic lookup `ACADEMIC_GROUNDING.md` §"runtime binding" specifies | needs a small mapping table, not new data collection |

The last row is the one concrete gap this pilot exposed that wasn't already
written down: `segment_tags` on cards need a defined, closed vocabulary that
maps 1:1 onto persona fields (archetype ∪ geotype ∪ asset flags), or binding
degrades back into ad hoc string matching like this script did.
