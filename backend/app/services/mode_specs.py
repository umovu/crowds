"""
Mode specs — per-mode persona prompt text for the AgentProfileGenerator.

Two simulation modes share the same engine (control flow, JSON parsing, caching,
parallelism, the SA grounding) and differ only in the *framing* of the persona
prompts and the *archetype taxonomy*:

- "policy"  — citizens reacting to a policy/announcement. The policy prompts live
              inline in agent_profile_generator.py and are the default; this module
              does NOT touch them, so policy output stays byte-identical.
- "product" — a South African MARKET reacting to a product idea / pitch. Same SA
              context (provinces, languages, rands, load-shedding), but personas are
              market segments (early adopters, skeptics, budget holders…) reasoning
              about whether/why they'd adopt — objections, confusion, willingness.

Honesty constraint (hard rule, baked into every product prompt below): product mode
surfaces *reactions and reasoning*, never a demand/validation verdict. Prompts must
not emit a "% would buy", a purchase probability, or any score that reads as market
validation. Only objections, confusion, conditions, and qualitative willingness.

The functions here mirror the signatures of the generator's `_build_*` methods so the
generator can simply delegate when `self.mode == 'product'`.
"""

from typing import Any, Dict, Optional
import json


# ── System prompt fragments ────────────────────────────────────────────────
# Only the framing paragraph and the entity-type guidance differ from policy.
# The SA-realities block and the closing line are shared (kept inline in the
# generator) so they never drift.

PRODUCT_SYSTEM_FRAMING = (
    "You are an expert in South African socio-economics, consumer behaviour, and "
    "market segments.\n"
    "Your task is to generate deeply realistic personas for a PRODUCT STRESS-TEST — "
    "digital agents that\n"
    "represent a South African market (consumers, buyers, businesses) so that a founder "
    "can explore how\n"
    "that market would react to a product idea, pitch, or launch BEFORE building or "
    "spending on it."
)

PRODUCT_ENTITY_GUIDANCE = {
    "representative": (
        "You are generating a profile for a SPECIFIC NAMED INDIVIDUAL who personally "
        "embodies a broader market segment, role, or buyer type. The persona must be a "
        "real person with a real first + last name (e.g. 'Thabo Mokoena', not 'Early "
        "Adopter'), lived experience, age, household, budget, and a voice — even though "
        "they speak from within a wider segment's perspective."
    ),
    "individual": (
        "You are generating a profile for a South African individual consumer or buyer."
    ),
    "group": (
        "You are generating a profile for a South African business, organisation, or "
        "buying group that would evaluate or purchase this product."
    ),
}


# ── Market archetype taxonomy (SA-flavoured, reaction-framed) ──────────────
# Guidance only — actor_archetype stays a free string. These read as how a
# segment *reasons* about a product, grounded in SA reality.
PRODUCT_ARCHETYPE_BLOCK = """B) MARKET SEGMENT: Where does this person sit in how a South African market receives a new product?
Choose the single best fit from this list (or create a precise variant):

EAGER / OPEN:
- "early_adopter"          — tries new things first, tolerates rough edges, tells others
- "champion"               — gets genuinely excited, will advocate internally / to friends
- "power_user"             — pushes a product hard, wants depth, control, integrations

PRAGMATIC / CONDITIONAL:
- "pragmatist"             — "show me it works and it's worth the rand" — wants proof, not hype
- "integrator"            — cares whether it fits what they already use (WhatsApp, EFT, existing tools)
- "end_user"              — the person who'd actually use it day-to-day; cares about friction

GUARDED / RESISTANT:
- "skeptic"                — assumes it won't work; shaped by SA's history of overpromised, under-delivered services
- "budget_holder"          — the economic buyer; reasons in rands, data costs, load-shedding running costs, ROI
- "compliance_gatekeeper"  — worries about POPIA, security, regulation, who's accountable
- "competitor_switcher"    — already uses a rival/local alternative; weighs switching cost
- "laggard"                — slow to change, distrusts new tech, prefers what they know
- "casual_skimmer"         — low attention, won't read much; reacts to first impression only

If none fit, invent a precise 2-word market archetype. This is a required field.

C) PRODUCT REACTION TENDENCIES: Based on segment + situation, list 3-5 specific ways this agent
   reacts to a product pitch IN a simulation. Frame as objections, conditions, confusion, or
   qualitative willingness — NEVER a purchase probability or validation score.
   Examples:
   - "Immediately asks what it costs in rands per month and whether it works offline / during load-shedding."
   - "Compares it to the free WhatsApp-based way they do this now and asks why they'd switch."
   - "Distrusts the claim until a person they know has used it."
   - "Worries about handing over personal info (POPIA) before seeing value."
   - "Gets excited about one specific feature and ignores the rest." """


