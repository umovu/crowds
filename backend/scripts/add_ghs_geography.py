"""Land METRO + DWELLING on the persona library from real GHS 2025 microdata.

Same discipline as the attitude import: the persona's own demographics pick a
pool of real surveyed people, and the new field is DRAWN from that pool's
population-weighted spread. No LLM, no network, deterministic for a given seed.

Why this exists: QLFS gives the skeletons a province and a 3-way geotype
(Urban/Traditional/Farms) and nothing finer, so every township, suburb and
small town collapses into one "Urban" blob. Rooms asked for a place can only be
tilted to a province. GHS carries the named metro (`Metro_code`, the same 17
Stats SA codes QLFS uses) and the dwelling type, which together give a room a
real place and give "township" a measured definition.

Honesty boundary: the drawn value is an IMPUTATION, not a fact about that
individual. Every written row carries the pool size and the drawn value's share
of that pool, so downstream can say how sure the placement is. The personas are
synthetic to begin with -- their province came from a weighted draw too -- so
this does not lower the standard. Inventing a suburb would.

Dry run by default: prints what would be written and changes nothing.
Pass --write to back up and apply.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import random
import re
import sys
import warnings
from typing import Dict, List, Optional, Tuple

import pandas as pd

warnings.filterwarnings("ignore")

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_HERE, "..")
GHS_PERSON = os.path.join(_ROOT, "data", "microdata", "ghs-2025-v1",
                          "ghs-2025-person-v1.dta")
GHS_HOUSEHOLD = os.path.join(_ROOT, "data", "microdata", "ghs-2025-v1",
                             "ghs-2025-household-v1.dta")
LIBRARY = os.path.join(_ROOT, "app", "data", "persona_library", "personas.json")
BACKUP = os.path.join(_ROOT, "app", "data", "persona_library",
                      "personas.backup-pre-ghs-geography.json")

# A pool smaller than this is too thin to draw a stable share from, so the
# matcher backs off a rung instead. 30 is where the sampled spreads stopped
# swinging on the seed.
MIN_POOL = 30

# GHS geotype is numeric; the labels are the same Stats SA 3-way the QLFS
# skeletons already carry, so one field name means one thing everywhere.
_GEOTYPE = {"1": "Urban", "2": "Traditional", "3": "Farms"}

# The 12 GHS dwelling types, collapsed onto slugs that describe the PLACE
# someone lives rather than the building's construction. Backyard room and
# backyard shack stay apart (very different rent, security and standing) but
# cluster/townhouse/semi-detached fold together -- that distinction is
# architectural, not social.
_DWELLING = {
    "Dwelling/house or brick/concrete block structure on a separate stand or yard or on a farm": "house_own_stand",
    "Traditional dwelling/hut/structure made of traditional materials": "traditional_dwelling",
    "Flat or apartment in a block of flats": "flat",
    "Cluster house in complex": "complex_house",
    "Townhouse (semi-detached house in complex)": "complex_house",
    "Semi-detached house": "complex_house",
    "Dwelling/house/flat/room in backyard": "backyard_room",
    "Informal dwelling/shack in backyard": "backyard_shack",
    "Informal dwelling/shack not in backyard, e.g. in an informal/squatter settlement or on a farm": "informal_settlement",
    "Room/flatlet on a property or a larger dwelling servants' quarters/granny flat": "room_on_property",
    "Caravan/tent": "other_dwelling",
    "OTHER DWELLING TYPE": "other_dwelling",
}

# What "township" means here, said out loud: an urban household in backyard or
# informal housing. It is a proxy -- GHS has no township flag -- but it is a
# MEASURED proxy, which is the most this data can honestly support.
_TOWNSHIP_DWELLINGS = {"backyard_room", "backyard_shack", "informal_settlement"}


def _strip(value: object) -> str:
    """GHS labels ship as '7. Gauteng', and Metro_code uses an en dash."""
    return re.sub(r"^\d+\.\s*", "", str(value)).replace("–", "-").strip()


def load_ghs() -> pd.DataFrame:
    """One row per GHS person aged 15+, with their household's housing.

    Numeric and labelled columns are read in separate passes for the same
    reason `persona_sampler._load` does it: a single categorical pass turns age
    and the weight into unusable category dtypes.
    """
    for path in (GHS_PERSON, GHS_HOUSEHOLD):
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"GHS microdata not found at {path}. Download the 2025 .dta "
                f"files from DataFirst into backend/data/microdata/ (gitignored).")

    num = pd.read_stata(GHS_PERSON, columns=["uqnr", "age", "person_wgt"],
                        convert_categoricals=False)
    lab = pd.read_stata(GHS_PERSON,
                        columns=["prov", "Sex", "Population", "geotype", "Metro_code"],
                        convert_categoricals=True)
    person = pd.concat([num.reset_index(drop=True), lab.reset_index(drop=True)], axis=1)

    household = pd.read_stata(GHS_HOUSEHOLD,
                              columns=["uqnr", "hsg_maind", "hsg_rdp"],
                              convert_categoricals=True)
    df = person.merge(household, on="uqnr", how="left")

    for col in ("prov", "Sex", "Population", "Metro_code", "geotype",
                "hsg_maind", "hsg_rdp"):
        df[col] = df[col].map(_strip)

    df["geo"] = df["geotype"].map(_GEOTYPE)
    df["dwelling"] = df["hsg_maind"].map(_DWELLING)
    df["rdp"] = df["hsg_rdp"].map({"Yes": "yes", "No": "no"})

    # 15+ matches the QLFS universe the skeletons were drawn from, and a row
    # with no weight or no housing answer cannot contribute to a draw.
    df = df[(df["age"] >= 15) & df["person_wgt"].notna() & (df["person_wgt"] > 0)]
    df = df[df["dwelling"].notna() & df["geo"].notna()]
    return df.reset_index(drop=True)


# Match rungs, widest last. The first rung whose pool clears MIN_POOL wins, so a
# common persona is matched on their whole demographic and a rare one still gets
# a real (if blunter) pool instead of a coin flip.
_RUNGS: List[Tuple[str, List[str]]] = [
    ("prov_geo_race_sex_age", ["province", "geotype", "race", "gender", "age"]),
    ("prov_geo_race_sex",     ["province", "geotype", "race", "gender"]),
    ("prov_geo_race",         ["province", "geotype", "race"]),
    ("prov_geo",              ["province", "geotype"]),
    ("prov",                  ["province"]),
    ("population",            []),
]


def match_pool(df: pd.DataFrame, persona: Dict) -> Tuple[pd.DataFrame, str]:
    """The most specific pool of real people like this persona that is big enough."""
    for quality, keys in _RUNGS:
        pool = df
        if "province" in keys:
            pool = pool[pool["prov"] == persona.get("province")]
        if "geotype" in keys:
            pool = pool[pool["geo"] == persona.get("geotype")]
        if "race" in keys:
            pool = pool[pool["Population"] == persona.get("race")]
        if "gender" in keys:
            pool = pool[pool["Sex"] == persona.get("gender")]
        if "age" in keys:
            age = persona.get("age")
            pool = pool[pool["age"].between(age - 5, age + 5)]
        if len(pool) >= MIN_POOL:
            return pool, quality
    return df, "population"


def spread(pool: pd.DataFrame, column: str) -> Dict[str, float]:
    """A pool's population-weighted spread over one column, as value -> share."""
    weights = pool.groupby(column, observed=True)["person_wgt"].sum()
    total = float(weights.sum())
    if not total:
        return {}
    return {str(value): float(weight) / total for value, weight in weights.items()}


