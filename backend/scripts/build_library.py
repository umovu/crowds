"""
build_library — run the offline persona factory and write the persona library.

Pipeline: sample_skeletons (QLFS, weighted) → map_skeletons (honest archetype) →
generate_texture (English-only LLM surface) → stable id → personas.json.

This is the one expensive step (texture = Plus-tier LLM, once per persona). Run it
offline to build/refresh the library; the hosted app then reads personas.json (via
PersonaLibrary) and never pays texture cost per user.

Each persona gets a STABLE id (hash of its frozen skeleton + build seed) so rebuilds
are reproducible and a given persona keeps its id across runs — important once the
library is referenced by id from sims.

Run:  python backend/scripts/build_library.py [N] [--seed S] [--out path]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from persona_sampler import sample_skeletons, sample_teacher_skeletons
from archetype_mapper import map_skeletons
from attitude_fuser import fuse_attitudes
from ghs_adapter import sample_education_skeletons
import attitude_donor_adapter as ada
import texture_generator as tg

_DEFAULT_OUT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "app", "data", "persona_library", "personas.json")
)

# Fields that define a persona's stable identity hash. Texture (name etc.) is NOT
# included so a re-run with the same skeleton+seed keeps the same id even if the LLM
# phrases the texture slightly differently.
_ID_FIELDS = ["age", "gender", "province", "education", "occupation",
              "employment_status", "informal", "industry", "marriage_status",
              "is_neet", "actor_archetype"]

# Education-build distinguishers. Included in the hash ONLY when present, so
# civic personas keep their existing ids while two same-age learners in the same
# province still get distinct identities.
_EDU_ID_FIELDS = ["ghs_role", "current_grade", "monthly_household_income_rand",
                  "learners_in_household", "geotype", "home_language"]


def _stable_id(persona: dict, seed: int) -> str:
    payload = {k: persona.get(k) for k in _ID_FIELDS}
    for k in _EDU_ID_FIELDS:
        if persona.get(k) is not None:
            payload[k] = persona.get(k)
    payload["_seed"] = seed
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def build(
    n: int,
    seed: int,
    out_path: str,
    allow_synthetic_attitudes: bool = False,
    learners: int = 0,
    guardians: int = 0,
    teachers: int = 0,
    append: bool = False,
) -> int:
    print(f"Building persona library: n={n}, learners={learners}, guardians={guardians}, "
          f"teachers={teachers}, seed={seed}, append={append}")

    # Refuse to ship a library built on the synthetic attitude fixture unless explicitly
    # forced — fake moods grounded in nothing are worse than no attitudes. Pass
    # --allow-synthetic-attitudes only for dev/preview builds.
    if ada.is_synthetic() and not allow_synthetic_attitudes:
        print(
            "REFUSING: attitude donor pool is the SYNTHETIC fixture (not real licensed "
            "microdata). A shipped library must not carry invented attitudes. Source the "
            "Afrobarometer R9 SA data and wire load_donors(), or pass "
            "--allow-synthetic-attitudes for a dev/preview build.",
            file=sys.stderr,
        )
        return 2

    mapped = []

    if n > 0:
        skeletons = sample_skeletons(n, seed=seed)
        # Fuse measured attitudes onto each skeleton by demographic donor matching BEFORE
        # archetype/texture, so attitudes are part of the fixed identity the LLM only styles.
        fused = fuse_attitudes(skeletons, seed=seed)
        mapped.extend(map_skeletons(fused, seed=seed))

    # Education roles (GHS + QLFS teacher proxy). Their archetype is known from the
    # data itself — the adapter knows who's a learner/guardian — so the civic
    # archetype mapper's heuristics are deliberately bypassed.
    edu_skeletons = []
    if learners > 0 or guardians > 0:
        edu_skeletons.extend(sample_education_skeletons(
            n_learners=learners, n_guardians=guardians, seed=seed))
    if teachers > 0:
        edu_skeletons.extend(sample_teacher_skeletons(teachers, seed=seed))
    if edu_skeletons:
        for sk in edu_skeletons:
            sk["actor_archetype"] = sk.get("ghs_role") or "educator"
        # Role-aware donor pools: learners fuse against student respondents,
        # educators against teacher-class professionals; guardians (and any other
        # role) stay on the full pool. Provenance records which pool donated.
        groups = {}
        for sk in edu_skeletons:
            role = sk["actor_archetype"]
            key = role if role in ("learner", "educator") else "_general"
            groups.setdefault(key, []).append(sk)
        for key, group in groups.items():
            pool, suffix = ada.donor_pool_for_role(None if key == "_general" else key)
            source = f"afrobarometer_r9_sa:{suffix}" if suffix else None
            mapped.extend(fuse_attitudes(group, seed=seed, donors=pool, source=source))

    print(f"Generating English-only texture for {len(mapped)} personas (LLM, offline)...")
    client = tg.LLMClient()
    # Shared name state: names come from a curated pool (not the LLM) and must be
    # unique across the whole library. Seed the used-set with any existing names
    # when appending, so new personas never collide with already-built ones.
    name_rng = random.Random(seed)
    used_names: set = set()
    if append and os.path.exists(out_path):
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                for ep in json.load(f).get("personas", []):
                    nm = (ep.get("name") or "").strip().lower()
                    if nm:
                        used_names.add(nm)
        except Exception:  # noqa: BLE001 — best-effort seed; collisions still resolved downstream
            pass
    personas = []
    for i, sk in enumerate(mapped):
        try:
            p = tg.generate_texture(sk, client=client, used_names=used_names, rng=name_rng)
        except Exception as e:  # noqa: BLE001
            print(f"  [skip {i}] {e}", file=sys.stderr)
            continue
        p["id"] = _stable_id(p, seed)
        p["source_entity_type"] = "library_persona"
        personas.append(p)
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(mapped)}")

    # De-dup by id (identical skeleton+archetype collapses to one library entry).
    by_id = {p["id"]: p for p in personas}

    # Append mode: merge into the existing library, keeping already-textured
    # personas (their texture cost real tokens — never re-pay or overwrite it).
    if append and os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8") as f:
            existing = json.load(f).get("personas", [])
        merged = {p["id"]: p for p in existing}
        new_count = sum(1 for pid in by_id if pid not in merged)
        merged.update({pid: p for pid, p in by_id.items() if pid not in merged})
        unique = list(merged.values())
        print(f"Append: {len(existing)} existing + {new_count} new")
    else:
        unique = list(by_id.values())

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "seed": seed, "count": len(unique), "personas": unique},
                  f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(unique)} personas → {out_path}")
    return len(unique)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("n", nargs="?", type=int, default=50,
                    help="civic personas to sample from QLFS (0 for an education-only build)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=_DEFAULT_OUT)
    ap.add_argument("--learners", type=int, default=0,
                    help="GHS learner personas (15-18, in the school system)")
    ap.add_argument("--guardians", type=int, default=0,
                    help="GHS guardian personas (parent/gogo split follows the data)")
    ap.add_argument("--teachers", type=int, default=0,
                    help="QLFS educator-role personas (role assigned, marked in provenance)")
    ap.add_argument("--append", action="store_true",
                    help="merge into the existing library instead of overwriting it")
    ap.add_argument("--allow-synthetic-attitudes", action="store_true",
                    help="Build even though attitudes come from the synthetic fixture "
                         "(dev/preview only — do not ship).")
    args = ap.parse_args()

    # Load root .env so LLM_* is available when run as a standalone script.
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")))
    except Exception:
        pass

    rc = build(args.n, args.seed, args.out,
               allow_synthetic_attitudes=args.allow_synthetic_attitudes,
               learners=args.learners, guardians=args.guardians,
               teachers=args.teachers, append=args.append)
    return 2 if rc == 2 else 0  # 2 = refused (synthetic attitudes); else success


if __name__ == "__main__":
    sys.exit(main())
