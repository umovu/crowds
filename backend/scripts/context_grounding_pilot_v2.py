"""
Context-grounding pilot v2 — papers + stats shaping persona responses.

Extends v1 (context_grounding_pilot.py) along the lines the plan calls for:
  - 3 mechanism cards distilled from real papers (stokvels, CSG allocation,
    credit/aspiration) — qualitative mechanisms only, cited.
  - A STATS block loaded from the repo's real curated data files
    (sa_world_facts.json, sa_grant_amounts.json) — numbers never come from
    the LLM or from hand-typed memory.
  - 3 real library personas whose archetypes match the cards' segment_tags.
  - 3 conditions per persona: BASELINE / CARDS / CARDS+STATS, so the papers'
    contribution and the stats' contribution are separable.

Run: D:/Fub-agentsociety/backend/.venv/Scripts/python.exe backend/scripts/context_grounding_pilot_v2.py
"""

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

MAIN_REPO_ROOT = Path("D:/Fub-agentsociety")
load_dotenv(MAIN_REPO_ROOT / ".env")

SIM_API_KEY = os.environ.get("SIM_LLM_API_KEY") or os.environ.get("LLM_API_KEY")
SIM_BASE_URL = os.environ.get("SIM_LLM_BASE_URL") or os.environ.get("LLM_BASE_URL")
SIM_MODEL = os.environ.get("SIM_LLM_MODEL") or os.environ.get("LLM_MODEL_NAME")

client = OpenAI(api_key=SIM_API_KEY, base_url=SIM_BASE_URL)


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


@dataclass
class MechanismCard:
    id: str
    citation: str
    segment_tags: list[str]
    mechanisms: list[str]
    vocabulary: list[str]
    objection_patterns: list[str]
    claim_type: str
    confidence: str


# ── Cards: distilled from real papers (qualitative mechanisms only) ──────────

CARDS = [
    MechanismCard(
        id="orange-farm-stokvels-2014",
        citation="Matuku & Kaseke (2014), 'The role of stokvels in improving people's lives: Orange Farm, Johannesburg', Social Work/Maatskaplike Werk",
        segment_tags=["grant_dependent_survivor", "informal_trader", "unemployed_youth", "gogo_guardian"],
        mechanisms=[
            "Stokvels are joined to smooth irregular income around known cost spikes (December, funerals, school fees) — the payout is timed to a need, not a habit",
            "The lump sum is mentally earmarked for a deliberate purchase, not absorbed into daily spending",
            "Trust is the binding constraint: face-to-face accountability with people who know your circumstances beats institutional guarantees",
            "The group doubles as social infrastructure — problem-sharing and mutual aid, not just savings",
        ],
        vocabulary=["stokvel", "the group", "our turn", "society money"],
        objection_patterns=[
            "Can I trust the people/institution holding my money?",
            "What happens when I need my money before the agreed time?",
        ],
        claim_type="qualitative",
        confidence="small-sample qualitative, single site — high texture, low generalizability",
    ),
    MechanismCard(
        id="csg-allocation-zembe-mkabile",
        citation="Zembe-Mkabile et al., SA Medical Research Council CSG studies (2015–2023)",
        segment_tags=["grant_dependent_survivor", "guardian_parent", "gogo_guardian"],
        mechanisms=[
            "Grant money is allocated across competing essentials, not merely spent: school uniforms, transport and social obligations compete directly with food",
            "Caregivers ration or skip their own meals to protect children's school-related costs — education outlays are defended before food",
            "Part of the grant sustains social-capital obligations (funerals, reciprocal help) because those networks are the real safety net",
            "New costs are evaluated as 'what existing essential does this displace', not 'can I afford this'",
        ],
        vocabulary=["the grant", "SASSA money", "month-end", "stretch it"],
        objection_patterns=[
            "Which existing essential would this replace in my budget?",
            "Does this arrive/renew in rhythm with grant payment dates?",
        ],
        claim_type="qualitative",
        confidence="multiple qualitative studies, Western Cape-weighted",
    ),
    MechanismCard(
        id="james-2015-credit-aspiration",
        citation="Deborah James (2015), 'Money from Nothing: Indebtedness and Aspiration in South Africa', Stanford UP",
        segment_tags=["informal_trader", "small_business_owner", "unemployed_youth", "civic_moderate"],
        mechanisms=[
            "Borrowing is aspirational as much as survivalist — credit is taken to signal and build upward mobility (education, furniture, appearance), not only to cover shortfalls",
            "Informal lenders (mashonisas) are used alongside formal credit because they are relational: known, negotiable, immediate — even at worse rates",
            "Indebtedness carries status ambivalence: visible consumption earns respect while debt itself is concealed",
            "New financial products are read through past extraction: deductions, garnishee orders and hidden fees are the expected trick",
        ],
        vocabulary=["mashonisa", "on credit", "lay-by", "deductions"],
        objection_patterns=[
            "Where is the hidden deduction or fee in this?",
            "Can I negotiate with a person if things go wrong, or is it a faceless system?",
        ],
        claim_type="qualitative",
        confidence="book-length ethnography, multi-site, pre-2015 fieldwork — mechanisms durable, details dated",
    ),
]