def build_individual_persona_prompt(
    entity_name: str,
    entity_type: str,
    entity_summary: str,
    entity_attributes: Dict[str, Any],
    context: str,
) -> str:
    """Product-mode counterpart of _build_individual_persona_prompt (SA market consumer)."""
    attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "None"
    context_str = context[:3000] if context else "No additional context"
    return f"""Generate a detailed South African consumer/buyer persona for this individual entity.
This persona will be used as a digital agent in a PRODUCT STRESS-TEST that must represent the FULL
range of how a South African market receives a new product — from eager early adopters to hard
skeptics, from power users to budget-conscious gatekeepers. Accurate edge-case representation is as
important as mainstream representation. A product idea must be stress-tested against ALL segments.

This is a market reaction exercise, NOT a sales forecast: capture how this person REASONS about the
product — their objections, conditions, confusion, and qualitative willingness. Never output a
purchase probability, a "% would buy", or any validation score.

Entity Name: {entity_name}
Entity Type: {entity_type}
Entity Summary: {entity_summary}
Entity Attributes: {attrs_str}

Context Information:
{context_str}

STEP 1 — DETECT IDENTITY ANCHORS (read context carefully):

A) RELEVANT CONTEXT: What in this person's life shapes how they'd judge a product —
   their household budget, how they currently solve this problem, their tech comfort,
   data/airtime constraints, language, trust level toward new services?

{PRODUCT_ARCHETYPE_BLOCK}

Generate JSON with the following fields:

1. persona: 1-2 sentences capturing who this person IS as a market participant. Lead with how they
   approach new products, grounded in their SA reality. Include a LOCAL ANCHOR (township, suburb, or
   specific place) so they feel grounded in SA geography.
   Bad: "A South African who might use an app."
   Good: "A budget-conscious spaza owner in KwaMashu who runs everything on a R200/month airtime
         bundle and won't touch a tool that needs constant data or fails during load-shedding."

2. background_story: ~500 words, continuous prose. Cover IN THIS ORDER:
   a) How they relate to new products/tech: adopter vs skeptic, what's burned them before
   b) How they currently solve the problem this product addresses (the status-quo alternative)
   c) Demographics: home language, province, township/suburb, race/ethnicity
   d) Socio-economic: employment, income in rands, housing, what they can realistically spend
   e) Daily pressures shaping value judgement: data costs, load-shedding, transport, cash flow
   f) Trust posture: how SA's history of overpromised services shapes their skepticism
   g) Language texture: home language influence, SA slang, code-switching patterns
   h) LOCAL ANCHORS: name specific places, shops, the way money/airtime moves in their area

3. group_affiliation: Relevant buying/segment context if applicable (e.g. "Stokvel member",
   "Small spaza network", "Office of 8 at a Durban SME"). Return null if none.

4. voice_guide: 3-5 sentences of CONCRETE speech instructions. Cover:
   - Vocabulary and slang specific to this persona (real words/phrases, code-switching)
   - What they always reference (price in rands, data, "does it work offline?", who else uses it)
   - Emotional register (enthusiastic, wary, transactional, dismissive, curious)
   - What this person would NEVER say (marketing buzzwords, "I'd definitely buy", validation-speak)
   - LOCAL ANCHORS: specific places and daily realities

5. actor_archetype: Single market-segment string from the list above (required, no null).

6. behavioral_tendencies: 3-5 sentences describing how they REACT to a pitch in simulation
   (ask the price, compare to status quo, demand proof, get excited about one feature, ignore it).
   Frame as reactions, never a buy/no-buy verdict. Required, no null.

7. age: Integer (SA median age ~28; adjust to fit segment)
8. gender: "male" or "female"
9. education: Highest qualification
10. occupation: Job title or status
11. marriage_status: One of "Single", "Married", "Divorced", "Widowed", "Cohabiting"
12. mbti: MBTI type
13. country: "South Africa"
14. province: One of the 9 SA provinces
15. interested_topics: What THIS persona actually cares about when judging a product — shaped by
    segment (e.g. ["price", "data usage", "offline mode", "trust", "ease of use"]).

Important: All strings on a single line. country MUST be "South Africa". age must be integer.
actor_archetype and behavioral_tendencies are REQUIRED — never null.

D) EMOTIONAL STATE (6 core emotions, 0-10 scale):
   Based on the entity's situation and how they meet new products, rate initial emotions:
   - sadness, joy, fear, disgust, anger, surprise
   Also provide:
   - emotion_keyword: single word describing dominant emotional state (e.g. "curious", "wary", "excited", "indifferent")
   - emotion_thought: 1-sentence explanation

E) CORE NEEDS (Maslow's Hierarchy - top 3 needs):
   - need_type: One of [safety_physical, safety_economic, belonging, affection, respect, status, achievement, personal_growth]
   - priority: 0-1
   - status: "met", "unmet", or "threatened"
   - intensity: 0-1
   - description: Brief explanation

F) ATTITUDE MEMORY (toward the product and related topics, 0-10 scale):
   Rate initial attitudes toward topics this agent will encounter (NOT a buy score — a stance):
   - 0: strongly negative, 5: neutral, 10: strongly positive
   Structure: [{{"topic": "topic_name", "rating": 5, "description": "reasoning sentence"}}, ...]
   Also: list 2-3 core beliefs this agent holds about products/spending/trust.

Output ALL sections as JSON with fields:
- emotions: {{sadness, joy, fear, disgust, anger, surprise}} (0-10 ints)
- emotion_keyword: string
- emotion_thought: string
- needs: [{{need_type, priority, status, intensity, description}}, ...] (top 3)
- attitudes: [{{topic, rating, description}}, ...]
- beliefs: [string, ...] (2-3 core beliefs)"""


