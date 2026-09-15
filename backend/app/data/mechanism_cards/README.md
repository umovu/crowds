# Mechanism cards

Research cards: how people in a situation reason, distilled from South African
qualitative research. One card per file, named `<id>.json`.

- **Shape:** `app/data/model/mechanism_card.json`. Every card must fit it
  (`tests/test_mechanism_card_model.py`); the app logs any card that does not.
- **Made by:** `scripts/extract_card.py` (draft) → `scripts/validate_card.py` →
  human sign-off → the model check → copied here.
- **Used by:** `app/services/mechanism_card_service.py`. A card reaches a persona
  when its `applies_when` rule fits the persona's measured facts, and reaches a
  prompt only when the question mentions one of its `topic_tags`.
- **Claims:** each finding is one self-contained claim: its `text`, its `needs`
  rule, its `chain_id` and `passages`, and its own `objections`, `vocabulary` and
  `evaluative_rules`. A claim reaches only people the card fits and its own `needs`
  fit (`[]` means everyone the card fits). A claim left out takes its words with it.

## Cards (16)

- `communal-cattle-asset-logic` — cattle as savings, insurance and status
- `farmer-stock-theft-exposure` — theft risk, police distrust
- `farmer-market-participation` — why smallholders do or don't sell
- `farmer-intervention-adoption` — reaction to new agri interventions and tech
- `middle-class-status-identity` — status signalling, Black Tax, asset deficit
- `fintech-adoption-trust` — cost, convenience, trust, self-efficacy, social proof
- `education-payment-conversion` — free-to-paid school and edtech decisions
- `edtech-adoption-barriers` — money, home and infrastructure barriers to e-learning
- `incentivized-learning-engagement` — public vs private reward design
- `reward-design-motivation-crowding-sa-v2` — intrinsic vs extrinsic motivation (SA classrooms)
- `parent-digital-learning-perceptions-sa` — parent trust and permission for digital tools
- `township-parent-motivation-sdl` — township parents supporting self-directed learning
- `youth-waithood-identity` — unemployed youth identity, dignity, nihilism
- `youth-mobile-airtime-economy` — phone and airtime as status and currency
- `youth-phone-safety-cost-economics` — theft, cost and safety in device decisions
- `stokvels-calibration` — stokvel trust, lump sums, social infrastructure

## Gaps still open

No card for `institutional_loyalist` or `community_leader` specifically. No SA
qualitative source for subscription persistence. Health cards are drafted
(`docs/extraction/`) and awaiting sign-off.
