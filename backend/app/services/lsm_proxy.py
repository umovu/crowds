"""
LSM proxy scorer — living-standard band from household assets.

Real LSM (SAARF/AMPS) is a checklist of household things, not an income measure.
Our personas already carry those things, so we score them directly. This is a
*proxy*: it approximates official LSM from 8 signals, it does not reproduce it.
Say "proxy" everywhere it surfaces to a client.

This module is pure. Persona dict in, {score, band, confidence} out. No file
reads, no network, no model calls. That is deliberate — the whole thing must be
assertable with the LLM switched off (see CLAUDE.md, product-mode economy rules).

Rubric (version 3, tested against all 297 personas — see local plan doc):

    owns_vehicle          own +4      household +2
    owns_computer         own +3      household +2
    owns_bank_account     own or household +2
    owns_television       own or household +1
    internet_use          daily +2    weekly +1
    geotype               Urban +1
    electricity_reliability   always or most +1
                                                     asset max 14

    lived_poverty brake   none +3   low +1   moderate -1   high -3
                                        (absolute max score: 17)

    bands   <=4 Band 1 - Going without | 5-8 Band 2 - Getting by
            9-12 Band 3 - Steady        | 13+ Band 4 - Comfortable

The numbering is ours, not LSM's. Real LSM runs 1-10 off a ~14-signal checklist
including water in the home, a flushing toilet and a domestic worker - none of
which our personas carry. We score 8 signals, so we borrow no acronym.

Missing values score zero, never guessed. Cutoffs are a house judgement tuned so
the spread stopped being top-heavy; they are not calibrated against a published
national distribution. Challenge a number here, that is what this table is for.

Version 2.1 clamped grant_dependent_survivor personas below Comfortable. That cap
was removed in version 3: the 5 personas it targeted are asset-rich people who are
not working, not data errors. Archetype and band disagreeing is information.
"""

from __future__ import annotations

from typing import Dict, List, Optional

# Fields filled by donor matching, in the persona's `circumstances` list. Used
# for confidence — geotype is top-level and not donor-matched, so it is absent.
DONOR_FIELDS = (
    "lived_poverty",
    "owns_vehicle",
    "owns_computer",
    "owns_bank_account",
    "owns_television",
    "internet_use",
    "electricity_reliability",
)

BAND_1 = "Band 1 — Going without"
BAND_2 = "Band 2 — Getting by"
BAND_3 = "Band 3 — Steady"
BAND_4 = "Band 4 — Comfortable"

BANDS = (BAND_1, BAND_2, BAND_3, BAND_4)

# Client-facing wording. Every claim below is a measured share of the personas in
# that band, not a mood word - so a client can check it against a card on screen.
# "Goes without" is Afrobarometer's lived-poverty question: how often in the past
# year the household ran out of food, clean water, medicine or medical care,
# cooking fuel, or cash income. We hold only the rolled-up level, never which of
# the five it was, so never name a specific item in this copy.
BAND_MEANING = {
    BAND_1: (
        "No car and no computer, and money runs out often. 98% own neither. "
        "95% went without basics more than once or twice this year."
    ),
    BAND_2: (
        "A TV and a bank account, sometimes a shared computer, rarely their own "
        "car. Only 10% own a car. Two thirds still go short."
    ),
    BAND_3: (
        "A car or a computer in the household, usually online daily. 54% own a "
        "computer. Just under half still go short some months."
    ),
    BAND_4: (
        "Owns both a car and a computer. All have a TV and a bank account, and "
        "94% rarely or never go without."
    ),
}

_VEHICLE_POINTS = {"own": 4, "household": 2}
_COMPUTER_POINTS = {"own": 3, "household": 2}
_INTERNET_POINTS = {"daily": 2, "weekly": 1}
_POVERTY_POINTS = {"none": 3, "low": 1, "moderate": -1, "high": -3}


def _circumstances(persona: Dict) -> Dict[str, Dict]:
    """Flatten the circumstances list into {field: record}.

    Assets are NOT top-level persona keys. They live as records shaped
    {"field": ..., "value": ..., "source": ..., "match_quality": ...}.
    """
    out: Dict[str, Dict] = {}
    for record in persona.get("circumstances") or []:
        if isinstance(record, dict) and record.get("field"):
            out[record["field"]] = record
    return out


def _confidence(records: Dict[str, Dict]) -> str:
    """How many donor-filled fields matched exactly. Never affects the score."""
    exact = sum(
        1
        for field in DONOR_FIELDS
        if (records.get(field) or {}).get("match_quality") == "exact"
    )
    if exact == len(DONOR_FIELDS):
        return "high"
    if exact >= 4:
        return "medium"
    return "low"


def band_for_score(score: int) -> str:
    if score <= 4:
        return BAND_1
    if score <= 8:
        return BAND_2
    if score <= 12:
        return BAND_3
    return BAND_4


def score_persona(persona: Dict) -> Dict:
    """Score one persona. Returns {score, band, band_meaning, confidence}."""
    records = _circumstances(persona)

    def value(field: str) -> Optional[str]:
        return (records.get(field) or {}).get("value")

    score = 0
    score += _VEHICLE_POINTS.get(value("owns_vehicle"), 0)
    score += _COMPUTER_POINTS.get(value("owns_computer"), 0)
    if value("owns_bank_account") in ("own", "household"):
        score += 2
    if value("owns_television") in ("own", "household"):
        score += 1
    score += _INTERNET_POINTS.get(value("internet_use"), 0)
    if persona.get("geotype") == "Urban":
        score += 1
    if value("electricity_reliability") in ("always", "most"):
        score += 1
    score += _POVERTY_POINTS.get(value("lived_poverty"), 0)

    band = band_for_score(score)
    return {
        "score": score,
        "band": band,
        "band_meaning": BAND_MEANING[band],
        "confidence": _confidence(records),
    }


def band_counts(personas: List[Dict]) -> Dict[str, int]:
    """Band histogram for a set of personas, in band order. For the UI picker."""
    counts = {band: 0 for band in BANDS}
    for persona in personas:
        scored = persona.get("lsm_proxy") or score_persona(persona)
        band = scored.get("band")
        if band in counts:
            counts[band] += 1
    return counts
