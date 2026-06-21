"""
ghs_adapter — decode GHS person+household microdata into education-persona skeletons.

The GHS (Stats SA General Household Survey) is the education counterpart of the QLFS
skeleton source: a household survey whose roster links learners to the people who
raise and pay for them. This is the ONE GHS-specific file — it decodes raw variables
(with their sentinels) into the same skeleton vocabulary persona_sampler emits, plus
the education fields QLFS cannot provide:

  * LEARNERS (15-18, currently attending) — institution type, current grade, fees
    band, time to school, who their guardian is. Under-15s are deliberately NOT
    emitted as personas (the library universe is 15+, same rule as QLFS); they appear
    instead as context on their guardians.
  * GUARDIANS (head/spouse of a household containing school-age learners) — split
    parent vs gogo (grandparent) by the learners' relationship to the household head,
    with learner count, fee burden, and grant receipt as context.

Every skeleton carries the household's REAL reported net monthly income in rand
(fin_reqinc, populated for all 20,095 households) with provenance — the affordability
anchor for the product-economy budget tier, same integrity class as the SASSA grant
schedule: looked up, never modelled.

Whole-row, person-weight sampling (like persona_sampler): each skeleton is a real
co-occurrence of circumstances, and samples reproduce population marginals.

Encoding note: Stats SA value labels are Windows-1252 (en-dashes in fee bands);
pyreadstat must be told so or it crashes on byte 0x96.

LLM-free. Deterministic. Data is gitignored, licensed from DataFirst.
"""

from __future__ import annotations

import os
import random
from typing import Any, Dict, List, Optional, Tuple

import pyreadstat

# ── Paths ──────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_GHS_DIR = os.path.join(_HERE, "..", "data", "microdata", "ghs-2025-v1")
_PERSON_DTA = os.path.join(_GHS_DIR, "ghs-2025-person-v1.dta")
_HOUSEHOLD_DTA = os.path.join(_GHS_DIR, "ghs-2025-household-v1.dta")
_ENCODING = "WINDOWS-1252"

# The library/persona universe is 15+ (same rule as QLFS — no child personas).
# Younger learners still count: they become guardian context (learner counts, fees).
MIN_PERSONA_AGE = 15
LEARNER_MAX_AGE = 18
SCHOOL_AGE = (6, 18)        # range counted as "learners in household" context
GUARDIAN_MIN_AGE = 25

# ── Code maps (verified against ghs-2025-v1 value labels) ────────────────────
_SENTINELS = {7.0, 8.0, 9.0, 88.0, 98.0, 99.0}   # NA / refused / DK / unspecified

_GEOTYPE = {1: "Urban", 2: "Traditional", 3: "Farms"}  # Stats SA convention (unlabelled var)

_REL_HEAD, _REL_SPOUSE, _REL_CHILD, _REL_GRANDCHILD = 1, 2, 3, 7

_INSTITUTION = {       # edu_edui → short institution label
    1: "Pre-school",
    2: "School",
    3: "ABET centre",
    4: "Literacy classes",
    5: "University",
    6: "TVET college",
    7: "Other college",
    8: "Home schooling",
    9: "Other institution",
}

# edu_totfees: 16 rand bands (0..15) decoded from the file's own value labels;
# 16=DK, 88=NA, 99=Unspecified are dropped.
_FEES_NON_ANSWERS = {16.0, 88.0, 99.0}

# fin_reqinc is a real rand amount for every household EXCEPT the 9999999 sentinel
# (204 households, "unspecified") — real values top out at R800k.
_INCOME_SENTINEL = 9999999.0

_TIME_TO_SCHOOL = {
    1: "under 15 minutes", 2: "15-30 minutes", 3: "31-60 minutes",
    4: "61-90 minutes", 5: "more than 90 minutes",
}


