"""
Mode specs — product-mode runtime economics for the simulation.

NOTE: LLM persona *generation* has been removed (personas are never authored by an
LLM — curated library first, custom second; see CLAUDE.md). What remains here is the
product-mode RUNTIME lens: the deterministic budget/affordability machinery and the
per-round economic-reasoning block injected into the opinion prompt. The LLM animates
grounded personas; it never invents them.

Honesty constraint (hard rule): product mode surfaces *reactions and reasoning*,
never a demand/validation verdict — no "% would buy", no purchase probability, no
score that reads as market validation. "Wants it" (LLM impulse) and "can afford it"
(deterministic budget_tier, computed only from real persona data) stay separate.
"""

from typing import Any, Dict, Optional


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
        f"- If you need a real SA cost to reason properly and it is NOT in YOUR REAL NUMBERS\n"
        f"  above, do NOT invent a figure. Instead name what you need in the 'needed_fact'\n"
        f"  field (e.g. 'petrol price per litre', 'cost of 1GB data') and reason qualitatively\n"
        f"  without a number. Never state a rand amount you are not sure of.\n"
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
