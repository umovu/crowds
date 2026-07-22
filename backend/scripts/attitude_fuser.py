"""
attitude_fuser — fuse measured SA attitudes onto a QLFS identity skeleton by
matching on shared demographics (hot-deck / statistical matching).

The problem: QLFS has no attitude data, and the attitudinal survey interviewed
DIFFERENT people, so there is no exact join. The honest technique is donor matching:
for each QLFS skeleton, find the donor respondents whose DEMOGRAPHICS are nearest, and
import one of their measured ATTITUDE vectors. The persona then carries an attitude a
real South African of that demographic actually held — not the LLM's guess.

  match ON  : gender, province, education_band, employment_status, age_band  (QLFS has these)
  import    : attitudes dict over ATTITUDE_VOCAB                              (only the donor has these)

Design (mirrors archetype_mapper's discipline):
  * **Deterministic.** Donor pick is a weighted draw seeded from (global seed + a stable
    hash of the skeleton), so the same (skeleton, seed) always yields the same attitudes.
  * **Graceful backoff.** If the exact 5-key cell has no donor, drop keys in a fixed
    order (age_band → education_band → province) until donors exist, recording how coarse
    the match was as `match_quality`. A persona is never left without an attitude, and the
    provenance of every match is auditable.
  * **LLM-free.** Fully assertable with the model off; the LLM later only STYLES the
    imported attitudes into voice, never sets or contradicts them.

This slots between sample_skeletons and map_skeletons in build_library.py. Output keys
added to each skeleton dict:
  * "attitudes": List[{topic, stance, source, match_quality}]  → lands in AgentProfile.attitudes
  * "beliefs":   List[str]  deterministic phrasing of the stances → AgentProfile.beliefs
  * "attitude_match_quality": coarsest backoff level used (for the validator / audit)
"""

from __future__ import annotations

import hashlib
import json
import random
from typing import Dict, List, Optional, Tuple

import attitude_donor_adapter as ada

# Backoff ladder: full 6-key match first, then drop keys left-to-right. age_band and
# education_band are dropped before province because province is a stronger attitude
# predictor in SA (service delivery, provincial government performance vary by province).
# employment_status and gender are kept longest — both correlate hard with economic mood.
#
# `race` is dropped LAST, just above whole-population. Chosen by held-out evaluation over
# five candidate ladders (eval_attitude_match.py, 5-fold, subgroup distribution fidelity):
# this shape scored best overall (TVD 2.5 vs 2.8 for the previous ladder) and roughly
# halved distribution error for the minority groups it exists to serve —
# Indian/Asian 14.0 -> 7.0, White 12.7 -> 7.8, Coloured 6.7 -> 3.9 — while leaving the
# African/Black majority marginally better. Swapping race in for age instead of adding it
# scored WORST of the five, so it is a sixth key, not a replacement.
#
# Cost, measured and accepted: top-rung ("exact") share falls from ~85% to ~76%, because
# six keys over 1,384 donors leaves more cells empty. A same-race donor one rung down is a
# better match than a different-race donor at the top rung, so the label is what changes,
# not the quality.
_BACKOFF_LADDER: List[List[str]] = [
    ["gender", "province", "education_band", "employment_status", "age_band", "race"],  # exact
    ["gender", "province", "education_band", "employment_status", "race"],              # drop age
    ["gender", "province", "employment_status", "race"],                                # drop education
    ["gender", "employment_status", "race"],                                            # drop province
    ["employment_status", "race"],                                                      # drop gender
    ["race"],                                                                           # race only
    [],                                                                                 # whole-population
]

# Human-readable label per ladder rung, for match_quality provenance. Named for what is
# PRESERVED, not merely how far down the ladder we went: every rung above "population"
# keeps race, which is the point of the ordering.
_QUALITY_LABELS = [
    "exact", "age_backoff", "education_backoff",
    "province_backoff", "status_race", "race_only", "population",
]

