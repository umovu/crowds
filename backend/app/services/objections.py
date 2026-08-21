"""Deterministic objection-type classifier — LLM-free, and deliberately so.

What a persona OBJECTS TO is a fact about the text they produced, not a second
opinion to ask a model for. Keeping this a keyword matcher means the fit card's
"how many hit the same wall" number can be asserted in a test with the LLM
switched off, which is the bar every economic/fit number in this repo has to
clear.

Mention-based, like the benchmark report it came from: it detects what a
response TALKS ABOUT, not how it feels about it. A response mentioning "branch"
raises `no_human_support` whether it wants one or is glad to skip it. That is a
known, accepted imprecision — the signal is "this is the axis this room keeps
returning to", which is what the user needs in order to pick the next room.

`backend/scripts/classify_objections.py` is a CLI over this module, so the
benchmark and the product score the same way.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

# Stable order — the UI's tie-break and the benchmark table's row order.
OBJECTION_TYPES: Tuple[str, ...] = (
    "no_human_support",
    "digital_capability",
    "identity_biometric",
    "fee_sensitivity",
    "cost_of_access",
    "trust_social_proof",
    "interest_scepticism",
    "trust_authority",
)

# What each type is called on screen. Written as the wall the room hit, in the
# words a founder would use — never the internal id.
LABELS: Dict[str, str] = {
    "no_human_support": "No one to talk to when it goes wrong",
    "digital_capability": "Phone, data or power gets in the way",
    "identity_biometric": "Uneasy about ID and fingerprints",
    "fee_sensitivity": "Watching the fees and charges",
    "cost_of_access": "Costs something just to reach it",
    "trust_social_proof": "Wants proof before believing it",
    "interest_scepticism": "The returns sound too good",
    "trust_authority": "Doesn't trust who's behind it",
}

# Keyword vocab. Order within a type doesn't matter — first hit wins per type.
VOCAB: Dict[str, List[str]] = {
    "no_human_support": [
        "branch", "teller", "real person", "real people", "human", "staff",
        "speak to", "talk to", "someone", "office", "face-to-face",
        "face to face", "counter", "point of contact", "recourse",
        "recover", "gladly pay extra",
    ],
    "digital_capability": [
        "internet", "data", "smartphone", "screen", "network", "airtime",
        "bundle", "battery", "buttons", "computer", "load-shedding",
        "load shedding", "offline", "power", "glitch", "never used the internet",
    ],
    "identity_biometric": [
        "fingerprint", "biometric", "thumbprint", "finger print", "scanned",
        "scanning", "scan", "my finger", "identity document", "id card",
    ],
    "fee_sensitivity": [
        "fee", "fees", "charge", "charges", "hidden", "admin", "monthly fee",
        "free", "no monthly", "cost", "bank charges", "rand",
    ],
    "cost_of_access": [
        "transport", "taxi", "fare", "fares", "trip", "travel", "travelling",
        "walk", "walking", "distance", "commute",
    ],
    "trust_social_proof": [
        "trust", "proof", "promise", "promises", "promising", "wary", "scam",
        "too good", "heard", "neighbour", "neighbor", "reliab", "proven",
        "waiting to see", "show me", "convince", "reputation",
    ],
    "interest_scepticism": [
        "interest", "return", "yield", "rate", "10%", "ten per cent",
        "ten percent", "too good to be true", "lure", "payout", "lucrative",
    ],
    "trust_authority": [
        "government", "minister", "corruption", "corrupt", "stole", "stolen",
        "official", "officials", "municipal", "parliament", "legislature",
        "politician", "public money", "state", "authority", "councillor",
    ],
}

# A response reading as a satisfiable condition ("if you do X, I would") is a
# different product signal from a flat refusal — a condition names the change
# that would win the room. Unmatched text counts as a dealbreaker: the honest
# default is that we did NOT hear a condition, not that we heard one.
_CONDITION_MARKERS = (
    "only if", "unless", "if you can", "if the", "if there", "if that",
    "if it", "provided", "as long as", "so long as", "once", "until",
    "if you prove", "if you show", "when the", "if i", "if my",
)


def classify(text: str) -> List[str]:
    """Objection types this one response raises, in OBJECTION_TYPES order."""
    if not text:
        return []
    lower = text.lower()
    return [
        otype for otype in OBJECTION_TYPES
        if any(word in lower for word in VOCAB[otype])
    ]


def tally(responses: List[str]) -> Dict[str, int]:
    """How many of these responses raise each objection type.

    Only types that actually appear are keys — a zero row carries no signal and
    would just pad the fit card.
    """
    counts: Dict[str, int] = {}
    for text in responses:
        for otype in classify(text):
            counts[otype] = counts.get(otype, 0) + 1
    return counts


def top(responses: List[str], limit: int = 3) -> List[Dict[str, object]]:
    """The objections this room kept returning to, most-raised first.

    Returns `[{"id", "label", "count"}]`. Ties break on OBJECTION_TYPES order so
    the same round always renders the same card.
    """
    counts = tally(responses)
    order = {otype: i for i, otype in enumerate(OBJECTION_TYPES)}
    ranked = sorted(counts, key=lambda t: (-counts[t], order[t]))
    return [
        {"id": t, "label": LABELS[t], "count": counts[t]}
        for t in ranked[:limit]
    ]


def is_condition(text: str) -> bool:
    """True when the response frames its objection as a condition to satisfy."""
    if not text:
        return False
    lower = text.lower()
    return any(marker in lower for marker in _CONDITION_MARKERS)