def _education_group(code: float) -> Optional[str]:
    """Collapse the GHS highest-education ladder (0..29, 98) to QLFS-style labels so
    education_to_band and the texture layer see one vocabulary."""
    if code != code or code in (28.0, 29.0, 99.0):
        return None
    c = int(code)
    if c == 98:
        return "No schooling"
    if c <= 7:                      # Grade R..7
        return "Primary"
    if c <= 11:                     # Grade 8..11
        return "Secondary not completed"
    if c == 12:                     # Grade 12 / matric
        return "Secondary completed"
    return "Tertiary"               # NTC/certificates/diplomas/degrees (13..27)


def _status_from_label(label: Optional[str]) -> Optional[str]:
    """Map employ_Status1's label text onto the QLFS status vocabulary."""
    t = str(label or "").lower()
    if not t or t in ("nan",):
        return None
    if "discouraged" in t:
        return "Discouraged job seeker"
    if "unemployed" in t:
        return "Unemployed"
    if "employed" in t:
        return "Employed"
    if "not economically active" in t or "inactive" in t:
        return "Other not economically active"
    return None


# ── Loading ──────────────────────────────────────────────────────────────────

def _load() -> Tuple["pandas.DataFrame", Dict[str, Dict]]:
    """Load + join the person and household files. Cached per process.

    Returns (person_df_with_household_cols, person_value_labels). All variables stay
    numeric; decoding to text happens in the skeleton builders via the code maps.
    """
    cache = getattr(_load, "_cache", None)
    if cache is not None:
        return cache

    for path in (_PERSON_DTA, _HOUSEHOLD_DTA):
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"GHS microdata not found at {path}. Download person+household .dta "
                f"from DataFirst into backend/data/microdata/ghs-2025-v1/ (gitignored)."
            )

    person, pmeta = pyreadstat.read_dta(_PERSON_DTA, encoding=_ENCODING)
    household, _ = pyreadstat.read_dta(_HOUSEHOLD_DTA, encoding=_ENCODING)

    hh_cols = ["uqnr", "fin_reqinc", "com_int_fixed", "com_int_mobile", "hwl_assets_comp"]
    merged = person.merge(household[hh_cols], on="uqnr", how="left", suffixes=("", "_hh"))

    result = (merged, pmeta.variable_value_labels)
    _load._cache = result
    return result


def _fix_mojibake(s: str) -> str:
    """Repair UTF-8-bytes-read-as-cp1252 mojibake (en-dashes in fee bands show
    as 'â€“'). pyreadstat is told the labels are WINDOWS-1252, but some Stats SA
    labels are actually UTF-8, so their en-dash bytes (E2 80 93) get decoded one
    byte at a time into 'â€“'. Reversing the misdecode (cp1252 → utf-8) restores
    the real dash. Idempotent: only strings carrying the '€' marker are touched;
    clean labels pass through unchanged."""
    if "€" not in s:
        return s
    try:
        return s.encode("cp1252", errors="strict").decode("utf-8", errors="strict")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _label(value_labels: Dict, var: str, code) -> Optional[str]:
    """Decoded label for a coded value, with the leading '1. ' index stripped."""
    if code != code:
        return None
    raw = value_labels.get(var, {}).get(code) or value_labels.get(var, {}).get(float(code))
    if raw is None:
        return None
    text = _fix_mojibake(str(raw))
    return text.split(". ", 1)[1].strip() if ". " in text[:5] else text.strip()


def _yes(code) -> Optional[bool]:
    if code != code or code in _SENTINELS:
        return None
    return code == 1.0


# ── Household education context ──────────────────────────────────────────────

