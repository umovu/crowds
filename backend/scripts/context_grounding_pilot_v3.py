"""
Context-grounding pilot v3 — qual-grounded need-vs-want (impulse) elicitation.

Question under test: does walking a persona through its segment's DOCUMENTED
evaluative rules (the new `evaluative_rules` card field) before it rates its
impulse produce better-grounded want-reasoning than injecting the card as flat
context — and than no card at all?

Three arms per (persona, scenario) case, N repeats each:
  A baseline       — no card; economic lens exactly as production builds it.
  B card-flat      — card mechanisms injected as context (v2 style); lens unchanged.
  C card-decision  — B plus a "HOW PEOPLE LIKE YOU DECIDE" block (evaluative_rules
                     + objection_patterns) and a restructured impulse elicitation:
                     answer your segment's questions first, THEN rate impulse.

Hard rules preserved in every arm: affordability = deterministic budget tier from
mode_specs (real persona data, LLM never touches it); impulse stays qualitative
desire; no "% would buy"; cards bind by archetype tag lookup only.

Run:      D:/Fub-agentsociety/backend/.venv/Scripts/python.exe backend/scripts/context_grounding_pilot_v3.py
LLM-off:  ... context_grounding_pilot_v3.py --selftest
"""

import argparse
import difflib
import json
import os
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

WORKTREE_ROOT = Path(__file__).resolve().parents[2]
MAIN_REPO_ROOT = Path("D:/Fub-agentsociety")
EXTRACTION_DIR = WORKTREE_ROOT / "docs" / "extraction"
load_dotenv(MAIN_REPO_ROOT / ".env")

# Deterministic economic pieces come from the real service layer (read-only import).
# Loaded straight from the file — importing the app.services package pulls in the
# whole agent stack (agentsociety2), which this pilot must not depend on.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "mode_specs", WORKTREE_ROOT / "backend" / "app" / "services" / "mode_specs.py")
mode_specs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mode_specs)
BUDGET_TIER_GLOSS = mode_specs.BUDGET_TIER_GLOSS
budget_headroom_tier = mode_specs.budget_tier
disposition = mode_specs.disposition

N_REPEATS = 5
TEMPERATURE = 0.7


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
    safety_economic: int | None = None


def load_card(card_id: str) -> dict:
    card = json.loads((EXTRACTION_DIR / f"{card_id}.card.json").read_text(encoding="utf-8"))
    if not card.get("evaluative_rules"):
        sys.exit(f"Card {card_id} has no evaluative_rules — backfill before running v3.")
    return card


def load_persona(archetype: str) -> Persona:
    data = json.loads(
        (MAIN_REPO_ROOT / "backend/app/data/persona_library/personas.json").read_text(encoding="utf-8")
    )
    for p in data["personas"]:
        if p.get("actor_archetype") == archetype:
            needs = p.get("needs") or {}
            return Persona(
                name=p["name"], age=p["age"], province=p["province"],
                occupation=p.get("occupation", ""), archetype=archetype,
                persona_summary=p.get("persona", ""),
                background_story=p.get("background_story", ""),
                beliefs=p.get("beliefs", []),
                safety_economic=needs.get("safety_economic"),
            )
    sys.exit(f"No library persona with archetype {archetype!r} — coverage-honesty stop.")


# ── Prompt blocks ────────────────────────────────────────────────────────────

SYSTEM_BASE = (
    "You are roleplaying a real South African person for a market simulation. "
    "Speak in first person, in your own voice, concrete to your own circumstances."
)

RESPONSE_FORMAT = (
    "\nReturn ONE JSON object only:\n"
    '{"reaction": "<4-6 sentences, your honest reaction in your own voice>",\n'
    ' "economic": {"impulse": 0.0-1.0, "perceived_cost": "...", "willingness_band": "...",\n'
    '              "primary_objection": "...", "reconsider_condition": "...", "needed_fact": "..."}}\n'
)


def identity_block(p: Persona) -> str:
    return (
        f"# Your identity (real survey-derived profile — do not contradict it)\n"
        f"Name: {p.name}\nAge: {p.age}\nProvince: {p.province}\n"
        f"Occupation: {p.occupation}\nArchetype: {p.archetype}\n"
        f"Summary: {p.persona_summary}\nBackground: {p.background_story}\n"
        f"Beliefs: {'; '.join(p.beliefs)}\n"
    )


