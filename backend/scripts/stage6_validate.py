"""
Stage 6 — validation harness for shipped mechanism cards against real personas.

Generalizes context_grounding_pilot_v2.py's baseline/cards/cards+stats pattern
from 3 hand-made cards to the full shipped set in
D:/Fub-agentsociety/backend/app/data/mechanism_cards/, bound against the real
persona library (D:/Fub-agentsociety/backend/app/data/persona_library/personas.json)
via the same deterministic archetype-in-segment_tags lookup used everywhere else
in this pipeline.

Per docs/EXTRACTION_PROTOCOL.md Stage 6: each (persona, card) pair is run
against a scenario the card's source papers never discussed, so any effect
observed is the card generalizing, not reciting. Evidence tests:
  - straw-in-the-wind: card vocabulary appears under `cards`
  - hoop: mechanism reasoning present under `cards`, RARE under `baseline`
  - smoking gun: mechanism applied to something novel in the scenario
  - doubly decisive: hoop + smoking gun, consistent across repeats (not run
    here by default — this script does 1 rep per condition; pass --repeats
    to increase, per the "single runs are never evidence" rule)

Run: D:/Fub-agentsociety/backend/.venv/Scripts/python.exe backend/scripts/stage6_validate.py
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

WORKTREE_ROOT = Path(__file__).resolve().parents[2]
MAIN_REPO_ROOT = Path("D:/Fub-agentsociety")
load_dotenv(MAIN_REPO_ROOT / ".env")

CARDS_DIR = MAIN_REPO_ROOT / "backend/app/data/mechanism_cards"
PERSONAS_PATH = MAIN_REPO_ROOT / "backend/app/data/persona_library/personas.json"

# Each card gets ONE unseen scenario from its cluster — none of the source papers
# behind any of these cards discuss the specific product below, which is the
# whole point (smoking-gun test needs a genuinely novel application).
SCENARIOS = {
    "farmer": (
        "AgriTrust Digital: an app where you register your livestock and crops "
        "in a digital ledger to unlock microloans, using the registered assets "
        "as collateral. The app also tracks your herd's location for insurance "
        "purposes."
    ),
    "middle_class": (
        "EliteSave: a no-monthly-fee digital bank account that gives you a "
        "shareable 'Top Saver' badge on your profile once your balance crosses "
        "a threshold, visible to your contacts on the app."
    ),
    "education": (
        "StudyCoins: an app that pays learners in mobile data for completing "
        "lessons, with a public class leaderboard showing top earners each "
        "week. Parents can pay R99/month to unlock detailed progress reports "
        "and a private (non-leaderboard) version for their child."
    ),
    "youth": (
        "GigConnect: an app matching unemployed youth to short informal gigs "
        "(deliveries, event staffing), paying out in airtime and data instead "
        "of cash, and requiring you to keep your phone visible during a gig "
        "so the client can verify your location."
    ),
    "stokvel": (
        "PocketStokvel: a savings app that mimics a stokvel — automatic "
        "monthly contributions, payout only released at year-end, with a 10% "
        "bonus if you make no early withdrawals."
    ),
}

# Some cards' segment_tags list order doesn't reflect intent (e.g. a farmer card
# whose paper sample also touched unemployed-youth passages) — pin the archetype
# validation should actually exercise, rather than picking whichever tag happens
# to come first and have a library persona.
PREFERRED_ARCHETYPE = {
    "communal-cattle-asset-logic": "communal_farmer",
    "farmer-stock-theft-exposure": "communal_farmer",
    "farmer-market-participation": "smallholder_emerging_farmer",
    "farmer-intervention-adoption": "smallholder_emerging_farmer",
}

CARD_CLUSTER = {
    "communal-cattle-asset-logic": "farmer",
    "farmer-stock-theft-exposure": "farmer",
    "farmer-market-participation": "farmer",
    "farmer-intervention-adoption": "farmer",
    "middle-class-status-identity": "middle_class",
    "fintech-adoption-trust": "middle_class",
    "education-payment-conversion": "education",
    "edtech-adoption-barriers": "education",
    "incentivized-learning-engagement": "education",
    "reward-design-motivation-crowding-sa-v2": "education",
    "parent-digital-learning-perceptions-sa": "education",
    "township-parent-motivation-sdl": "education",
    "youth-waithood-identity": "youth",
    "youth-mobile-airtime-economy": "youth",
    "youth-phone-safety-cost-economics": "youth",
    "stokvels-calibration": "stokvel",
}


@dataclass
class Persona:
    name: str
    age: int
    province: str
    occupation: str
    archetype: str
    persona_summary: str
    background_story: str
    beliefs: list[str] = field(default_factory=list)


def load_cards() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CARDS_DIR.glob("*.json"))]


def load_personas_by_archetype() -> dict[str, list[Persona]]:
    data = json.loads(PERSONAS_PATH.read_text(encoding="utf-8"))
    by_arch: dict[str, list[Persona]] = {}
    for p in data["personas"]:
        arch = p.get("actor_archetype")
        if not arch:
            continue
        by_arch.setdefault(arch, []).append(Persona(
            name=p["name"], age=p["age"], province=p["province"],
            occupation=p.get("occupation", ""), archetype=arch,
            persona_summary=p.get("persona", ""),
            background_story=p.get("background_story", ""),
            beliefs=p.get("beliefs", []),
        ))
    return by_arch


def build_stats_block() -> str:
    w = json.loads((MAIN_REPO_ROOT / "backend/app/data/sa_world_facts.json").read_text(encoding="utf-8"))
    g = json.loads((MAIN_REPO_ROOT / "backend/data/sa_grant_amounts.json").read_text(encoding="utf-8"))
    lines = ["# Real current SA costs and amounts (curated, dated — use these magnitudes, never invent numbers)"]
    for f in w["facts"]:
        derived = f.get("derived") or f"{f.get('value')} {f.get('unit')}"
        lines.append(f"- {derived}")
    eff = g.get("effective_date", "")
    lines.append(f"- (Grant schedule effective {eff}, SASSA published figures)")
    return "\n".join(lines)


SYSTEM_BASE = (
    "You are roleplaying a real South African person for a market/policy "
    "simulation. Speak in first person, in your own voice. Be concrete and "
    "specific to your own circumstances. Keep it to 4-6 sentences. End with "
    "one line exactly:\nSTANCE: <support | neutral | concerned | oppose | resist>"
)


def identity_block(p: Persona) -> str:
    return (
        f"# Your identity (real survey-derived profile — do not contradict it)\n"
        f"Name: {p.name}\nAge: {p.age}\nProvince: {p.province}\n"
        f"Occupation: {p.occupation}\nArchetype: {p.archetype}\n"
        f"Summary: {p.persona_summary}\nBackground: {p.background_story}\n"
        f"Beliefs: {'; '.join(p.beliefs)}\n"
    )


def mechanism_block(cards: list[dict]) -> str:
    if not cards:
        return ""
    lines = ["# Research-grounded context for people like you (reason through this; do not quote it verbatim)"]
    for c in cards:
        cite = c["citation"][0] if isinstance(c["citation"], list) else c["citation"]
        lines.append(f"\nFrom {cite} [{c['claim_type']}]:")
        lines.extend(f"  - {m}" for m in c["mechanisms"])
        if c.get("vocabulary"):
            lines.append(f"  Vocabulary people like you use: {', '.join(c['vocabulary'])}")
    return "\n".join(lines)


def respond(client, model, persona: Persona, scenario: str, cards: list[dict], stats: str) -> str:
    system = SYSTEM_BASE + "\n\n" + identity_block(persona)
    mb = mechanism_block(cards)
    if mb:
        system += "\n\n" + mb
    if stats:
        system += "\n\n" + stats
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"Scenario: {scenario}\n\nHow do you react? What's your honest first reaction and your main concern?"},
        ],
        temperature=0.7,
        max_tokens=350,
        extra_body={"enable_thinking": False},
    )
    return resp.choices[0].message.content.strip()


def extract_stance(text: str) -> str:
    for line in reversed(text.splitlines()):
        if "STANCE" in line.upper():
            return line.split(":", 1)[-1].strip().lower().strip("*[]<> ")
    return "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=1,
                    help="repeats per condition (protocol requires 2-3 before trusting; default 1)")
    ap.add_argument("--card", action="append", default=None,
                    help="card id(s) to validate; default: all mapped cards")
    ap.add_argument("--model", default="qwen3.7-max")
    ap.add_argument("--base-url", default="https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
    ap.add_argument("--api-key", default=None)
    args = ap.parse_args()

    import os
    key = args.api_key or os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        sys.exit("No API key: pass --api-key or set DASHSCOPE_API_KEY")
    client = OpenAI(api_key=key, base_url=args.base_url)

    cards = load_cards()
    personas_by_arch = load_personas_by_archetype()
    stats = build_stats_block()

    results = []
    for card in cards:
        card_id = card["id"]
        if args.card and card_id not in args.card:
            continue
        cluster = CARD_CLUSTER.get(card_id)
        if cluster is None:
            print(f"SKIP {card_id}: no scenario cluster mapped")
            continue
        scenario = SCENARIOS[cluster]

        # bind: preferred archetype if pinned above, else first tag with a library persona
        persona = None
        bound_archetype = None
        preferred = PREFERRED_ARCHETYPE.get(card_id)
        if preferred and personas_by_arch.get(preferred):
            persona = personas_by_arch[preferred][0]
            bound_archetype = preferred
        else:
            for arch in card["segment_tags"]:
                if personas_by_arch.get(arch):
                    persona = personas_by_arch[arch][0]
                    bound_archetype = arch
                    break
        if persona is None:
            print(f"SKIP {card_id}: no persona in the library matches any of {card['segment_tags']}")
            continue

        print(f"\n{'='*70}\n{card_id} -> {persona.name} ({bound_archetype}) [{cluster}]\n{'='*70}")
        row = {"card_id": card_id, "cluster": cluster, "persona": persona.name,
               "archetype": bound_archetype, "scenario": scenario, "conditions": {}}
        for label, (use_cards, use_stats) in {
            "baseline": (False, False),
            "cards": (True, False),
            "cards+stats": (True, True),
        }.items():
            reps = []
            for r in range(args.repeats):
                text = respond(client, args.model, persona, scenario,
                               [card] if use_cards else [], stats if use_stats else "")
                stance = extract_stance(text)
                reps.append({"stance": stance, "text": text})
                print(f"\n--- {label} rep{r+1} [stance: {stance}] ---\n{text}")
            row["conditions"][label] = reps
        results.append(row)

    out = {"model": args.model, "repeats": args.repeats,
           "n_cards_run": len(results), "results": results}
    out_path = WORKTREE_ROOT / "docs" / "extraction" / "stage6_validation_output.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n\nSaved: {out_path}")
    print(f"Ran {len(results)}/{len(cards)} cards.")


if __name__ == "__main__":
    main()