# Deterministic belief phrasing per (dimension, stance). Kept LLM-free on purpose: the
# belief sentence is data, not generation, so it's assertable. The LLM may later restate
# it in voice, but the canonical belief is fixed here. Only non-neutral stances yield a
# belief (a "mid"/"neutral" attitude is not a strong belief worth asserting).
_BELIEF_PHRASING: Dict[str, Dict[str, str]] = {
    "gov_trust": {
        "low": "Government and officials mostly don't act in people like me's interest.",
        "high": "Government and local institutions can generally be trusted to do their job.",
    },
    "economic_optimism": {
        "pessimistic": "The economy and my own prospects are getting worse, not better.",
        "optimistic": "Things are improving and there's a real chance to get ahead.",
    },
    "service_satisfaction": {
        "dissatisfied": "Basic services in my area are failing and complaints go nowhere.",
        "satisfied": "Basic services in my area mostly work and are improving.",
    },
    "crime_fear": {
        "high": "Crime is a constant threat that shapes my daily decisions.",
        "low": "Safety isn't a major day-to-day worry where I live.",
    },
}


def _skeleton_join_view(skeleton: Dict) -> Dict[str, Optional[str]]:
    """Project a QLFS skeleton onto the donor JOIN_KEYS (banded), so the two datasets
    share a vocabulary. Education and age are banded via the adapter's canonical mappers."""
    age = skeleton.get("age")
    return {
        "gender": skeleton.get("gender"),
        "province": skeleton.get("province"),
        "education_band": ada.education_to_band(skeleton.get("education")),
        "employment_status": skeleton.get("employment_status"),
        "age_band": ada.age_to_band(int(age)) if age is not None else None,
        # Already canonicalised by persona_sampler via the adapter, so no banding needed.
        "race": skeleton.get("race"),
    }


def _matching_donors(view: Dict, donors: List[Dict], keys: List[str]) -> List[Dict]:
    """Donors whose values equal the skeleton view on every key in `keys`.
    Empty `keys` → the whole population (final backoff rung)."""
    if not keys:
        return donors
    return [d for d in donors if all(d.get(k) == view.get(k) for k in keys)]


def _seeded_weighted_pick(donors: List[Dict], skeleton: Dict, seed: int) -> Dict:
    """Pick one donor by survey weight, deterministically for (skeleton, seed).

    Same seeding scheme as archetype_mapper._seeded_choice: the RNG is derived from the
    global seed XOR a stable hash of the skeleton, so identical skeletons resolve
    identically while different skeletons spread across the donor pool.
    """
    if len(donors) == 1:
        return donors[0]
    key = json.dumps({k: skeleton.get(k) for k in
                      ("age", "gender", "province", "education", "employment_status",
                       "occupation", "industry", "marriage_status", "is_neet")},
                     sort_keys=True, ensure_ascii=False)
    h = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed ^ h)
    weights = [float(d.get("weight", 1.0)) for d in donors]
    return rng.choices(donors, weights=weights, k=1)[0]


def _match_with_backoff(
    skeleton: Dict, donors: List[Dict], seed: int
) -> Tuple[Dict, str]:
    """Find a donor for one skeleton, climbing the backoff ladder until donors exist.
    Returns (donor, quality_label). The final rung is the whole population, so this
    always returns a donor as long as the pool is non-empty."""
    view = _skeleton_join_view(skeleton)
    for rung, keys in enumerate(_BACKOFF_LADDER):
        pool = _matching_donors(view, donors, keys)
        if pool:
            return _seeded_weighted_pick(pool, skeleton, seed), _QUALITY_LABELS[rung]
    # Unreachable unless donors is empty (caller guards), but be explicit.
    raise ValueError("no donors available to match — donor pool is empty")


def _attitudes_to_fields(
    donor_attitudes: Dict[str, str], source: str, quality: Dict[str, str]
) -> Tuple[List[Dict], List[str]]:
    """Turn the donor's raw attitude dict into AgentProfile-shaped `attitudes` rows and
    deterministic `beliefs` sentences. Every row carries source + a PER-DIMENSION
    match_quality (a donor-matched dim and a population-modal fallback dim differ), so the
    provenance of each stance is independently auditable."""
    attitudes: List[Dict] = []
    beliefs: List[str] = []
    for dim, stance in donor_attitudes.items():
        attitudes.append({
            "topic": dim,
            "stance": stance,
            "source": source,
            "match_quality": quality[dim],
        })
        phrasing = _BELIEF_PHRASING.get(dim, {})
        if stance in phrasing:  # only non-neutral stances become asserted beliefs
            beliefs.append(phrasing[stance])
    return attitudes, beliefs


