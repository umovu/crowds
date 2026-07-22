# Panel analysis — `panel_6599af0f65f4` vs. the grounding fixes

**Date:** 2026-07-19 · **Session:** `panel_6599af0f65f4` (created 12:06)
**Pitch:** Thuto.io, R50/month subscription, financial rewards for study effort
**Mode:** product · **Segment:** `guardians_high_fee` · **Seed:** 455564
**Cast:** 5 seated of 12 requested · **Tiers:** loose ×4, moderate ×1
**Sim model:** `qwen3.6-plus-2026-04-02` (dated snapshot pinned earlier today)

This panel is the first real run exercising all four July grounding fixes at
once: the annual-unit fix, the real-numbers anchor, tier-aware card binding,
and invisible-numbers rule 6. Verdict up front: **all four fixes held; the
run surfaced one new defect (a content-filter failure rendered as a neutral
"no comment") and three smaller issues.**

---

## 1. Fix-by-fix verification

### 1.1 Tier-aware card binding — ✅ working

| Panelist | Tier | Cards bound |
|---|---|---|
| Graham Mitchell | loose | education-payment-conversion, incentivized-learning-engagement |
| **Anita Botha** | **moderate** | **township-parent-motivation-sdl**, education-payment-conversion |
| Zanele Sithole | loose | education-payment-conversion, incentivized-learning-engagement |
| Karen van der Merwe | loose | education-payment-conversion, incentivized-learning-engagement |
| Jaco Botes | loose | education-payment-conversion, incentivized-learning-engagement |

The new `township-parent-motivation-sdl` card (Siziba et al. 2025, Sebokeng
parents — Stage-6 validated, human Stage-5 sign-off still pending) bound
**only** to the single moderate-tier parent. All loose-tier parents got the
two general cards. The `economic_tags` + `budget_tier` filter is doing
exactly what it was built to do.

### 1.2 Invisible-numbers rule 6 — ✅ holding in production

No persona stated their own household income or school fees as figures.
The only rand amount quoted anywhere is the pitch's own R50.

- Anita (moderate): "every cent of our household income is already stretched
  thin… school fees taking such a big chunk of our budget" — qualitative,
  no leak.
- Loose-tier parents: "fifty rand is a negligible amount", "significant fees",
  "R50 a month is negligible compared to the school fees I already pay" —
  fee levels implied, never numbered.

This matches the pilot's condition-D result (leak 83% → 0%) in a live panel,
not just the harness.

### 1.3 Tier signal in stances — ✅ clean separation

The moderate-tier parent is the **only** one whose objection leads with
affordability. All four loose-tier parents explicitly dismiss the cost
("the cost isn't the issue") and object on pedagogy, evidence, and intrinsic
motivation instead. "Wants it" and "can afford it" stayed unmerged — the
economy hard rule is respected end to end.

### 1.4 Annual-unit fix — ✅ no regression

Graham's profile frames school fees correctly as annual ("over eighty
thousand a year"). No annual-as-monthly misreads anywhere in profiles or
responses (the original `panel_39692ef06a7c` bug remains fixed).

---

## 2. Stance outcome

| Panelist | Tier | Stance shift |
|---|---|---|
| Graham Mitchell | loose | neutral → neutral *(⚠ failed interview, see §3.1)* |
| Anita Botha | moderate | neutral → concerned |
| Zanele Sithole | loose | neutral → concerned |
| Karen van der Merwe | loose | neutral → oppose |
| Jaco Botes | loose | neutral → concerned |

Dashboard: concerned ×3, oppose ×1, neutral ×1 · stance-change rate 0.8 ·
mobilization risk low ×5.

Substantively: for this segment the R50 price point is a non-issue; the
consistent objection is **unproven academic efficacy** and **extrinsic-reward
skepticism**. The pitch's weakness for high-fee guardians is evidence, not
price.

---

## 3. Defects surfaced by this run

### 3.1 Content-filter failure masquerading as a neutral answer (highest priority)

Graham Mitchell's "I have no comment on that." is not a persona response.
The round metadata records:

```
litellm.BadRequestError: OpenAIException - <400>
InternalError.Algo.DataInspectionFailed: Input text data may contain
inappropriate content. Model Group=qwen3.6-plus-2026-04-02
```

Yet the round counts him as `successful: 5/5` with stance neutral → neutral,
silently diluting the dashboard (true stance-change rate among real answers
is 4/4, not 4/5).

Two contributing factors:

1. **The interview service swallows the error** and substitutes a no-comment
   fallback instead of marking the interview failed.
