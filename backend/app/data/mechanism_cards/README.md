# Mechanism cards

15 machine-extracted, human-fix-reviewed cards produced via the pipeline in
`docs/EXTRACTION_PROTOCOL.md` (context-grounding-pilot worktree). Each file
is one card matching the schema in that doc.

Not yet wired into production binding/prompt injection — that's Phase 5
(`prepare_simulation` reads persona `segment_tags`, looks up matching cards
here, injects into the profile dict as `research_context`). See
`PILOT_README.md` in the pilot worktree for the full rollout plan.

## Cards

- `communal-cattle-asset-logic` — cattle as savings/insurance/status
- `farmer-stock-theft-exposure` — theft risk, police distrust
- `farmer-market-participation` — why smallholders do/don't sell
- `farmer-intervention-adoption` — reaction to new agri interventions/tech
- `middle-class-status-identity` — status signalling, Black Tax, asset deficit
- `fintech-adoption-trust` — cost/convenience/trust/self-efficacy/social-proof (broad SA fintech consumers — renamed from middle-class-fintech-trust to match its evidence base)
- `education-payment-conversion` — free-to-paid school/edtech decisions
- `edtech-adoption-barriers` — financial/home-environment/infrastructure barriers to e-learning
- `incentivized-learning-engagement` — public vs. private reward design
- `reward-design-motivation-crowding-sa-v2` — intrinsic/extrinsic motivation crowding (SA classrooms)
- `parent-digital-learning-perceptions-sa` — parent trust/permission for digital tools
- `youth-waithood-identity` — unemployed-youth identity, dignity, nihilism
- `youth-mobile-airtime-economy` — phone/airtime as status and currency
- `stokvels-calibration` — stokvel trust/lump-sum/social-infrastructure (also the extractor's calibration record)
- `youth-phone-safety-cost-economics` — theft/cost/safety driving device-carriage decisions

## Personas these cards can bind to

`communal_farmer` / `smallholder_emerging_farmer` (14 new, QLFS Q210MARKET /
Ste_icse93-derived, added via `backend/scripts/build_library.py
--communal-farmers N --smallholder-farmers N --append`) plus the existing
`learner`, `guardian_parent`, `unemployed_youth`, `disillusioned_dropout`,
`civic_moderate`, `institutional_loyalist` archetypes.

## Blocked/gaps still open

No card for institutional_loyalist or community_leader archetypes specifically.
No genuinely SA subscription-persistence qualitative source found (ICASA
industry data only).

## Retired, not shipped

Two earlier drafts were superseded by SA-sourced replacements and are kept
only in the pilot worktree's `docs/extraction/` for the record, not copied
here: a non-SA `reward-design-motivation-crowding` (Deci/Koestner/Ryan) and
a non-SA `parent-digital-learning-perceptions` (UK/Australia) — both
replaced by their `-sa` / `-sa-v2` counterparts above.