def mechanism_block(card: dict) -> str:
    lines = ["# Research-grounded context for people like you (reason through this; do not quote it verbatim)"]
    lines.append(f"\nFrom {'; '.join(card['citation'])} [{card['claim_type']}]:")
    lines.extend(f"  - {m}" for m in card["mechanisms"])
    if card.get("vocabulary"):
        lines.append(f"  Vocabulary people like you use: {', '.join(card['vocabulary'])}")
    return "\n".join(lines)


def decision_block(card: dict) -> str:
    """Arm C only: the segment's documented evaluative rules + objection questions."""
    lines = [
        "=== HOW PEOPLE LIKE YOU DECIDE (documented in research on your segment) ===",
        "These are tendencies documented for people in your situation, not a script —",
        "you may weigh them differently, but if you do, say why.",
        "Rules of thumb your segment applies when weighing something new:",
    ]
    lines.extend(f"- {r}" for r in card["evaluative_rules"])
    lines.append("Questions people like you actually ask before spending:")
    lines.extend(f"- {q}" for q in card.get("objection_patterns", []))
    return "\n".join(lines)


def economic_lens(pitch: dict, tier: str, decision_framed: bool) -> str:
    """Mirror of mode_specs.build_economic_lens for a first-round pilot call.

    Identical wants/affords separation; `decision_framed` swaps the impulse
    elicitation from a direct rating to rules-first reasoning (the v3 variable).
    """
    gloss = BUDGET_TIER_GLOSS.get(tier, BUDGET_TIER_GLOSS["moderate"])
    base = (
        f"\n=== PRODUCT UNDER STRESS-TEST ===\n"
        f"- What it is: {pitch['what_it_is']}\n"
        f"- Pricing: {pitch['pricing']}\n"
        f"- Problem it claims to solve: {pitch['problem_solved']}\n"
        f"- How you currently solve this (status quo): {pitch['status_quo_alternative']}\n\n"
        f"=== YOUR BUDGET REALITY (fixed — set by your real circumstances) ===\n"
        f"- Budget headroom: {tier.upper()}. {gloss}\n"
        f"  This is your real constraint. You may WANT something and still not be able to justify it.\n\n"
        f"=== ECONOMIC REASONING RULES ===\n"
        f"- Separate WANTING it from being able to AFFORD it. Desire is not the same as spending.\n"
        f"- Weigh PRICE against YOUR budget headroom above, and VALUE against your status-quo.\n"
        f"- Speak the economics in your own voice (rands, data, running cost, switching effort).\n"
        f"- NEVER state a purchase probability, a '% would buy', or any buy/validation verdict.\n"
        f"- If you need a real SA cost that was not provided, do NOT invent a figure — name it\n"
        f"  in 'needed_fact' and reason qualitatively. Never state a rand amount you are not sure of.\n"
    )
    if decision_framed:
        base += (
            f"- BEFORE rating your impulse: work through the HOW PEOPLE LIKE YOU DECIDE rules and\n"
            f"  answer your segment's questions above, one line each, inside your 'reaction'. THEN\n"
            f"  give 'impulse' as the residue of that reasoning — how much you WANT to spend on it\n"
            f"  right now (0 = no desire, 1 = strong pull), which is DESIRE, NOT a buy prediction.\n"
            f"- Pick 'primary_objection' from whichever of those questions actually blocked or\n"
            f"  dampened you; if none fit, state your own and say why the documented ones don't apply.\n"
        )
    else:
        base += (
            f"- In 'impulse', rate how much you WANT to spend on it right now (0 = no desire,\n"
            f"  1 = strong pull to spend) — it is DESIRE, NOT a prediction that you will buy.\n"
            f"  You can have high impulse and still be unable to afford it.\n"
        )
    return base


def build_system(persona: Persona, pitch: dict, card: dict | None, arm: str) -> str:
    tier = budget_headroom_tier(
        archetype=persona.archetype, safety_economic=persona.safety_economic,
        occupation=persona.occupation,
    )
    parts = [SYSTEM_BASE, identity_block(persona)]
    if card is not None:
        assert persona.archetype in card["segment_tags"], (
            f"binding violation: {persona.archetype} not in {card['id']}.segment_tags")
        parts.append(mechanism_block(card))
        if arm == "C":
            parts.append(decision_block(card))
    parts.append(economic_lens(pitch, tier, decision_framed=(arm == "C" and card is not None)))
    parts.append(RESPONSE_FORMAT)
    return "\n\n".join(parts)