2. **The dated snapshot may filter harder than the alias.** The pin to
   `qwen3.6-plus-2026-04-02` happened hours before this run. Graham's persona
   text (political-grievance framing: "Government and officials mostly don't
   act in people like me's interest… complaints go nowhere") is a plausible
   trigger for DashScope's input inspection.

**Recommended fix:** surface `impact_metadata.error` as a failed interview —
exclude from stance counts, flag in REPORT.md. Optionally retry once on
`DataInspectionFailed`.

### 3.2 Cast shortfall: 12 requested, 5 seated

The curated library holds only 5 personas matching `guardians_high_fee`.
Correct behaviour under the no-LLM-personas rule, but the report shows the
shortfall only implicitly (tier counts summing to 5). REPORT.md should state
"5 of 12 requested — library limit" explicitly so a reader doesn't assume a
12-person panel.

### 3.3 Prompt contradiction in Graham's persona

His HOW YOU SPEAK block says he "quotes figures in rands," while rule 6
forbids stating his own household figures. This run never collided (he
errored out), but the contradiction is latent. Either soften the speech
directive for product mode or scope it to public figures (rates, load-shedding
schedules) rather than household ones.

### 3.4 `affected_entities` extraction is junk

Dashboard emitted `["Fifty", "While", "Transforming"]` — capitalized
sentence-openers, not entities. Low stakes, but it pollutes the dashboard.

---

## 4. Mechanism trace — what each agent actually reasoned from

Each prompt carried three grounding layers from the July fixes: the fixed
budget-tier lens, the real-numbers anchor (surveyed income + annual fee band),
and two rendered research cards. Card slugs map to rendered sources as:
`education-payment-conversion` → RESEP low-fee independent schools;
`incentivized-learning-engagement` → gamified e-learning quizzes study;
`township-parent-motivation-sdl` → Siziba et al. 2025 (Sebokeng parents).

### Graham Mitchell — no mechanisms used
Content-filtered before the model answered (§3.1 above). His prompt carried RESEP + gamified-quizzes, LOOSE tier,
R100k/month, fees >R80k/yr — none of it was exercised.

### Anita Botha (moderate, R5,000/month, fees R12–16k/yr) — township card + real-numbers anchor
The clearest card uptake in the panel, and the only agent bound to the new
township card:

- **Real-numbers anchor + tier lens:** fees of R12–16k/yr against R5k/month
  income is a genuinely heavy ratio — her opener ("every cent… stretched
  thin… school fees taking such a big chunk") is that ratio verbalized
  without leaking a figure (rule 6 working *with* the anchor, not against it).
- **Siziba mechanism "parents own the motivating role; children rely on
  external regulation":** → "I already spend so much energy just getting
  them to open their books."
- **Siziba mechanism "motivational interventions are viewed as
  insufficient":** → "Unless I can see proof that this actually improves
  their grades and not just their pocket money."

### Zanele Sithole (loose, R100k/month, fees R16–20k/yr) — RESEP + gamified-quizzes
- **Tier lens:** "fifty rand is a negligible amount for our household" —
  cost dismissed up front, exactly what LOOSE instructs.
- **RESEP mechanism "parents evaluate schools by academic outcomes":**
  → "I value the discipline and academic rigor my children currently
  receive"; demands "clear evidence that it improves actual educational
  outcomes."
- **Gamified-quizzes card:** supplies the "gamifies test-taking" frame and
  the intrinsic-vs-extrinsic motivation objection.

### Karen van der Merwe (loose, R100k/month, fees R20–40k/yr) — RESEP quality-exit mechanism
- **RESEP "quality gaps trigger migration / active marketplace search":**
  → "already paying significant fees for a private school to ensure my son
  receives quality instruction" — she reasons as a parent who has already
  *bought* quality and sees Thuto as a downgrade to that decision.
- **Gamified-quizzes card:** → "outsource motivation to a gamified app",
  "treats learning as a transaction" — the strongest extrinsic-reward
  objection, driving the panel's only *oppose*.

### Jaco Botes (loose, R50,000/month, fees R4–8k/yr) — tier lens + RESEP outcomes filter
- **Tier lens + anchor:** "R50 a month is negligible compared to the school
  fees I already pay, so the cost isn't the issue" — the LOOSE framing
  almost verbatim ("budget is not the main obstacle; the question is whether
  it's worth it").
- **RESEP academic-outcomes mechanism:** → "tangible improvements in my
  teenager's performance to justify adding another digital tool."
- **Gamified-quizzes card:** → "gamifies distraction."

### Cross-cutting observation — the projection-guard to-do is live here

Three of the four real answers assert that Thuto *is* gamified ("gamifies
test-taking", "gamified app", "gamifies distraction"). The pitch never says
that — "gamified" is vocabulary from the incentivized-learning card being
projected onto the product as fact. This is exactly the known open to-do
(add a projection guard to `render_research_context`). It's mild here
because the inference is plausible, but it shows card language steering
*claims about the product*, not just reasoning style.

---

## 5. Suggested next steps

1. Fix §3.1 in `interview_service` (error → failed interview, not neutral).
2. Add the cast-shortfall note to REPORT.md generation (§3.2).
3. Get human Stage-5 sign-off on `township-parent-motivation-sdl` — it is now
   binding in real panels.
4. Re-run this exact panel (same seed 455564) after §3.1 to get Graham's real
   answer, and compare.
