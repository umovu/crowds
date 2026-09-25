"""
extract_readings — several honest readings of each finding on a draft card.

A finding such as "parents build their own reward schemes" is not one-dimensional:
the same behaviour can mean "already bought in", "already solved it for free" or
"wants to stay the author". One reading per claim hands a whole room the same angle.
This drafts 2-4 readings per claim, each tied to the passages it rests on, for a
human to sign off like the rest of the card (docs/EXTRACTION_PROTOCOL.md, Stage 5).

Rules the prompt enforces and this script checks, most of them without a model:
  * every reading cites passages, and only the passages behind its own finding;
  * no figures (cards give reasoning, never numbers) and no purchase decision:
    willingness is the persona's answer, not the card's;
  * no invented subjects: money, trust, privacy, technology, the state or safety may
    appear in a reading only if its finding or quotes raise them (RISKY);
  * a second model reads each reading beside its quotes: does it follow, or add
    something? and which way does it point? If every reading points the same way,
    the claim fails. A claim that fails is redrafted once with the failures.
The research model (LLM_*) writes and judges by default; tests/test_extract_readings.py
feeds the checks deliberately bad readings to prove they catch them.

Usage:
  <venv-python> backend/scripts/extract_readings.py --card-id township-parent-motivation-sdl [--sim-tier]
Reads and rewrites docs/extraction/<card-id>.card.json (a draft), or with --shipped the
card in app/data/mechanism_cards/ (then review the diff before it ships).
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_card import get_client, chat_json  # noqa: E402
from validate_card import EXTRACTION_DIR, parse_worksheet  # noqa: E402

SHIPPED_DIR = Path(__file__).resolve().parents[1] / "app" / "data" / "mechanism_cards"

SYSTEM = """You write readings of research findings for a South African simulation of real people.
A finding describes what some people do. A reading says how a person who does that
might look at a NEW product, service or policy in the same area of life.

Rules:
- Give 2 to 4 readings that genuinely differ: some make the person more open, some less,
  some conditional. They must not all point the same way.
- Every reading must follow from the quoted passages you are given. Cite the passage ids
  it rests on. Do not add facts, places, prices or motives the passages do not support.
- Use the words of the finding and its quotes; do not bring in new subjects.
- Never say whether they would buy, sign up or pay. Say how they would weigh it.
- Write each reading as one plain sentence starting "If ..." or "Someone who ...".
- No digits anywhere.
Return JSON only: {"readings": [{"text": "...", "passages": ["P1", "P2"]}]}"""

JUDGE = """You check readings of a research finding against the quotes they cite.
A reading's job is to say how a person who does what the quotes describe would weigh a NEW
product, service or policy. That step, from the behaviour to how they would judge a new offer,
is the point of a reading and is allowed.
For each reading answer:
- follows: false only if the reading says something about the PERSON that the quotes and finding
  do not support: a fact, feeling, motive, belief or behaviour they never mention. Otherwise true.
- adds: if follows is false, the unsupported part in a few words; otherwise "".
- direction: "open" (makes the person more open to a new offer), "less" (less open) or
  "conditional" (open only if something holds).
Return JSON only: {"readings": [{"i": 0, "follows": true, "adds": "", "direction": "open"}]}"""

# Subjects a reading tends to bring in that the quotes never raised: money, trust,
# privacy, technology, the state, safety. Each is a word stem; a reading that uses
# one its finding and quotes do not is inventing a motive. (A general "every content
# word must be quoted" check flagged all twenty readings of the first card for words
# like "sets" and "lets", so it caught nothing; the judge covers the rest.)
RISKY = ["price", "cost", "money", "afford", "cheap", "expens", "discount", "trust", "distrust",
         "scam", "brand", "privacy", "private", "phone", "online", "internet", "tech", "government",
         "municipal", "safe", "crime", "status", "prestige", "religio", "church", "tradition"]
# Short words match whole, not as a prefix ("app" is not "appeal", "pay" not "payoff").
RISKY_WORDS = {"rand": {"rand", "rands"}, "fee": {"fee", "fees"}, "pay": {"pay", "pays", "paid", "paying"},
               "data": {"data"}, "app": {"app", "apps"}, "state": {"state"}}


def _words(text: str) -> list:
    return re.findall(r"[a-z]+", text.lower())


def new_words(reading: str, claim: dict, passages: dict) -> list:
    """Risky subjects a reading raises that neither its finding nor its quotes mention."""
    source = claim.get("text", "") + " " + " ".join(passages.get(p, "") for p in claim.get("passages") or [])
    have = _words(source)
    used = _words(reading)
    found = {stem for stem in RISKY
             if any(w.startswith(stem) for w in used) and not any(w.startswith(stem) for w in have)}
    found |= {k for k, forms in RISKY_WORDS.items() if forms & set(used) and not forms & set(have)}
    return sorted(found)


def problems(readings: list, claim: dict, passages: dict) -> list:
    """Checks that need no model: count, cited quotes, figures, purchase words, invented content."""
    cid = claim.get("chain_id")
    own = set(claim.get("passages") or [])
    out = []
    if not 2 <= len(readings) <= 4:
        out.append(f"{cid}: {len(readings)} readings (want 2-4)")
    for r in readings:
        text, cited = r.get("text", ""), set(r.get("passages") or [])
        if not cited:
            out.append(f"{cid}: a reading cites no passage: {text!r}")
        if cited - set(passages):
            out.append(f"{cid}: cites passages not on the worksheet: {sorted(cited - set(passages))}")
        elif cited - own:
            out.append(f"{cid}: cites passages behind another finding: {sorted(cited - own)}")
        if re.search(r"\d", text):
            out.append(f"{cid}: number in reading: {text!r}")
        if re.search(r"\b(would buy|will buy|would pay|will pay|sign up|subscribe)\b", text, re.I):
            out.append(f"{cid}: reading states a purchase decision: {text!r}")
        invented = new_words(text, claim, passages)
        if invented:
            out.append(f"{cid}: raises {invented}, which the finding and its quotes do not: {text!r}")
    return out


def judge_problems(labels: list, claim: dict) -> list:
    """What the second model's labels fail: a reading that adds, or all readings one way."""
    cid = claim.get("chain_id")
    out = [f"{cid}: reading [{l.get('i')}] adds what the quotes do not say: {l.get('adds')!r}"
           for l in labels if l.get("follows") is False]
    directions = {l.get("direction") for l in labels if l.get("direction")}
    if len(labels) >= 2 and len(directions) == 1:
        out.append(f"{cid}: every reading points the same way ({next(iter(directions))})")
    return out


