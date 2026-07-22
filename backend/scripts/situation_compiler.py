"""Situation compiler — deterministic, LLM-free.

Compiles a persona record's surveyed economics into 1-3 sentences of LIVED
CIRCUMSTANCE (money rhythm + obligations) for the invisible-numbers pilot.
Spec: docs/INVISIBLE_NUMBERS_PILOT.md.

Hard constraints enforced by test_situation_compiler.py:
  - no numeric tokens anywhere in the output (the price lives only in the
    pitch; mapping it onto one's life is the behaviour under observation)
  - situation only, never decision style (how the persona weighs a new cost
    is what we measure; the compiler must not inject the answer)
  - referents licensed by survey fields only (grant / digital access / school
    costs; food+transport universals never carry prices)
  - COMPILER vocabulary and CLASSIFIER_MARKERS are disjoint (anti-circularity)
"""

import re

# ---------------------------------------------------------------------------
# Normalization (shared with the scorer — keep identical semantics)
# ---------------------------------------------------------------------------

_PUNCT = re.compile(r"[^\w\s]")
_DIGITS = re.compile(r"\d+")
_SPACES = re.compile(r"\s+")


def normalize(text):
    """lowercase, strip digits, punctuation->space, collapse spaces."""
    t = (text or "").lower()
    t = _DIGITS.sub(" ", t)
    t = _PUNCT.sub(" ", t)
    return _SPACES.sub(" ", t).strip()


# ---------------------------------------------------------------------------
# Tier + role resolution
# ---------------------------------------------------------------------------

TIERS = ("tight", "moderate", "loose")


def naive_income_band(income):
    """Income-only tier banding. Reproduces all 12 recorded tiers on the
    panel_07eb044c9c55 cast; the agreement test pins that."""
    if income is None:
        raise ValueError("no income and no recorded tier")
    inc = float(income)
    if inc < 5000:
        return "tight"
    if inc < 20000:
        return "moderate"
    return "loose"


def tier_of(profile):
    tier = (profile.get("budget_tier") or "").strip().lower()
    if tier:
        if tier not in TIERS:
            raise ValueError("unknown budget_tier: %r" % tier)
        return tier
    return naive_income_band(profile.get("monthly_household_income_rand"))


def role_of(profile):
    arch = (profile.get("actor_archetype") or "").strip().lower()
    if arch in ("guardian_parent", "gogo_guardian"):
        return "guardian"
    if arch == "learner":
        return "learner"
    raise ValueError("no role template for archetype: %r" % arch)


# ---------------------------------------------------------------------------
# Templates — money rhythm per (role, tier). Situation, never decision style.
# {obligations} is filled from licensed referents.
# ---------------------------------------------------------------------------

RHYTHM = {
    ("guardian", "tight"):
        "Money comes into your home once a month and most of it is spoken for "
        "in the first week — {obligations} — and by the last week of the month "
        "there is little left to move around.",
    ("guardian", "moderate"):
        "Your home gets through most months, but there is no room for "
        "surprises — {obligations} take up what comes in, and anything "
        "unplanned means borrowing or holding off until the month turns.",
    ("guardian", "loose"):
        "Your home does not watch the calendar for money — {obligations} and "
        "the monthly debit orders are covered, with room to spare.",
    ("learner", "tight"):
        "In your home, money is counted before the month begins — "
        "{obligations} first — and by the last week there is little left, so "
        "what you need often has to wait for the month to turn.",
    ("learner", "moderate"):
        "Your home manages most months, but surprises cause trouble — "
        "{obligations} take up what comes in, and when something runs out "
        "early, everyone feels it.",
    ("learner", "loose"):
        "Money is not a daily topic in your home — {obligations} and the "
        "monthly costs are handled without counting, and when you need "
        "something, the answer is about whether it makes sense, not about the "
        "week of the month.",
}

GRANT_LINE = "A grant is part of what carries your home through the month."
DIGITAL_PHONE_LINE = "The phone is how your home goes online; data is bought as it is needed."
DIGITAL_COMPUTER_LINE = "Your home has a computer and an internet connection."


def _bands(profile):
    out = []
    fb = profile.get("fees_band")
    if isinstance(fb, str) and fb:
        out.append(fb)
    lb = profile.get("learner_fee_bands")
    if isinstance(lb, (list, tuple)):
        out.extend(b for b in lb if b)
    elif isinstance(lb, str) and lb:
        out.append(lb)
    return out


def has_paid_fees(profile):
    """Any paid band licenses the 'school things' referent. Mojibake-tolerant:
    only the literal 'No fees' marker is compared, never the en-dash."""
    return any(b.strip().lower() != "no fees" for b in _bands(profile))


def _obligations(profile, role):
    parts = ["food", "transport"]
    if has_paid_fees(profile) or role == "learner" or profile.get("learners_in_household"):
        parts.append("school things")
    return ", ".join(parts[:-1]) + " and " + parts[-1]


