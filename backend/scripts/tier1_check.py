"""Tier 1 foundation check: does a selected room look like South Africa?

LLM-free. Draws real casts via select_for_query and tallies them against
published Stats SA GHS 2024 marginals. See CALIBRATION_TESTS.md section 1.

    python scripts/tier1_check.py
"""
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.persona_retrieval import select_for_query

ROOM_SIZE = 30
ROOMS = 40
QUERY = "a new service for South Africans"

# Stats SA GHS 2024 (released May 2025). Verify before relying on these.
KEY = {
    "medical_aid": ("individuals covered by medical aid", 15.5),
    "receives_grant": ("individuals receiving a social grant", 40.1),
    "internet_at_home": ("household internet by any means", 82.1),
    "computer_in_home": ("household with a computer", 22.0),
}
PROVINCE_KEY = {
    "Western Cape": 25.4,
    "Gauteng": 21.3,
    "KwaZulu-Natal": 10.2,
    "Limpopo": 10.0,
}


def main() -> None:
    yes, tot, missing = collections.Counter(), collections.Counter(), collections.Counter()
    prov = collections.defaultdict(lambda: [0, 0])
    bank_yes = bank_n = 0

    for seed in range(ROOMS):
        for p in select_for_query(ROOM_SIZE, QUERY, seed=seed):
            for field in KEY:
                if field in p:
                    tot[field] += 1
                    yes[field] += bool(p[field])
                else:
                    missing[field] += 1
            if "medical_aid" in p:
                slot = prov[p["province"]]
                slot[1] += 1
                slot[0] += bool(p["medical_aid"])
            for c in p.get("circumstances", []):
                if c["field"] == "owns_bank_account":
                    bank_n += 1
                    bank_yes += c["value"] == "own"

    seats = ROOMS * ROOM_SIZE
    print(f"{ROOMS} rooms x {ROOM_SIZE} = {seats} seats\n")
    print(f"{'measure':34} {'sim':>7} {'key':>7} {'gap':>8}  coverage")
    for field, (label, target) in KEY.items():
        if not tot[field]:
            print(f"{label:34} {'no data':>7}")
            continue
        pct = 100 * yes[field] / tot[field]
        print(
            f"{label:34} {pct:6.1f}% {target:6.1f}% {pct - target:+7.1f}pp"
            f"  {tot[field]}/{seats} seats carry the field"
        )
    if bank_n:
        print(f"{'owns a bank account':34} {100 * bank_yes / bank_n:6.1f}% {'n/a':>7}"
              f" {'':>8}  {bank_n}/{seats}")

    print("\nmedical aid gradient by province")
    for name, (covered, n) in sorted(prov.items(), key=lambda i: -i[1][1]):
        target = PROVINCE_KEY.get(name)
        tag = f"(key {target}%)" if target else ""
        print(f"  {name:16} {covered:4}/{n:<4} = {100 * covered / n:5.1f}%  {tag}")


if __name__ == "__main__":
    main()
