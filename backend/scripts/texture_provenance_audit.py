"""Texture-provenance audit: find empirical claims in persona texture (voice_guide,
background_story) that no survey field licenses.

Extends the repo's hard rule — "numbers never come from the LLM or from memory" —
to non-numeric empirical claims: a referent like load-shedding may only appear in a
persona's texture if some field in that persona's REAL record licenses it. Purely
deterministic; no LLM.

Each rule maps a texture pattern -> a license function over the persona record.
license(persona) returns True when the record contains data that justifies the
referent, False when the claim is unbacked (LLM-memory texture).

Run:
  D:/Fub-agentsociety/backend/.venv/Scripts/python.exe backend/scripts/texture_provenance_audit.py
"""

import json
import re
from collections import Counter

PERSONAS = "D:/Fub-agentsociety/backend/app/data/persona_library/personas.json"


def _attitude(p, topic):
    for a in p.get("attitudes") or []:
        if a.get("topic") == topic:
            return a.get("stance")
    return None


# pattern -> (label, license_fn, licensing_field_description)
RULES = [
    (
        r"load[- ]?shedding",
        "load-shedding",
        lambda p: False,  # no electricity-supply field exists in the record
        "NONE — no electricity-supply/outage field in persona record",
    ),
    (
        r"water outage|taps? run dry|water (cuts?|interruption)|no water",
        "water-outage",
        lambda p: False,  # no water-interruption field exists in the record
        "NONE — no water-interruption field in persona record",
    ),
    (
        r"crime|gang|robbery|hijack|break-?in|streetlight",
        "crime",
        lambda p: _attitude(p, "crime_fear") in ("high", "moderate"),
        "attitudes.crime_fear (high/moderate)",
    ),
    (
        r"taxi",
        "taxi",
        # a real commute or urban geotype loosely licenses taxi talk
        lambda p: bool(p.get("time_to_school")) or p.get("geotype") == "Urban",
        "time_to_school or geotype=Urban",
    ),
    (
        r"stokvel|society money",
        "stokvel",
        lambda p: False,  # no savings-group field exists in the record
        "NONE — no savings-group field in persona record",
    ),
    (
        r"grant|sassa",
        "grant",
        lambda p: bool(p.get("receives_grant")),
        "receives_grant",
    ),
    (
        r"data (costs?|bundle|prices?)|airtime",
        "data/airtime",
        lambda p: p.get("internet_at_home") is not None,
        "internet_at_home surveyed",
    ),
]


def main():
    with open(PERSONAS, encoding="utf-8") as f:
        raw = json.load(f)
    recs = raw if isinstance(raw, list) else raw.get("personas", raw)

    unlicensed = Counter()
    licensed = Counter()
    per_persona_hits = []
    name_mismatches = []

    for p in recs:
        text = " ".join(
            str(p.get(k) or "")
            for k in ("voice_guide", "background_story", "behavioral_tendencies", "persona")
        )
        hits = []
        for pat, label, lic, _desc in RULES:
            if re.search(pat, text, re.I):
                if lic(p):
                    licensed[label] += 1
                else:
                    unlicensed[label] += 1
                    hits.append(label)
        if hits:
            per_persona_hits.append((p.get("name"), p.get("actor_archetype"), hits))

        # Bonus deterministic check: voice_guide referring to a different name
        # (library-build sibling of the runtime "Thandi" mode-collapse bug).
        vg = p.get("voice_guide") or ""
        first = (p.get("name") or "").split()[0]
        m = re.match(r"([A-Z][a-z]+) speaks", vg)
        if m and first and m.group(1) not in (first, "She", "He", "They"):
            name_mismatches.append((p.get("name"), m.group(1)))

    n = len(recs)
    print(f"{n} personas audited\n")
    print("UNLICENSED texture claims (no survey field backs the referent):")
    for label, c in unlicensed.most_common():
        desc = next(d for _, l, _, d in RULES if l == label)
        print(f"  {c:4d} ({c / n * 100:4.1f}%)  {label:<14} license would be: {desc}")
    print("\nLICENSED texture claims (survey field backs it):")
    for label, c in licensed.most_common():
        print(f"  {c:4d} ({c / n * 100:4.1f}%)  {label}")

    print(f"\nPersonas carrying >=1 unlicensed claim: "
          f"{len(per_persona_hits)} / {n} ({len(per_persona_hits) / n * 100:.1f}%)")

    print(f"\nVoice-guide name mismatches: {len(name_mismatches)}")
    for name, wrong in name_mismatches:
        print(f"  record '{name}' -> guide says '{wrong} speaks'")

    out = {
        "personas": n,
        "unlicensed": dict(unlicensed),
        "licensed": dict(licensed),
        "personas_with_unlicensed": len(per_persona_hits),
        "name_mismatches": name_mismatches,
    }
    with open("backend/scripts/texture_provenance_audit_output.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("\nFull output -> backend/scripts/texture_provenance_audit_output.json")


if __name__ == "__main__":
    main()