# ── Test cases ───────────────────────────────────────────────────────────────

CASES = [
    {
        "label": "edtech-free-to-paid",
        "archetype": "guardian_parent",
        "card_id": "education-payment-conversion",
        "pitch": {
            "what_it_is": "a homework and exam-prep app your child's school recommends; the basic "
                          "version is free, and a premium tier adds past papers, weekly progress "
                          "reports to your phone, and one-on-one tutor chats",
            "pricing": "free basic tier; premium at R79/month, cancel any time",
            "problem_solved": "parents can't see how their child is really doing until the report card, "
                              "and extra lessons are expensive or far away",
            "status_quo_alternative": "helping with homework yourself, asking teachers at meetings, "
                                      "or paying for occasional extra classes",
        },
    },
    {
        "label": "locked-savings-app",
        "archetype": "grant_dependent_survivor",
        "card_id": "stokvels-calibration",
        "pitch": {
            "what_it_is": "a savings app that automatically moves small amounts from your account "
                          "into a locked pocket, with a bonus if you don't withdraw for three months",
            "pricing": "R15/month after a free first month; ten percent bonus on untouched savings at three months",
            "problem_solved": "money in the pocket gets absorbed by daily spending before month-end",
            "status_quo_alternative": "keeping cash aside at home, or saving through a stokvel or "
                                      "burial society with people you know",
        },
    },
]


# ── LLM plumbing ─────────────────────────────────────────────────────────────

def get_client():
    from openai import OpenAI
    key = os.environ.get("SIM_LLM_API_KEY")
    base = os.environ.get("SIM_LLM_BASE_URL")
    model = os.environ.get("SIM_LLM_MODEL") or os.environ.get("SIM_LLM_MODEL_NAME")
    if not (key and base and model):
        sys.exit("Missing SIM_LLM_* env vars")
    return OpenAI(api_key=key, base_url=base), model


