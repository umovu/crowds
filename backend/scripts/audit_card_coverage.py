"""audit_card_coverage — are mechanism cards in proportion to the persona library?

LLM-free, read-only. For every persona, compares:
  * label   — the old binding: actor_archetype in the card's segment_tags, capped at 2
  * fit     — situation matching: the card's applies_when holds on the persona's own record

Reports each card's reach, who is left with no card, and each archetype's share of the
library next to its share of card fits. The point is proportion: cards should follow
where the library's people are, not where papers happened to exist.

Usage:
    python audit_card_coverage.py [--drafts]   # --drafts also counts docs/extraction/*.card.json
"""
from __future__ import annotations

import argparse
import collections
import glob
import importlib.util
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..")
LIB = os.path.join(BACKEND, "app", "data", "persona_library", "personas.json")
DRAFTS = os.path.join(BACKEND, "..", "docs", "extraction")

_spec = importlib.util.spec_from_file_location(
    "mcs_coverage", os.path.join(BACKEND, "app", "services", "mechanism_card_service.py"))
mcs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcs)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drafts", action="store_true")
    args = ap.parse_args()

    people = json.load(open(LIB, encoding="utf-8"))["personas"]
    n = len(people)
    cards = list(mcs.load_cards())
    if args.drafts:
        for path in sorted(glob.glob(os.path.join(DRAFTS, "*.card.json"))):
            draft = json.load(open(path, encoding="utf-8"))
            if draft.get("claims") and draft["id"] not in {c["id"] for c in cards}:
                draft["_draft"] = True
                cards.append(draft)
    mcs._cache = cards

    label_reach, fit_reach = collections.Counter(), collections.Counter()
    no_label, no_fit = [], []
    arch = collections.Counter(p.get("actor_archetype") for p in people)
    fits_by_arch = collections.Counter()
    for p in people:
        labelled = [c for c in cards
                    if p.get("actor_archetype") in (c.get("segment_tags") or [])]
        labelled.sort(key=lambda c: (len(c.get("segment_tags") or []), c["id"]))
        labelled = labelled[:mcs.DEFAULT_CARD_CAP]
        facts = mcs.situation_facts(p)
        fitted = [c for c in cards if mcs.situation_match_strength(c, facts)]
        for c in labelled:
            label_reach[c["id"]] += 1
        for c in fitted:
            fit_reach[c["id"]] += 1
        if not labelled:
            no_label.append(p)
        if not fitted:
            no_fit.append(p)
        fits_by_arch[p.get("actor_archetype")] += len(fitted)

    print(f"personas: {n}")
    print(f"  no card by label : {len(no_label):>3} ({100 * len(no_label) / n:.0f}%)")
    print(f"  no card by fit   : {len(no_fit):>3} ({100 * len(no_fit) / n:.0f}%)")
    print()
    print(f"{'card':<42}{'label':>7}{'fit':>7}")
    for c in sorted(cards, key=lambda c: -fit_reach[c["id"]]):
        tag = " (draft)" if c.get("_draft") else ""
        rules = "" if c.get("applies_when") else "  ← no applies_when"
        print(f"{(c['id'] + tag):<42}{label_reach[c['id']]:>7}{fit_reach[c['id']]:>7}{rules}")
    print()
    print("claims with their own rule: people reached, of the people the card fits")
    facts = [mcs.situation_facts(p) for p in people]
    for c in sorted(cards, key=lambda c: c["id"]):
        fits = [f for f in facts if mcs.situation_match_strength(c, f)]
        for i, claim in enumerate(c.get("claims") or []):
            if claim.get("needs"):
                reached = sum(1 for f in fits if mcs._clause_strength(claim["needs"], f))
                print(f"  {c['id']} claim {i}: {reached} of {len(fits)}")
    print()
    total_fits = sum(fits_by_arch.values()) or 1
    print(f"{'archetype':<34}{'people':>7}{'share':>7}{'fit share':>10}{'no card':>9}")
    none_by_arch = collections.Counter(p.get("actor_archetype") for p in no_fit)
    for a, count in arch.most_common():
        print(f"{str(a):<34}{count:>7}{100 * count / n:>6.0f}%"
              f"{100 * fits_by_arch[a] / total_fits:>9.0f}%{none_by_arch[a]:>9}")


if __name__ == "__main__":
    main()
