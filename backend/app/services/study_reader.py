"""study_reader — deterministic pre-processor behind the confirmation chips.

Reads one plain sentence (what the user typed) and derives the structured
study spec the chips approve: what's being tested, the mode, the audience,
the price, and the probes to ask the panel.

Pure string + keyword logic. No LLM, no I/O — every function is unit-testable
with the model switched off. This is a structural pre-processing step, not a
chat: nothing here authors identity or budget numbers (persona rule), it only
labels what the sentence did or didn't say (confidence rule below).

Confidence rule (Option B, deterministic): a field is *strong-data* when it
came directly from the sentence, and *thin-data* when it was inferred,
assumed, or defaulted. Never a model's own certainty.
"""

import re

from .mode_detector import detect as _detect_mode
from . import panel_service

# --- Price ---------------------------------------------------------------

_PRICE_RE = re.compile(
    r"\bR\s?\d[\d\s,.]*(?:\.\d{1,2})?"
    r"(?:\s*(?:(?:/|per|a|each)\s*(?:month|week|year|annum)|\bonce\b(?:\s*off)?))?",
    re.IGNORECASE,
)


def find_price(text: str) -> str:
    """First price token, normalised ("R 50 a month" -> "R50/month"). None when
    the sentence states no price. A price is a literal, never inferred."""
    text = text or ""
    m = _PRICE_RE.search(text)
    if not m:
        return None
    return _normalize_price(m.group(0))


def _normalize_price(raw: str) -> str:
    s = " ".join(raw.split()).strip()
    body = s[1:].lstrip()  # everything after the R
    amount = re.match(r"[\d\s,]+(?:\.\d{1,2})?", body)
    if not amount:
        return s
    amount_txt = re.sub(r"\s+", "", amount.group(0))
    rest = body[len(amount.group(0)):]
    rest = re.sub(r"\b(per|a|each)\b", "/", rest, flags=re.IGNORECASE)
    rest = "".join(rest.split()).strip("/")
    return f"R{amount_txt}" if not rest else f"R{amount_txt}/{rest}"


# --- Probes --------------------------------------------------------------

BASE_PROBE = {
    "id": "reaction",
    "label": "First reaction",
    "question": "What's your honest first reaction?",
    "base": True,
    "confidence": "strong-data",
    "active": True,
}

# Themes are matched by keyword against the sentence. A matched theme is a
# strong-data probe (it came from the sentence); a fallback probe is thin-data.
PROBE_THEMES = {
    "trust": {
        "label": "Trust",
        "keywords": ("trust", "trustworthy", "believe", "scam", "legit", "genuine",
                     "hidden fees", "fine print", "secure", "security", "suspicious"),
        "questions": {
            "land": "What would make you trust or distrust it?",
            "breaks": "What would make you distrust it enough to say no?",
            "fit": "How much does trust in the messenger decide who this lands with?",
            "ab": "Which wording earns more trust?",
        },
    },
    "money": {
        "label": "Price / affordability",
        "keywords": ("price", "pricing", "cost", "afford", "fee", "fees", "budget",
                     "salary", "wage", "subscription", "free tier", "willing to pay",
                     "r/", "/month", "per month", "a month"),
        "questions": {
            "land": "Could you afford it, and would it be worth it?",
            "breaks": "What makes it unaffordable or bad value to you?",
            "fit": "Who could actually afford this?",
            "ab": "Which version makes the price feel fairer?",
        },
    },
    "effort": {
        "label": "What changes for them",
        "keywords": ("have to", "switch", "sign up", "give up", "require", "paperwork",
                     "means", "onboarding", "set up", "effort"),
        "questions": {
            "land": "What would you have to do, pay, or give up to go along with it?",
            "breaks": "What's the extra cost or hassle that would push you away?",
            "fit": "Who will tolerate the change, and who won't?",
            "ab": "Which version makes the change sound easier?",
        },
    },
    "fairness": {
        "label": "Fairness",
        "keywords": ("fair", "unfair", "favour", "favour some", "only some", "exclude",
                     "excluded", "treated", "everyone gets", "privilege"),
        "questions": {
            "land": "Does this feel fair to you and people like you?",
            "breaks": "Who does this leave out or treat unfairly?",
            "fit": "Does this land differently across groups?",
            "ab": "Which version sounds fairer to a wider group?",
        },
    },
    "risk": {
        "label": "Worries",
        "keywords": ("worry", "worried", "afraid", "risk", "danger", "lose", "losing",
                     "scared", "anxious", "what could go wrong"),
        "questions": {
            "land": "What are you worried could go wrong?",
            "breaks": "What's the worst that could happen if you went along with it?",
            "fit": "Which group carries the most risk if this goes wrong?",
            "ab": "Which version feels riskier?",
        },
    },
}

