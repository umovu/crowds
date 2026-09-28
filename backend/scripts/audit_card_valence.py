"""audit_card_valence — do the mechanism cards only ever let a group say no?

LLM-free, read-only. Reads the labels `cache_card_valence.py` fetched into
`scripts/out/card_valence.json` and counts them per persona archetype, so the
"this tool skews negative" complaint becomes a number you can re-measure after
adding cards.

A segment's skew is barriers as a share of the sentences that point either way
(neutrals are excluded — they carry no direction). 1.00 means that group has
nothing in the cards but reasons to refuse.

Usage:
    python audit_card_valence.py [--min-confidence 0.5] [--by-card]
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..")
LIB = os.path.join(BACKEND, "app", "data", "persona_library", "personas.json")
LABELS = os.path.join(HERE, "out", "card_valence.json")

_spec = importlib.util.spec_from_file_location(
    "mcs_valence", os.path.join(BACKEND, "app", "services", "mechanism_card_service.py"))
mcs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcs)


def tally(labels, cards, min_confidence):
    """archetype -> Counter of valences, plus the same per card."""
    tags = {c["id"]: (c.get("segment_tags") or []) for c in cards}
    by_segment = collections.defaultdict(collections.Counter)
    by_card = collections.defaultdict(collections.Counter)
    skipped = 0
    for row in labels.values():
        if (row.get("confidence") or 0) < min_confidence:
            skipped += 1
            continue
        valence = row.get("valence")
        by_card[row["card"]][valence] += 1
        for archetype in tags.get(row["card"], []):
            by_segment[archetype][valence] += 1
    return by_segment, by_card, skipped


def tally_by_person(labels, people, min_confidence):
    """The same count, but over what each persona is actually handed.

    `tally` follows segment_tags — the old label binding. This one calls
    mechanism_card_service.cards_for_persona, so it sees the claims that survive
    situation matching and each claim's own needs rule, weighted by how many real
    people in the library get them.
    """
    lookup = {(r["card"], r["text"]): r for r in labels.values()}
    by_segment = collections.defaultdict(collections.Counter)
    reached = collections.Counter()
    for person in people:
        archetype = person.get("actor_archetype")
        bound = mcs.cards_for_persona(person)
        if bound:
            reached[archetype] += 1
        for card in bound:
            for claim in card.get("claims") or []:
                texts = [claim.get("text", "")] + list(claim.get("objections") or [])
                for text in texts:
                    row = lookup.get((card["id"], text))
                    if row and (row.get("confidence") or 0) >= min_confidence:
                        by_segment[archetype][row["valence"]] += 1
    return by_segment, reached


def skew(counts):
    """Barriers as a share of the directional sentences; None when there are none."""
    directional = counts["barrier"] + counts["motivator"]
    return counts["barrier"] / directional if directional else None


def line(name, counts, extra=""):
    value = skew(counts)
    shown = "  n/a" if value is None else f"{value:5.2f}"
    return (f"  {name:<28} {sum(counts.values()):>6} {counts['barrier']:>8}"
            f" {counts['motivator']:>10} {counts['neutral']:>8} {shown}{extra}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-confidence", type=float, default=0.0,
                    help="ignore labels Jev was less sure about than this")
    ap.add_argument("--by-card", action="store_true", help="also break it down per card")
    ap.add_argument("--by-person", action="store_true",
                    help="count what personas are actually handed (situation matching) "
                         "instead of what segment_tags label")
    args = ap.parse_args()

    if not os.path.exists(LABELS):
        raise SystemExit(f"no labels yet — run cache_card_valence.py first ({LABELS})")
    labels = json.load(open(LABELS, encoding="utf-8"))
    cards = list(mcs.load_cards())
    people = json.load(open(LIB, encoding="utf-8"))["personas"]
    population = collections.Counter(p.get("actor_archetype") for p in people)

    by_segment, by_card, skipped = tally(labels, cards, args.min_confidence)
    reached = None
    if args.by_person:
        by_segment, reached = tally_by_person(labels, people, args.min_confidence)

    header = (f"  {'segment':<28} {'lines':>6} {'barrier':>8} {'motivator':>10}"
              f" {'neutral':>8} {'skew':>5}  people")
    print(f"\n{len(labels)} labelled sentence(s) over {len(cards)} card(s)"
          + (f", {skipped} below confidence {args.min_confidence}" if skipped else ""))
    binding = "what personas are handed" if args.by_person else "segment_tags"
    print(f"\nPER SEGMENT — barriers as a share of what points either way ({binding})\n")
    print(header)
    ordered = sorted(by_segment.items(),
                     key=lambda kv: (skew(kv[1]) is not None, skew(kv[1]) or 0),
                     reverse=True)
    for archetype, counts in ordered:
        share = population[archetype] / len(people) * 100 if people else 0
        extra = f"  {population[archetype]:>4} ({share:4.1f}%)"
        if reached is not None:
            extra += f"  {reached[archetype]:>4} reached"
        print(line(archetype, counts, extra))

    starved = [a for a, c in ordered if c["motivator"] == 0 and c["barrier"]]
    if starved:
        print("\nOnly reasons to refuse, never a reason to want it:")
        for archetype in starved:
            print(f"  - {archetype} ({population[archetype]} people in the library)")

    uncovered = sorted(set(population) - set(by_segment))
    if uncovered:
        print("\nNo labelled card sentences at all:")
        for archetype in uncovered:
            print(f"  - {archetype} ({population[archetype]} people)")

    if args.by_card:
        print("\nPER CARD\n")
        print(header.rsplit("  people", 1)[0].replace("segment", "card"))
        for card_id, counts in sorted(by_card.items(),
                                      key=lambda kv: skew(kv[1]) or 0, reverse=True):
            print(line(card_id, counts))
    print()


if __name__ == "__main__":
    main()
