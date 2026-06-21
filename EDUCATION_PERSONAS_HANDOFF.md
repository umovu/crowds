# Education personas + Panel Pitch — session handoff (2026-06-10/11)

State dump of everything built in this session, what is verified, and the exact
remaining steps. **Nothing in this session is committed yet.**

---

## 1. Where things stand right now

### DONE and verified (all LLM-off validators green at last run)

| Piece | File(s) | Validation |
|---|---|---|
| Panel Pitch feature (sessions, pitch rounds, variants, follow-ups) | `backend/app/services/panel_service.py`, `backend/app/api/panel.py`, `frontend/src/components/PanelPitchPanel.vue` (tab in `Home.vue`) | `validate_panel_service.py` — 60/60 |
| Segments incl. mixing (multi-select, even split, dedup) | `panel_service.SEGMENTS`, `_mixed_cast` | same script |
| Chat memory for panel follow-ups (chat_state, pitch-round seed, rounds stay stateless) | `interview_service.py` (`_chat_profile`, `_persist_chat_state`), `panel_service.latest_round_exchange` | same script |
| Self-reported stance (STANCE: line, parsed; keyword heuristic = fallback) | `opinion_agent.py` (`extract_self_reported_stance`, `stance_check_footer`), mode-aware | same script |
| Sims drawer + delete endpoint (replaced HistoryDatabase) | `frontend/src/components/SimsDrawer.vue`, `DELETE /api/simulation/<id>` in `api/simulation.py` | manual HTTP tests pass |
| GHS 2025 adapter (learner/guardian/gogo skeletons, real income) | `backend/scripts/ghs_adapter.py` | `validate_ghs_adapter.py` — 20/20 |
| Teacher skeletons (QLFS proxy pool, role assigned) | `persona_sampler.sample_teacher_skeletons` | covered in dry-runs |
| `education_satisfaction` attitude (Afrobarometer Q46H) | `attitude_donor_adapter.py` (vocab + decode), `texture_generator.py` (gloss) | `validate_attitude_fuser.py` — PASS, ±5pp |
| Budget tier real-income override (GHS `fin_reqinc`) | `mode_specs.budget_tier(household_income_rand=…)`, wired in `panel_service._build_profile`, `opinion_block._budget_tier_for`, `opinion_agent` init_state carry | asserted in `validate_panel_service.py` |
| Library build education path | `build_library.py` — `--learners N --guardians N --teachers N --append`, per-role fusion, stable-id extension (civic ids unchanged) | assembly dry-run pass |
| Role-aware donor pools (Q93B) | `attitude_donor_adapter.py`: donors carry `occupation_class`; `donor_pool_for_role()`; `build_library` fuses learners vs 166 student donors, educators vs 40 teacher-class donors | inline dry-run: all assertions pass |
| Education panel segments (Learners, Parents & guardians, Gogo guardians, Educators) | `panel_service.SEGMENTS` | counts appear after library build |

### Bug fixes made along the way (also uncommitted)
- `opinion_agent.OpinionCitizenAgent.__init__` clobbered caller `init_state`
  (wiped interview memory/posts/stance for ALL standalone interviews). Fixed:
  init_state wins, defaults fill gaps. Sim path passes no init_state → unchanged.
- `deep_research_service.py` missing `Optional` import (broke `app.services` import).
- `Step2EnvSetup.vue` unbalanced `</div>` (frontend build was failing entirely).
- `prompt_reframer._build_impact_question` latent `NameError` (`persona` undefined).
- Stats SA `.dta` files need `encoding="WINDOWS-1252"` with pyreadstat.