def _household_learner_context(df, value_labels) -> Dict[float, Dict[str, Any]]:
    """Per-household education facts: school-age learners attending, their relation to
    the head, and the fee bands paid. Computed once over the full roster (all ages —
    this is where the under-15s count)."""
    ctx: Dict[float, Dict[str, Any]] = {}
    learners = df[
        (df["edu_attend"] == 1.0)
        & df["age"].between(*SCHOOL_AGE)
        & (df["edu_edui"].isin([1.0, 2.0, 3.0, 4.0, 6.0, 8.0]))  # school-system, not university
    ]
    for _, row in learners.iterrows():
        c = ctx.setdefault(row["uqnr"], {
            "learner_count": 0, "any_child_of_head": False,
            "any_grandchild_of_head": False, "fee_bands": [],
        })
        c["learner_count"] += 1
        rel = row.get("hhc_relationship")
        if rel == _REL_CHILD:
            c["any_child_of_head"] = True
        elif rel == _REL_GRANDCHILD:
            c["any_grandchild_of_head"] = True
        band = _fees_band(value_labels, row.get("edu_totfees"))
        if band:
            c["fee_bands"].append(band)
    return ctx


# ── Skeleton builders ────────────────────────────────────────────────────────

def _fees_band(value_labels, code) -> Optional[str]:
    if code != code or code in _FEES_NON_ANSWERS:
        return None
    return _label(value_labels, "edu_totfees", code)


def _base_skeleton(row, value_labels) -> Dict[str, Any]:
    """The persona_sampler-compatible core plus the GHS household-reality fields."""
    income = row.get("fin_reqinc")
    if income != income or income >= _INCOME_SENTINEL:
        income = None
    return {
        "age": int(row["age"]),
        "gender": _label(value_labels, "Sex", row.get("Sex")),
        "province": _label(value_labels, "prov", row.get("prov")),
        "education": _education_group(row.get("education")),
        "occupation": None,            # set per role below
        "employment_status": _status_from_label(
            _label(value_labels, "employ_Status1", row.get("employ_Status1"))),
        "informal": None,              # GHS has no formality coding
        "industry": None,
        "marriage_status": _label(value_labels, "hhc_marital", row.get("hhc_marital")),
        "is_neet": None,
        # GHS extensions
        "geotype": _GEOTYPE.get(int(row["geotype"])) if row.get("geotype") == row.get("geotype") else None,
        "home_language": _label(value_labels, "Languages", row.get("Languages")),
        # REAL household income (rand/month) — affordability anchor, never modelled.
        "monthly_household_income_rand": float(income) if income is not None else None,
        "income_provenance": "ghs_2025_reported" if income is not None else None,
        "internet_at_home": _yes(row.get("com_int_fixed")) or _yes(row.get("com_int_mobile")),
        "computer_in_home": _yes(row.get("hwl_assets_comp")),
        "receives_grant": _yes(row.get("soc_grant")),
        "source_survey": "ghs_2025",
    }


def _learner_skeleton(row, value_labels) -> Dict[str, Any]:
    sk = _base_skeleton(row, value_labels)
    inst = _INSTITUTION.get(int(row["edu_edui"])) if row.get("edu_edui") == row.get("edu_edui") else "School"
    grade = _label(value_labels, "edu_grde", row.get("edu_grde"))
    rel = row.get("hhc_relationship")
    tts = row.get("edu_time")
    sk.update({
        "ghs_role": "learner",
        "occupation": f"Learner ({inst})",
        "employment_status": "Other not economically active",
        "is_neet": False,
        "edu_institution": inst,
        "current_grade": grade,
        "fees_band": _fees_band(value_labels, row.get("edu_totfees")),
        "time_to_school": _TIME_TO_SCHOOL.get(int(tts)) if tts == tts and int(tts) in _TIME_TO_SCHOOL else None,
        "guardian_type": (
            "parent" if rel == _REL_CHILD else
            "grandparent" if rel == _REL_GRANDCHILD else
            "self" if rel == _REL_HEAD else "other relative"
        ),
    })
    return sk