# ── Stats block: loaded from the repo's REAL curated files, never typed in ───

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


# ── Personas: real library records only ─────────────────────────────────────

def load_personas_by_archetype(wanted: dict[str, int]) -> list[Persona]:
    data = json.loads((MAIN_REPO_ROOT / "backend/app/data/persona_library/personas.json").read_text(encoding="utf-8"))
    picked, seen_names = [], set()
    for arch, n in wanted.items():
        count = 0
        for p in data["personas"]:
            if p.get("actor_archetype") == arch and p["name"] not in seen_names:
                picked.append(Persona(
                    name=p["name"], age=p["age"], province=p["province"],
                    occupation=p.get("occupation", ""), archetype=arch,
                    persona_summary=p.get("persona", ""),
                    background_story=p.get("background_story", ""),
                    beliefs=p.get("beliefs", []),
                ))
                seen_names.add(p["name"])
                count += 1
                if count >= n:
                    break
    return picked


def cards_for(persona: Persona) -> list[MechanismCard]:
    """Deterministic binding: archetype must appear in the card's segment_tags."""
    return [c for c in CARDS if persona.archetype in c.segment_tags]


# ── Response block ───────────────────────────────────────────────────────────

SYSTEM_BASE = (
    "You are roleplaying a real South African person for a market simulation. "
    "Speak in first person, in your own voice. Be concrete and specific to your "
    "own circumstances. Keep it to 4-6 sentences. End with one line exactly:\n"
    "STANCE: <support | neutral | concerned | oppose | resist>"
)


def identity_block(p: Persona) -> str:
    return (
        f"# Your identity (real survey-derived profile — do not contradict it)\n"
        f"Name: {p.name}\nAge: {p.age}\nProvince: {p.province}\n"
        f"Occupation: {p.occupation}\nArchetype: {p.archetype}\n"
        f"Summary: {p.persona_summary}\nBackground: {p.background_story}\n"
        f"Beliefs: {'; '.join(p.beliefs)}\n"
    )


def mechanism_block(cards: list[MechanismCard]) -> str:
    if not cards:
        return ""
    lines = ["# Research-grounded context for people like you (reason through this; do not quote it verbatim)"]
    for c in cards:
        lines.append(f"\nFrom {c.citation} [{c.claim_type}]:")
        lines.extend(f"  - {m}" for m in c.mechanisms)
        if c.vocabulary:
            lines.append(f"  Vocabulary people like you use: {', '.join(c.vocabulary)}")
    return "\n".join(lines)


def respond(persona: Persona, scenario: str, cards: list[MechanismCard], stats: str) -> str:
    system = SYSTEM_BASE + "\n\n" + identity_block(persona)
    mb = mechanism_block(cards)
    if mb:
        system += "\n\n" + mb
    if stats:
        system += "\n\n" + stats
    resp = client.chat.completions.create(
        model=SIM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"Scenario: {scenario}\n\nHow do you react? What's your honest first reaction and your main concern?"},
        ],
        temperature=0.7,
        max_tokens=350,
    )
    return resp.choices[0].message.content.strip()


def extract_stance(text: str) -> str:
    for line in reversed(text.splitlines()):
        if "STANCE" in line.upper():
            return line.split(":", 1)[-1].strip().lower().strip("*[]<> ")
    return "?"


def main():
    if not (SIM_API_KEY and SIM_BASE_URL and SIM_MODEL):
        print("Missing SIM_LLM_* env vars"); sys.exit(1)

    scenario = (
        "A fintech company is launching a savings app: you save small amounts "
        "automatically from your account, and you unlock a 10% bonus if you don't "
        "withdraw anything for 3 months. It costs R15/month after a free first month."
    )

    personas = load_personas_by_archetype({
        "grant_dependent_survivor": 1,
        "informal_trader": 1,
        "unemployed_youth": 1,
    })
    stats = build_stats_block()
    print(f"Model: {SIM_MODEL}\nPersonas: {[(p.name, p.archetype) for p in personas]}\n")

    results = []
    for p in personas:
        bound = cards_for(p)
        print(f"\n{'='*70}\n{p.name} ({p.archetype}) — bound cards: {[c.id for c in bound]}\n{'='*70}")
        row = {"persona": p.name, "archetype": p.archetype,
               "bound_cards": [c.id for c in bound], "conditions": {}}
        for label, (cards, st) in {
            "baseline": ([], ""),
            "cards": (bound, ""),
            "cards+stats": (bound, stats),
        }.items():
            text = respond(p, scenario, cards, st)
            stance = extract_stance(text)
            row["conditions"][label] = {"stance": stance, "text": text}
            print(f"\n--- {label} [stance: {stance}] ---\n{text}")
        results.append(row)

    out = {"model": SIM_MODEL, "scenario": scenario,
           "stats_block": stats, "results": results}
    out_path = Path(__file__).resolve().parent / "context_grounding_pilot_v2_output.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
