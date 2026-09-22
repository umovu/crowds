"""audit_card_reach_by_pitch — does a real pitch reach the library with evidence?

`audit_card_coverage` answers "how many personas does each card fit". That is the
supply side, and it looks healthy: 374 of 375 personas fit at least one card.

It is the wrong question for a room. A room is asked about ONE subject, and only
cards about that subject survive the prompt-time gate. So the number that decides
whether a panel sounds grounded or invented is:

    of the people in a room asked about X, how many arrive holding evidence,
    and how many of them hold the SAME evidence as each other?

This asks that, over a spread of pitches and the whole library. It reports, per
pitch, the share of personas who get at least one card, and how many distinct
sets of claims the library produces — because a pitch where everyone gets the
identical card is a pitch where everyone reasons identically.

Runs both gates so the two are separable:

    tags   — topic_tags whole-word match (today's default)
    typed  — tags widened by the typed reader (FUB_TYPED_CARDS)

LLM-free except for one typed read per pitch, and only with --typed.

Usage:
    python audit_card_reach_by_pitch.py                # tags only, no network
    python audit_card_reach_by_pitch.py --typed        # both gates, one read per pitch
    python audit_card_reach_by_pitch.py --sample 120   # faster, sampled library
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
LIB = os.path.join(BACKEND, "app", "data", "persona_library", "personas.json")
sys.path.insert(0, BACKEND)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(BACKEND, "..", ".env"))

# A spread of realistic pitches, one per subject a user might plausibly bring.
# Written the way a founder or a department writes, not the way a card's tags do
# — that gap is the thing being measured.
PITCHES = [
    ("health / paid clinic",
     "A private clinic chain wants to launch a R150 pay-per-visit nurse service. You book "
     "on WhatsApp and see a nurse the same day, with no queue and no medical aid needed."),
    ("health / medicine delivery",
     "A pharmacy wants to deliver your repeat medicine to your door each month for R49, "
     "so you never queue for a script again."),
    ("education / tutoring",
     "An after-school maths programme for Grade 9s, R200 a month, two afternoons a week "
     "at a community hall."),
    ("education / school fees",
     "A low-fee independent school is opening nearby, charging R900 a month instead of "
     "the R30,000 a year the private schools charge."),
    ("money / savings app",
     "An app that rounds up what you spend and puts the change away for you, with no "
     "monthly fee and your money out within a day."),
    ("money / funeral cover",
     "Funeral cover for R80 a month that pays out within 48 hours, signed up on your "
     "phone with no paperwork and no medical questions."),
    ("jobs / placement",
     "A programme that places matriculants in their first paid job within six months, "
     "free to join, and takes a small cut of the first three months of pay."),
    ("transport",
     "A shared ride service to and from the taxi rank at fixed times each morning for "
     "R15 a trip, booked the night before."),
    ("power",
     "A small solar and battery kit rented for R299 a month that keeps your lights, "
     "fridge and phone going when the power is out."),
    ("water",
     "A municipality wants to install prepaid water meters, with 6,000 litres a month "
     "free and the rest paid for up front."),
    ("safety",
     "A neighbourhood patrol funded by R100 a month per household, with a panic button "
     "app linked to a response vehicle."),
    ("food / retail",
     "A bulk buying club where twenty households order groceries together each month and "
     "split the delivery, saving about 15 percent."),
    ("farming",
     "A scheme that helps small livestock owners get their cattle to market together, "
     "with shared transport and one auction day a month."),
    ("connectivity",
     "Uncapped home wifi for R249 a month, installed free, on a month-to-month contract "
     "with no credit check."),
    ("environment / recycling",
     "A company collects your sorted recycling from your door every week and pays you "
     "R20 a month in airtime for it."),
    ("environment / climate",
     "The city wants to add R30 a month to every rates bill to fund tree planting and "
     "clean-up of the river that runs through the township."),
]

# What real users have actually brought, in their own terms. Kept separate from the
# spread above so the audit can say whether the gaps land on the people using it.
TESTER_PITCHES = [
    ("Thuto / parent app",
     "An app that shows parents how much effort their child puts into schoolwork each "
     "day, so they can reward it. R60 a month."),
    ("school phone ban",
     "Your child's school wants to ban smartphones during school hours. Phones would be "
     "handed in at the gate each morning and collected after school."),
    ("Ntombi / chronic meds",
     "A private clinic hands out your government chronic medication for free. You collect "
     "with a barcode, no queue, and no one opens your file."),
    ("Ntombi / diabetes",
     "A free diabetes screening day at your local private clinic in November, with a "
     "finger-prick test and a nurse to talk you through the result."),
    ("biodigester",
     "A home biodigester that turns kitchen and garden waste into cooking gas, R17,000 "
     "installed, or R700 a month over two years."),
]


def _load(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--typed", action="store_true", help="also run the typed reader gate")
    ap.add_argument("--sample", type=int, default=0, help="sample N personas (0 = all)")
    args = ap.parse_args()

    from app.services import mechanism_card_service as mcs
    from app.services import card_subjects as cs

    library = json.load(open(LIB, encoding="utf-8"))
    if isinstance(library, dict):
        library = library.get("personas", library.get("library", []))
    if args.sample:
        library = random.Random(7).sample(library, min(args.sample, len(library)))

    # Bind once: who each persona is does not change with the pitch.
    bound = []
    for p in library:
        ids = [c["id"] for c in mcs.cards_for_persona(p)]
        q = dict(p)
        q["research_citations"] = [{"card_id": i} for i in ids]
        bound.append(q)
    print(f"library: {len(bound)} personas | cards: {len(mcs.load_cards())}\n")

    modes = [("tags", "0")] + ([("typed", "1")] if args.typed else [])
    header = "pitch".ljust(26) + "".join(f"{m:>22}" for m, _ in modes)
    print(header)
    print("-" * len(header))

    totals = collections.defaultdict(lambda: [0, 0])
    for label, pitch in PITCHES + [("* " + l, t) for l, t in TESTER_PITCHES]:
        row = label[:25].ljust(26)
        for mode, flag in modes:
            os.environ["FUB_TYPED_CARDS"] = flag
            cs.reset_memo()
            touched = mcs.subjects_touched(pitch)
            shapes = collections.Counter()
            grounded = 0
            for p in bound:
                got = mcs.cards_for_question(p, pitch, touched=touched) or []
                if got:
                    grounded += 1
                shapes[tuple(sorted(
                    (c["id"], tuple(cl["text"][:40] for cl in c.get("claims", [])))
                    for c in got))] += 1
            pct = 100.0 * grounded / len(bound)
            # Distinct evidence shapes among the GROUNDED (an empty set is not variety).
            distinct = len([k for k in shapes if k])
            row += f"{pct:>8.0f}% {distinct:>4} sets  "
            totals[mode][0] += pct
            totals[mode][1] += distinct
        print(row)

    print("-" * len(header))
    row = "mean".ljust(26)
    for mode, _ in modes:
        n = len(PITCHES) + len(TESTER_PITCHES)
        row += f"{totals[mode][0]/n:>8.0f}% {totals[mode][1]/n:>4.0f} sets  "
    print(row)
    print("\n'%' = personas arriving with at least one card. "
          "'sets' = distinct claim combinations among them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
