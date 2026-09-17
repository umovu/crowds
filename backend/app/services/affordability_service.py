"""Price → who could afford it. Deterministic, with the model switched off.

The affordability lens is NOT a user control: hand-picking who can pay lets an
operator stack the room and call the result evidence. Instead the price stated in the
operator's own pitch decides it, and the picker shows what was done so it can be
switched off. Every function here is pure — same pitch, same number, every time — and
is asserted with the LLM off (tests/test_price_affordability.py).

The LLM `pricing` field in mode_specs is deliberately NOT used here: an economic
filter must not depend on a model's re-reading of the text.

"Can afford it" is a floor computed from real income. "Wants it" is a separate,
qualitative question the interview answers. They never collapse into one number, and
nothing here produces a purchase probability.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

BUDGET_TIERS = ("tight", "moderate", "loose")

# Once-off rand thresholds. A price at or above the cut needs at least that tier.
_ONCE_OFF_CUTS = ((15000, "loose"), (2000, "moderate"))
# Monthly commitments bite harder per rand — a R900/month subscription is a
# bigger ask than a R900 once-off, because it recurs.
_MONTHLY_CUTS = ((800, "loose"), (150, "moderate"))

# R40 000 / R40,000 / R40000 / R199.99, optionally followed by a recurrence
# ("/month", "per month", "pm", "p.m."). Only the operator's own digits are read.
_PRICE_RE = re.compile(
    r"R\s?(\d{1,3}(?:[\s, ]\d{3})+|\d+(?:\.\d{2})?)"
    # The recurrence tail. "R2 500 a month" and "R2 500 monthly" are as common in
    # a pitch as "/month"; without them a subscription priced as a once-off, and
    # the derived room came out wider than the stated price allows.
    r"(\s*(?:/|\bper\b|\ba\b|\bevery\b|\bp\.?m\.?\b)\s*(?:month|mo\b|year|yr\b|annum)?"
    r"|\s*\bmonthly\b)?",
    re.IGNORECASE,
)
_MONTHLY_RE = re.compile(r"month|monthly|/\s*mo\b|\bp\.?m\.?\b", re.IGNORECASE)

# Money the pitch OFFERS the person — a loan, grant, subsidy, bursary, prize or
# salary — is not a price they must find. Read as one, "loans of up to R50,000"
# priced a township product out of reach of everyone it was for, and the room
# came back all well-off. Checked in the words just before the figure.
_INBOUND_MONEY_RE = re.compile(
    r"\b(loan|loans|grant|grants|subsidy|subsidised|subsidized|bursary|bursaries|"
    r"stipend|salary|salaries|wage|wages|payout|prize|funding|rebate|refund|"
    r"credit|financing|compensation|pension)\b[^.]{0,40}$",
    re.IGNORECASE,
)


def parse_price(pitch: str) -> Optional[Dict[str, Any]]:
    """The largest rand figure stated in the pitch, and whether it recurs.

    Pure text match over the operator's OWN words — it cannot invent a number,
    only find one. Returns None when the pitch states no price, in which case no
    affordability filter runs at all.
    """
    best: Optional[Dict[str, Any]] = None
    for m in _PRICE_RE.finditer(pitch or ""):
        if _INBOUND_MONEY_RE.search((pitch or "")[:m.start()]):
            continue  # money offered to them, not a price they pay
        amount = float(re.sub(r"[\s, ]", "", m.group(1)))
        monthly = bool(_MONTHLY_RE.search(m.group(2) or ""))
        if best is None or amount > best["amount"]:
            best = {"amount": amount, "monthly": monthly}
    return best


def price_to_tiers(amount: float, monthly: bool = False) -> List[str]:
    """Budget tiers whose income could absorb this price, cheapest tier first.

    Says who COULD pay, never who would — wanting it stays a separate,
    qualitative question the interview answers.
    """
    cuts = _MONTHLY_CUTS if monthly else _ONCE_OFF_CUTS
    for cut, floor in cuts:
        if amount >= cut:
            return list(BUDGET_TIERS[BUDGET_TIERS.index(floor):])
    return list(BUDGET_TIERS)


def derive_budget_tiers(pitch: str) -> Optional[Dict[str, Any]]:
    """Affordability lens read off the pitch, or None when no price is stated."""
    price = parse_price(pitch)
    if not price:
        return None
    tiers = price_to_tiers(price["amount"], price["monthly"])
    if set(tiers) == set(BUDGET_TIERS):
        return None  # everyone qualifies — no filter, nothing to explain
    return {"amount": price["amount"], "monthly": price["monthly"], "tiers": tiers}
