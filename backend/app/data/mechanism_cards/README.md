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

- **Readings:** a claim can carry 2-4 `readings`, different ways someone who does
  this might read a new offer (some more open, some less), each tied to its passages.
  Drafted by `scripts/extract_readings.py`, signed off like the rest of the card. The
  prompt lists them and the persona takes the one that fits their life.

- **Borrowed gate:** `borrowed_when` lets a close group (parents of the learners studied) get the card, marked as borrowed and ranked below direct fits.

## Cards (26)

- `communal-cattle-asset-logic` — cattle as savings, insurance and status
- `farmer-stock-theft-exposure` — theft risk, police distrust
- `farmer-market-participation` — why smallholders do or don't sell
- `farmer-intervention-adoption` — reaction to new agri interventions and tech
- `middle-class-status-identity` — status signalling, Black Tax, asset deficit
- `fintech-adoption-trust` — familiarity, convenience, fingerprint security, cost, wanting a person (7 interviews: thin)
- `education-payment-conversion` — choosing a school: quality, teachers, reputation, safety, zoning (fee-paying parents; no-fee parents borrowed)
- `incentivized-learning-engagement` — gamified quizzes, leaderboards, freeloading (university students; learners and parents borrowed)
- `learner-motivation-grade12-sa` — what keeps a high-school learner working: escaping poverty, making caregivers proud, being acknowledged (parents borrowed)
- `township-parent-motivation-sdl` — parents at no-fee and low-fee city schools motivating a child to study on their own (claims carry readings)
- `youth-waithood-identity` — unemployed youth identity, dignity, nihilism
- `youth-mobile-airtime-economy` — phone and airtime as status and currency
- `youth-phone-safety-cost-economics` — theft, cost and safety in device decisions
- `stokvels-calibration` — stokvel trust, lump sums, funeral saving (struggling city residents; others borrowed)
- `chronic-care-repeat-cost-sa` — living with chronic illness on a precarious income: debt, guilt about asking family, unsafe routes, stress (2021 interviews)
- `healthcare-access-barriers-sa` — distance, transport and grant money competing with clinic visits
- `men-health-seeking-sa` — adult men and clinics: confidentiality, herbs vs pills, queues, dignity, female nurses, masculinity (replaces the staff-reported clinic-choice card)
- `older-persons-clinic-experience-sa` — older patients, overcrowding, being listened to and respected
- `youth-clinic-privacy-stigma-sa` — young people and sexual health services: privacy, judgement, a positive result, relatable staff (young people's own accounts)
- `medical-aid-copayment-sa` — people with medical aid who still pay out of pocket: co-payments, savings, pharmacies, generics
- `municipal-waste-failure-sa` — when rubbish collection fails: suburbs store or pay a collector, townships dump or burn (claims routed by poverty)
- `rural-water-scarcity-sa` — rural villages without water: buying it, boreholes, tanker queues, broken promises
- `women-taxi-commuting-sa` — young women commuting by minibus taxi: fares, safety, drivers and dark ranks
- `going-private-when-the-state-fails-sa` — comfortable city homeowners paying for their own water and security; **borrowed** for backup power
- `paying-for-care-without-medical-aid-sa` — paying for care or convenience without medical aid: fees vs food and wages, a lost day, being seen (struggling city residents; comfortable borrowed)
- `black-tax-obligation-sa` — employed middle-class people supporting family from their salary, weighing new spending against it

## Gaps still open

No card for `institutional_loyalist` or `community_leader` specifically. No SA
qualitative source for subscription persistence.