def quotas(target: Dict[str, float], n: int) -> Dict[str, int]:
    """Split `n` seats across `target`'s shares by largest remainder.

    Largest remainder rather than rounding each share: rounding loses or gains
    seats and the leftovers have to go somewhere arbitrary anyway. This way the
    seats always sum to n and the ones that don't divide evenly go to whoever
    was closest to earning them.
    """
    if n <= 0 or not target:
        return {}
    exact = {value: share * n for value, share in target.items()}
    seats = {value: int(count) for value, count in exact.items()}
    left = n - sum(seats.values())
    order = sorted(exact, key=lambda value: (-(exact[value] - seats[value]), value))
    for value in order[:left]:
        seats[value] += 1
    return {value: count for value, count in seats.items() if count}


def allocate(personas: List[Dict], pools: List[pd.DataFrame], stratum: pd.DataFrame,
             column: str, rng: random.Random) -> List[Optional[Tuple[str, float]]]:
    """Assign one value per persona so the GROUP total matches real SA.

    Drawing each persona independently is unbiased but noisy: 101 Gauteng draws
    landed Tshwane at half its real size, which a room of "Pretoria people" would
    show immediately. So the stratum's real spread is turned into integer seats
    first, and each persona then draws from their OWN finely-matched spread
    restricted to the seats still going. Individual conditioning is kept (a farm
    worker still cannot draw a flat in a complex) while the totals come out right.

    Returns (value, that value's share of the persona's own pool) per persona, so
    the confidence written to the row is still personal, not the stratum's.
    """
    target = spread(stratum.dropna(subset=[column]), column)
    left = quotas(target, len(personas))
    if not left:
        return [None] * len(personas)

    # Hardest first: a persona whose own spread allows few values must pick before
    # the seats they could use are taken by someone with options.
    spreads = [spread(pool.dropna(subset=[column]), column) for pool in pools]
    order = sorted(range(len(personas)),
                   key=lambda i: (len([v for v in spreads[i] if v in left]),
                                  str(personas[i].get("id"))))

    out: List[Optional[Tuple[str, float]]] = [None] * len(personas)
    for i in order:
        own = {value: share for value, share in spreads[i].items()
               if left.get(value, 0) > 0}
        if own:
            total = sum(own.values())
            cut = rng.random() * total
            cumulative = 0.0
            for value in sorted(own, key=lambda v: (-own[v], v)):
                cumulative += own[value]
                if cut <= cumulative:
                    break
        else:
            # Their own spread has nothing left to give. Take the roomiest
            # remaining seat rather than inventing a value off-stratum.
            value = max(left, key=lambda v: (left[v], v))

        left[value] -= 1
        if not left[value]:
            del left[value]
        out[i] = (value, round(spreads[i].get(value, 0.0), 3))
    return out