def _population_modal_stances(donors: List[Dict]) -> Dict[str, str]:
    """The survey-weighted most-common stance per dimension across the whole donor pool.

    Real survey respondents sometimes refuse/skip a question, so a matched donor can be
    missing a dimension. Rather than emit an incomplete vector, we fill ONLY the missing
    dimension with the population's modal stance — honest ("this is what people typically
    hold"), weighted, and flagged with its own match_quality so it's never mistaken for a
    real demographic match."""
    from collections import defaultdict
    weighted = {dim: defaultdict(float) for dim in ada.ATTITUDE_VOCAB}
    for d in donors:
        w = float(d.get("weight", 1.0))
        for dim, stance in d["attitudes"].items():
            weighted[dim][stance] += w
    modal: Dict[str, str] = {}
    for dim, stances in weighted.items():
        if stances:
            modal[dim] = max(stances.items(), key=lambda kv: kv[1])[0]
        else:
            modal[dim] = ada.ATTITUDE_VOCAB[dim][len(ada.ATTITUDE_VOCAB[dim]) // 2]  # neutral middle
    return modal


def _population_distributions(donors: List[Dict], key: str, vocab: Dict) -> Dict[str, Tuple[List[str], List[float]]]:
    """Survey-weighted stance distribution per dimension, for the population fallback.

    Used INSTEAD of the modal value when a matched donor didn't answer a dimension.
    Filling every gap with the mode biases the library toward that mode in proportion to
    how often the dimension is missing — invisible at 99% coverage, but business_trust is
    only 89% answered and modal-filling drifted its marginals 6pp (caught by
    validate_attitude_fuser). A weighted draw preserves the population marginals by
    construction, and is just as honest: "someone plausible from this population" rather
    than "the most typical person".
    """
    from collections import defaultdict
    weighted = {dim: defaultdict(float) for dim in vocab}
    for d in donors:
        w = float(d.get("weight", 1.0))
        for dim, value in (d.get(key) or {}).items():
            if dim in weighted:
                weighted[dim][value] += w
    return {
        dim: (list(vals.keys()), list(vals.values()))
        for dim, vals in weighted.items() if vals
    }


def _population_draw(
    dists: Dict[str, Tuple[List[str], List[float]]], dim: str, skeleton: Dict, seed: int
) -> Optional[str]:
    """Deterministic weighted draw from the population distribution for one dimension.

    Seeded on (skeleton, dim) so the same persona always fills the same gap the same way,
    and two personas don't both collapse onto the same value.
    """
    dist = dists.get(dim)
    if not dist:
        return None
    options, weights = dist
    key = json.dumps({k: skeleton.get(k) for k in
                      ("age", "gender", "province", "education", "employment_status",
                       "occupation", "industry", "marriage_status", "is_neet")},
                     sort_keys=True, ensure_ascii=False) + f"|{dim}"
    h = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16)
    return random.Random(seed ^ h).choices(options, weights=weights, k=1)[0]


def _population_modal_circumstances(donors: List[Dict]) -> Dict[str, Optional[str]]:
    """Survey-weighted most-common value per circumstance field.

    Same role as _population_modal_stances: fills a field the matched donor didn't answer.
    Unlike attitudes there is NO neutral-middle fallback — if nothing was measured anywhere
    (the synthetic fixture carries no circumstances) the field stays None and is omitted
    entirely, rather than inventing a middle value for a material fact."""
    from collections import defaultdict
    weighted = {field: defaultdict(float) for field in ada.CIRCUMSTANCE_VOCAB}
    for d in donors:
        w = float(d.get("weight", 1.0))
        for field, value in (d.get("circumstances") or {}).items():
            if field in weighted:
                weighted[field][value] += w
    return {
        field: (max(vals.items(), key=lambda kv: kv[1])[0] if vals else None)
        for field, vals in weighted.items()
    }