def parse_reply(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"reaction": text.strip(), "economic": {}, "_parse_error": "no JSON found"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return {"reaction": text.strip(), "economic": {}, "_parse_error": str(e)}


# ── Deterministic scoring ────────────────────────────────────────────────────

def rand_amounts(text: str) -> set[str]:
    return {m.replace(" ", "").replace(",", "").upper()
            for m in re.findall(r"R\s?[\d][\d\s,]*(?:\.\d+)?", text or "")}


def score_run(reply: dict, card: dict, system_prompt: str) -> dict:
    reaction = reply.get("reaction", "") or ""
    econ = reply.get("economic", {}) or {}
    blob = (reaction + " " + json.dumps(econ)).lower()
    vocab_hits = [v for v in card.get("vocabulary", []) if v.lower() in blob]
    # objection grounding: does primary_objection echo a documented pattern?
    obj = (econ.get("primary_objection") or "").lower()
    obj_grounded = any(
        difflib.SequenceMatcher(None, obj, q.lower()).ratio() > 0.45
        or len(set(re.findall(r"[a-z']+", obj)) & set(re.findall(r"[a-z']+", q.lower()))) >= 3
        for q in card.get("objection_patterns", [])
    ) if obj else False
    # leak check: rand amounts in the reply that were never in the prompt
    leaked = sorted(rand_amounts(reaction + " " + json.dumps(econ)) - rand_amounts(system_prompt))
    return {
        "impulse": econ.get("impulse"),
        "primary_objection": econ.get("primary_objection"),
        "vocab_hits": vocab_hits,
        "objection_grounded": obj_grounded,
        "leaked_rand_amounts": leaked,
        "parse_error": reply.get("_parse_error"),
    }


def summarize_arm(runs: list[dict]) -> dict:
    impulses = [r["impulse"] for r in runs if isinstance(r.get("impulse"), (int, float))]
    objections = [r.get("primary_objection") or "" for r in runs]
    dupes = sum(
        1 for i in range(len(objections)) for j in range(i + 1, len(objections))
        if objections[i] and difflib.SequenceMatcher(None, objections[i], objections[j]).ratio() > 0.85
    )
    return {
        "impulse_mean": round(statistics.mean(impulses), 3) if impulses else None,
        "impulse_stdev": round(statistics.stdev(impulses), 3) if len(impulses) > 1 else None,
        "vocab_hits_total": sum(len(r["vocab_hits"]) for r in runs),
        "objection_grounded_count": sum(1 for r in runs if r["objection_grounded"]),
        "near_duplicate_objection_pairs": dupes,  # >3 of 5 near-identical = over-scripting flag
        "leaks": sum(len(r["leaked_rand_amounts"]) for r in runs),
        "parse_errors": sum(1 for r in runs if r.get("parse_error")),
    }


# ── LLM-off selftest ─────────────────────────────────────────────────────────

def selftest():
    for case in CASES:
        card = load_card(case["card_id"])
        persona = load_persona(case["archetype"])
        sys_a = build_system(persona, case["pitch"], None, "A")
        sys_b = build_system(persona, case["pitch"], card, "B")
        sys_c = build_system(persona, case["pitch"], card, "C")
        # no card → no research/decision content, and A is arm-independent
        assert "Research-grounded" not in sys_a and "HOW PEOPLE LIKE YOU DECIDE" not in sys_a
        assert sys_a == build_system(persona, case["pitch"], None, "C"), \
            "arm flag must be inert without a bound card"
        # B has mechanisms but NOT the decision framing
        assert "Research-grounded" in sys_b and "HOW PEOPLE LIKE YOU DECIDE" not in sys_b
        assert "BEFORE rating your impulse" not in sys_b
        # C has both, including every rule and objection pattern
        assert "HOW PEOPLE LIKE YOU DECIDE" in sys_c and "BEFORE rating your impulse" in sys_c
        for r in card["evaluative_rules"]:
            assert r in sys_c
        # budget block identical across arms — affordability never moves with the card
        block = "=== YOUR BUDGET REALITY"
        get_budget = lambda s: s[s.index(block): s.index("=== ECONOMIC REASONING")]
        assert get_budget(sys_a) == get_budget(sys_b) == get_budget(sys_c)
        # hard-rule text present in every arm
        for s in (sys_a, sys_b, sys_c):
            assert "NEVER state a purchase probability" in s
        # disposition mapping stays deterministic and probability-free
        assert "buy" not in disposition(0.9, "tight")
        print(f"selftest OK: {case['label']} ({persona.name}, {persona.archetype}, card {card['id']})")
    print("All LLM-off assertions passed.")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true", help="run LLM-off assertions only")
    ap.add_argument("--repeats", type=int, default=N_REPEATS)
    args = ap.parse_args()

    selftest()
    if args.selftest:
        return

    client, model = get_client()
    print(f"\nModel: {model} — {len(CASES)} cases x 3 arms x {args.repeats} repeats\n")
    results = []
    for case in CASES:
        card = load_card(case["card_id"])
        persona = load_persona(case["archetype"])
        row = {"case": case["label"], "persona": persona.name,
               "archetype": persona.archetype, "card": card["id"], "arms": {}}
        for arm, bound in (("A", None), ("B", card), ("C", card)):
            system = build_system(persona, case["pitch"], bound, arm)
            runs = []
            for i in range(args.repeats):
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content":
                            "The founder has just described this product to you. "
                            "React honestly. Return the JSON object only."},
                    ],
                    temperature=TEMPERATURE,
                    max_tokens=700,
                    extra_body={"enable_thinking": False},
                )
                reply = parse_reply(resp.choices[0].message.content or "")
                scored = score_run(reply, card, system)
                scored["reaction"] = reply.get("reaction")
                scored["economic"] = reply.get("economic")
                runs.append(scored)
                print(f"  {case['label']} arm {arm} run {i+1}: impulse={scored['impulse']} "
                      f"grounded_objection={scored['objection_grounded']} "
                      f"vocab={len(scored['vocab_hits'])} leaks={scored['leaked_rand_amounts']}")
            row["arms"][arm] = {"summary": summarize_arm(runs), "runs": runs}
        results.append(row)
        for arm in ("A", "B", "C"):
            print(f"{case['label']} arm {arm} summary: {row['arms'][arm]['summary']}")

    out = {"model": model, "temperature": TEMPERATURE, "repeats": args.repeats,
           "cases": [c["label"] for c in CASES], "results": results}
    out_path = Path(__file__).resolve().parent / "context_grounding_pilot_v3_output.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