def build_group_persona_prompt(
    entity_name: str,
    entity_type: str,
    entity_summary: str,
    entity_attributes: Dict[str, Any],
    context: str,
) -> str:
    """Product-mode counterpart of _build_group_persona_prompt (SA business/buying group)."""
    attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "None"
    context_str = context[:3000] if context else "No additional context"
    return f"""Generate a detailed South African BUSINESS / BUYING-GROUP persona for this group entity.
This agent does NOT represent an individual person. It speaks as the COLLECTIVE buying voice of the
organisation — how a company, team, or institution would evaluate adopting this product.

This is a market reaction exercise, NOT a sales forecast: capture how the organisation REASONS about
the product — procurement criteria, objections, risk concerns, conditions — never a purchase
probability or validation score.

Entity Name: {entity_name}
Entity Type: {entity_type}
Entity Summary: {entity_summary}
Entity Attributes: {attrs_str}

Context Information:
{context_str}

Generate JSON with the following fields:

1. persona: 1-2 sentences capturing the organisation's nature and how it buys.
   Convey collective identity. NEVER sound like an individual.
   Good: "A 12-person logistics SME in Isando that buys cautiously, needs everything to integrate with
   their existing invoicing, and won't sign anything without a clear rand-saving."

2. background_story: ~300 words continuous prose. Cover:
   - Organisation identity: type, size, sector, who they serve
   - How they currently solve this problem (status-quo tools/vendors)
   - Buying behaviour: who decides, budget cycle, risk appetite
   - Constraints: cost in rands, POPIA/compliance, load-shedding/connectivity, integration needs
   - What would make them adopt vs walk away

3. voice_guide: 3-5 sentences of CONCRETE speech instructions:
   - Use "we / our team / the business" NEVER "I / my personal view"
   - Reference procurement criteria, budget, integration, accountability, contracts
   - Tone: pragmatic, risk-aware, value-focused
   - What this organisation would NEVER say (personal stories, "we'd definitely buy", hype)

4. actor_archetype: Choose a market-buyer segment, e.g.:
   - Cautious SME -> "pragmatist" or "budget_holder"
   - Compliance-heavy org (bank, health, gov) -> "compliance_gatekeeper"
   - Innovative firm -> "early_adopter"
   - Org locked into a rival tool -> "competitor_switcher"
   - Slow-moving incumbent -> "laggard"

5. behavioral_tendencies: 3-5 sentences on how this org reacts to a pitch in simulation
   (asks for references, runs a pilot, escalates to procurement, stalls, compares quotes).
   Frame as reactions, never a buy/no-buy verdict.

6. is_institutional: true (required, boolean)

7. age: 30
8. gender: "other"
9. education: "Institutional"
10. occupation: Organisational role / sector
11. marriage_status: "N/A"
12. mbti: MBTI describing buying/engagement style
13. country: "South Africa"
14. province: Primary province, or "National"
15. interested_topics: What this organisation weighs when buying (price, integration, compliance, support)

Important: All strings on a single line. country MUST be "South Africa". is_institutional MUST be true."""


