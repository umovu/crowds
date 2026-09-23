"""propose_claim_needs — draft a per-claim `needs` rule for a human to review.

A card's `applies_when` says whose research this is. Its claims then all reach
whoever passed that gate. So a card about chronic care hands its "the clinic
lets me down" reasoning to someone who is satisfied with theirs, and a room of
twelve argues the same points for the same reasons.

`narrowed_to` has always been able to drop a claim the persona does not fit —
every claim carries `needs`, and `_clause_strength` checks it against their own
measured facts. All 98 shipped claims carry `needs: []`, so nothing is ever
dropped. This is the missing data, not missing code.

BUILD TIME ONLY. The typed reader drafts the rule here, once, and a human
approves it into the card. Nothing calls a model when a room runs: `needs` is a
rule over measured facts, checked with the model off, same answer every time.

What is asked
-------------
One `choice` question per fact, over that fact's real answers plus "any":

    "Which lived poverty does this finding depend on? Pick 'any' if it does not
     depend on this at all."

Asked as a noul per value instead ("this only holds for people with X"), the
reader returned nothing on any of 98 claims — every value sat under the
threshold. The choice shape with an explicit "any" escape is what produces a
usable answer, because it makes the reader spend its probability on one value
rather than spreading it over four.

Unsure means OPEN. Below --min-confidence the fact is left out of the rule, so
the claim keeps reaching everyone. A claim that reaches someone it does not
quite describe costs a little relevance; a claim dropped from someone it does
describe costs them their grounding on the question asked, which is the failure
this whole layer exists to prevent.

Usage:
    python propose_claim_needs.py                      # print proposals, write nothing
    python propose_claim_needs.py --write              # write them into the cards
    python propose_claim_needs.py --card chronic-care-repeat-cost-sa
    python propose_claim_needs.py --min-confidence 0.8
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
CARDS = os.path.join(BACKEND, "app", "data", "mechanism_cards")
sys.path.insert(0, BACKEND)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(BACKEND, "..", ".env"))
load_dotenv(os.path.join(BACKEND, ".env"))

from app.services import data_model as dm  # noqa: E402
from app.utils import typesafe_client as ts  # noqa: E402

# The facts a claim may be narrowed on. Deliberately short: a rule is only worth
# writing on something every persona in the library carries, and every extra
# field is another question the reader spends probability on.
FIELDS = [
    "owns_vehicle",
    "lived_poverty",
    "went_without_care",
    "geotype",
    "age_band",
    "employment_status",
    "health_service_satisfaction",
    "owns_computer",
    "internet_use",
    "gender",
]

# Below this, the fact is left out and the claim stays open. High on purpose —
# see the module docstring on why unsure means open.
MIN_CONFIDENCE = 0.75

ANY = "any"


def _questions():
    """One choice question per fact, over its own answers plus an `any` escape."""
    out = {}
    for field in FIELDS:
        answers = dm.fact_answers(field)
        if not answers:
            continue
        options = {a: None for a in answers}
        options[ANY] = "the finding holds whatever this is"
        out[field] = ts.choice_question(
            f"The research behind this finding studied particular people. Which "
            f"{field.replace('_', ' ')} does the finding depend on? Pick "
            f"\"{ANY}\" if it does not depend on this at all.",
            options,
        )
    return out


def propose(claim_text: str, min_confidence: float):
    """(rule, notes) for one claim. `rule` is [] when nothing is confident enough."""
    answers = ts.ask(claim_text, _questions())
    if not answers:
        return [], [("reader returned nothing", 0.0)]
    clause, notes = {}, []
    for field, answer in (answers or {}).items():
        choice = (answer or {}).get("choice")
        confidence = float((answer or {}).get("confidence") or 0.0)
        if choice is None or choice == ANY:
            continue
        if confidence < min_confidence:
            notes.append((f"{field}={choice} left out", confidence))
            continue
        clause.setdefault(field, []).append(choice)
        notes.append((f"{field}={choice} KEPT", confidence))
    notes.sort(key=lambda n: -n[1])
    return ([clause] if clause else []), notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--card", help="one card id, instead of all of them")
    ap.add_argument("--write", action="store_true",
                    help="write the proposals into the card files (review the diff)")
    ap.add_argument("--min-confidence", type=float, default=MIN_CONFIDENCE)
    ap.add_argument("--overwrite", action="store_true",
                    help="also redraft claims that already carry a needs rule")
    args = ap.parse_args()

    if not ts.enabled():
        print("TYPESAFE_API_KEY is not set — nothing to ask.", file=sys.stderr)
        return 1

    names = sorted(n for n in os.listdir(CARDS) if n.endswith(".json"))
    if args.card:
        names = [n for n in names if json.load(open(os.path.join(CARDS, n),
                                                    encoding="utf-8")).get("id") == args.card]
        if not names:
            print(f"no card with id {args.card!r}", file=sys.stderr)
            return 1

    totals = collections.Counter()
    for name in names:
        path = os.path.join(CARDS, name)
        card = json.load(open(path, encoding="utf-8"))
        print(f"\n=== {card['id']} — {card.get('subject', '')}")
        changed = False
        for i, claim in enumerate(card.get("claims", []), 1):
            if claim.get("needs") and not args.overwrite:
                print(f"{i}. already has a rule, left alone")
                totals["kept"] += 1
                continue
            rule, notes = propose(claim["text"], args.min_confidence)
            print(f"{i}. {claim['text'][:100]}...")
            print(f"   needs: {json.dumps(rule)}")
            for note, confidence in notes[:4]:
                print(f"      {confidence:.2f}  {note}")
            totals["narrowed" if rule else "open"] += 1
            if rule != (claim.get("needs") or []):
                claim["needs"] = rule
                changed = True
        if args.write and changed:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(card, fh, indent=2, ensure_ascii=False)
                fh.write("\n")

    print(f"\nclaims narrowed: {totals['narrowed']} | left open: {totals['open']} | "
          f"already ruled: {totals['kept']}")
    print("written into the cards." if args.write else "nothing written (pass --write).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