### Data on disk (gitignored, licensed from DataFirst)
- `backend/data/microdata/ghs-2025-v1/ghs-2025-person-v1.dta` (67,748 persons)
  and `ghs-2025-household-v1.dta` (20,095 households). Join key `uqnr`.
  Original download: `D:\downloads\ghs-2025-v1\` (also has .csv versions).
- `backend/data/microdata/attitudes/afrobarometer_r9_sa.sav` (1,384 usable donors).
- `backend/data/microdata/qlfs-2026-q1-v1/` (QLFS, civic skeletons + teacher pool).

---

## 2a. BUILD RESULT (2026-06-11) — 70/100 built, teachers deferred

**Library is now 269 personas** (199 civic untouched + 70 education). Verified:
- **39 learners** — all carry real GHS household income; attitudes from the
  `students` donor pool; `education_satisfaction` present. 100% complete.
- **25 guardian_parent + 6 gogo_guardian** — attitudes from the general
  Afrobarometer pool; real household income. 100% complete.
- **0 educators** — the LLM **free-tier quota ran out** (z.ai/glm-5.1:
  `403 AllocationQuota.FreeTierOnly`) before the teacher batch. NOT a code
  issue. Teachers deliberately DEFERRED per user ("optimise teachers later").
- Panels verified live: learner cast selects with real-income budget tiers
  (e.g. 7 moderate / 1 tight on n=8); learner+guardian mix splits 4/4.
- Segment counts live: Learners 39, Parents & guardians 31, Gogo guardians 6,
  Educators 0 (self-corrects when teachers are built).
- Backup of the pre-education 199 library:
  `app/data/persona_library/personas.backup-pre-edu.json`.

**To finish teachers later** (needs LLM quota cleared first — disable
"use free tier only" / add paid credit on the z.ai account):
```bash
python scripts/build_library.py 0 --teachers 20 --append --seed 2
```
`--append` skips the 70 already built (no re-pay) — only textures the 20 educators.

**Still TODO to use what's built:** restart the backend (it predates the new
library + all this session's code) so panels/sims see the 70 education personas.

## 2b. ORIGINAL BUILD COMMAND (for reference) — RUN 2026-06-11

```bash
cd backend
python scripts/build_library.py 0 --learners 40 --guardians 40 --teachers 20 --append --seed 2
```

- `0` = no new civic personas; `--append` merges into the existing 199 without
  re-texturing them (their texture is never overwritten).
- ~100 textures at the same per-persona cost as the original 199 build.
- After it finishes: the new segments show live counts in Panel Pitch, and the
  personas appear in the library drawer for sim rosters. **No further code needed**
  for panels or sims on education personas.

**Pre-build safety done:** snapshot at
`app/data/persona_library/personas.backup-pre-edu.json` (the 199-persona library)
— restore from it if the append needs undoing. 3-persona smoke test passed first
(learner/guardian/educator all textured, real income present, role-sourced
attitudes, education_satisfaction present). Then the full build was launched
in the background. If interrupted: re-running with `--append` is safe (already-
textured ids are skipped), so it resumes rather than re-pays.

Last action in flight when session paused: final validator sweep
(`validate_attitude_fuser / ghs_adapter / panel_service / persona_sampler /
texture_generator`) — each had passed individually right before the role-pool
change; fuser + role-pool dry-run passed AFTER it. Re-run all five before building:

```bash
python scripts/validate_attitude_fuser.py
python scripts/validate_ghs_adapter.py
python scripts/validate_panel_service.py
python scripts/validate_persona_sampler.py
python scripts/validate_texture_generator.py
```

---

## 3. Key design decisions (and why)

- **Persona universe stays 15+.** Learner personas are 15–18 in the school system
  (GHS `edu_attend`, `edu_edui`). Under-15s are NOT personas — they appear as
  guardian context (`learners_in_household`, fee bands). Same rule as QLFS.
- **Guardians split by data, not quota:** `gogo_guardian` when the household's
  learners are grandchildren of the head — ~39% of SA learner households
  (6,357/16,274 in GHS 2025). `guardian_parent` otherwise.
- **Real income beats inference.** `fin_reqinc` (net household income, rand/month,
  100% populated; sentinel 9999999 → unknown) drives `budget_tier`:
  ≤R4,500 tight / ≤R20,000 moderate / else loose (GHS quartiles 3k/5k/12k).
  Precedence: household income > grant amount > archetype. LLM never touches it.
- **Teachers are an honest proxy:** QLFS Professionals/Assoc.-professionals ×
  Community services × Tertiary, role assigned, `occupation_provenance:
  "role_assigned"`. Upgrade path = TIMSS teacher questionnaire.
- **Role-aware attitude donors (Q93B):** learner attitudes from student
  respondents (n=166, source `afrobarometer_r9_sa:students`), educator attitudes
  from "mid-level professional (e.g., teacher, nurse…)" respondents (n=40, source
  `afrobarometer_r9_sa:teacher_class_professionals`). Guardians stay on the full
  pool — R9 has no children-in-household item. Slices under 30 donors fall back
  to the full pool automatically (synthetic fixture → full pool, by design).
- **TIMSS is additive, not replaced** by role pools: it brings dimensions
  Afrobarometer lacks (learner motivation/subject attitudes, teacher working
  conditions, parent home-support). Use TIMSS 2019 **Grade 9** for teen learner
  attitudes (2023 is Grade 5 — guardian/home context), teacher questionnaire to
  upgrade educators. Build = a second donor adapter; fuser unchanged.
- **Panels = sim-dir-without-a-sim:** panel sessions write
  `agentsociety_profiles.json` + `document_context.json` in
  `uploads/panel_sessions/` so the whole InterviewService/agentsociety2 stack
  (PersonAgent, `answer_external_question`, skill state) runs unchanged.
- **Product honesty rules hold everywhere:** wants-it (LLM) vs can-afford-it
  (computed) never merge; no "% would buy"; dashboard shows counts of
  qualitative outputs + a real-data budget mix.

## 4. Suggested next steps after the build

1. Commit everything (suggested split: panel feature / stance+chat memory /
   sims drawer + delete / GHS+education pipeline / bug fixes).
2. Restart the backend (running process predates all of this).
3. Smoke a panel: pitch something Thuto-shaped at segment "Gogo guardians" and
   "Learners"; check budget tiers come from real income (`income_provenance:
   "ghs_2025_reported"` on roster).
4. TIMSS adapter — full provision in section 4b below.
5. Facts JSONs still worth adding: DBE class sizes / no-fee proportions,
   prepaid data prices (the `sa_grant_amounts.json` pattern).
6. **Cheapest free enrichment, GHS already loaded:** pull `edu_nofees` (why no
   fees: cannot afford / no-fee school / exemption / bursary) onto learner
   skeletons in `ghs_adapter._learner_skeleton`. Populated for attending
   learners, speaks directly to the affordability story. NOTE: `edu_rsnn`
   (reason for NOT attending) is only populated for DROPOUTS, so it yields nulls
   on our currently-attending learners — use it for a future dropout persona,
   not the active-learner ones. (Deferred this session: build was mid-run reading
   the same GHS file; don't change the sampler under a live build.)

## 4b. TIMSS provision (next data milestone)

**Why (what role-aware Afrobarometer pools still can't give):** dimensions that
don't exist in a civic survey — learner motivation (likes/avoids maths & science,
confidence, sense of belonging, bullying), teacher working conditions and job
satisfaction (real teachers, fixes the `role_assigned` proxy), parental
home-learning support. For edtech pitches, learner motivation is the single most
product-relevant missing signal.

**Where to get it (all free, registered download):**
- TIMSS 2019 international database — <https://timss2019.org/international-database/>
  → SA **Grade 9** (the age-appropriate donor for our 15–18 learner personas).
- TIMSS 2023 international database — <https://timss2023.org/data/>
  → SA **Grade 5 only** (younger kids — use for guardian/home-support context,
  NOT for teen learner attitudes).
- TIMSS SA (HSRC/DBE) datasets page — <https://www.timss-sa.org/datasets> —
  SA-specific files + national context.
- Files come as SPSS `.sav` (pyreadstat reads them; same toolchain as
  Afrobarometer). Country code in filenames is `ZAF`; cycle suffix `m7` = 2019,
  `m8` = 2023. The ones that matter:
  - student/context: `bsg zaf m7` (G9 2019 student background)
  - teacher: `btm/bts zaf m7` (G9 maths/science teacher questionnaires)
  - home (2023 G5): `ash zaf m8` (Early Learning / home context)
  (verify exact names against the download's codebook — naming follows the
  TIMSS IDB convention.)

**Where to drop them:** `backend/data/microdata/timss/` (gitignored like the rest).

**CORRECTED role mapping (TIMSS enriches teachers + learners, NOT parents):**

| Persona | TIMSS enrichment | Verdict |
|---|---|---|
| Educators | Teacher questionnaire (G9 2019) — working conditions, job satisfaction, class size. Upgrades the `role_assigned` QLFS proxy into surveyed-teacher attitudes. | **Yes — top-priority TIMSS use** |
| Learners (15–18) | Student questionnaire (G9 2019) — motivation, belonging, subject attitudes. | Yes, on the Grade 8–9 slice |
| Guardians/parents | TIMSS home/parent questionnaire is **Grade 5 ONLY** — wrong life stage for our senior-phase guardians. | **No — do NOT promise this.** Parents stay on GHS facts + Afrobarometer general pool. |

**Grade coverage reality (why TIMSS isn't the whole answer for learner attitudes):**
- GHS already gives learner GRADE IDENTITY across the full range (R→12, every
  grade ~900–1,600 learners). Grade is never the gap.
- Our 15–18 persona window is ~80% Grade 10/11/12 (senior phase) — correct
  demographically. So the library is effectively a senior-secondary learner set.
- TIMSS tests only Grade 4 + Grade 8/9 → its motivation attitudes map onto the
  Grade 8–9 slice, NOT Grade 10–12. There is no TIMSS senior-secondary.
- The senior-secondary international study is **PISA** (tests 15-year-olds) — BUT
  **South Africa has historically not participated in PISA**, so a clean SA PISA
  microdata file likely does NOT exist. Check before relying on it.
- Cheapest CURRENT senior-grade signal, already in the loaded GHS file, not yet
  extracted: `edu_rsnn` (reason for not attending) + dropout reasons. Real,
  current, right cohort — extract these onto learner personas as a free first move.
- **NIDS** (SALDRU/DataFirst, free): its lane is income/schooling DYNAMICS and
  dropout TRAJECTORIES (longitudinal), NOT senior-grade attitudes — last wave is
  2017 (stale for tech attitudes) and its attitude battery is thin. Use it later
  for the disillusioned-dropout / second-chance persona, not for this.

**Build plan (mirrors the Afrobarometer adapter — fuser unchanged):**
1. New `backend/scripts/timss_donor_adapter.py` — the one TIMSS-specific file.
   Decodes student/teacher questionnaire items into donor records with the SAME
   join-key vocabulary (gender, province*, education_band, employment_status,
   age_band). *Province may be unavailable/coarse in the public IDB — if so,
   drop it from that donor source's keys; the fuser's backoff ladder already
   handles absent keys.
2. Extend `ATTITUDE_VOCAB` with the new dimensions, e.g.
   `learning_motivation` (low/mid/high), `school_belonging` (low/mid/high),
   `teacher_morale` (low/mid/high — teacher donors only). Each needs a
   `_STANCE_GLOSS` entry in `texture_generator.py` (same pattern as
   `education_satisfaction`).
3. Fuse role-keyed, exactly like the Q93B pools: learner skeletons get a second
   fusion pass against TIMSS student donors (`source: "timss_2019_zaf:students"`),
   educators against TIMSS teacher donors. `fuse_attitudes(skeletons,
   donors=…, source=…)` already supports this — no fuser change.
4. Validator: extend `validate_attitude_fuser.py`'s marginal check to the new
   dims; add a `validate_timss_adapter.py` in the same shape as the GHS one.
5. Library: re-run the education build with `--append` (new personas) or add a
   re-fuse mode for existing education personas (attitudes are data, not
   texture — re-fusing does NOT cost texture tokens; only a rebuild of the
   attitude block + a texture refresh IF you want voices to reflect the new
   dims).

**Caveats to respect:** TIMSS 2019 G9 learners were surveyed in 2019 — the
attitude vintage predates the persona vintage (fine; record it in `source`).
G5 2023 data must never donate to teen learner personas. Teacher questionnaires
are per-subject (maths/science) — collapse or carry the subject as context.

**Effort estimate:** same shape as the GHS adapter build — an afternoon of
decode-map work + validators, zero changes downstream of the fuser.

## 5. Open/known caveats

- Learner attitudes come from 18+ student respondents (Afrobarometer surveys
  adults) — closest measured stand-in until TIMSS.
- Educator donor pool is 40 after decode drops → more `age_backoff` matches
  (flagged in `match_quality`; honest, visible).
- `Config.MAX_ROUNDS` (renamed from `OASIS_DEFAULT_MAX_ROUNDS`) is still
  unwired by deliberate choice.
- GHS guardians can have `employment_status: None` (a third of adults are
  "Unspecified" in `employ_Status1`) — left None rather than fabricated; fuser
  backoff handles it.
- LadybugDB WAL was quarantined once during testing (`*.corrupt-20260610-*.bak`
  next to `backend/ladybug_data`) — graph DB came up empty; backups exist.