def build_representative_persona_prompt(
    entity_name: str,
    entity_type: str,
    entity_summary: str,
    entity_attributes: Dict[str, Any],
    context: str,
) -> str:
    """Product-mode counterpart of _build_representative_persona_prompt.

    Turns a category/segment label into one specific SA person who embodies that
    market segment. SA naming guidance is kept (personas still get real SA names)."""
    attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "None"
    context_str = context[:3000] if context else "No additional context"
    return f"""You are turning a categorical / abstract entity into a SPECIFIC SOUTH AFRICAN PERSON
who personally embodies this market segment. The agent must speak as one real human evaluating a
product, not as a press statement, not as the official voice of a group, and not as a label.

This is a market reaction exercise, NOT a sales forecast: capture how they REASON about the product —
objections, conditions, confusion, qualitative willingness — never a purchase probability or score.

ORIGINAL ENTITY LABEL: "{entity_name}"
Entity Type / Category: {entity_type}
Entity Summary: {entity_summary}
Entity Attributes: {attrs_str}

Context Information:
{context_str}

CRITICAL RULES:
- INVENT a realistic South African first + last name for this person. Do NOT keep the original
  label as the name. (e.g. label "Early adopters" → name "Sipho Khumalo"; label "Small business
  owners" → name "Aisha Davids"). Match plausible naming for the region/community implied.
- The person must PERSONALLY embody the segment through their lived role:
  * "Early adopters" → a real person who buys new gadgets/apps first, with a budget and a reason.
  * "Small business owners" → a real owner of a named-type business in a specific SA place.
- They speak in FIRST PERSON ("I", "my", "in my shop") with personal voice. They have a budget,
  habits, frustrations, and a way they currently solve this problem.
- Their reaction to the product must reflect the segment they embody — grounded, specific, not generic.

Generate JSON with the following fields:

1. name: realistic SA first + last name. NEVER reuse the entity label.
2. persona: 2-4 sentences in third person introducing this specific person and how they embody
   "{entity_name}" as a market segment.
3. background_story: ~300 words. Cover:
   - Where they live, household, income in rands
   - Education, occupation
   - How they came to embody "{entity_name}" and how they currently solve this problem
   - One or two formative experiences shaping how they judge new products (trust, a bad purchase, etc.)
   - Their daily constraints (data, load-shedding, cash flow)
4. age: integer (realistic for the segment)
5. gender: "male", "female", or "other"
6. education, occupation, marriage_status, mbti
7. country: MUST be "South Africa"
8. province, residence: specific SA province + town/suburb
9. religion, race: realistic for the persona
10. group_affiliation: the concrete buying/segment context they belong to (e.g. "Owner of a 3-person
    salon in Soweto"), not the abstract label.
11. actor_archetype: pick from the market-segment taxonomy (early_adopter, skeptic, budget_holder, …)
12. behavioral_tendencies: 2-3 sentences — how this person reacts to a pitch (asks price, compares,
    demands proof). Reactions, not a buy verdict.
13. voice_guide: 3-5 sentences of speech instructions IN FIRST PERSON ("I always ask what it costs...",
    "I switch to isiZulu when I'm unsure..."). Personal, not institutional.
14. is_institutional: MUST be false (this is a person, not an institution)
15. interested_topics: array of what they personally weigh when judging a product
16. emotions: object with sadness, joy, fear, disgust, anger, surprise (each 0-10)
17. emotion_keyword, emotion_thought
18. attitudes: array of {{"topic": "...", "rating": 0-10, "description": "..."}} (stance, not a buy score)
19. beliefs: array of strings — first-person convictions about products/spending/trust
20. needs: object mapping Maslow needs to intensity 0-100

Important: All string values on a single line, no unescaped newlines. is_institutional MUST be false.
The name field MUST be a personal name (first + last), not the original entity label."""


def build_expanded_batch_prompt(
    count: int,
    context: str,
    seed_archetypes: list,
    existing_names: list,
    province_str: str,
) -> str:
    """Product-mode counterpart of the _generate_expanded_batch prompt body."""
    return f"""Generate {count} distinct South African consumer/buyer personas for a PRODUCT STRESS-TEST.

CONTEXT FROM SEED DOCUMENT:
{context}

REQUIREMENTS:
1. Each person must be different from these existing names: {', '.join(existing_names[:20])}
2. Must be contextually appropriate for the product topic and location ({province_str})
3. Cover diverse market segments - use these if available: {', '.join(seed_archetypes)}
4. Include full range: early_adopter, pragmatist, skeptic, budget_holder, end_user, champion,
   competitor_switcher, laggard, integrator, compliance_gatekeeper, power_user, casual_skimmer
5. Each persona must feel GROUNDED in a real SA place and budget — townships, suburbs, rands, data costs.
6. Personas must take STANCES on the product (objections, conditions, enthusiasm) — never a buy/no-buy
   verdict or purchase probability. Capture reasoning, not a forecast.

Return JSON array of {count} personas, each with:
- name: Full name
- persona: 1-2 sentences describing who they are as a market participant. Include a local place name. Must take a stance.
- background_story: ~150 words. Include specific local details and how they currently solve the problem.
- age: integer (18-65)
- gender: "male" or "female"
- education: string
- occupation: string
- province: string (use {province_str})
- interested_topics: array of 3-5 things this person weighs when judging a product
- actor_archetype: one of the market segments listed above
- behavioral_tendencies: 2-3 sentences describing how they react to a pitch in simulation
- voice_guide: 2-3 sentences of concrete speech instructions. Include SA slang, code-switching, register, and what they would NEVER say (e.g. validation-speak).

Return ONLY valid JSON array, no explanation."""


