"""cache_card_valence — one typed label per mechanism-card claim, saved to disk.

Separated from the audit so the counting costs nothing: fetch once with Jev,
then re-run `audit_card_valence.py` offline against
`scripts/out/card_valence.json` as often as you like.

Each claim gets one choice question: is this sentence a reason the person
resists, a reason they lean in, or neither. Objections on the claim are
labelled too, since a card can carry its weight in objections alone.

Usage:
    python cache_card_valence.py [--refresh]   # --refresh re-asks everything
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND)

_ENV = os.path.join(BACKEND, "..", ".env")
if os.path.exists(_ENV):
    for line in open(_ENV, encoding="utf-8"):
        line = line.strip()
        if line.startswith("TYPESAFE_") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)

OUT = os.path.join(BACKEND, "scripts", "out", "card_valence.json")

# Loaded by path: importing app.services pulls in the whole simulation stack.
_spec = importlib.util.spec_from_file_location(
    "mcs_cache_valence", os.path.join(BACKEND, "app", "services", "mechanism_card_service.py"))
mcs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcs)

VALENCE = {
    "barrier": "A reason this person hesitates, doubts, resists or says no.",
    "motivator": "A reason this person wants it, leans in or says yes.",
    "neutral": "Neither — it describes how they decide without pointing either way.",
}


def units(cards):
    """(key, kind, card_id, text) for every labellable sentence in the cards."""
    for card in cards:
        for i, claim in enumerate(card.get("claims") or []):
            yield f"{card['id']}#c{i}", "claim", card["id"], claim.get("text", "")
            for j, objection in enumerate(claim.get("objections") or []):
                yield (f"{card['id']}#c{i}o{j}", "objection", card["id"], objection)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="re-ask every unit instead of only the missing ones")
    args = ap.parse_args()

    from app.utils import typesafe_client as ts

    if not ts.enabled():
        print("TYPESAFE_API_KEY is not set — nothing to fetch.")
        return

    cached = {}
    if os.path.exists(OUT) and not args.refresh:
        cached = json.load(open(OUT, encoding="utf-8"))

    todo = [u for u in units(mcs.load_cards()) if u[0] not in cached and u[3].strip()]
    print(f"{len(cached)} cached, {len(todo)} to label")

    question = {"valence": ts.choice_question(
        "Read this sentence from South African research about how a group of people "
        "reason. Does it give a reason to resist, a reason to want it, or neither?",
        VALENCE)}

    failed = 0
    for key, kind, card_id, text in todo:
        answers = ts.ask(text, question)
        if not answers or "valence" not in answers:
            print("FAILED", key)
            failed += 1
            continue
        answer = answers["valence"]
        cached[key] = {
            "card": card_id,
            "kind": kind,
            "text": text,
            "valence": answer.get("choice"),
            "confidence": answer.get("confidence"),
        }
        print(f"{answer.get('choice'):<9} {key}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(cached, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"\nwrote {len(cached)} label(s), {failed} failed -> {OUT}")


if __name__ == "__main__":
    main()
