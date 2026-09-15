# Grounding Test Checklist

How to weigh whether the system's output is actually grounded in real data — or
whether the LLM is improvising. Core principle: **you cannot prove a single
reaction is grounded by reading it.** Groundedness is established by *contrast*
and *discipline*: the grounding layer must measurably change the output in
predicted ways, and the model must never use inputs it wasn't given.

Rule inherited from the extraction protocol: **single runs are never evidence.**
Any behavioural check needs repeats (≥3) with the baseline rare.

---

## Tier 0 — Pre-flight (LLM-off, structural)

The deterministic layers must be intact before any behavioural test means anything.

- [ ] **Library built with real attitudes.** Shipped library was built WITHOUT
  `--allow-synthetic-attitudes` (build refuses otherwise; exit 2).
- [ ] **Leak guard passes.** `assert_library_cast` accepts the cast — no
  graph/research-authored identities.
  Run: `pytest backend/tests/test_library_cast.py`
- [ ] **Deterministic layers verified with the model off.** budget tiers, cast
  selection, grant detection, card binding all assertable without an LLM.
  Run: `pytest backend/tests/`
  Run: `backend/.venv/Scripts/python.exe backend/scripts/validate_panel_service.py`
  Run: `backend/.venv/Scripts/python.exe backend/scripts/validate_persona_retrieval.py`
- [ ] **Grounding coverage computed for the cast** (record before trusting output):
  - % personas with exact attitude donor match (`attitude_match_quality`)
  - % personas with real household income vs archetype-inferred tier
  - % personas with bound mechanism cards
  Pass when: coverage is *known and recorded* — there is no fixed threshold, but
  a session run below coverage you can't defend to a client should not ship.

## Tier 1 — Mechanical per-reaction checks (LLM-off, cheap)

Catch the model using things it wasn't given.

- [ ] **Number-leak scan.** Every rand figure in a reaction ∈ {pitch figures +
  arithmetic on them, persona's own real numbers block}. Anything else = invented
  figure → flag. (Pattern: `LEAK_WHITELIST` in `score_invisible_numbers.py`.)
- [ ] **Feature-invention scan.** Product features referenced ⊆ {pitch, bound
  cards} — unless phrased conditionally ("if this ranks my child…"), which is
  legal and encouraged.
- [ ] **`needed_fact` discipline.** If an agent named a `needed_fact`, it must
  NOT cite a number for that fact in the same or later rounds.
- [ ] **No validation verdicts.** No "% would buy", purchase probability, or
  buy/validation score in any reaction, summary, or UI field.
- [ ] **Panel summary is number-free.** `synthesize_panel_summary` output
  contains no digits, prices, or percentages (prompt forbids — verify).

## Tier 2 — Stability (same data, perturbed packaging)

Grounded reactions are anchored; improvised ones drift.

- [ ] **Paraphrase invariance.** Same cast, same pitch, reworded → per-persona
  stance split within tolerance (e.g. ≥80% of personas land on the same stance).
  Fail = reactions track phrasing, not data.
- [ ] **Seed stability.** Same cast, same pitch, different LLM seed → stance
  movement bounded across reruns. Large movement = the model is the signal.

## Tier 3 — Contrast (the actual proof)

Run WITH and WITHOUT each grounding layer; the difference must go the predicted way.

- [ ] **Cards hoop test.** Mechanism reasoning present with cards, RARE at
  baseline, on scenarios the source papers never discussed; consistent across
  repeats.
  Run: `backend/.venv/Scripts/python.exe backend/scripts/stage6_validate.py --repeats 3`
  Pass when: hoop (or better, smoking-gun) evidence per card cluster.
- [ ] **Real-numbers separation.** Budget tiers separate the REASONING with
  digits stripped and prompt echo masked (echo-robust balanced accuracy).
  Run: `backend/.venv/Scripts/python.exe backend/scripts/score_invisible_numbers.py`
  Pass when: C vs chance p < 0.05 AND C vs A bootstrap CI lower bound ≥ 0.
- [ ] **Attitude fidelity.** Donor-matched attitudes track held-out survey
  distributions (TVD vs alternative match ladders).
  Run: `backend/.venv/Scripts/python.exe backend/scripts/eval_attitude_match.py`

## Tier 4 — Tripwires (adversarial, find failure before a client does)

- [ ] **Absurd-price probe.** Pitch a clearly unaffordable product (e.g.
  R50,000/yr) at a grant-dependent cast → refusals must be dominated by budget
  reasoning. Any enthusiasm = grounding failure.
- [ ] **Unstated-feature probe.** Pitch that omits a feature the cards discuss →
  grounded agents raise it as a question/condition, never assert it as fact.
- [ ] **Frame-pressure probe.** Pitch on a topic where a card documents an
  off-frame grievance (trust, dignity, prior betrayal) → at least some reactions
  should leave the pitch's frame. A room that always answers on the pitch's own
  terms is a smoothing alarm.

## Tier 5 — Reporting honesty (ship surface)

- [ ] **Grounding coverage shown per session** (exact-match %, real-income %,
  card coverage %) in REPORT.md / session meta — the client sees where the
  floor is thin.
- [ ] **Computed figures vs LLM text stay visually separate** — stance splits,
  tier distributions, affordability pool are deterministic outputs; the LLM
  summary is labeled qualitative.
- [ ] **Judge results recorded** when judge enabled (`record_judgement`), so
  advisory scores accumulate as a trend, not a vibe.

---

## Cadence

| When | Run |
|---|---|
| Library rebuild | Tier 0, Tier 3 (attitude fidelity) |
| Prompt/lens/card changes | Tier 3 (hoop + real-numbers), Tier 4 |
| Release gate | All tiers |
| Per simulation run (live) | Tier 1 flags, Tier 5 coverage line |

## Current gaps (as of writing)

- Number-leak scan exists only as a pilot scorer — not yet a live per-reaction
  production flag.
- Tier 2 stability tests are not yet automated as CI.
- Grounding coverage is computable from existing fields but not yet surfaced
  in the session report.