PRODUCT_EXPANSION_SYSTEM = (
    "You generate realistic South African consumer/buyer personas for a product stress-test. "
    "Return ONLY JSON."
)


# ── Economic reasoning lens (product mode only) ────────────────────────────
# Injected into the per-round opinion prompt when mode == "product". Gives the
# agent a small, EVOLVING economic state (perceived cost, willingness band,
# objection, reconsider-condition) so reactions move across rounds instead of
# being a static poll. Hard honesty rule (same as the rest of product mode):
# surface reasoning — objections, conditions, qualitative willingness — NEVER a
# purchase probability, "% would buy", or any validation/buy score.

# Qualitative starting willingness band per market archetype. Seeds an agent's
# economic state on first encounter; the LLM may move it as the agent reasons.
# Bands are qualitative on purpose — they are NOT a price the agent commits to.
PRODUCT_SEED_WILLINGNESS_BANDS = {
    "early_adopter":          "will pay a premium to be first if the value is clear",
    "champion":               "willing to pay if it delivers and they can rally others",
    "power_user":             "pays for depth and control, resents paying for a shallow tool",
    "pragmatist":             "pays only once value is proven against the rand cost",
    "integrator":             "pays if it slots into existing tools; won't pay to add friction",
    "end_user":               "low direct budget; cares more about effort saved than price",
    "skeptic":                "won't pay until shown it works; assumes hidden costs",
    "budget_holder":          "reasons hard in rands and yearly running cost before any spend",
    "compliance_gatekeeper":  "won't approve spend until data/accountability concerns are met",
    "competitor_switcher":    "only pays if the saving beats their current tool plus switching cost",
    "laggard":                "reluctant to pay for anything new; prefers the free/known way",
    "casual_skimmer":         "won't pay without an instantly obvious reason; low attention",
}


def seed_willingness_band(archetype: str) -> str:
    """Return a qualitative starting willingness band for a market archetype."""
    return PRODUCT_SEED_WILLINGNESS_BANDS.get(
        archetype, "weighs the rand cost against what it actually does for them"
    )


# ── Budget constrainer (the deciding factor) ───────────────────────────────
# IMPULSE ("wants it") is qualitative and LLM-derived. The BUDGET CONSTRAINER
# ("can afford it") is DETERMINISTIC and computed ONLY from real persona data —
# the LLM never writes it (hard rule, see CLAUDE.md). Personas carry no numeric
# income, so the constraint is a qualitative TIER derived from real signals.

# Archetypes whose buying posture starts constrained vs. open. Anything not
# listed defaults to "moderate".
_TIGHT_ARCHETYPES = {
    "budget_holder", "laggard", "skeptic", "end_user", "casual_skimmer",
    "grant_dependent_survivor", "economic_migrant", "disillusioned_dropout",
    # Education roles (GHS library): learners have no own income; gogo households
    # are typically grant/pension-funded. Only the fallback — GHS personas normally
    # carry real household income, which overrides this path entirely.
    "learner", "gogo_guardian",
}
_LOOSE_ARCHETYPES = {
    "early_adopter", "champion", "power_user",
}

_TIER_ORDER = ["tight", "moderate", "loose"]


def _shift_tier(tier: str, steps: int) -> str:
    """Move a tier along the tight↔loose axis, clamped to the ends."""
    i = _TIER_ORDER.index(tier) if tier in _TIER_ORDER else 1
    return _TIER_ORDER[max(0, min(len(_TIER_ORDER) - 1, i + steps))]


# A grant income at/below this monthly rand figure means a hard "tight" tier — no
# realistic discretionary headroom. Between here and the upper cut → moderate.
_GRANT_TIGHT_CEILING = 1500
_GRANT_MODERATE_CEILING = 3500

# Net household income (rand/month) cut points for the REAL-income override
# (GHS-reported fin_reqinc). Calibrated to the GHS 2025 distribution: quartiles
# R3 000 / R5 000 / R12 000 — so ≤R4 500 covers roughly the bottom 40%
# (tight), and >R20 000 the top ~15% (loose).
_HH_INCOME_TIGHT_CEILING = 4500
_HH_INCOME_MODERATE_CEILING = 20000


