"""
Context-grounding pilot — validates whether mechanism-card injection changes
persona reasoning in a testable, LLM-off-comparable way.

Deliberately does NOT use agentsociety2.agent.person.PersonAgent — that class
is a coding-tool agent (workspace/bash/skill tool-loop for automating dev
tasks), not a persona/opinion agent. This repo already diverged from it for
that reason (see backend/app/services/agentsociety_opinion_block.py). Instead
this pilot reuses the same minimal Agent-Block-Action shape that file already
established: a Persona holds a profile, a Block executes one reasoning action
(RESPOND), and the environment is just "what mechanism context is bound".

Run: backend/.venv/Scripts/python.exe backend/scripts/context_grounding_pilot.py
(uses env vars from repo root .env: SIM_LLM_API_KEY / SIM_LLM_BASE_URL / SIM_LLM_MODEL)
"""

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from openai import OpenAI
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]  # .../fub-agentsociety-context-pilot
MAIN_REPO_ROOT = Path("D:/Fub-agentsociety")      # source of .env + persona library + venv

load_dotenv(MAIN_REPO_ROOT / ".env")

SIM_API_KEY = os.environ.get("SIM_LLM_API_KEY") or os.environ.get("LLM_API_KEY")
SIM_BASE_URL = os.environ.get("SIM_LLM_BASE_URL") or os.environ.get("LLM_BASE_URL")
SIM_MODEL = os.environ.get("SIM_LLM_MODEL") or os.environ.get("LLM_MODEL_NAME")

client = OpenAI(api_key=SIM_API_KEY, base_url=SIM_BASE_URL)


# ── Minimal Agent-Block-Action shape (mirrors agentsociety_opinion_block.py) ──

@dataclass
class Persona:
    """A persona: real survey-born identity fields only. No LLM authorship here."""
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


class RespondBlock:
    """The single action under test: RESPOND_TO_SCENARIO.

    Equivalent in spirit to OpinionCaptureBlock.EXPRESS_OPINION but stripped to
    one action, since this pilot isolates the effect of context injection, not
    multi-agent interaction.
    """

    SYSTEM_BASE = (
        "You are roleplaying a real South African person for a market/policy "
        "simulation. Speak in first person, in your own voice. Be concrete and "
        "specific to your own circumstances — do not generalise to 'people like me' "
        "in the abstract. Keep it to 4-6 sentences."
    )

    @staticmethod
    def build_identity_block(p: Persona) -> str:
        return (
            f"# Your identity (real survey-derived profile — do not contradict it)\n"
            f"Name: {p.name}\nAge: {p.age}\nProvince: {p.province}\n"
            f"Occupation: {p.occupation}\nArchetype: {p.archetype}\n"
            f"Summary: {p.persona_summary}\n"
            f"Background: {p.background_story}\n"
            f"Beliefs: {'; '.join(p.beliefs)}\n"
        )

    @staticmethod
    def build_mechanism_block(cards: list[MechanismCard]) -> str:
        if not cards:
            return ""
        lines = ["# Research-grounded context for people like you (styling only — reason through this, do not quote it verbatim)"]
        for c in cards:
            lines.append(f"\nFrom {c.citation} [{c.claim_type}, confidence: {c.confidence}]:")
            for m in c.mechanisms:
                lines.append(f"  - {m}")
            if c.vocabulary:
                lines.append(f"  Vocabulary they'd use: {', '.join(c.vocabulary)}")
        return "\n".join(lines)

    def run(self, persona: Persona, scenario: str, cards: list[MechanismCard]) -> str:
        system = self.SYSTEM_BASE + "\n\n" + self.build_identity_block(persona)
        mech_block = self.build_mechanism_block(cards)
        if mech_block:
            system += "\n\n" + mech_block

        resp = client.chat.completions.create(
            model=SIM_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Scenario: {scenario}\n\nHow do you react? What's your honest first reaction and your main concern?"},
            ],
            temperature=0.7,
            max_tokens=300,
        )
        return resp.choices[0].message.content.strip()


# ── Load real personas from the actual library (no synthetic personas) ──

def load_persona(name_substring: str) -> Persona:
    data = json.loads((MAIN_REPO_ROOT / "backend/app/data/persona_library/personas.json").read_text(encoding="utf-8"))
    for p in data["personas"]:
        if name_substring.lower() in p["name"].lower():
            return Persona(
                name=p["name"], age=p["age"], province=p["province"],
                occupation=p.get("occupation", ""), archetype=p.get("actor_archetype", ""),
                persona_summary=p.get("persona", ""), background_story=p.get("background_story", ""),
                beliefs=p.get("beliefs", []),
            )
    raise ValueError(f"no persona matching {name_substring!r}")