def fuse_attitudes(
    skeletons: List[Dict],
    seed: int = 0,
    donors: Optional[List[Dict]] = None,
    source: Optional[str] = None,
) -> List[Dict]:
    """Attach a measured-attitude vector to each skeleton via demographic donor matching.

    Returns NEW dicts (originals untouched), each with `attitudes`, `beliefs`, and
    `attitude_match_quality` added. Every persona gets a COMPLETE vector: any dimension the
    matched donor lacked (survey refusal) is filled from the population modal stance and
    flagged match_quality="population_modal". Deterministic for (skeletons, seed, donors).
    LLM-free.
    """
    pool = donors if donors is not None else ada.load_donors()
    if not pool:
        raise ValueError("attitude donor pool is empty — cannot fuse attitudes")
    # Label provenance by the active data source unless the caller overrides it.
    if source is None:
        source = "synthetic_donor" if ada.is_synthetic() else "afrobarometer_r9_sa"

    modal = _population_modal_stances(pool)
    modal_circ = _population_modal_circumstances(pool)
    dist_att = _population_distributions(pool, "attitudes", ada.ATTITUDE_VOCAB)
    dist_circ = _population_distributions(pool, "circumstances", ada.CIRCUMSTANCE_VOCAB)

    out: List[Dict] = []
    for sk in skeletons:
        donor, quality = _match_with_backoff(sk, pool, seed)
        # Complete the vector: matched stances win; missing dims fall back to modal.
        full: Dict[str, str] = dict(donor["attitudes"])
        per_dim_quality = {dim: quality for dim in full}
        for dim in ada.ATTITUDE_VOCAB:
            if dim not in full:
                # Weighted draw, not the mode — see _population_distributions.
                full[dim] = _population_draw(dist_att, dim, sk, seed) or modal[dim]
                per_dim_quality[dim] = "population_draw"

        attitudes, beliefs = _attitudes_to_fields(full, source, per_dim_quality)
        merged = dict(sk)
        merged["attitudes"] = attitudes
        merged["beliefs"] = beliefs
        merged["attitude_match_quality"] = quality
        # Material circumstances ride the SAME donor, so the persona stays internally
        # coherent. Missing fields fall back to the population mode and are flagged
        # per-field, exactly as attitudes are — a modal fill is never passed off as a match.
        circ_rows = []
        donor_circ = donor.get("circumstances") or {}
        for field in ada.CIRCUMSTANCE_VOCAB:
            value = donor_circ.get(field)
            field_quality = quality
            if value is None:
                value = _population_draw(dist_circ, field, sk, seed) or modal_circ.get(field)
                field_quality = "population_draw"
            if value is None:
                continue  # nothing measured anywhere (synthetic fixture) — emit nothing
            circ_rows.append({
                "field": field,
                "value": value,
                "source": source,
                "match_quality": field_quality,
            })
        if circ_rows:
            merged["circumstances"] = circ_rows
        out.append(merged)
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from persona_sampler import sample_skeletons

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    try:
        sks = sample_skeletons(n, seed=1)
    except FileNotFoundError as e:
        print(f"SKIP live QLFS ({e}); using hand-built skeletons.")
        sks = [
            {"age": 33, "gender": "Female", "province": "KwaZulu-Natal",
             "education": "Secondary completed", "employment_status": "Other not economically active"},
            {"age": 22, "gender": "Male", "province": "Gauteng",
             "education": "Secondary not completed", "employment_status": "Employed"},
            {"age": 67, "gender": "Female", "province": "Eastern Cape",
             "education": "Primary", "employment_status": "Other not economically active"},
        ]
    for p in fuse_attitudes(sks, seed=1):
        print(f"\n{p.get('gender')} {p.get('age')} {p.get('province')} "
              f"[{p.get('attitude_match_quality')}]")
        for a in p["attitudes"]:
            print(f"   {a['topic']:22} {a['stance']:14} ({a['match_quality']})")
        for b in p["beliefs"]:
            print(f"   belief: {b}")