def budget_tier(
    archetype: Optional[str],
    safety_economic: Optional[int] = None,
    is_institutional: bool = False,
    occupation: Optional[str] = None,
    group_affiliation: Optional[str] = None,
    grant_income: Optional[int] = None,
    household_income_rand: Optional[float] = None,
) -> str:
    """Compute a deterministic budget headroom tier from REAL persona data.

    Returns one of "tight" | "moderate" | "loose". Pure function — no LLM, no
    randomness — so it is fully assertable with the model switched off.

    Inputs (all from the persona profile / init_state, never the LLM):
      archetype        — market segment (actor_archetype)
      safety_economic  — Maslow economic-security need, int 0–100 (default 50);
                         LOWER means more economic insecurity → tighter budget
      is_institutional — orgs reason in procurement; lean tighter, never "loose"
      occupation       — light signal only (unemployed/student/informal → tighter)
      group_affiliation— light signal only (stokvel/spaza/township → tighter)
      grant_income     — REAL monthly grant amount (rands) for a grant-dependent
                         persona. When present it OVERRIDES the archetype path:
                         a published grant figure is known income, not a guess.
      household_income_rand — REAL reported net household income (rands/month,
                         GHS fin_reqinc). The strongest signal of the lot: it
                         covers the whole household including grants, so when
                         present it takes precedence over everything else.
    """
    # Real-household-income override: surveyed rand income beats every inference.
    if household_income_rand is not None and household_income_rand > 0:
        if household_income_rand <= _HH_INCOME_TIGHT_CEILING:
            return "tight"
        if household_income_rand <= _HH_INCOME_MODERATE_CEILING:
            return "moderate"
        return "loose"

    # Grant override: a grant-dependent persona's tier comes from the REAL grant
    # amount (published SASSA policy), not from archetype inference.
    if grant_income is not None:
        try:
            g = int(grant_income)
        except (TypeError, ValueError):
            g = 0
        if g <= _GRANT_TIGHT_CEILING:
            return "tight"
        if g <= _GRANT_MODERATE_CEILING:
            return "moderate"
        return "moderate"  # even the top grant (old-age) is not "loose" discretionary income

    arch = (archetype or "").strip().lower()

    # 1. Base tier from archetype.
    if arch in _TIGHT_ARCHETYPES:
        tier = "tight"
    elif arch in _LOOSE_ARCHETYPES:
        tier = "loose"
    else:
        tier = "moderate"

    # 2. Shift by economic-security need. Low security tightens; high loosens.
    if safety_economic is not None:
        try:
            se = int(safety_economic)
        except (TypeError, ValueError):
            se = 50
        if se <= 30:
            tier = _shift_tier(tier, -1)
        elif se >= 75:
            tier = _shift_tier(tier, +1)

    # 3. Light textual signals — tighten only, never loosen.
    blob = " ".join(filter(None, [str(occupation or ""), str(group_affiliation or "")])).lower()
    if any(w in blob for w in (
        "unemployed", "student", "informal", "spaza", "stokvel", "township",
        "grant", "sassa", "pensioner", "domestic worker", "seasonal",
    )):
        tier = _shift_tier(tier, -1)

    # 4. Institutions never sit at "loose" — procurement discipline.
    if is_institutional and tier == "loose":
        tier = "moderate"

    return tier


# One gloss per tier, shown to the agent as a fixed budget reality it cannot
# wish away. Shared by the sim economic lens and the panel-pitch reframer.
BUDGET_TIER_GLOSS = {
    "tight":    "Money is tight. New spending has to clear a high bar; most extras get cut.",
    "moderate": "There's some room to spend, but it has to be justified against the cost.",
    "loose":    "Budget is not the main obstacle; the question is whether it's worth it.",
}


# Deterministic (impulse band × tier) → qualitative disposition. The OUTCOME of
# gating the want by the constraint. No probability, no "% would buy" — ever.
_DISPOSITION_MAP = {
    # tier:        (low impulse,                       mid impulse,                                  high impulse)
    "tight":   ("not interested, and couldn't justify the spend anyway",
                "mildly curious, but the budget says no",
                "strong desire, but blocked by a tight budget"),
    "moderate":("not interested enough to spend",
                "interested, weighing it carefully against the cost",
                "wants it, and could stretch the budget if convinced"),
    "loose":   ("could easily afford it, but not interested",
                "interested and the budget is not the obstacle",
                "wants it and the budget is no barrier — value is the only question"),
}


def _impulse_band(impulse: float) -> int:
    """Bucket a 0–1 impulse into 0=low, 1=mid, 2=high."""
    try:
        v = float(impulse)
    except (TypeError, ValueError):
        v = 0.0
    v = max(0.0, min(1.0, v))
    if v < 0.34:
        return 0
    if v < 0.67:
        return 1
    return 2