def find_closest_archetype_persona(target_archetype_hint: str) -> Optional[Persona]:
    """Coverage-honesty check: is there a REAL persona this card could bind to?"""
    data = json.loads((MAIN_REPO_ROOT / "backend/app/data/persona_library/personas.json").read_text(encoding="utf-8"))
    archetypes = sorted({p.get("actor_archetype") for p in data["personas"]})
    return archetypes  # returns the list for inspection; used as a coverage report, not a match


# ── The two validated mechanism cards from the pilot digest ──

STOKVEL_CARD = MechanismCard(
    id="orange-farm-stokvels-2014",
    citation="The role of stokvels in improving people's lives: Orange Farm, Johannesburg (2014)",
    segment_tags=["informal_worker", "grant_recipient", "urban_township", "unemployed"],
    mechanisms=[
        "Stokvels are joined to smooth irregular/absent income around known cost spikes (December, funerals, school fees) — the payout is timed to a need, not a habit",
        "The lump sum is mentally earmarked for a bigger, deliberate purchase rather than absorbed into routine spending",
        "Trust is the binding constraint, not money: dishonesty ends memberships faster than financial strain does",
        "The group is social infrastructure as much as financial — mutual problem-sharing, not just a savings mechanism",
    ],
    vocabulary=["stokvel", "the group", "our turn"],
    objection_patterns=["Can I trust the people I'd be doing this with?", "Is this money for now or am I saving it for something specific?"],
    claim_type="qualitative",
    confidence="8 participants, single-site, exploratory — low generalizability, high texture value",
)

STOCK_THEFT_CARD = MechanismCard(
    id="eastern-cape-stock-theft-2024",
    citation="Farmers' perceptions on stock theft in some districts of the Eastern Cape Province, South Africa (PLOS One, 2024)",
    segment_tags=["communal_farmer", "rural", "livestock_owner"],
    mechanisms=[
        "Farmers distrust government capacity to prevent theft, so they self-fund coping measures (fencing, guard dogs, community watch) rather than waiting on formal protection",
        "Traditional, tangible identification (branding/tattooing) is trusted; unfamiliar tech-based solutions (forensic DNA, tracking apps) are met with skepticism — new interventions read as untested",
        "Livestock loss causes real mental distress, especially for elderly farmers, not just financial loss",
    ],
    vocabulary=["stock theft", "branding", "community watch"],
    objection_patterns=["Will this actually work, or is it another unproven system?", "Can I trust an app/technology with something this valuable?"],
    claim_type="mixed",
    confidence="192-farmer survey, 3 districts, chi-square tested",
)


def main():
    if not SIM_API_KEY or not SIM_BASE_URL or not SIM_MODEL:
        print("Missing SIM_LLM_* / LLM_* env vars — check repo root .env at", MAIN_REPO_ROOT / ".env")
        sys.exit(1)

    print(f"Using model: {SIM_MODEL} @ {SIM_BASE_URL}\n")

    # ── Coverage-honesty check first: does a real persona exist for the farmer card? ──
    archetypes = find_closest_archetype_persona("communal_farmer")
    print("=== Coverage check against real library archetypes ===")
    print(json.dumps(archetypes, indent=2))
    has_farmer = any("farm" in a.lower() or "livestock" in a.lower() for a in archetypes if a)
    print(f"\nDoes a communal_farmer / livestock archetype exist in the library? {has_farmer}")
    print("=> This is the coverage-honesty result the design doc calls for: STOCK_THEFT_CARD")
    print("   has NO real persona to bind to today. Confirms Tumelo's gap directly against live data.\n")

    block = RespondBlock()
    scenario = (
        "A fintech company is launching a new savings app that lets you save small "
        "amounts automatically and unlock a bonus if you don't withdraw for 3 months."
    )

    # ── Real test: grant_dependent_survivor persona, stokvel card (segment DOES match) ──
    persona = load_persona("Thandeka Nene")
    print(f"=== Persona: {persona.name} ({persona.archetype}) ===\n")

    print("--- WITHOUT mechanism card ---")
    resp_plain = block.run(persona, scenario, cards=[])
    print(resp_plain, "\n")

    print("--- WITH stokvel mechanism card ---")
    resp_grounded = block.run(persona, scenario, cards=[STOKVEL_CARD])
    print(resp_grounded, "\n")

    out = {
        "model": SIM_MODEL,
        "persona": persona.name,
        "archetype": persona.archetype,
        "scenario": scenario,
        "response_without_card": resp_plain,
        "response_with_card": resp_grounded,
        "coverage_check": {
            "library_archetypes": archetypes,
            "communal_farmer_archetype_exists": has_farmer,
        },
    }
    out_path = Path(__file__).resolve().parent / "context_grounding_pilot_output.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved full output to {out_path}")


if __name__ == "__main__":
    main()
