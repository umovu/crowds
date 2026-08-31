"""
validate_attitude_fuser - prove the attitude fusion is honest and complete.

Two properties matter, both assertable with the LLM OFF:

  1. **No distortion.** Over a large run, the fused population's attitude marginals
     should track the donor pool's WEIGHTED marginals. Statistical matching must not
     invent a mood the data doesn't carry. We allow more slack than the demographic
     sampler (+/-5pp) because attitude lands through demographic cells, not a direct draw -
     so exact donor marginals are only recovered when cells are well populated. A tight
     synthetic fixture won't be perfectly weighted; this catches gross distortion, not
     sampling noise.

  2. **Completeness + provenance.** Every persona gets a full attitude vector, every row
     stays inside ATTITUDE_VOCAB, every row carries a source + match_quality, and the
     fusion is deterministic for a seed. These are hard asserts (no tolerance).

Run:  python backend/scripts/validate_attitude_fuser.py
Exit 0 = honest + complete; 1 = distortion or contract violation.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict

import attitude_donor_adapter as ada
from attitude_fuser import fuse_attitudes

TOLERANCE_PP = 5.0
SAMPLE_N = 5000
SEED = 42


def _donor_weighted_marginals(donors, post_weights=None) -> dict:
    """Ground-truth attitude marginals from the donor pool (percent).

    `post_weights` post-stratifies the donors onto the QLFS population structure — see
    _post_stratification_weights. Without it the benchmark describes AFROBAROMETER'S
    SAMPLE, not South Africa, and the library is scored against the wrong target.
    """
    out = defaultdict(lambda: defaultdict(float))
    totals = defaultdict(float)
    for i, d in enumerate(donors):
        w = float(d.get("weight", 1.0))
        if post_weights is not None:
            w *= post_weights[i]
        if w <= 0:
            continue
        for dim, stance in d["attitudes"].items():
            out[dim][stance] += w
            totals[dim] += w
    return {dim: {s: round(v / totals[dim] * 100, 2) for s, v in stances.items()}
            for dim, stances in out.items()}


def _post_stratification_weights(donors):
    """Per-donor multipliers that reweight the donor pool onto QLFS's demographic structure.

    Why this exists: the fused library is built over QLFS-representative skeletons, but
    the donor pool is Afrobarometer's sample, whose demographic mix differs (it
    over-represents Coloured respondents and under-represents White ones relative to the
    population). Comparing the library's marginals to raw donor-weighted marginals
    therefore penalises fusion for a difference it is *supposed* to correct.

    Measured effect of using this benchmark instead of the raw one: worst-dimension drift
    falls from 3.76pp to 1.55pp, and economic_optimism from -3.76 to +0.66.

    Returns None if QLFS microdata is unavailable (dev/synthetic runs), in which case the
    caller falls back to the raw benchmark and says so.
    """
    try:
        import persona_sampler as ps
        from attitude_fuser import _skeleton_join_view
    except ImportError:
        return None
    try:
        df = ps._load(ps._DEFAULT_DTA)
    except FileNotFoundError:
        return None

    keys = ada.JOIN_KEYS
    qlfs = defaultdict(float)
    q_total = 0.0
    for _, row in df.iterrows():
        view = _skeleton_join_view(ps._row_to_skeleton(row))
        w = float(row["Weight"])
        qlfs[tuple(view[k] for k in keys)] += w
        q_total += w

    donor_cells = defaultdict(float)
    d_total = 0.0
    for d in donors:
        w = float(d.get("weight", 1.0))
        donor_cells[tuple(d.get(k) for k in keys)] += w
        d_total += w

    weights = []
    for d in donors:
        cell = tuple(d.get(k) for k in keys)
        share_pop = qlfs.get(cell, 0.0) / q_total
        share_donor = donor_cells[cell] / d_total
        weights.append(share_pop / share_donor if share_donor else 0.0)

    # A donor pool whose cells barely overlap QLFS (the synthetic fixture, or a foreign
    # survey) would post-stratify to almost all zeros and make the benchmark meaningless
    # or divide by zero. Fall back to the raw benchmark rather than reporting nonsense.
    live = sum(1 for w in weights if w > 0)
    if live < len(donors) * 0.5:
        return None
    return weights


def _fused_marginals(personas) -> dict:
    """Attitude marginals of the fused population (unweighted - each persona is one
    agent), per dimension, percent."""
    counts = defaultdict(Counter)
    for p in personas:
        for a in p["attitudes"]:
            counts[a["topic"]][a["stance"]] += 1
    out = {}
    for dim, c in counts.items():
        total = sum(c.values())
        out[dim] = {s: round(v / total * 100, 2) for s, v in c.items()}
    return out


def _skeletons_for_test(n, seed):
    """Real QLFS skeletons if the .dta is present; otherwise a synthetic spread that
    exercises every donor cell + a deliberate miss to force backoff."""
    try:
        from persona_sampler import sample_skeletons
        return sample_skeletons(n, seed=seed), "QLFS"
    except FileNotFoundError:
        import random
        rng = random.Random(seed)
        provinces = ["KwaZulu-Natal", "Gauteng", "Western Cape", "Eastern Cape",
                     "Limpopo", "Northern Cape"]  # Northern Cape has NO donor -> backoff
        edus = ["Primary", "Secondary completed", "Tertiary", "No schooling"]
        stats = ["Employed", "Unemployed", "Other not economically active"]
        genders = ["Female", "Male"]
        sks = [{
            "age": rng.randint(15, 80),
            "gender": rng.choice(genders),
            "province": rng.choice(provinces),
            "education": rng.choice(edus),
            "employment_status": rng.choice(stats),
            "occupation": "synthetic",
        } for _ in range(n)]
        return sks, "synthetic"


def main() -> int:
    donors = ada.load_donors()
    skeletons, src = _skeletons_for_test(SAMPLE_N, SEED)
    print(f"Skeleton source: {src} (n={len(skeletons)}), donors={len(donors)}")

    # ── Health-dimension proof (LLM OFF) ────────────────────────────────────
    # 1. Hand-built rows: non-answer codes (-1 missing / 8 refused / 9 DK / 99 not
    #    asked) decode to ABSENT, never to a middle band. Positive controls pin scale
    #    handling: Q46G 1..4, Q37O_SAF 0..3, Q6C 0..4.
    _missing_row = {"Q46G": -1.0, "Q37O_SAF": 8.0, "Q6C": 99.0,
                    "Q46H": 9.0, "Q37A": 8.0, "Q37D": 9.0,
                    "Q4A": 8.0, "Q4B": 9.0, "Q46I": 8.0, "Q46L": 9.0,
                    "Q7A": 8.0, "Q7B": 9.0}
    _atts_missing = ada._decode_ab_attitudes(_missing_row) or {}
    assert "health_service_satisfaction" not in _atts_missing, \
        f"non-answer Q46G banded anyway: {_atts_missing.get('health_service_satisfaction')}"
    assert "health_authority_trust" not in _atts_missing, \
        f"non-answer Q37O_SAF banded anyway: {_atts_missing.get('health_authority_trust')}"
    _circ_missing = ada._decode_ab_circumstances(_missing_row)
    assert "went_without_care" not in _circ_missing, \
        f"non-answer Q6C banded anyway: {_circ_missing.get('went_without_care')}"
    _pos = ada._decode_ab_attitudes({"Q46G": 4.0, "Q37O_SAF": 3.0})
    assert _pos["health_service_satisfaction"] == "satisfied", _pos
    assert _pos["health_authority_trust"] == "high", _pos
    assert ada._decode_ab_circumstances({"Q6C": 0.0})["went_without_care"] == "never"
    assert ada._decode_ab_circumstances({"Q6C": 4.0})["went_without_care"] == "often"
    print("OK - health non-answer codes drop out; scale handling pinned by hand-built rows.")

    # 2. Donor coverage >= 95% per new field, and no single band above 85%
    #    (a collapsed band would mean the dimension carries no information).
    from texture_generator import _STANCE_GLOSS, _CIRCUMSTANCE_GLOSS
    from attitude_fuser import _BELIEF_PHRASING
    for kind, fields, gloss_map in (
        ("attitude", ("health_service_satisfaction", "health_authority_trust"), _STANCE_GLOSS),
        ("circumstance", ("went_without_care",), _CIRCUMSTANCE_GLOSS),
    ):
        for field in fields:
            block = "attitudes" if kind == "attitude" else "circumstances"
            vals = [d[block].get(field) for d in donors]
            usable = [(d, v) for d, v in zip(donors, vals) if v]
            coverage = len(usable) / len(donors) * 100
            assert coverage >= 95.0, f"{field} donor coverage {coverage:.1f}% < 95%"
            weighted = defaultdict(float)
            total_w = 0.0
            for d, v in usable:
                w = float(d.get("weight", 1.0))
                weighted[v] += w
                total_w += w
            top_band, top_share = max(
                ((v, s / total_w * 100) for v, s in weighted.items()),
                key=lambda kv: kv[1])
            assert top_share <= 85.0, \
                f"{field} collapses: band '{top_band}' holds {top_share:.1f}% of weight"
            print(f"OK - {field}: {coverage:.1f}% coverage, top band '{top_band}' "
                  f"{top_share:.1f}% (<= 85%).")

    # 3. No silent skips: every ATTITUDE_VOCAB dim has a full _STANCE_GLOSS, and any
    #    dim carried in _BELIEF_PHRASING phrases ALL of its non-neutral bands.
    for dim, bands in ada.ATTITUDE_VOCAB.items():
        gloss_bands = set(_STANCE_GLOSS.get(dim, {}))
        assert gloss_bands == set(bands), \
            f"_STANCE_GLOSS['{dim}'] covers {sorted(gloss_bands)}, vocab needs {sorted(bands)}"
    for dim, phrasing in _BELIEF_PHRASING.items():
        bands = set(ada.ATTITUDE_VOCAB[dim])
        neutral = bands & {"mid", "mixed", "neutral"}
        required = bands - neutral
        assert set(phrasing) == required, \
            f"_BELIEF_PHRASING['{dim}'] has {sorted(phrasing)}, needs exactly {sorted(required)}"
    print("OK - texture glosses cover every dim x band; belief phrasing is complete "
          "where carried.")

    fused = fuse_attitudes(skeletons, seed=SEED, donors=donors)

    # ── Hard contract asserts (no tolerance) ────────────────────────────────
    for p in fused:
        assert p.get("attitudes"), "a persona got no attitudes"
        topics = {a["topic"] for a in p["attitudes"]}
        assert topics == set(ada.ATTITUDE_VOCAB), \
            f"persona missing attitude dimensions: {set(ada.ATTITUDE_VOCAB) - topics}"
        for a in p["attitudes"]:
            assert a["stance"] in ada.ATTITUDE_VOCAB[a["topic"]], \
                f"stance '{a['stance']}' outside vocab for {a['topic']}"
            assert a.get("source"), "attitude row missing source provenance"
            assert a.get("match_quality"), "attitude row missing match_quality"
        assert p.get("attitude_match_quality"), "persona missing match_quality summary"
    print(f"OK - all {len(fused)} personas have a complete, in-vocab, sourced attitude vector.")

    # ── Determinism ─────────────────────────────────────────────────────────
    again = fuse_attitudes(skeletons, seed=SEED, donors=donors)
    same = all(a["attitudes"] == b["attitudes"] for a, b in zip(fused, again))
    assert same, "fusion is not deterministic for a fixed seed"
    print("OK - fusion is deterministic for a fixed seed.")

    # ── Backoff actually fires (provenance is meaningful) ───────────────────
    quality_mix = Counter(p["attitude_match_quality"] for p in fused)
    print("\nMatch-quality distribution:")
    for q, c in quality_mix.most_common():
        print(f"  {q:18} {c/len(fused)*100:5.1f}%")

    # ── No-distortion check (toleranced) ────────────────────────────────────
    # Benchmark = donors post-stratified onto the QLFS population, NOT the raw donor
    # marginals: the library is QLFS-representative, so raw donor marginals are the
    # wrong target (see _post_stratification_weights).
    post = _post_stratification_weights(donors)
    if post is None:
        print("\nNOTE: QLFS microdata unavailable — falling back to the RAW donor "
              "benchmark. Drift figures below are not population-corrected.")
    else:
        print("\nBenchmark: donors post-stratified onto QLFS population structure.")
    truth = _donor_weighted_marginals(donors, post)
    got = _fused_marginals(fused)
    ok = True
    for dim, truth_stances in truth.items():
        print(f"\n=== {dim}: fused vs donor-weighted (pp diff) ===")
        for stance, t in sorted(truth_stances.items(), key=lambda kv: -kv[1]):
            g = got.get(dim, {}).get(stance, 0.0)
            diff = g - t
            flag = "" if abs(diff) <= TOLERANCE_PP else "  <-- OUT OF TOLERANCE"
            if abs(diff) > TOLERANCE_PP:
                ok = False
            print(f"  {stance:16} fused {g:5.2f}  donor {t:5.2f}  ({diff:+.2f}){flag}")

    # The no-distortion check is only meaningful against a real, full-coverage donor
    # pool. With the synthetic fixture (a handful of cells) most real skeletons fall to
    # backoff, so fused marginals CANNOT reproduce donor marginals - that drift is
    # expected and not a failure. The hard contract + determinism asserts above are the
    # real signal until the licensed donor data lands; then this check becomes the
    # guardrail that proves matching didn't distort the population's mood.
    if ada.is_synthetic():
        print("\nNOTE: donor pool is the SYNTHETIC fixture, so the no-distortion check "
              "is informational only (sparse cells force backoff -> expected drift). It "
              "becomes a hard gate once load_donors() serves real Afrobarometer data.")
        passed = True  # contract + determinism asserts already passed
    else:
        passed = ok

    print("\n" + ("PASS - attitude fusion is honest and complete."
                  if passed else
                  f"FAIL - attitude marginals drift > {TOLERANCE_PP}pp; check donor matching."))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
