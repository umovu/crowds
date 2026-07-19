"""Role x fee-tier segmentation across the persona library distribution.

Splits the old binary "fee-paying" segment along two axes the data actually
supports (worktree experiment — main repo panel_service untouched):

  role:      learner | guardian (guardian_parent + gogo_guardian)
  fee tier:  no_fee | low_fee (paid, <= R4,000/yr) | high_fee (> R4,000/yr)

The R4,000 threshold is derived from the library's observed band distribution
(clear gap between the <=R2,000 cluster and the R4,001+ cluster; matches the
no-fee/former-Model-C divide). A persona's tier is their HIGHEST attached band
(a guardian with one no-fee and one R8k learner is a high-fee household).

Everything is deterministic — GHS fee bands in, group memberships out.

Run:
  D:/Fub-agentsociety/backend/.venv/Scripts/python.exe backend/scripts/segment_groups.py
"""

import json
import re
from collections import defaultdict
from pathlib import Path

PERSONAS = Path("D:/Fub-agentsociety/backend/app/data/persona_library/personas.json")

LOW_FEE_CEILING = 4000  # R/yr — data-derived threshold (see module docstring)

ROLE = {
    "learner": "learner",
    "guardian_parent": "guardian",
    "gogo_guardian": "guardian",
}


def band_upper(band: str):
    """Upper rand bound of a GHS fee band string; 0 for 'No fees'; None if unparseable.
    'More than R80 000' has no upper bound -> a big sentinel."""
    if not band:
        return None
    if band.strip().lower() == "no fees":
        return 0
    nums = [int(re.sub(r"[^\d]", "", n)) for n in re.findall(r"R[\d\s, ]+", band)]
    if not nums:
        return None
    if band.strip().lower().startswith("more than"):
        return nums[-1] + 1
    return max(nums)


def fee_bands(p):
    bands = list(p.get("learner_fee_bands") or [])
    if p.get("fees_band"):
        bands.append(p["fees_band"])
    return bands


def fee_tier(p):
    """no_fee | low_fee | high_fee | None (no fee data). Highest attached band wins."""
    uppers = [u for u in (band_upper(b) for b in fee_bands(p)) if u is not None]
    if not uppers:
        return None
    top = max(uppers)
    if top == 0:
        return "no_fee"
    return "low_fee" if top <= LOW_FEE_CEILING else "high_fee"


def build_groups(recs):
    """{'learner_low_fee': [personas...], 'guardian_high_fee': [...], ...}"""
    groups = defaultdict(list)
    for p in recs:
        role = ROLE.get(p.get("actor_archetype"))
        tier = fee_tier(p)
        if role and tier:
            groups[f"{role}_{tier}"].append(p)
    return dict(groups)


def main():
    recs = json.loads(PERSONAS.read_text(encoding="utf-8"))
    if isinstance(recs, dict):
        recs = recs.get("personas", recs)

    groups = build_groups(recs)

    print(f"{'group':<22}{'n':>4}   members (name — top band — income R/m)")
    print("-" * 100)
    order = [f"{r}_{t}" for r in ("learner", "guardian")
             for t in ("no_fee", "low_fee", "high_fee")]
    for g in order:
        members = groups.get(g, [])
        print(f"{g:<22}{len(members):>4}")
        for p in sorted(members, key=lambda x: x.get("name", "")):
            top = max(fee_bands(p), key=lambda b: band_upper(b) or -1)
            inc = p.get("monthly_household_income_rand")
            inc_s = f"R{inc:,.0f}" if inc else "?"
            print(f"{'':<26}{p.get('name'):<28} {top:<18} {inc_s}")

    out = {
        "low_fee_ceiling_rand_per_year": LOW_FEE_CEILING,
        "groups": {g: [p.get("name") for p in ms] for g, ms in groups.items()},
        "sizes": {g: len(ms) for g, ms in groups.items()},
    }
    out_path = Path(__file__).parent / "segment_groups_output.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved -> {out_path}")


if __name__ == "__main__":
    main()