# Metro and dwelling are allocated within (province, geotype): the province fixes
# which metros exist at all, and the geotype keeps traditional-area and farm
# people out of the metro cores they are not in. RDP is a yes/no on the same
# stratum for consistency.
_FIELDS = (("metro", "Metro_code"), ("dwelling", "dwelling"), ("rdp_housing", "rdp"))


def assign(personas: List[Dict], df: pd.DataFrame) -> List[List[Dict]]:
    """The circumstance rows every persona would gain. Deterministic.

    Seeded per stratum on the stratum's own name, not on position, so re-running
    after the library is re-ordered gives the same answer.
    """
    pools_and_quality = [match_pool(df, persona) for persona in personas]
    rows: List[List[Dict]] = [[] for _ in personas]

    groups: Dict[Tuple[str, str], List[int]] = collections.defaultdict(list)
    for i, persona in enumerate(personas):
        groups[(persona.get("province"), persona.get("geotype"))].append(i)

    for key, members in sorted(groups.items(), key=lambda kv: str(kv[0])):
        province, geotype = key
        stratum = df[(df["prov"] == province) & (df["geo"] == geotype)]
        if stratum.empty:
            stratum = df[df["prov"] == province]

        for field, column in _FIELDS:
            rng = random.Random(f"{province}|{geotype}|{field}")
            drawn = allocate([personas[i] for i in members],
                             [pools_and_quality[i][0] for i in members],
                             stratum, column, rng)
            for i, result in zip(members, drawn):
                if result is None:
                    continue
                value, share = result
                rows[i].append({
                    "field": field,
                    "value": value,
                    "source": "ghs_2025",
                    "match_quality": pools_and_quality[i][1],
                    "pool": len(pools_and_quality[i][0]),
                    "share": share,
                })
    return rows


