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
}

# The demographic fields a donor must carry to be matchable. These are exactly the
# fields QLFS already fills on a skeleton (after banding), so they are the join surface.
JOIN_KEYS = ["gender", "province", "education_band", "employment_status", "age_band"]

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


def _validate_donor(d: Dict, idx: int) -> None:
    """Fail loud if a donor record is malformed — a bad donor silently skews every
    persona that matches it, so we reject rather than coerce."""
    for k in JOIN_KEYS:
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