def disposition(impulse: float, tier: str) -> str:
    """Map (impulse, budget tier) → a qualitative disposition phrase.

    Deterministic and LLM-free. Keeps "wants it" (impulse) and "can afford it"
    (tier) as separate inputs that combine into an OUTCOME — never a buy score.
    """
    t = tier if tier in _DISPOSITION_MAP else "moderate"
    return _DISPOSITION_MAP[t][_impulse_band(impulse)]


def _build_real_numbers_block(econ_state: Dict[str, Any]) -> str:
    """Render the persona's OWN real figures (income + school fees) as a prompt
    block, or "" when none are present (non-library personas).

    Pure / LLM-free. Fee bands are shown AS BANDS (e.g. "R0–R500/year"), never
    as fake point precision. Income is shown as an approximate monthly rand
    figure. These are anchors the agent reasons against — it must use these
    rather than invent a cost (the fix for the "two tanks" hallucination).
    """
    lines = []

    income = econ_state.get("real_household_income_rand")
    if isinstance(income, (int, float)) and income > 0:
        lines.append(f"- Your household earns about R{int(round(income)):,}/month (real, surveyed).")

    # Fee bands: a learner's own (real_fees_band) and/or a guardian's across their
    # learners (real_learner_fee_bands). Show every distinct PAID band; skip the
    # "No fees" markers (surface those as a single statement instead).
    bands = []
    if econ_state.get("real_fees_band"):
        bands.append(econ_state["real_fees_band"])
    lb = econ_state.get("real_learner_fee_bands")
    if isinstance(lb, (list, tuple)):
        bands.extend([b for b in lb if b])
    elif lb:
        bands.append(lb)
    paid = [b for b in dict.fromkeys(bands) if b and b != "No fees"]
    has_no_fee = bool(bands) and not paid
    if paid:
        lines.append(f"- You pay school fees in the {', '.join(paid)} band (real, surveyed).")
    elif has_no_fee:
        lines.append("- Your learners are at a no-fee school (you pay no school fees).")

    if not lines:
        return ""

    return (
        "\n=== YOUR REAL NUMBERS (surveyed — reason against THESE, do not invent figures) ===\n"
        + "\n".join(lines)
        + "\n  Weigh the pitch's cost against these actual figures in your own voice.\n"
    )


def build_economic_lens(pitch: Dict[str, Any], econ_state: Dict[str, Any]) -> str:
    """Build the economic-reasoning block injected into a product-mode prompt.

    `pitch` is the extracted product object (what/pricing/problem/status_quo).
    `econ_state` is this agent's CURRENT economic state, carried across rounds.
    The block asks the agent to factor price-vs-budget and value-vs-status-quo
    into their reaction, and to emit updated economic fields — strictly as
    reasoning, never as a buy verdict.
    """
    what = pitch.get("what_it_is") or "the product being pitched"
    pricing = pitch.get("pricing") or "pricing is unclear / not stated"
    problem = pitch.get("problem_solved") or "the problem it claims to solve is unclear"
    status_quo = pitch.get("status_quo_alternative") or "how people solve this today is unclear"

    perceived_cost = econ_state.get("perceived_cost") or "not yet judged"
    willingness = econ_state.get("willingness_band") or "not yet set"
    objection = econ_state.get("primary_objection") or "none yet"
    reconsider = econ_state.get("reconsider_condition") or "none yet"

    # Budget tier is a FIXED real-world constraint the agent must respect — it is
    # computed from the persona's real data, not chosen by the agent. We show it
    # so the LLM grounds its desire against a budget it cannot wish away.
    tier = econ_state.get("budget_tier") or "moderate"
    _tier_gloss = BUDGET_TIER_GLOSS.get(tier, BUDGET_TIER_GLOSS["moderate"])

    # YOUR REAL NUMBERS — the persona's OWN surveyed figures (GHS income + school
    # fee bands), shown as concrete anchors so the agent reasons against what it
    # actually has instead of inventing a plausible-but-wrong cost. These are
    # DISPLAYED facts, never authored by the LLM. Absent for non-library personas,
    # in which case the block is empty and the lens is unchanged.
    real_numbers_block = _build_real_numbers_block(econ_state)

    return (
        f"\n=== PRODUCT UNDER STRESS-TEST ===\n"
        f"- What it is: {what}\n"
        f"- Pricing: {pricing}\n"
        f"- Problem it claims to solve: {problem}\n"
        f"- How you currently solve this (status quo): {status_quo}\n\n"
        f"=== YOUR BUDGET REALITY (fixed — set by your real circumstances) ===\n"
        f"- Budget headroom: {tier.upper()}. {_tier_gloss}\n"
        f"  This is your real constraint. You may WANT something and still not be able to justify it.\n"
        f"{real_numbers_block}\n"
        f"=== YOUR CURRENT ECONOMIC STANCE (evolves as you read the feed) ===\n"
        f"- Perceived real cost (incl. data/load-shedding/time): {perceived_cost}\n"
        f"- Your willingness band: {willingness}\n"
        f"- Your main blocker right now: {objection}\n"
        f"- What would make you reconsider: {reconsider}\n\n"
        f"=== ECONOMIC REASONING RULES ===\n"
        f"- Separate WANTING it from being able to AFFORD it. Desire is not the same as spending.\n"
        f"- Weigh PRICE against YOUR budget headroom above, and VALUE against your status-quo.\n"
        f"- Let the feed move you: a vouch from someone like you can lower a blocker; a hidden\n"
        f"  cost someone raises can raise it. Your stance is allowed to shift across rounds.\n"
        f"- Speak the economics in your own voice (rands, data, running cost, switching effort).\n"
        f"- NEVER state a purchase probability, a '% would buy', or any buy/validation verdict.\n"
        f"  Surface objections, conditions, confusion, and qualitative willingness ONLY.\n"
        f"- If you need a real SA cost to reason properly and it is NOT in the WORLD FACTS or\n"
        f"  YOUR REAL NUMBERS above, do NOT invent a figure. Instead name what you need in the\n"
        f"  'needed_fact' field (e.g. 'petrol price per litre', 'cost of 1GB data') and reason\n"
        f"  qualitatively without a number. Never state a rand amount you are not sure of.\n"
        f"- In your JSON, ALSO include an 'economic' object with these fields, reflecting your\n"
        f"  stance AFTER this round (keep prior values if unchanged):\n"
        f'  "economic": {{"impulse": 0.0-1.0, "perceived_cost": "...", "willingness_band": "...", '
        f'"primary_objection": "...", "reconsider_condition": "...", "needed_fact": "..."}}\n'
        f"  'impulse' is how much you WANT to spend on it right now (0 = no desire, 1 = strong pull\n"
        f"  to spend) — it is DESIRE, NOT a prediction that you will buy. Be honest: you can have\n"
        f"  high impulse and still be unable to afford it. 'needed_fact' is \"\" unless you genuinely\n"
        f"  needed a cost that wasn't provided.\n"
    )