# v2 templates: ONLY the loose rhythm is rewritten (run 1 showed the loose
# block did not differentiate; tight/moderate worked and stay frozen).
# Loose v2 shows surplus concretely — things replaced before they break,
# school chosen on fit — instead of the abstract "does not watch the
# calendar". Disjoint from CLASSIFIER_MARKERS_V2 (tested).
RHYTHM_V2_OVERRIDES = {
    ("guardian", "loose"):
        "In your home, a broken appliance is replaced before it becomes a "
        "crisis, and the school was chosen for what it offers, not for what "
        "it charges — {obligations} and the monthly debit orders go through "
        "without being tallied.",
    ("learner", "loose"):
        "When you need something for school in your home, the question is "
        "what it will do for you, not what week of the month it is — "
        "{obligations} and the monthly costs are handled without counting.",
}


def compile_situation(profile, version=1):
    """Persona record -> 1-3 sentences of lived circumstance. Number-free.
    version=1: run-1 blocks (frozen). version=2: loose-rhythm overrides."""
    tier = tier_of(profile)
    role = role_of(profile)
    tpl = RHYTHM_V2_OVERRIDES.get((role, tier), None) if version == 2 else None
    tpl = tpl or RHYTHM[(role, tier)]
    lines = [tpl.format(obligations=_obligations(profile, role))]
    if profile.get("receives_grant"):
        lines.append(GRANT_LINE)
    if profile.get("computer_in_home"):
        lines.append(DIGITAL_COMPUTER_LINE)
    elif profile.get("internet_at_home"):
        lines.append(DIGITAL_PHONE_LINE)
    return " ".join(lines)


# ---------------------------------------------------------------------------
# Frozen lexicons (spec: docs/INVISIBLE_NUMBERS_PILOT.md)
# ---------------------------------------------------------------------------

def compiler_vocabulary(version=None):
    """Every normalized token the compiler can emit (templates are fixed).
    version=1 -> v1 templates only; version=2 -> v2 effective templates;
    None -> the union across all versions (safest for disjointness)."""
    texts = []
    for key, tpl in RHYTHM.items():
        variants = [tpl]
        if version != 1 and key in RHYTHM_V2_OVERRIDES:
            variants = [RHYTHM_V2_OVERRIDES[key]] if version == 2 else variants + [RHYTHM_V2_OVERRIDES[key]]
        for v in variants:
            for oblig in ("food and transport", "food, transport and school things"):
                texts.append(v.format(obligations=oblig))
    texts += [GRANT_LINE, DIGITAL_PHONE_LINE, DIGITAL_COMPUTER_LINE]
    vocab = set()
    for t in texts:
        vocab.update(normalize(t).split())
    return vocab


# CLASSIFIER_MARKERS — curated ONLY from production calibration language
# (panel_07eb044c9c55 + panel_39692ef06a7c round 1). Never from the templates
# above. Multi-word markers match as substrings of normalized text;
# single-word markers match on word boundaries. Frozen before B/C/D output.
CLASSIFIER_MARKERS = {
    "tight": [
        "impossible",
        "out of the question",
        "too expensive",
        "barely",
        "just to get by",
        "struggling to cover",
        "cover the basics",
        "can't afford",
        "cannot afford",
    ],
    "moderate": [
        "stretch",
        "every rand",
        "every cent",
        "watching every",
        "guarantee",
        "guaranteed",
        "can't risk",
        "cannot risk",
        "a lot when",
        "too much for us",
    ],
    "loose": [
        "negligible",
        "not the issue",
        "isn't the issue",
        "affordability isn't",
        "not the barrier",
        "isn't the barrier",
        "cost isn't",
        "before i commit",
    ],
}

# CLASSIFIER_MARKERS_V2 — frozen for run 2 (2026-07-17), BEFORE run-2 output
# exists. v1 markers retained verbatim; additions curated ONLY from run-1's
# A-condition (production channel) under the rule: >=2 occurrences within one
# tier, 0 in the other tiers, across the 36 A responses. Rejected by the rule
# despite face validity: "pocket change", "a drop in the ocean" (single
# occurrence each). Provenance: docs/INVISIBLE_NUMBERS_PILOT.md addendum.
CLASSIFIER_MARKERS_V2 = {
    "tight": list(CLASSIFIER_MARKERS["tight"]),
    "moderate": CLASSIFIER_MARKERS["moderate"] + [
        "no sense",
        "gamble",
        "upfront",
        "risk",
    ],
    "loose": CLASSIFIER_MARKERS["loose"] + [
        "easily afford",
        "easily affordable",
        "gimmick",
        "gimmicky",
        "bribe",
        "bribing",
        "gamify",
        "gamified",
        "gamifying",
    ],
}
