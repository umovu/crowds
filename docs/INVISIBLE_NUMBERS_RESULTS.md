# Invisible-numbers pilot — results (runs 1+2)

- **Run:** 2026-07-17, model `qwen3.7-max-2026-05-17` (substituted at user
  direction after `qwen3.6-plus` free-quota exhaustion), seed 241946,
  3 repeats × 12 personas × 4 conditions = 144 calls, **144 valid, 0 errors**.
- **Instrument:** frozen lexicons from `docs/INVISIBLE_NUMBERS_PILOT.md`
  (calibrated on `qwen3.6-plus` production language). No retuning after output
  existed.
- **Output:** `backend/scripts/invisible_numbers_pilot_output.json`;
  scorer `score_invisible_numbers.py`.

## Headline

| condition | BA(echo-robust) | p(echo) | abstain | number_leak |
|---|---|---|---|---|
| A_control | 0.41 | 0.0017 | 19/36 | **83%** |
| B_block_only | 0.10 | 0.9187 | 15/36 | 3% |
| C_full | 0.24 | 0.0501 | 21/36 | 3% |
| D_rule_only | 0.31 | 0.0445 | 17/36 | **0%** |

**Gates: both FAIL.** C vs chance p = 0.0501 (needed < 0.05 — a marginal
miss, but the gate is the gate). C vs A bootstrap CI [-0.36, +0.06] (needed
lower bound ≥ 0). Under the frozen instrument, the compiled situation block
did not preserve measurable tier signal; it degraded it.

## Findings

**1. The original complaint, quantified — and the cheap fix works.**
Production (A) cites own income/fee figures in **83%** of responses. D
(production + one rule: "never state your own household income or school fees
as figures") drives that to **0%** while keeping tier signal above chance
(BA 0.31, p = 0.044), killing template collapse (0% vs A's 17%), and producing
the highest opener diversity (0.88 bits). D is a one-line change to
`prompt_reframer._build_constraints` — the evidence-backed production port.

**2. The situation block (B/C) lost signal, and not via echo.**
Containment check: block echo in B/C is ~9–10 overlapping 4-grams across 36
responses (6 responses, mostly Palesa/Slindile) — negligible, and echo-robust
≈ raw BA everywhere. So the collapse is not circularity surfacing; the block
as written does not reproduce what figures + tier gloss carry. B (block +
justify ask) is worst — below chance. C (block + open ask) recovers some of
it: 0.10 → 0.24. The ask matters.

**3. Instrument validity on the substituted model.**
The frozen classifier was calibrated on `qwen3.6-plus` idiolect. On
`qwen3.7-max`, tier language drifted: loose personas say "pocket change",
"a drop in the ocean", "easily digestible" — none in the frozen loose lexicon
("negligible", "not the issue"). Tight personas say "not in my budget" —
also unmarked. Consequences: abstain rates 42–58% in all conditions; loose
recall 0.00 **in every condition including A**, where Jaco Botes is
unmistakably loose to a human reader. The internal A-vs-C comparison stands
(same instrument everywhere); absolute BA levels are model-bound. The freeze
held and did its job — it prevented rescuing the hypothesis by retuning.

**4. Persona prose is a second leak channel.**
In C (no figures injected), Nolwandle cited "my R25,000 health department
salary" — her real income, carried inside her own persona narrative. Removing
the numbers block does not fully de-figure a prompt; production port must
also scrub figures from persona prose (or rely on D's rule, which suppressed
even this channel: D leak = 0%).

**5. The design instinct is right; the instrument can't yet prove it.**
Jaco Botes, C_full, rep0: *"fifty rand is pocket change compared to the
massive private school fees I pay … adding another random R50 debit order for
an EdTech gimmick just doesn't sit right with me. I would only reconsider if
the platform proved it actually secures university entrance."* This is
exactly the target behaviour: economics shaping posture (worth-it framing,
efficacy conditions) with zero figure citation. A human reads it instantly
as loose-tier; the frozen classifier scores nothing. The construct emerges;
measurement lags.

## Limitations (in addition to spec's recorded ones)

- Model substitution: absolute levels not comparable to earlier pilots;
  internal contrasts unaffected.
- Cast is tight 3 / moderate 7 / loose 2 — loose tier rests on 2 personas
  (6 responses/condition), one of them (Nolwandle) known-noisy.
- Objection bucketing is crude (price regex catches any "pay"); economics-
  retained tables should be read as descriptive only.
- Containment printed as mean rounds small values to 0.00; distribution
  counts are in this doc (finding 2).

## Next steps

1. **Port D to production** (main repo, separate change): add the no-cite
   rule to `prompt_reframer._build_constraints`; scrub figures from persona
   narrative fields at library build. Evidence: this run.
2. **If the block approach is pursued:** rerun on `qwen3.6-plus` when quota
   returns (frozen lexicon matches its calibration model), OR pre-register an
   extended lexicon calibrated *only* on this run's A-condition outputs,
   frozen, and validated on a *fresh* run — never calibrated and evaluated on
   the same data.
3. **Block v2:** strengthen loose-tier texture (surplus shown concretely —
   replacing things before they break, comparing on quality), drop the
   justify-ask for block conditions (C > B supports this).