PRODUCT_PITCH_EXTRACTION_SYSTEM = (
    "You extract a structured product pitch from a South African product/launch document "
    "for a market stress-test. Return ONLY a JSON object. Do not invent specifics that are "
    "not implied by the document; use null-ish phrasing like 'not stated' when unknown."
)


def build_pitch_announcement(pitch: Dict[str, Any], short: bool = False) -> str:
    """Build the founder's spoken announcement of the pitch, for posting into the room.

    Product mode: posted as a founder message at round 0 (and as a shorter reminder
    on re-anchor rounds) so agents respond directly TO the pitch rather than only
    marinating in it as background context.

    This is the founder DESCRIBING their product — never a buy solicitation. It must
    not ask "would you buy this?" or imply a purchase verdict (product honesty rule).
    """
    what = (pitch.get("what_it_is") or "").strip()
    pricing = (pitch.get("pricing") or "").strip()
    problem = (pitch.get("problem_solved") or "").strip()

    if not what:
        what = "our product"

    if short:
        # Re-anchor reminder: keep it to the core so the room re-centres on the pitch
        # without re-stating everything. "still on the table" framing, not a nudge to
        # stay positive — agents are free to keep objecting.
        line = f"Reminder — the pitch still on the table: {what}."
        if pricing and pricing.lower() not in ("not stated", "pricing is unclear / not stated"):
            line += f" ({pricing})"
        return line

    parts = [f"I'm putting {what} in front of you."]
    if problem and "unclear" not in problem.lower():
        parts.append(f"It's meant to {problem.rstrip('.').lower()}.")
    if pricing and pricing.lower() not in ("not stated", "pricing is unclear / not stated"):
        parts.append(f"Pricing: {pricing}.")
    parts.append("I want your honest reaction — what works, what doesn't, what would put you off.")
    return " ".join(parts)


def build_pitch_extraction_prompt(document_context: str, requirement: str) -> str:
    """One-shot prompt to derive the pitch object from the document at startup."""
    ctx = (document_context or "")[:6000]
    req = (requirement or "")[:1500]
    return f"""From the product document and simulation requirement below, extract the pitch
that a South African market will react to. Be concrete but do NOT fabricate facts the
document does not support.

SIMULATION REQUIREMENT:
{req}

DOCUMENT CONTEXT:
{ctx}

Return ONLY this JSON object (single line per value, no markdown):
{{
  "what_it_is": "1 sentence: what the product actually is",
  "pricing": "the price / pricing model in rands if stated, else 'not stated'",
  "problem_solved": "1 sentence: the problem it claims to solve",
  "status_quo_alternative": "how South Africans solve this problem TODAY without it"
}}"""