def _report(personas: List[Dict], assigned: List[List[Dict]], df: pd.DataFrame) -> None:
    """Print the whole spread -- the point of the dry run is seeing this once."""
    def values(field: str) -> List[str]:
        return [r["value"] for rows in assigned for r in rows if r["field"] == field]

    def ghs_share(column: str) -> Dict[str, float]:
        weights = df.groupby(column, observed=True)["person_wgt"].sum()
        return {str(k): float(v) for k, v in (weights / weights.sum()).items()}

    def expected(column: str) -> Dict[str, float]:
        """What the library SHOULD show given its own province/geotype mix.

        Not the same as the national share: the library is 19% Western Cape
        where SA is 13%, so it will over-show Cape Town however well this
        script works. Printing both separates "the allocation is off" from
        "the library's province mix is off" -- two different jobs.
        """
        out: Dict[str, float] = collections.defaultdict(float)
        groups = collections.Counter((p.get("province"), p.get("geotype"))
                                     for p in personas)
        for (province, geotype), count in groups.items():
            stratum = df[(df["prov"] == province) & (df["geo"] == geotype)]
            if stratum.empty:
                stratum = df[df["prov"] == province]
            for value, share in spread(stratum.dropna(subset=[column]), column).items():
                out[value] += share * count / len(personas)
        return dict(out)

    print(f"\nGHS pool: {len(df):,} people aged 15+")
    print(f"Personas: {len(personas)}\n")

    print("MATCH QUALITY")
    quality = collections.Counter(r["match_quality"] for rows in assigned for r in rows
                                  if r["field"] == "metro")
    for name, count in quality.most_common():
        print(f"  {count:4d}  {name}")

    for field, column in (("metro", "Metro_code"), ("dwelling", "dwelling")):
        print(f"\n{field.upper()}   got / expected-for-this-library / real SA")
        counts = collections.Counter(values(field))
        want_here, want_sa = expected(column), ghs_share(column)
        total = sum(counts.values()) or 1
        for value, count in counts.most_common():
            got = count / total * 100
            here = want_here.get(value, 0.0) * 100
            sa = want_sa.get(value, 0.0) * 100
            flag = "  <-- allocation off" if abs(got - here) > 1.5 else (
                "  <-- library province mix" if abs(here - sa) > 2 else "")
            print(f"  {count:4d}  {got:5.1f}%  {here:5.1f}%  {sa:5.1f}%  {value}{flag}")

    township = sum(
        1 for rows in assigned
        if any(r["field"] == "dwelling" and r["value"] in _TOWNSHIP_DWELLINGS
               for r in rows)
    )
    print(f"\nTOWNSHIP PROXY (backyard/informal dwelling): {township} personas")

    shares = sorted(r["share"] for rows in assigned for r in rows
                    if r["field"] == "metro")
    if shares:
        print(f"CONFIDENCE: median drawn-metro share {shares[len(shares) // 2]:.2f}, "
              f"{sum(1 for s in shares if s >= 0.5)} of {len(shares)} on a majority metro")

    print("\nSAMPLE")
    for persona, rows in list(zip(personas, assigned))[:8]:
        summary = "  ".join(f"{r['field']}={r['value']} ({r['share']:.0%})" for r in rows)
        print(f"  {str(persona.get('name'))[:22]:<23} "
              f"{persona.get('province'):<14} {persona.get('geotype'):<12} {summary}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="back up the library and apply the rows (default: dry run)")
    args = parser.parse_args()

    df = load_ghs()
    with open(LIBRARY, encoding="utf-8") as handle:
        library = json.load(handle)
    personas = library["personas"]

    assigned = assign(personas, df)
    _report(personas, assigned, df)

    if not args.write:
        print("\nDry run. Nothing written. Re-run with --write to apply.")
        return 0

    with open(BACKUP, "w", encoding="utf-8") as handle:
        json.dump(library, handle, ensure_ascii=False, indent=1)
    print(f"\nBacked up to {os.path.basename(BACKUP)}")

    # Re-running replaces this source's rows rather than stacking a second set.
    for persona, rows in zip(personas, assigned):
        kept = [row for row in persona.get("circumstances") or []
                if row.get("source") != "ghs_2025"]
        persona["circumstances"] = kept + rows

    with open(LIBRARY, "w", encoding="utf-8") as handle:
        json.dump(library, handle, ensure_ascii=False, indent=1)
    print(f"Wrote {sum(len(r) for r in assigned)} rows onto {len(personas)} personas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
