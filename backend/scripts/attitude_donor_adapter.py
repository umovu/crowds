"""
attitude_donor_adapter — decode a raw attitudinal-survey dataset into donor records
expressed in the SAME vocabulary AgentProfile/QLFS uses, so the fuser can match on
shared demographic keys.

This is the ONE dataset-specific file in the fusion stage. The fuser
(attitude_fuser.py) is dataset-agnostic and only ever sees the normalized donor
records this module yields. Sourcing a different survey later (SASAS, Afrobarometer
R10) = writing a second adapter here, nothing downstream changes.

A donor record is a dict with:
  * the shared JOIN KEYS, decoded to AgentProfile vocabulary:
      gender              — "Female" / "Male"        (matches QLFS Q13GENDER)
      province            — one of SA_PROVINCES        (matches QLFS Province)
      education_band      — "primary"|"secondary"|"tertiary"|"none"
      employment_status   — "Employed"|"Unemployed"|"Other not economically active"|...
      age_band            — "15-29"|"30-44"|"45-59"|"60+"
  * "weight": float survey weight (so donor marginals are population-correct)
  * "attitudes": dict over the fixed ATTITUDE_VOCAB (the behavior we IMPORT)

Until the licensed Afrobarometer microdata is in hand, the default loader reads a
synthetic fixture of the exact same shape, so the whole fuser + validator can be
built and tested with the LLM off and no licensed data. Swapping in the real file
means implementing load_afrobarometer() over the .sav/.dta and pointing
load_donors() at it.

LLM-free. Deterministic.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_SYNTHETIC_PATH = os.path.join(
    _HERE, "..", "data", "microdata", "attitudes", "synthetic_donor.json"
)

# The fixed attitude vocabulary the library standardises on. The fuser imports these
# verbatim; the validator asserts every donor and every fused persona only uses these.
# Ordinal scales are listed low→high so a future numeric mapping is unambiguous.
ATTITUDE_VOCAB: Dict[str, List[str]] = {
    "gov_trust": ["low", "mid", "high"],
    "economic_optimism": ["pessimistic", "neutral", "optimistic"],
    "service_satisfaction": ["dissatisfied", "mixed", "satisfied"],
    "crime_fear": ["low", "mid", "high"],
    "education_satisfaction": ["dissatisfied", "mixed", "satisfied"],
    # ── policy-mode ────────────────────────────────────────────────────────────
    # Political efficacy: does engaging with the state achieve anything. Predicts
    # whether a persona petitions, protests, or disengages — the mechanism policy
    # simulations most often get wrong.
    "councillor_responsiveness": ["low", "mid", "high"],
    "official_responsiveness": ["low", "mid", "high"],
    "crime_handling": ["dissatisfied", "mixed", "satisfied"],
    # Strongly held and politically live: any policy touching jobs, services or
    # migration collides with it.
    "immigration_priority": ["low", "mid", "high"],
    # ── product-mode ───────────────────────────────────────────────────────────
    # Willingness to pay more for better service. A measured ATTITUDE, deliberately
    # not a purchase probability — it never becomes a "% who would buy".
    "pays_for_quality": ["no", "mixed", "yes"],
    # Baseline scepticism toward companies; governs how much proof a pitch needs.
    "business_trust": ["low", "mid", "high"],
    # Governs whether word-of-mouth / referral adoption is plausible for a segment.
    "social_trust": ["low", "mid", "high"],
}

# Material circumstances the donor also reports. Deliberately NOT part of ATTITUDE_VOCAB:
# "owns no car" and "went without food several times" are FACTS ABOUT A LIFE, not opinions.
# Attitudes are stances the LLM may restate in voice; circumstances are constraints it must
# not contradict. Merging the two vocabularies would destroy that distinction.
#
# These ride the SAME donor match as attitudes — one real respondent supplies the whole
# vector, so a persona's deprivation, assets and outlook stay internally coherent (a real
# person held all of them at once). They are not matched or sampled independently.
CIRCUMSTANCE_VOCAB: Dict[str, List[str]] = {
    # Afrobarometer Lived Poverty Index: mean of the five Q6 "gone without" items.
    "lived_poverty": ["none", "low", "moderate", "high"],
    "owns_vehicle": ["none", "household", "own"],
    "owns_computer": ["none", "household", "own"],
    "owns_bank_account": ["none", "household", "own"],
    "owns_television": ["none", "household", "own"],
    "internet_use": ["never", "rarely", "monthly", "weekly", "daily"],
    "electricity_reliability": ["never", "occasional", "half", "most", "always"],
    # Household spending authority — whether this person can decide a purchase at all,
    # or has to consult. The closest thing to a purchase-capability variable that exists
    # in real SA data, and absent from the model until now.
    "money_decision": ["self", "joint", "other", "none"],
    # Which channels actually reach this person. Answers "how would they even hear
    # about it", which panels currently guess at.
    "news_radio": ["never", "rarely", "monthly", "weekly", "daily"],
    "news_tv": ["never", "rarely", "monthly", "weekly", "daily"],
    "news_internet": ["never", "rarely", "monthly", "weekly", "daily"],
    "news_social": ["never", "rarely", "monthly", "weekly", "daily"],
}

# The demographic fields a donor must carry to be matchable. These are exactly the
# fields QLFS already fills on a skeleton (after banding), so they are the join surface.
#
# `race` was added after held-out evaluation (eval_attitude_match.py) showed it halves
# subgroup distribution error for Indian/Asian (14.0 -> 7.0) and White (12.7 -> 7.8)
# personas without hurting the African/Black majority. It is added as a SIXTH key rather
# than swapping out an existing one: swapping age for race scored worst of five candidate
# ladders. See _BACKOFF_LADDER in attitude_fuser for where it sits.
JOIN_KEYS = ["gender", "province", "education_band", "employment_status", "age_band", "race"]

# Canonical bands the fuser keys on. Kept here (next to the adapter) because the
# adapter is responsible for producing skeletons-and-donors in the SAME band vocab.
AGE_BANDS = ["15-29", "30-44", "45-59", "60+"]


def age_to_band(age: int) -> str:
    """Bucket a numeric age into the canonical band. Used for BOTH donors and skeletons
    so they share a join surface."""
    if age < 30:
        return "15-29"
    if age < 45:
        return "30-44"
    if age < 60:
        return "45-59"
    return "60+"


def education_to_band(education: str | None) -> str:
    """Collapse a QLFS-style education label to the coarse band donors are keyed on.

    QLFS labels seen in the library: 'No schooling', 'Primary', 'Secondary not completed',
    'Secondary completed', 'Tertiary', 'Other'. The donor survey's education codes are
    decoded to the same four bands so the two datasets join. Unknown → 'none' (the most
    conservative bucket — never invents attainment the data doesn't show).
    """
    e = (education or "").strip().lower()
    if not e or "no schooling" in e or e == "none":
        return "none"
    if "tertiary" in e or "degree" in e or "diploma" in e or "university" in e:
        return "tertiary"
    if "secondary" in e or "matric" in e or "grade 1" in e or "fet" in e:
        return "secondary"
    if "primary" in e or "grade" in e:
        return "primary"
    return "secondary"  # ambiguous mid-level attainment → secondary, the modal band


# Canonical race + settlement vocabularies. QLFS and Afrobarometer label these
# differently ('African/Black' vs 'Black / African', 'Indian/Asian' vs 'South Asian
# (Indian, Pakistani, etc.)'), so both sides are normalised here — the same reason
# age/education are banded here. A silent vocabulary mismatch would make every match
# fall to backoff while still looking like it worked, so the validator asserts both
# sides produce the same set.
#
# These are MATCHING KEYS and persona data fields. They must never be handed to a
# model as a reason to hold a view: the donor's *measured* attitude carries the
# effect, the LLM only styles the wording.
RACE_VOCAB = ["African/Black", "Coloured", "Indian/Asian", "White"]
GEOTYPES = ["Urban", "Rural"]

# QLFS Q15POPULATION → canonical. QLFS already uses the canonical labels verbatim
# (same convention as Province), so this is an identity map kept explicit so the
# adapter, not the caller, owns the vocabulary.
_QLFS_RACE = {
    "African/Black": "African/Black",
    "Coloured": "Coloured",
    "Indian/Asian": "Indian/Asian",
    "White": "White",
}

# Afrobarometer Q101 → canonical. 'Other' / 'Arab' / "Don't know" (4 respondents in
# R9 SA) deliberately map to None: they never match on race and fall through the
# ladder rather than being coerced into a group they didn't claim.
_AB_RACE = {
    "Black / African": "African/Black",
    "Coloured / Mixed race": "Coloured",
    "South Asian (Indian, Pakistani, etc.)": "Indian/Asian",
    "White / European": "White",
}

# QLFS Geo_Type_Code → canonical. QLFS distinguishes 'Traditional' (tribal areas)
# from 'Farms'; Afrobarometer URBRUR is binary, so both collapse to Rural for the
# JOIN. The finer QLFS distinction is not carried here — if a persona field needs
# it later, add it separately rather than widening the join surface.
_QLFS_GEOTYPE = {"Urban": "Urban", "Traditional": "Rural", "Farms": "Rural"}
_AB_GEOTYPE = {"Urban": "Urban", "Rural": "Rural"}


def race_to_canonical(value: str | None, source: str = "qlfs") -> Optional[str]:
    """Normalise a race label from either dataset onto RACE_VOCAB.

    Unknown / refused / 'Other' → None, which simply never matches on this key.
    """
    v = (value or "").strip()
    if not v:
        return None
    table = _QLFS_RACE if source == "qlfs" else _AB_RACE
    return table.get(v)


def geotype_to_canonical(value: str | None, source: str = "qlfs") -> Optional[str]:
    """Normalise a settlement label from either dataset onto GEOTYPES."""
    v = (value or "").strip()
    if not v:
        return None
    table = _QLFS_GEOTYPE if source == "qlfs" else _AB_GEOTYPE
    return table.get(v)


def _validate_donor(d: Dict, idx: int) -> None:
    """Fail loud if a donor record is malformed — a bad donor silently skews every
    persona that matches it, so we reject rather than coerce."""
    for k in JOIN_KEYS:
        # race is the one join key that may legitimately be None: 4 R9 SA respondents
        # answered 'Other'/'Arab'/'Don't know' and are deliberately not coerced into a
        # group they didn't claim. They simply never match a race rung and fall through
        # to the population rung. Every other key is mandatory.
        if k == "race":
            continue
        if not d.get(k):
            raise ValueError(f"donor[{idx}] missing join key '{k}': {d}")
    if d["age_band"] not in AGE_BANDS:
        raise ValueError(f"donor[{idx}] bad age_band '{d['age_band']}'")
    atts = d.get("attitudes")
    if not isinstance(atts, dict) or not atts:
        raise ValueError(f"donor[{idx}] has no attitudes block")
    for dim, val in atts.items():
        if dim not in ATTITUDE_VOCAB:
            raise ValueError(f"donor[{idx}] unknown attitude dimension '{dim}'")
        if val not in ATTITUDE_VOCAB[dim]:
            raise ValueError(f"donor[{idx}] attitude {dim}='{val}' not in vocab {ATTITUDE_VOCAB[dim]}")
    w = d.get("weight")
    if not isinstance(w, (int, float)) or w <= 0:
        raise ValueError(f"donor[{idx}] non-positive weight {w!r}")
    # circumstances may be absent entirely (synthetic fixture, or a respondent who
    # answered none of them) — but a present value must be in vocab.
    circ = d.get("circumstances")
    if circ is not None:
        if not isinstance(circ, dict):
            raise ValueError(f"donor[{idx}] circumstances must be a dict, got {type(circ)}")
        for field, val in circ.items():
            if field not in CIRCUMSTANCE_VOCAB:
                raise ValueError(f"donor[{idx}] unknown circumstance '{field}'")
            if val not in CIRCUMSTANCE_VOCAB[field]:
                raise ValueError(
                    f"donor[{idx}] circumstance {field}='{val}' not in vocab "
                    f"{CIRCUMSTANCE_VOCAB[field]}")
    # race/geotype are not yet join keys, so None is legal (the synthetic fixture has
    # neither). A *present* value must be canonical — an un-normalised label would
    # silently never match once these are promoted to join keys.
    if d.get("race") is not None and d["race"] not in RACE_VOCAB:
        raise ValueError(f"donor[{idx}] non-canonical race '{d['race']}' (expected {RACE_VOCAB})")
    if d.get("geotype") is not None and d["geotype"] not in GEOTYPES:
        raise ValueError(f"donor[{idx}] non-canonical geotype '{d['geotype']}' (expected {GEOTYPES})")


def load_synthetic(path: str = _SYNTHETIC_PATH) -> List[Dict]:
    """Load the synthetic donor fixture (development/test stand-in for real microdata)."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"synthetic donor fixture not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    donors = data.get("donors", [])
    for i, d in enumerate(donors):
        _validate_donor(d, i)
    return donors


# ── Afrobarometer R9 South Africa decode map ────────────────────────────────
# Verified against SAF_R9.data_.final_.wtd_release.30May23.sav (1580 rows, 390 cols).
# Sentinels that mean "no usable answer" across the survey: -1 Missing, 8/98 Refused,
# 9/99 Don't know, 99 Not asked. Any of these on a needed field drops that contribution.
_AB_MISSING = {-1.0, 8.0, 9.0, 98.0, 99.0, 998.0, 999.0}

_AB_REGION_TO_PROVINCE = {
    700.0: "Eastern Cape", 701.0: "Free State", 702.0: "Gauteng",
    703.0: "KwaZulu-Natal", 704.0: "Limpopo", 705.0: "Mpumalanga",
    706.0: "North West", 707.0: "Northern Cape", 708.0: "Western Cape",
}

# Q93A employment status → AgentProfile/QLFS employment vocabulary. Afrobarometer asks a
# coarser question than QLFS, so we map to the same three buckets the skeletons carry:
# part/full-time → Employed; looking → Unemployed; not looking → Other NEA.
_AB_Q93A_TO_STATUS = {
    0.0: "Other not economically active",  # No (not looking)
    1.0: "Unemployed",                     # No (looking)
    2.0: "Employed",                       # Yes, part time
    3.0: "Employed",                       # Yes, full time
}

# Q93B occupation of respondent → coarse class, used ONLY for role-aware donor
# pooling (it is NOT a join key). 1=Student (n=170), 11=Mid-level professional
# whose label literally reads "e.g., teacher, nurse, mid-level government
# officer" (n=78). Everything else is "general".
_AB_Q93B_CLASS = {
    1.0: "student",
    11.0: "mid_professional",
    12.0: "upper_professional",
}


# Role-aware donor slices: which persona roles prefer which donor class. Learners
# draw their attitudes from respondents actually inside the education system;
# educators from the teacher-class professionals. Guardians intentionally absent —
# R9 has no children-in-household item, so they stay on the full pool until a
# parent-survey donor (TIMSS) exists.
_ROLE_DONOR_CLASSES = {
    "learner": {"student"},
    "educator": {"mid_professional"},
}

# Below this many donors a role slice is too thin to demographic-match inside —
# fall back to the full pool rather than matching everyone to the same 5 people.
_MIN_ROLE_POOL = 30


def donor_pool_for_role(role: Optional[str], donors: Optional[List[Dict]] = None) -> Tuple[List[Dict], Optional[str]]:
    """The donor pool a persona role should fuse against, plus a source suffix.

    Returns (pool, suffix): learners → student respondents ("students"),
    educators → teacher-class professionals ("teacher_class_professionals"),
    everything else → the full pool (None). Falls back to the full pool when the
    slice is too thin (or when donors carry no occupation_class — e.g. the
    synthetic fixture)."""
    pool = donors if donors is not None else load_donors()
    classes = _ROLE_DONOR_CLASSES.get(role or "")
    if not classes:
        return pool, None
    sliced = [d for d in pool if d.get("occupation_class") in classes]
    if len(sliced) < _MIN_ROLE_POOL:
        return pool, None
    suffix = "students" if role == "learner" else "teacher_class_professionals"
    return sliced, suffix


# Q94 education (0-9 ladder) → coarse band matching education_to_band's vocab.
def _ab_education_band(code: float) -> Optional[str]:
    if code in _AB_MISSING:
        return None
    if code <= 1:      # no schooling / informal only
        return "none"
    if code <= 3:      # some primary / primary completed
        return "primary"
    if code <= 5:      # some secondary / secondary completed
        return "secondary"
    return "tertiary"  # post-secondary, university, post-grad


def _ab_band_3(value: float, lo: float, hi: float, labels=("low", "mid", "high")) -> Optional[str]:
    """Map a numeric mean onto a 3-band ordinal by equal thirds of [lo, hi]."""
    if value is None:
        return None
    span = (hi - lo) / 3.0
    if value < lo + span:
        return labels[0]
    if value < lo + 2 * span:
        return labels[1]
    return labels[2]


def _ab_mean(row, cols) -> Optional[float]:
    """Mean of the given Afrobarometer columns, ignoring missing/refused/DK. None if all
    contributing items are unusable for this respondent."""
    vals = [row[c] for c in cols if c in row and row[c] not in _AB_MISSING and row[c] == row[c]]
    return sum(vals) / len(vals) if vals else None


def _ab_max(row, cols) -> Optional[float]:
    vals = [row[c] for c in cols if c in row and row[c] not in _AB_MISSING and row[c] == row[c]]
    return max(vals) if vals else None


def _ab_code(row, col, table: Dict[float, str]) -> Optional[str]:
    """Map a single Afrobarometer coded answer through a code→label table.

    Anything not in the table (missing, refused, DK, 'not applicable') → None, which the
    fuser fills from the population mode and flags. Never coerced to a real answer.
    """
    v = row.get(col)
    if v is None or v != v or v in _AB_MISSING:
        return None
    return table.get(float(v))


# Q90 asset battery: 0 = nobody in household, 1 = someone else, 2 = personally owns.
_AB_ASSET = {0.0: "none", 1.0: "household", 2.0: "own"}
# Q90i internet frequency: 0 never … 4 every day.
_AB_INTERNET = {0.0: "never", 1.0: "rarely", 2.0: "monthly", 3.0: "weekly", 4.0: "daily"}
# Q92b mains electricity availability: 1 never … 5 all of the time.
_AB_ELECTRICITY = {1.0: "never", 2.0: "occasional", 3.0: "half", 4.0: "most", 5.0: "always"}
# Q74 news-channel frequency: same 0..4 shape as Q90i.
_AB_NEWS = dict(_AB_INTERNET)
# Q93c spending authority. 6 ("none of the above") and 7 ("not applicable, no earnings")
# are absent from the table on purpose — they fall through to None rather than being
# coerced into a decision role the respondent didn't claim.
_AB_MONEY_DECISION = {
    1.0: "self",   # decides alone
    2.0: "other",  # spouse decides
    3.0: "joint",  # jointly with spouse
    4.0: "joint",  # jointly with other family
    5.0: "other",  # other family decides without them
}

# ── New attitude scales, decoded by explicit code table rather than a banded mean.
# Several carry out-of-scale codes a mean would silently absorb: Q34b has 94 ("not asked
# in this country"), Q93c has 6/7. An explicit table simply omits them.
#
# Q34b councillors listen / Q36a likelihood of response: 0..3 low→high. Banded by thirds
# of the scale, matching _ab_band_3 so every dimension in the vocab bands the same way.
_AB_EFFICACY = {0.0: "low", 1.0: "mid", 2.0: "high", 3.0: "high"}
# Q86a trust other citizens: 0 not at all … 3 a lot. Same thirds convention.
_AB_SOCIAL_TRUST = {0.0: "low", 1.0: "mid", 2.0: "high", 3.0: "high"}
# Q38j corruption among business executives — INVERTED: more perceived corruption is
# LESS trust. 0 none → high trust; 3 all of them → low trust.
_AB_BUSINESS_TRUST = {0.0: "high", 1.0: "mid", 2.0: "low", 3.0: "low"}
# Q46f government handling of crime: 1 very badly … 4 very well. Same thirds banding the
# other Q46 items get via _ab_band_3(1.0, 4.0), so crime_handling is directly comparable
# to service_satisfaction and education_satisfaction.
_AB_HANDLING = {1.0: "dissatisfied", 2.0: "mixed", 3.0: "satisfied", 4.0: "satisfied"}
# 5-point agreement scales (Q80c better services worth higher cost, Q82c prioritise
# South Africans). 3 = "neither" is the genuine middle.
_AB_AGREE_PAY = {1.0: "no", 2.0: "no", 3.0: "mixed", 4.0: "yes", 5.0: "yes"}
_AB_AGREE_3 = {1.0: "low", 2.0: "low", 3.0: "mid", 4.0: "high", 5.0: "high"}


def _decode_ab_circumstances(row) -> Dict[str, str]:
    """Decode one Afrobarometer row into the CIRCUMSTANCE_VOCAB dict.

    Unlike attitudes, a donor missing every circumstance is still a usable donor (their
    attitudes remain valid), so this returns a possibly-empty dict rather than None.
    """
    out: Dict[str, str] = {}

    # Lived Poverty Index — the standard Afrobarometer construct: mean of the five Q6
    # "how often have you gone without" items, each 0 (never) … 4 (always). Banded rather
    # than kept numeric so it shares the ordinal vocabulary style of every other field.
    lpi = _ab_mean(row, ["Q6A", "Q6B", "Q6C", "Q6D", "Q6E"])
    if lpi is not None:
        if lpi == 0:
            out["lived_poverty"] = "none"
        elif lpi <= 1.0:
            out["lived_poverty"] = "low"
        elif lpi <= 2.0:
            out["lived_poverty"] = "moderate"
        else:
            out["lived_poverty"] = "high"

    for field, col in (("owns_vehicle", "Q90C"), ("owns_computer", "Q90D"),
                       ("owns_bank_account", "Q90E"), ("owns_television", "Q90B")):
        val = _ab_code(row, col, _AB_ASSET)
        if val:
            out[field] = val

    net = _ab_code(row, "Q90I", _AB_INTERNET)
    if net:
        out["internet_use"] = net

    elec = _ab_code(row, "Q92B", _AB_ELECTRICITY)
    if elec:
        out["electricity_reliability"] = elec

    money = _ab_code(row, "Q93C", _AB_MONEY_DECISION)
    if money:
        out["money_decision"] = money

    for field, col in (("news_radio", "Q74A"), ("news_tv", "Q74B"),
                       ("news_internet", "Q74D"), ("news_social", "Q74E")):
        val = _ab_code(row, col, _AB_NEWS)
        if val:
            out[field] = val

    return out


def _decode_ab_attitudes(row) -> Optional[Dict[str, str]]:
    """Decode one Afrobarometer row into the ATTITUDE_VOCAB dict. Returns None if the
    respondent lacks usable answers across all four dimensions (a donor with no attitude
    is no donor)."""
    # gov_trust: trust in president (Q37A) + local council (Q37D), scale 0..3.
    trust = _ab_band_3(_ab_mean(row, ["Q37A", "Q37D"]), 0.0, 3.0)
    # economic_optimism: present economy (Q4A) + living conditions (Q4B), scale 1..5.
    econ = _ab_band_3(_ab_mean(row, ["Q4A", "Q4B"]), 1.0, 5.0,
                      labels=("pessimistic", "neutral", "optimistic"))
    # service_satisfaction: water/sanitation (Q46I) + electricity (Q46L) handling, 1..4.
    svc = _ab_band_3(_ab_mean(row, ["Q46I", "Q46L"]), 1.0, 4.0,
                     labels=("dissatisfied", "mixed", "satisfied"))
    # crime_fear: WORST of unsafe-walking (Q7A) / feared-crime-at-home (Q7B), scale 0..4.
    crime = _ab_band_3(_ab_max(row, ["Q7A", "Q7B"]), 0.0, 4.0)
    # education_satisfaction: government handling of educational needs (Q46H), 1..4 —
    # same battery/scale as the Q46 service items. Single item by design: Q61B is on a
    # different 0..3 scale and Q40B/Q40D are experience, not evaluation. 1542/1580 usable.
    edu = _ab_band_3(_ab_mean(row, ["Q46H"]), 1.0, 4.0,
                     labels=("dissatisfied", "mixed", "satisfied"))

    out = {}
    if trust: out["gov_trust"] = trust
    if econ:  out["economic_optimism"] = econ
    if svc:   out["service_satisfaction"] = svc
    if crime: out["crime_fear"] = crime
    if edu:   out["education_satisfaction"] = edu

    # Policy-mode and product-mode dimensions. Decoded by explicit code table (see the
    # tables above) because several carry out-of-scale codes a banded mean would absorb.
    for dim, col, table in (
        ("councillor_responsiveness", "Q34B", _AB_EFFICACY),
        ("official_responsiveness", "Q36A", _AB_EFFICACY),
        ("crime_handling", "Q46F", _AB_HANDLING),
        ("immigration_priority", "Q82C_SAF", _AB_AGREE_3),
        ("pays_for_quality", "Q80C_SAF", _AB_AGREE_PAY),
        ("business_trust", "Q38J", _AB_BUSINESS_TRUST),
        ("social_trust", "Q86A", _AB_SOCIAL_TRUST),
    ):
        value = _ab_code(row, col, table)
        if value:
            out[dim] = value
    return out or None


def load_afrobarometer(sav_path: str) -> List[Dict]:
    """Decode real Afrobarometer R9 South Africa microdata into donor records.

    Verified against SAF_R9.data_.final_.wtd_release.30May23.sav. Each respondent becomes
    one donor with the JOIN_KEYS (decoded to AgentProfile vocab) + an in-vocab attitudes
    block + the household survey weight (withinwt_hh). Respondents missing a join key or
    all four attitudes are skipped (can't match or contribute nothing). Every emitted
    record is run through _validate_donor.
    """
    import pyreadstat  # local import: only needed when real data is loaded

    df, _meta = pyreadstat.read_sav(sav_path)
    # Q101 (race) and URBRUR (settlement) come through as numeric codes; decode via the
    # .sav value labels, then normalise onto the canonical vocabulary both datasets share.
    _race_labels = _meta.variable_value_labels.get("Q101", {})
    _geo_labels = _meta.variable_value_labels.get("URBRUR", {})
    donors: List[Dict] = []
    skipped = 0
    for _, row in df.iterrows():
        age = row.get("Q1")
        gender_code = row.get("THISINT")
        province = _AB_REGION_TO_PROVINCE.get(row.get("REGION"))
        edu_band = _ab_education_band(row.get("Q94"))
        status = _AB_Q93A_TO_STATUS.get(row.get("Q93A"))
        weight = row.get("withinwt_hh")

        # Drop respondents we can't place demographically — they can't be matched.
        if (age is None or age in _AB_MISSING or age != age or age < 15
                or gender_code not in (1.0, 2.0)
                or not province or not edu_band or not status
                or weight is None or weight != weight or weight <= 0):
            skipped += 1
            continue

        attitudes = _decode_ab_attitudes(row)
        if not attitudes:
            skipped += 1
            continue

        donors.append({
            "gender": "Male" if gender_code == 1.0 else "Female",
            "province": province,
            "education_band": edu_band,
            "employment_status": status,
            "age_band": age_to_band(int(age)),
            "weight": float(weight),
            "attitudes": attitudes,
            # Material facts from the SAME respondent, so the persona stays coherent.
            "circumstances": _decode_ab_circumstances(row),
            # Carried but NOT yet join keys — promoting them to the backoff ladder is a
            # separate change with a measurable match-quality trade-off. None where the
            # respondent answered 'Other'/'Don't know' (4 people in R9 SA).
            "race": race_to_canonical(_race_labels.get(row.get("Q101")), "ab"),
            "geotype": geotype_to_canonical(_geo_labels.get(row.get("URBRUR")), "ab"),
            # Not a join key — drives role-aware pooling (donor_pool_for_role).
            "occupation_class": _AB_Q93B_CLASS.get(row.get("Q93B"), "general"),
        })

    for i, d in enumerate(donors):
        _validate_donor(d, i)
    if not donors:
        raise ValueError(f"no usable donors decoded from {sav_path} (all {skipped} skipped)")
    return donors


# ── Active donor source ──────────────────────────────────────────────────────
# Real Afrobarometer R9 SA microdata, if present, else the synthetic dev fixture.
# Dropping the .sav at this path is what flips the library from invented to measured
# attitudes — no other code change needed.
_AFROBAROMETER_PATH = os.path.join(
    _HERE, "..", "data", "microdata", "attitudes", "afrobarometer_r9_sa.sav"
)


def load_donors() -> List[Dict]:
    """Return the active donor pool. Real Afrobarometer data if the .sav is in place,
    otherwise the synthetic fixture. This is the single swap point."""
    if os.path.exists(_AFROBAROMETER_PATH):
        return load_afrobarometer(_AFROBAROMETER_PATH)
    return load_synthetic()


def is_synthetic() -> bool:
    """True while load_donors() serves the development fixture rather than real licensed
    microdata. Source of truth for 'am I on real data yet' — the validator gates its
    no-distortion check on this and build_library.py refuses to ship off synthetic
    attitudes. Tied to the real .sav's presence so it can never drift out of sync."""
    return not os.path.exists(_AFROBAROMETER_PATH)


if __name__ == "__main__":
    donors = load_donors()
    print(f"Loaded {len(donors)} donor records "
          f"({'synthetic fixture' if is_synthetic() else 'real Afrobarometer R9 SA'}).")
    print(f"Join keys: {JOIN_KEYS}")
    print(f"Attitude vocab: {ATTITUDE_VOCAB}")
    for d in donors[:3]:
        print(json.dumps(d, ensure_ascii=False))