def draft(client, model, claim: dict, passages: dict, feedback: str = "") -> list:
    quoted = "\n".join(f"{pid}: {passages[pid]}" for pid in claim["passages"] if pid in passages)
    user = f"FINDING: {claim['text']}\n\nPASSAGES:\n{quoted}"
    if feedback:
        user += f"\n\nYOUR LAST DRAFT FAILED THESE CHECKS; fix them:\n{feedback}"
    out = chat_json(client, model, SYSTEM, user, max_tokens=1500) or {}
    return out.get("readings") or []


def judge(client, model, claim: dict, readings: list, passages: dict) -> list:
    """A second read of each reading beside its quotes: does it follow, which way does it point."""
    listed = "\n".join(
        f"[{i}] {r['text']}\n    QUOTES: " + " | ".join(f"{p}: {passages.get(p, '')}" for p in r.get("passages") or [])
        for i, r in enumerate(readings))
    out = chat_json(client, model, JUDGE, f"FINDING: {claim['text']}\n\nREADINGS:\n{listed}", max_tokens=1500) or {}
    return out.get("readings") or []


def read_claim(client, model, claim: dict, passages: dict, tries: int = 2):
    """Draft, check, and redraft once with the failures. Returns (readings, labels, problems)."""
    feedback, readings, labels, issues = "", [], [], []
    for _ in range(tries):
        readings = draft(client, model, claim, passages, feedback)
        issues = problems(readings, claim, passages)
        labels = []
        if not issues:
            labels = judge(client, model, claim, readings, passages)
            issues = judge_problems(labels, claim)
        if not issues:
            break
        feedback = "\n".join(issues)
    return readings, labels, issues


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--card-id", required=True)
    ap.add_argument("--sim-tier", action="store_true",
                    help="use the cheap simulation model instead of the research model")
    ap.add_argument("--shipped", action="store_true",
                    help="add readings to the shipped card in app/data/mechanism_cards, whose gates and "
                         "claims may have been edited since the draft; its passage ids must be the worksheet's")
    args = ap.parse_args()
    card_path = (SHIPPED_DIR / f"{args.card_id}.json" if args.shipped
                 else EXTRACTION_DIR / f"{args.card_id}.card.json")
    ws = parse_worksheet(EXTRACTION_DIR / f"{args.card_id}.worksheet.md")
    passages = {p["id"]: p["passage"] for p in ws["passages"]}
    card = json.loads(card_path.read_text(encoding="utf-8"))
    # Readings are research, not runtime: the research model by default (LLM_*).
    client, model = get_client(not args.sim_tier, None, None, None)
    print(f"model: {model}")
    issues = []
    for claim in card["claims"]:
        readings, labels, found = read_claim(client, model, claim, passages)
        issues += found
        by_i = {l.get("i"): l for l in labels}
        claim["readings"] = [{"text": r["text"].strip(), "passages": list(r["passages"])} for r in readings]
        print(f"\n{claim['chain_id']}: {claim['text'][:100]}")
        for i, r in enumerate(claim["readings"]):
            print(f"   - [{by_i.get(i, {}).get('direction', '?')}] {r['text']}  {r['passages']}")
    card_path.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n" + ("\n".join(issues) if issues else
                  "Checks: passed (quotes, invented words, figures, purchase, judge, direction)"))
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
