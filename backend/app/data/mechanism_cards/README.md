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

- **Borrowed:** a card with `borrowed_from` was heard from a close group, not the
  people it is gated to (no interview study covers them). The quotes stay the
  source's own; only the gate is stretched. It needs a gate of at least two facts per
  clause, and the prompt says the reasoning comes from a nearby group.

## Cards (28)

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
- `chronic-care-repeat-cost-sa` — repeat costs of chronic care, transport, when treatment feels worth returning to
- `healthcare-access-barriers-sa` — distance, transport and grant money competing with clinic visits
- `healthcare-facility-choice-sa` — bypassing the clinic, choosing where to seek care
- `older-persons-clinic-experience-sa` — older patients, overcrowding, being listened to and respected
- `youth-clinic-privacy-stigma-sa` — young people, sexual health, judgement and privacy (claims routed by study group)
- `medical-aid-copayment-sa` — people with medical aid who still pay out of pocket: co-payments, savings, pharmacies, generics
- `municipal-waste-failure-sa` — when rubbish collection fails: suburbs store or pay a collector, townships dump or burn (claims routed by poverty)
- `rural-water-scarcity-sa` — rural villages without water: buying it, boreholes, tanker queues, broken promises
- `women-taxi-commuting-sa` — young women commuting by minibus taxi: fares, safety, drivers and dark ranks
- `going-private-when-the-state-fails-sa` — comfortable city homeowners paying for their own water and security; **borrowed** for backup power
- `paying-for-care-without-medical-aid-sa` — paying for care without medical aid: price, trusted pharmacist, work hours, judgement on sexual health (**borrowed**)
- `black-tax-obligation-sa` — employed middle-class people supporting family from their salary, weighing new spending against it

## Gaps still open

No card for `institutional_loyalist` or `community_leader` specifically. No SA
qualitative source for subscription persistence.