def _guardian_skeleton(row, value_labels, ctx: Dict[str, Any]) -> Dict[str, Any]:
    sk = _base_skeleton(row, value_labels)
    gogo = bool(ctx.get("any_grandchild_of_head"))
    role = "gogo_guardian" if gogo else "guardian_parent"
    # GHS has no occupation coding, and a third of adults have "Unspecified" labour
    # status — when unknown, say nothing rather than invent ("Unspecified" stays None).
    sk.update({
        "ghs_role": role,
        "occupation": sk.get("employment_status"),
        "learners_in_household": ctx.get("learner_count", 0),
        "learner_fee_bands": sorted(set(ctx.get("fee_bands", []))),
        "guards_grandchildren": gogo,
    })
    return sk


# ── Sampling API ─────────────────────────────────────────────────────────────

def sample_education_skeletons(
    n_learners: int,
    n_guardians: int,
    seed: int = 0,
) -> List[Dict[str, Any]]:
    """Draw population-weighted education skeletons: learners (15-18, in the school
    system) and guardians (head/spouse, 25+, of households with school-age learners).

    Whole-row sampling with person_wgt, with replacement — every skeleton is a real
    person's co-occurrence of circumstances and samples track population marginals.
    Deterministic for (n_learners, n_guardians, seed).
    """
    df, value_labels = _load()
    ctx = _household_learner_context(df, value_labels)

    out: List[Dict[str, Any]] = []

    learner_pool = df[
        (df["edu_attend"] == 1.0)
        & df["age"].between(MIN_PERSONA_AGE, LEARNER_MAX_AGE)
        & (df["edu_edui"].isin([2.0, 3.0, 6.0, 8.0]))   # school / ABET / TVET / home-school
        & df["person_wgt"].notna() & (df["person_wgt"] > 0)
    ]
    if n_learners > 0 and len(learner_pool) > 0:
        drawn = learner_pool.sample(n=n_learners, replace=True,
                                    weights=learner_pool["person_wgt"], random_state=seed)
        out.extend(_learner_skeleton(row, value_labels) for _, row in drawn.iterrows())

    guardian_pool = df[
        (df["hhc_relationship"].isin([_REL_HEAD, _REL_SPOUSE]))
        & (df["age"] >= GUARDIAN_MIN_AGE)
        & df["uqnr"].isin(ctx.keys())
        & df["person_wgt"].notna() & (df["person_wgt"] > 0)
    ]
    if n_guardians > 0 and len(guardian_pool) > 0:
        drawn = guardian_pool.sample(n=n_guardians, replace=True,
                                     weights=guardian_pool["person_wgt"], random_state=seed + 1)
        out.extend(
            _guardian_skeleton(row, value_labels, ctx[row["uqnr"]])
            for _, row in drawn.iterrows()
        )

    return out


def education_marginals() -> Dict[str, Dict[str, float]]:
    """Weighted ground truth for the validator: province mix of the learner pool and
    the parent/gogo split among guardian households (percent)."""
    df, value_labels = _load()
    ctx = _household_learner_context(df, value_labels)

    learner_pool = df[
        (df["edu_attend"] == 1.0)
        & df["age"].between(MIN_PERSONA_AGE, LEARNER_MAX_AGE)
        & (df["edu_edui"].isin([2.0, 3.0, 6.0, 8.0]))
        & df["person_wgt"].notna() & (df["person_wgt"] > 0)
    ]
    prov = learner_pool.groupby("prov", observed=True)["person_wgt"].sum()
    prov_pct = {
        _label(value_labels, "prov", k): round(v / prov.sum() * 100, 2)
        for k, v in prov.items()
    }

    gogo_hh = sum(1 for c in ctx.values() if c["any_grandchild_of_head"])
    return {
        "learner_province_pct": prov_pct,
        "guardian_household_split": {
            "gogo_pct": round(gogo_hh / max(len(ctx), 1) * 100, 2),
            "households_with_learners": len(ctx),
        },
    }


if __name__ == "__main__":
    import json
    skeletons = sample_education_skeletons(n_learners=5, n_guardians=5, seed=1)
    for sk in skeletons:
        print(json.dumps(sk, ensure_ascii=False))
    print(json.dumps(education_marginals(), ensure_ascii=False, indent=1))
