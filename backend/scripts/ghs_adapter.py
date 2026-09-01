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

# Shared vocabulary owner (bands, race, settlement) — so every skeleton source
# normalises the same way, whatever survey it came from.
import attitude_donor_adapter as ada

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

# GHS `Population` → the canonical race vocabulary shared with QLFS/Afrobarometer.
# GHS labels carry a numeric prefix ("1. African/Black"), so map by code, not label.
_GHS_RACE = {1: "African/Black", 2: "Coloured", 3: "Indian/Asian", 4: "White"}


def _race_from_ghs(value) -> Optional[str]:
    """Canonical race from GHS `Population`. Unknown/missing → None, never coerced."""
    if value is None or value != value:
        return None
    return _GHS_RACE.get(int(value))

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
    household, hmeta = pyreadstat.read_dta(_HOUSEHOLD_DTA, encoding=_ENCODING)

    hh_cols = ["uqnr", "fin_reqinc", "com_int_fixed", "com_int_mobile", "hwl_assets_comp",
               "hhw_hltfac", "hhw_transp", "hhw_time",
               # Does the household run any agriculture. Needed by the affluent
               # sampler: land plus a daily organic waste stream is what makes a
               # household a candidate for on-site processing, and it is a
               # surveyed fact rather than an inference from occupation.
               "agr_agri"]
    merged = person.merge(household[hh_cols], on="uqnr", how="left", suffixes=("", "_hh"))

    # Household-only variables (the hhw_* health-access answers) carry their value
    # labels in the household metadata, so the skeleton builders would decode them to
    # None off the person labels alone. Person labels win on any name collision.
    labels = dict(hmeta.variable_value_labels)
    labels.update(pmeta.variable_value_labels)

    result = (merged, labels)
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


# ── Health circumstances ─────────────────────────────────────────────────────
# Real reported healthcare access, so personas can react to health messaging from
# their own circumstances instead of the model's assumptions. Decoded by explicit
# code table, NOT through _SENTINELS/_yes: hhw_hltfac uses 7/8/9 for traditional
# healer / spiritual healer / pharmacy — real answers the shared sentinel set
# would silently discard — and hlt_medi uses 3 for "do not know", which _yes
# would read as "no".

_HLT_MEDI = {1.0: True, 2.0: False}                     # 3 = DK, 9 = unspecified → None
_HEALTH_STATUS = {1.0: "Excellent", 2.0: "Very good", 3.0: "Good",
                  4.0: "Fair", 5.0: "Poor"}             # 6 = not sure, 9 = unspecified
_DISAB = {0.0: False, 1.0: True}                        # 9 = unspecified → None
_FACILITY_NON_ANSWERS = {13.0, 99.0}                    # DK / unspecified
_PUBLIC_FACILITY_CODES = {1.0, 2.0, 3.0}                # 4..12 are private sector
_TRANSPORT_NON_ANSWERS = {9.0}                          # 7 = "other means" is an answer
_TIME_NON_ANSWERS = {5.0, 9.0}                          # DK / unspecified


def _health_block(row, value_labels) -> Dict[str, Any]:
    """Healthcare access + self-rated health for one person, from the GHS person
    file plus the household's usual-facility answers. Every field is nullable and
    carries no imputation: a missing answer stays missing."""
    facility_code = row.get("hhw_hltfac")
    facility = None
    sector = None
    if facility_code == facility_code and facility_code not in _FACILITY_NON_ANSWERS:
        facility = _label(value_labels, "hhw_hltfac", facility_code)
        sector = "public" if facility_code in _PUBLIC_FACILITY_CODES else "private"

    transport_code = row.get("hhw_transp")
    transport = (_label(value_labels, "hhw_transp", transport_code)
                 if transport_code == transport_code
                 and transport_code not in _TRANSPORT_NON_ANSWERS else None)

    time_code = row.get("hhw_time")
    travel_time = (_label(value_labels, "hhw_time", time_code)
                   if time_code == time_code
                   and time_code not in _TIME_NON_ANSWERS else None)

    return {
        "medical_aid": _HLT_MEDI.get(row.get("hlt_medi")),
        "self_rated_health": _HEALTH_STATUS.get(row.get("hlt_genhealth")),
        "has_disability": _DISAB.get(row.get("disab")),
        "usual_health_facility": facility,
        "health_facility_sector": sector,
        "transport_to_health_facility": transport,
        "time_to_health_facility": travel_time,
        "health_provenance": "ghs_2025_reported",
    }


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
    band = _label(value_labels, "edu_totfees", code)
    # edu_totfees is an ANNUAL amount but the Stats SA value labels carry no
    # unit; downstream LLMs read a bare band next to monthly income as
    # monthly. Stamp the period on paid bands so it survives into prompts.
    if band and band != "No fees" and "year" not in band.lower():
        band = f"{band} per year"
    return band


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
        # race is a JOIN KEY (attitude_donor_adapter.JOIN_KEYS). Omitting it here sent
        # every education skeleton down the ladder to the race-unknown rung, where only
        # 2 of 1,384 donors live — 39 of 40 education personas would have drawn their
        # attitudes from the same two respondents. GHS `Population` uses the same four
        # categories as QLFS Q15POPULATION, so it normalises through the shared mapper.
        "race": _race_from_ghs(row.get("Population")),
        "geotype": _GEOTYPE.get(int(row["geotype"])) if row.get("geotype") == row.get("geotype") else None,
        "home_language": _label(value_labels, "Languages", row.get("Languages")),
        # REAL household income (rand/month) — affordability anchor, never modelled.
        "monthly_household_income_rand": float(income) if income is not None else None,
        "income_provenance": "ghs_2025_reported" if income is not None else None,
        "internet_at_home": _yes(row.get("com_int_fixed")) or _yes(row.get("com_int_mobile")),
        "computer_in_home": _yes(row.get("hwl_assets_comp")),
        "receives_grant": _yes(row.get("soc_grant")),
        **_health_block(row, value_labels),
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


