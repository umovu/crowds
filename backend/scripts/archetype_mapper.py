"""
archetype_mapper — assign an actor_archetype to a QLFS identity skeleton.

This is stage 2 of the persona-library build. actor_archetype is NOT cosmetic: in
the sim it drives activity_level (how often the agent speaks), event targeting
(affected_archetypes), the homophily feed, and downstream voice. A skeleton with no
archetype defaults to civic_moderate, so an unmapped library would be 200 identical
moderates — useless for stress-testing. This module turns the demographic skeleton
into a representative SPREAD of behaviors.

Two hard rules:

1. **Demographically-honest archetypes ONLY.** We assign only archetypes that census
   fields legitimately imply (livelihood + civic). We NEVER infer the behavioral-edge
   archetypes (violent_agitator, gang_member, opportunist_looter, conspiracy_spreader,
   criminal_opportunist) from demographics — there is no survey field for "incites
   violence", and rules like "young + unemployed + male → agitator" are false
   stereotypes and demographic profiling. Edge archetypes enter the library later from
   the user's scenario / research pipeline (the "leave a slot" decision), never here.

2. **Deterministic + LLM-free.** Same (skeleton, seed) → same archetype, so the build
   is reproducible and assertable with the model switched off. Variety comes from a
   weighted candidate set per skeleton, resolved by a seeded RNG — not from randomness
   at runtime.
"""

from __future__ import annotations

import hashlib
import json
import random
from typing import Dict, List, Optional, Tuple

# Archetypes this mapper is ALLOWED to emit. Anything outside this set is, by design,
# not demographically inferable and must come from scenario/research instead.
HONEST_ARCHETYPES = {
    "civic_moderate",
    "institutional_loyalist",
    "community_leader",
    "small_business_owner",
    "informal_trader",
    "unemployed_youth",
    "grant_dependent_survivor",
    "disillusioned_dropout",
    "economic_migrant",  # only when context supports it; not assigned from QLFS alone
}

# Behavioral-edge archetypes the mapper must NEVER assign from demographics.
# Listed explicitly so the validator can assert none of these ever appear.
FORBIDDEN_FROM_DEMOGRAPHICS = {
    "violent_agitator", "gang_member", "opportunist_looter",
    "conspiracy_spreader", "criminal_opportunist", "mob_follower",
    "community_protector", "whistleblower", "political_activist",
}

# Youth cutoff for unemployed_youth (SA youth defn is 15–34).
YOUTH_MAX_AGE = 34


def _base_occupation(occ: Optional[str]) -> str:
    """Strip the '(informal)' suffix to get the base occupation category."""
    if not occ:
        return ""
    return occ.replace(" (informal)", "").strip()


def _seeded_choice(candidates: List[Tuple[str, float]], skeleton: Dict, seed: int) -> str:
    """Pick one archetype from weighted candidates, deterministically.

    The RNG is seeded from (global seed + a stable hash of the skeleton) so the same
    skeleton always resolves the same way for a given build seed, while different
    skeletons spread across the candidate set.
    """
    if len(candidates) == 1:
        return candidates[0][0]
    key = json.dumps(skeleton, sort_keys=True, ensure_ascii=False)
    h = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed ^ h)
    labels = [c[0] for c in candidates]
    weights = [c[1] for c in candidates]
    return rng.choices(labels, weights=weights, k=1)[0]


