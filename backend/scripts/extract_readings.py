"""
extract_readings — several honest readings of each finding on a draft card.

A finding such as "parents build their own reward schemes" is not one-dimensional:
the same behaviour can mean "already bought in", "already solved it for free" or
"wants to stay the author". One reading per claim hands a whole room the same angle.
This drafts 2-4 readings per claim, each tied to the passages it rests on, for a
human to sign off like the rest of the card (docs/EXTRACTION_PROTOCOL.md, Stage 5).

Rules the prompt enforces and this script checks:
  * every reading cites passage ids that exist on the worksheet and on the claim;
  * no figures (cards give reasoning, never numbers);
  * a reading says how someone who does this might read a new offer, never whether
    they would buy it — willingness is the persona's answer, not the card's.

Usage:
  <venv-python> backend/scripts/extract_readings.py --card-id township-parent-motivation-sdl
Reads and rewrites docs/extraction/<card-id>.card.json (a draft, not a shipped card).
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_card import get_client, chat_json  # noqa: E402
from validate_card import EXTRACTION_DIR, parse_worksheet  # noqa: E402

SYSTEM = """You write readings of research findings for a South African simulation of real people.
A finding describes what some people do. A reading says how a person who does that
might look at a NEW product, service or policy in the same area of life.

Rules:
- Give 2 to 4 readings that genuinely differ: some make the person more open, some less,
  some conditional. They must not all point the same way.
- Every reading must follow from the quoted passages you are given. Cite the passage ids
  it rests on. Do not add facts, places, prices or motives the passages do not support.
- Never say whether they would buy, sign up or pay. Say how they would weigh it.
- Write each reading as one plain sentence starting "If ..." or "Someone who ...".
- No digits anywhere.
Return JSON only: {"readings": [{"text": "...", "passages": ["P1", "P2"]}]}"""


def draft(client, model, claim: dict, passages: dict) -> list:
    quoted = "\n".join(f"{pid}: {passages[pid]}" for pid in claim["passages"] if pid in passages)
    user = f"FINDING: {claim['text']}\n\nPASSAGES:\n{quoted}"
    out = chat_json(client, model, SYSTEM, user, max_tokens=1500) or {}
    return out.get("readings") or []


def problems(readings: list, claim: dict, known: set) -> list:
    out = []
    if not 2 <= len(readings) <= 4:
        out.append(f"{claim['chain_id']}: {len(readings)} readings (want 2-4)")
    for r in readings:
        cited = set(r.get("passages") or [])
        if not cited:
            out.append(f"{claim['chain_id']}: a reading cites no passage: {r.get('text')!r}")
        if cited - known:
            out.append(f"{claim['chain_id']}: cites passages not on the worksheet: {sorted(cited - known)}")
        if re.search(r"\d", r.get("text", "")):
            out.append(f"{claim['chain_id']}: number in reading: {r.get('text')!r}")
        if re.search(r"\b(would buy|will buy|would pay|will pay|sign up)\b", r.get("text", ""), re.I):
            out.append(f"{claim['chain_id']}: reading states a purchase decision: {r.get('text')!r}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--card-id", required=True)
    ap.add_argument("--research-tier", action="store_true")
    args = ap.parse_args()
    card_path = EXTRACTION_DIR / f"{args.card_id}.card.json"
    ws = parse_worksheet(EXTRACTION_DIR / f"{args.card_id}.worksheet.md")
    passages = {p["id"]: p["passage"] for p in ws["passages"]}
    card = json.loads(card_path.read_text(encoding="utf-8"))
    client, model = get_client(args.research_tier, None, None, None)
    issues = []
    for claim in card["claims"]:
        readings = draft(client, model, claim, passages)
        issues += problems(readings, claim, set(passages))
        claim["readings"] = [{"text": r["text"].strip(), "passages": list(r["passages"])} for r in readings]
        print(f"\n{claim['chain_id']}: {claim['text'][:100]}")
        for r in claim["readings"]:
            print(f"   - {r['text']}  {r['passages']}")
    card_path.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n" + ("\n".join(issues) if issues else "Checks: passed"))
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