# ── Affluent households ─────────────────────────────────────────────────────
# The library samples to look like South Africa, where most households cannot
# find R17,000. That is honest and stays that way — the "everyone" room must keep
# its population shape. But it leaves almost nobody to answer a product question
# aimed at people who CAN pay: 16 of 297 personas reach the "loose" budget tier,
# and only 11 personas are both able to pay and low on environment_priority.
#
# These samplers draw from the same GHS households, restricted by REAL reported
# income (fin_reqinc), so every persona carries a surveyed rand figure rather
# than a tier inferred from a job title. They are meant to be added as their OWN
# named segments, never folded into "everyone".
#
# Bands match mode_specs.budget_tier so the sampler and the tier agree by
# construction: "loose" is above R20,000, "moderate" is R4,500–R20,000.
AFFLUENT_INCOME_FLOOR = 20_000.0     # budget_tier -> "loose"
COMFORTABLE_INCOME_FLOOR = 12_000.0  # upper half of "moderate"; R17k is ~a month


def _affluent_pool(df, floor: float):
    """Household heads and spouses whose household reports income above `floor`.

    Head/spouse only: the money question is asked of the household, so a
    17-year-old in a high-earning home is not someone who can authorise a
    R17,000 purchase. That was the bug in the first filtered room — it came back
    full of learners who had passed an affordability test on their parents'
    income.
    """
    income = df["fin_reqinc"]
    return df[
        (df["hhc_relationship"].isin([_REL_HEAD, _REL_SPOUSE]))
        & (df["age"] >= GUARDIAN_MIN_AGE)
        & income.notna() & (income > floor) & (income < _INCOME_SENTINEL)
        & df["person_wgt"].notna() & (df["person_wgt"] > 0)
    ]


def _affluent_skeleton(row, value_labels, archetype: str) -> Dict[str, Any]:
    sk = _base_skeleton(row, value_labels)
    sk["actor_archetype"] = archetype
    sk["occupation"] = _label(value_labels, "employ_Status1", row.get("employ_Status1")) \
        or sk.get("employment_status")
    # A surveyed fact, not an inference: does this household farm at all. It is
    # what separates "has a waste stream and land" from "has money and a flat".
    agri = row.get("agr_agri")
    sk["household_farms"] = bool(agri == 1.0) if agri == agri else None
    return sk


def sample_affluent_skeletons(
    n_agri: int = 0,
    n_urban: int = 0,
    n_comfortable: int = 0,
    n_rural: int = 0,
    seed: int = 0,
) -> List[Dict[str, Any]]:
    """Draw weighted skeletons of people who can actually authorise a large
    purchase, split into four groups with different reasons to care.

      n_agri        income > R12k AND the household farms — land, a daily organic
                    waste stream, and money. Pool ~660 households.
      n_urban       income > R20k, urban formal — can pay, small yard. The
                    "where would it even go" objection lives here. Pool ~2,276.
      n_comfortable R12k–R20k — R17,000 is about a month's income, so this is the
                    financing conversation rather than the cash one. Pool ~2,256.
      n_rural       income > R12k, traditional or farm settlement — the
                    small-scale-but-doing-well owner. Pool ~470.

    Whole-row weighted sampling with replacement, deterministic for (counts, seed),
    same discipline as sample_education_skeletons. LLM-free.
    """
    df, value_labels = _load()
    out: List[Dict[str, Any]] = []

    def draw(pool, n, archetype, offset):
        if n <= 0 or len(pool) == 0:
            return
        drawn = pool.sample(n=n, replace=True, weights=pool["person_wgt"],
                            random_state=seed + offset)
        out.extend(_affluent_skeleton(row, value_labels, archetype)
                   for _, row in drawn.iterrows())

    comfortable = _affluent_pool(df, COMFORTABLE_INCOME_FLOOR)
    affluent = _affluent_pool(df, AFFLUENT_INCOME_FLOOR)

    draw(comfortable[comfortable["agr_agri"] == 1.0], n_agri,
         "affluent_agricultural_household", 10)
    # geotype arrives as a STRING code ('1' urban formal, '2' traditional,
    # '3' farms) in this release, so compare as text — a numeric comparison
    # silently matched nothing and drew empty groups.
    geo = df["geotype"].astype(str)
    draw(affluent[geo.loc[affluent.index] == "1"], n_urban,
         "affluent_urban_household", 11)
    # Comfortable band only — above R20k is the "affluent" groups' territory.
    draw(comfortable[comfortable["fin_reqinc"] <= AFFLUENT_INCOME_FLOOR], n_comfortable,
         "comfortable_household", 12)
    draw(comfortable[geo.loc[comfortable.index].isin(["2", "3"])], n_rural,
         "rural_landholding_household", 13)
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

    # Weighted medical-aid share over the persona-age population — the ground truth
    # the sampled skeletons must track, so health access can never drift upmarket.
    medi = df[df["age"] >= MIN_PERSONA_AGE]
    medi = medi[medi["hlt_medi"].isin([1.0, 2.0])
                & medi["person_wgt"].notna() & (medi["person_wgt"] > 0)]
    covered = medi.loc[medi["hlt_medi"] == 1.0, "person_wgt"].sum()

    return {
        "learner_province_pct": prov_pct,
        "medical_aid_pct": round(covered / medi["person_wgt"].sum() * 100, 2),
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
