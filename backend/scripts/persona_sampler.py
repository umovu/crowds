"""
persona_sampler — LLM-free, weighted sampler of demographically-coherent SA
identity skeletons from Stats SA QLFS microdata.

This is stage 1 of the hosted persona-library build (see the library blueprint):
it draws the *structural skeleton* of an identity — age, gender, province,
education, occupation, employment status, marital status — from real survey
microdata so that the bundle of fields actually co-occurred in a real person.
The LLM never touches this stage; it only writes texture (name, voice) on top of
a skeleton it did not invent.

Why whole-row sampling: drawing each field independently would produce
demographically impossible people (a 19-year-old professor earning R90k). We
sample whole survey rows with the survey WEIGHT, so every skeleton is a real,
population-weighted co-occurrence. This is the property the validation script
asserts (sampled marginals ≈ weighted population marginals).

Deterministic and model-free → fully testable with the LLM switched off.

Data: QLFS .dta from DataFirst (backend/data/microdata/, gitignored, licensed).
QLFS only asks labour questions of people 15+, so under-15s (no Status) are
dropped — that is also the simulation's universe (we don't make toddler personas).
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_DTA = os.path.join(
    _HERE, "..", "data", "microdata", "qlfs-2026-q1-v1", "qlfs-2026-q1-v1.dta"
)

# ── Column map (QLFS variable → skeleton field) ────────────────────────────
# NUMERIC columns must be read with convert_categoricals=False (age/weight are
# coded as Stata categoricals otherwise and break arithmetic). LABELLED columns
# are read with categoricals ON so they self-decode to readable strings.
_NUMERIC_COLS = ["Q14AGE", "Weight"]
_LABELLED_COLS = [
    "Q13GENDER",          # Female / Male
    "Province",           # already matches AgentProfile.SA_PROVINCES verbatim
    "Education_status",   # grouped: "Secondary completed", "Tertiary", ...
    "Occup",              # grouped occupation; NaN for the not-employed
    "Status",             # Employed / Unemployed / Discouraged / Other NEA
    "Infempl",            # Formal / Informal employment (NaN if not employed)
    "Indus",              # grouped industry
    "Q16MARITALSTATUS",   # Never married / Married / ...
    "Neet",               # Yes/No — not in employment, education or training
]

MIN_AGE = 15  # QLFS labour-status universe; also the sim's persona universe


def _load(dta_path: str) -> pd.DataFrame:
    """Load the QLFS .dta, joining the numeric and labelled passes.

    Cached on the function attribute so repeated sampling in one process does
    not re-read the ~60k-row file. Keyed by path so tests can load fixtures.
    """
    cache = getattr(_load, "_cache", {})
    if dta_path in cache:
        return cache[dta_path]

    if not os.path.exists(dta_path):
        raise FileNotFoundError(
            f"QLFS microdata not found at {dta_path}. Download the .dta from "
            f"DataFirst into backend/data/microdata/ (it is gitignored)."
        )

    # The file uses latin-1 for a few labels; pandas falls back automatically and
    # warns. Reading the two passes separately keeps age/weight numeric.
    num = pd.read_stata(dta_path, columns=_NUMERIC_COLS, convert_categoricals=False)
    lab = pd.read_stata(dta_path, columns=_LABELLED_COLS, convert_categoricals=True)
    df = pd.concat([num.reset_index(drop=True), lab.reset_index(drop=True)], axis=1)

    # Restrict to the labour-status universe (15+ with a valid weight).
    df = df[(df["Q14AGE"] >= MIN_AGE) & df["Weight"].notna() & (df["Weight"] > 0)]
    df = df.reset_index(drop=True)

    cache[dta_path] = df
    _load._cache = cache
    return df


def _occupation_label(row: pd.Series) -> str:
    """Derive a single occupation descriptor.

    Occup is only populated for the employed (~25% of adults). Dropping the rest
    would bias the library hard toward the employed, so the not-employed get a
    descriptor from their labour Status instead — which is itself a meaningful
    persona signal (an unemployed person is a distinct lived reality, not a gap).
    """
    occ = row.get("Occup")
    if pd.notna(occ) and str(occ).strip():
        infempl = row.get("Infempl")
        if pd.notna(infempl) and "Informal" in str(infempl):
            return f"{occ} (informal)"
        return str(occ)

    status = row.get("Status")
    if pd.isna(status):
        return "Not economically active"
    return str(status)  # "Unemployed", "Discouraged job seeker", "Other not economically active"


def _row_to_skeleton(row: pd.Series) -> Dict[str, object]:
    """Decode one survey row into an identity skeleton dict."""
    def s(v) -> Optional[str]:
        return str(v) if pd.notna(v) else None

    return {
        "age": int(row["Q14AGE"]),
        "gender": s(row.get("Q13GENDER")),
        "province": s(row.get("Province")),            # verbatim SA_PROVINCES label
        "education": s(row.get("Education_status")),
        "occupation": _occupation_label(row),
        "employment_status": s(row.get("Status")),
        "informal": (
            bool("Informal" in str(row.get("Infempl")))
            if pd.notna(row.get("Infempl")) else None
        ),
        "industry": s(row.get("Indus")),
        "marriage_status": s(row.get("Q16MARITALSTATUS")),
        "is_neet": (
            str(row.get("Neet")).strip().lower() == "yes"
            if pd.notna(row.get("Neet")) else None
        ),
    }


def sample_skeletons(
    n: int,
    seed: int = 0,
    dta_path: str = _DEFAULT_DTA,
) -> List[Dict[str, object]]:
    """Draw `n` population-weighted, demographically-coherent identity skeletons.

    Whole rows are sampled with replacement using the survey weight, so the
    returned set reproduces SA's population marginals (validated separately) and
    every individual skeleton is internally coherent.

    Deterministic for a given (n, seed, dta_path). No LLM, no network.
    """
    df = _load(dta_path)
    drawn = df.sample(n=n, replace=True, weights=df["Weight"], random_state=seed)
    return [_row_to_skeleton(row) for _, row in drawn.iterrows()]


def sample_teacher_skeletons(
    n: int,
    seed: int = 0,
    dta_path: str = _DEFAULT_DTA,
) -> List[Dict[str, object]]:
    """Educator-ROLE skeletons from real QLFS rows.

    QLFS's grouped occupation has no teacher category, so we sample from the
    closest honest pool — professionals/associate professionals in community &
    social services with tertiary education (the bucket educators sit in) — and
    ASSIGN the teacher role on top. Demographics (age/gender/province/education/
    employment) are real surveyed co-occurrences; the occupation itself is
    declared, and marked so: occupation_provenance="role_assigned". Upgrade path
    is a real teacher survey donor (TIMSS teacher questionnaire).
    """
    df = _load(dta_path)
    pool = df[
        df["Occup"].astype(str).isin(
            ["Professionals", "Technical and associate professionals"])
        & df["Indus"].astype(str).str.startswith("Community")
        & df["Education_status"].astype(str).str.lower().str.contains("tertiary")
        & df["Q14AGE"].between(23, 65)
    ]
    if pool.empty:
        raise ValueError("teacher proxy pool is empty — QLFS labels changed?")
    drawn = pool.sample(n=n, replace=True, weights=pool["Weight"], random_state=seed)
    out = []
    for _, row in drawn.iterrows():
        sk = _row_to_skeleton(row)
        sk["occupation"] = "School teacher"
        sk["occupation_provenance"] = "role_assigned"
        sk["source_survey"] = "qlfs_2026_q1"
        out.append(sk)
    return out


def population_marginals(dta_path: str = _DEFAULT_DTA) -> Dict[str, Dict[str, float]]:
    """Weighted ground-truth marginals (percent) for the adult universe.

    The validation script compares a large sample's marginals against these.
    Returned as {dimension: {label: pct}}.
    """
    df = _load(dta_path)
    out: Dict[str, Dict[str, float]] = {}
    for dim in ("Province", "Status"):
        sub = df.dropna(subset=[dim])
        w = sub.groupby(dim, observed=True)["Weight"].sum()
        out[dim] = (w / w.sum() * 100).round(2).to_dict()
    return out


if __name__ == "__main__":
    import json
    for sk in sample_skeletons(20, seed=1):
        print(json.dumps(sk, ensure_ascii=False))