LENS_FALLBACK_PROBES = {
    "land": [
        {"id": "assume", "label": "First impression",
         "question": "What's the first thing you'd assume about it?"},
    ],
    "breaks": [
        {"id": "dealbreaker", "label": "Deal-breaker",
         "question": "What's the biggest thing that would stop you?"},
    ],
    "fit": [
        {"id": "who", "label": "Who it's for",
         "question": "Who is this for, and who can't use it?"},
    ],
    "ab": [
        {"id": "verdict", "label": "Which version",
         "question": "Which version convinces you, and why?"},
    ],
}


def infer_probes(text: str, lens: str = "land") -> list:
    """The probe set for the run, derived from the sentence.

    The base reaction probe is always present and not toggleable (it IS the
    run). Matched themes become toggleable, strong-data probes. When nothing
    matches, a lens-appropriate fallback probe carries the read (thin-data).
    """
    belt = (text or "").lower()
    probes = [dict(BASE_PROBE)]
    matched = False
    for theme_id, spec in PROBE_THEMES.items():
        if any(kw in belt for kw in spec["keywords"]):
            probes.append({
                "id": theme_id,
                "label": spec["label"],
                "question": spec["questions"].get(lens, spec["questions"]["land"]),
                "confidence": "strong-data",
                "active": True,
            })
            matched = True
    if not matched:
        for fb in LENS_FALLBACK_PROBES.get(lens, LENS_FALLBACK_PROBES["land"]):
            probes.append({
                **fb,
                "base": False,
                "confidence": "thin-data",
                "active": True,
            })
    return probes


# --- The read --------------------------------------------------------------

def _lead_line(text: str) -> str:
    """The short label the chips show for what's being tested."""
    line = ""
    for ln in (text or "").splitlines():
        body = ln.strip()
        if body:
            line = body
            break
    line = re.sub(r"\s+", " ", line)
    return line if len(line) <= 140 else line[:137] + "…"


def _infer_worry(probes: list) -> str:
    """The single concern the summary should address, or None.

    Taken from the strongest strong-data probe (it came from the sentence).
    Anything thin-data or absent yields None — no invented worry.
    """
    for p in probes:
        if p.get("confidence") == "strong-data" and not p.get("base") and p.get("active"):
            return p["label"]
    return None


def read_study(text: str, lens: str = "land") -> dict:
    """One sentence -> the structured study spec the chips approve."""
    text = (text or "").strip()
    mode_info = _detect_mode(text)
    mode = mode_info.get("mode", "product")
    suggested = panel_service.suggest_segments(text, cap=2)
    probes = infer_probes(text, lens)
    return {
        "lens": lens,
        "what": _lead_line(text),
        "mode": mode,
        "mode_confidence": mode_info.get("confidence", "thin"),
        "price": find_price(text) if mode == "product" else None,
        "worry": _infer_worry(probes),
        "audience": {
            "segments": suggested,
            "confidence": "strong-data" if suggested else "thin-data",
        },
        "probes": probes,
    }