def _candidates(skeleton: Dict) -> List[Tuple[str, float]]:
    """Return the weighted archetype candidate set for one skeleton.

    Weights are intentionally soft: the dominant archetype carries most of the mass,
    with minority alternatives so the population isn't mechanically uniform.
    """
    status = (skeleton.get("employment_status") or "").strip()
    informal = bool(skeleton.get("informal"))
    age = skeleton.get("age") or 0
    is_neet = bool(skeleton.get("is_neet"))
    occ = _base_occupation(skeleton.get("occupation"))
    industry = (skeleton.get("industry") or "")

    # ── Not economically active ─────────────────────────────────────────────
    # Pensioners, homemakers, the long-term withdrawn. Older → grant-dependent
    # survivor (old-age pension reality); younger NEET-but-not-jobseeking → the
    # disengaged path, not "youth" (which implies active job-seeking).
    if status in ("Other not economically active", "Discouraged job seeker"):
        if age >= 60:
            return [("grant_dependent_survivor", 0.85), ("civic_moderate", 0.15)]
        if is_neet and age <= YOUTH_MAX_AGE:
            return [("disillusioned_dropout", 0.6), ("unemployed_youth", 0.3),
                    ("grant_dependent_survivor", 0.1)]
        return [("grant_dependent_survivor", 0.5), ("disillusioned_dropout", 0.3),
                ("civic_moderate", 0.2)]

    # ── Unemployed (actively, by QLFS definition) ───────────────────────────
    if status == "Unemployed":
        if age <= YOUTH_MAX_AGE:
            return [("unemployed_youth", 0.8), ("disillusioned_dropout", 0.2)]
        return [("disillusioned_dropout", 0.5), ("grant_dependent_survivor", 0.3),
                ("civic_moderate", 0.2)]

    # ── Employed ─────────────────────────────────────────────────────────────
    if status == "Employed":
        # Informal sales/services → informal trader (the spaza/street-vendor reality).
        if informal and occ in ("Service workers and shop and market sales workers",
                                 "Elementary Occupation"):
            return [("informal_trader", 0.8), ("small_business_owner", 0.2)]
        # Any other informal work → mostly informal trader, some micro-business.
        if informal:
            return [("informal_trader", 0.6), ("small_business_owner", 0.3),
                    ("civic_moderate", 0.1)]
        # Managers / own-account formal → small business owner leans.
        if occ == "Legislators; senior officials and managers":
            return [("small_business_owner", 0.5), ("community_leader", 0.25),
                    ("institutional_loyalist", 0.25)]
        # Public-service-ish formal employment → institutional loyalist leans.
        if industry == "Community; social and personal services":
            return [("institutional_loyalist", 0.45), ("civic_moderate", 0.4),
                    ("community_leader", 0.15)]
        # Default formal worker → civic moderate, with civic-leadership minority.
        return [("civic_moderate", 0.7), ("institutional_loyalist", 0.15),
                ("community_leader", 0.15)]

    # ── Unknown / missing status → safe neutral default ─────────────────────
    return [("civic_moderate", 1.0)]


def assign_archetype(skeleton: Dict, seed: int = 0) -> str:
    """Assign one honest actor_archetype to a skeleton. Deterministic for (skeleton, seed)."""
    choice = _seeded_choice(_candidates(skeleton), skeleton, seed)
    # Defensive: never let a forbidden archetype escape, even via a future rule edit.
    if choice in FORBIDDEN_FROM_DEMOGRAPHICS:
        raise AssertionError(
            f"archetype_mapper tried to assign forbidden edge archetype '{choice}' "
            f"from demographics — this is a profiling bug, not allowed."
        )
    return choice


def map_skeletons(skeletons: List[Dict], seed: int = 0) -> List[Dict]:
    """Attach actor_archetype to each skeleton (returns new dicts, originals untouched).

    The result still has NO behavioral-edge archetypes and NO texture — it is the
    'ordinary population baseline'. Edge archetypes and name/voice come later.
    """
    out = []
    for sk in skeletons:
        merged = dict(sk)
        merged["actor_archetype"] = assign_archetype(sk, seed=seed)
        out.append(merged)
    return out


if __name__ == "__main__":
    from persona_sampler import sample_skeletons
    from collections import Counter
    mapped = map_skeletons(sample_skeletons(2000, seed=1), seed=1)
    dist = Counter(m["actor_archetype"] for m in mapped)
    total = sum(dist.values())
    for arch, n in dist.most_common():
        print(f"  {arch:28} {n/total*100:5.1f}%")
