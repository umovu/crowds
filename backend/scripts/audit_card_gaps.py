"""audit_card_gaps — which kinds of persona does no card speak for, topic by topic?

The card shopping list should come from the library, not from where papers happen to
exist. For each topic this takes one realistic pitch, finds the personas who arrive with
no research card for it, and describes them by their OWN measured facts (medical aid,
car, poverty, housing, work…). The biggest uncovered groups are what to find papers for.

It also reports the second gap, variety: groups that do get a card but all get the same
one. A room of them reasons alike however well they are covered.

Read-only and LLM-free unless --typed, which asks the typed reader once per pitch, the
way production routes cards (FUB_TYPED_CARDS). Re-run after every card that lands.

Usage:
    python audit_card_gaps.py                 # topic tags only
    python audit_card_gaps.py --typed         # route the way production does
    python audit_card_gaps.py --topic health  # one topic
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
LIB = os.path.join(BACKEND, "app", "data", "persona_library", "personas.json")
sys.path.insert(0, BACKEND)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.environ.get("DOTENV_PATH") or os.path.join(BACKEND, "..", ".env"))

_DWELLING = {"house_own_stand": "house", "traditional_dwelling": "traditional",
             "flat": "flat/complex", "complex_house": "flat/complex",
             "backyard_room": "backyard/informal", "backyard_shack": "backyard/informal",
             "informal_settlement": "backyard/informal", "room_on_property": "backyard/informal"}
_POWER = {"always": "reliable", "most": "reliable", "half": "unreliable",
          "occasional": "unreliable", "never": "unreliable"}


def _derived(facts: dict, persona: dict) -> dict:
    """A few facts grouped so a segment is a kind of person, not a single answer."""
    out = dict(facts)
    out["housing"] = _DWELLING.get(facts.get("dwelling"), facts.get("dwelling"))
    out["power"] = _POWER.get(facts.get("electricity_reliability"), facts.get("electricity_reliability"))
    out["poverty"] = {"none": "comfortable", "low": "comfortable",
                      "moderate": "struggling", "high": "struggling"}.get(facts.get("lived_poverty"))
    out["car"] = {"own": "car", "household": "car", "none": "no car"}.get(facts.get("owns_vehicle"))
    out["parent"] = "parent" if facts.get("ghs_role") in ("guardian_parent", "gogo_guardian") else "not a parent"
    out["informal"] = {"True": "informal work"}.get(str(persona.get("informal")), "")
    out["area"] = {"Urban": "urban"}.get(facts.get("geotype"), "rural")
    return out


# topic -> (a realistic pitch, the persona facts that make someone a different kind of
# person for THIS topic). Facts are the library's own; nothing here is authored about
# a persona.
TOPICS = {
    "health": ("A private clinic chain wants to launch a R150 pay-per-visit nurse service, "
               "no medical aid needed.", ("medical_aid", "poverty", "area")),
    "money": ("Funeral cover for R80 a month, signed up on your phone, paying out in 48 hours.",
              ("poverty", "employment_status", "area")),
    "safety": ("A neighbourhood patrol funded by R100 a month per household, with a panic "
               "button app.", ("crime_fear", "housing", "poverty")),
    "power": ("A solar and battery kit rented for R299 a month that keeps the lights on "
              "when the power is out.", ("power", "poverty", "area")),
    "water": ("The municipality wants to install prepaid water meters, with some water free "
              "each month.", ("area", "housing", "poverty")),
    "transport": ("A shared ride to and from the taxi rank each morning for R15 a trip.",
                  ("car", "area", "employment_status")),
    "work": ("A programme that places people in paid jobs within six months, taking a small "
             "cut of the first pay.", ("employment_status", "age_band", "informal")),
    "housing": ("An app that matches backyard rooms with tenants, with a written lease and "
                "deposit held safely.", ("housing", "area", "poverty")),
    "education": ("An after-school maths programme for Grade 9s, R200 a month.",
                  ("parent", "poverty", "area")),
    "environment": ("A company collects your sorted recycling from your door each week.",
                    ("area", "poverty", "environment_priority")),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--typed", action="store_true")
    ap.add_argument("--topic")
    ap.add_argument("--top", type=int, default=6)
    args = ap.parse_args()
    os.environ["FUB_TYPED_CARDS"] = "1" if args.typed else "0"

    from app.services import card_subjects as cs
    from app.services import mechanism_card_service as mcs
    from app.services import panel_service as ps

    library = json.load(open(LIB, encoding="utf-8"))
    library = library["personas"] if isinstance(library, dict) else library
    people = []
    for p in library:
        q = dict(p)
        q["research_citations"] = [{"card_id": c["id"]} for c in mcs.cards_for_persona(p)]
        people.append((q, _derived(mcs.situation_facts(p), p)))

    for topic, (pitch, keys) in TOPICS.items():
        if args.topic and topic != args.topic:
            continue
        framed = ps.frame_pitch(pitch, "panel")
        cs.reset_memo()
        touched = mcs.subjects_touched(framed)
        held = []
        for q, facts in people:
            cards = mcs.cards_for_question(q, framed, touched=touched) or []
            held.append((facts, tuple(sorted(c["id"] for c in cards))))

        total = len(held)
        covered = sum(1 for _, c in held if c)
        by_group = collections.defaultdict(list)
        for facts, cards in held:
            group = " · ".join(str(facts.get(k) or "?") for k in keys if facts.get(k) != "")
            by_group[group].append(cards)

        print(f"\n=== {topic.upper()}  — {covered}/{total} get a card  "
              f"({len({c for _, c in held if c})} different card sets)")
        print(f"    pitch: {pitch}")
        print(f"    grouped by: {' · '.join(keys)}")
        gaps = sorted(((sum(1 for c in cs_ if not c), len(cs_), g) for g, cs_ in by_group.items()),
                      reverse=True)
        print("    UNCOVERED — no card at all")
        for missing, size, group in [x for x in gaps if x[0]][:args.top]:
            print(f"      {missing:4d} of {size:<4d} {group}")
        same = []
        for group, cs_ in by_group.items():
            got = [c for c in cs_ if c]
            if len(got) >= 5 and len(set(got)) == 1:
                same.append((len(got), group, ", ".join(got[0])))
        if same:
            print("    COVERED BUT ALL ALIKE — everyone in the group holds the same cards")
            for n, group, cards in sorted(same, reverse=True)[:args.top]:
                print(f"      {n:4d}  {group}   [{cards}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
