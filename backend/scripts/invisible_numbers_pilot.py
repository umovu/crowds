"""Invisible-numbers pilot runner (spec: docs/INVISIBLE_NUMBERS_PILOT.md).

Holds EVERYTHING constant across 4 conditions except the economic channel:

  A_control     production-faithful: tier gloss + REAL NUMBERS block, justify ask.
                (Block text mirrors prompt_reframer._build_budget_reality +
                mode_specs._build_real_numbers_block verbatim, incl. glosses.)
  B_block_only  compiled situation block instead of gloss+numbers, justify ask.
  C_full        compiled situation block + open reaction ask.
  D_rule_only   A + "never cite own income/fees as figures" rule (cheapest
                possible production patch).

Research cards are bound deterministically and recorded per run, but NOT
rendered in any condition — the economic channel is the only variable under
test (A stays a faithful production control, which buries research).

12 personas (panel_07eb044c9c55 cast) x 4 conditions x n_repeats = 48 calls
per repeat on the sim tier. Incremental flush after every call; __ERROR__ on
LLM failure (never a synthetic quote).

Run:
  D:/Fub-agentsociety/backend/.venv/Scripts/python.exe backend/scripts/invisible_numbers_pilot.py [n_repeats]
"""

import json
import os
import re
import sys
import time
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from situation_compiler import compile_situation  # noqa: E402

MAIN_REPO_ROOT = Path("D:/Fub-agentsociety")
load_dotenv(MAIN_REPO_ROOT / ".env")

SIM_API_KEY = os.environ.get("SIM_LLM_API_KEY") or os.environ.get("LLM_API_KEY")
SIM_BASE_URL = os.environ.get("SIM_LLM_BASE_URL") or os.environ.get("LLM_BASE_URL")
# .strip(): cmd's `set VAR=value &&` idiom leaks a trailing space into the
# value, which the provider rejects with "Model not exist" (run-2 lesson).
SIM_MODEL = (os.environ.get("SIM_LLM_MODEL") or os.environ.get("LLM_MODEL_NAME") or "").strip()

# timeout+max_retries: a hung streaming call once stalled a run for 10+ min;
# fail fast into __ERROR__ (scorer skips it; resume retries it later).
client = OpenAI(api_key=SIM_API_KEY, base_url=SIM_BASE_URL,
                timeout=90.0, max_retries=1)

PANEL_DIR = MAIN_REPO_ROOT / "backend/uploads/panel_sessions/panel_07eb044c9c55"
CARDS_DIR = MAIN_REPO_ROOT / "backend/app/data/mechanism_cards"

PITCH = (
    "I'm building Thuto.io , Thuto.io is an innovative South African EdTech platform "
    "designed to boost high school student motivation by transforming study efforts "
    "into actual financial rewards . how would you feel about paying a 50rand per "
    "month subscription for Thuto ?"
)

FRAMED_PITCH = (
    f"I'm putting this in front of you: {PITCH}\n"
    "I want your honest reaction — what works, what doesn't, what would put you off."
)

# Production glosses, verbatim from backend/app/services/mode_specs.py
# (BUDGET_TIER_GLOSS). Copied, not imported, to keep the pilot self-contained.
TIER_GLOSS = {
    "tight": "Money is tight. New spending has to clear a high bar; most extras get cut.",
    "moderate": "There's some room to spend, but it has to be justified against the cost.",
    "loose": "Budget is not the main obstacle; the question is whether it's worth it.",
}

JUSTIFY_ASK = (
    "How do you react to this pitch, {name}? Be specific: what works for you, "
    "what puts you off, and what would have to change for you to reconsider. "
    "Be honest about whether you could justify the spend — wanting it and "
    "affording it are different things."
)

OPEN_ASK = (
    "React as you actually would, {name} — in your own voice, leading with "
    "whatever hits you first. One concern is allowed to dominate; you do not "
    "need to cover everything."
)

RULES = (
    "\nRULES:\n"
    "1. Answer in first person ('I', 'my family', 'my street').\n"
    "2. Reference specific details from your background.\n"
    "3. Do not speak in generalities. Speak from YOUR experience.\n"
    "4. Keep it to 2-4 sentences. Be specific, not vague.\n"
    "5. Do NOT invent facts not in your background story.\n"
)

D_EXTRA_RULE = (
    "6. Never state your own household income or school fees as figures — "
    "speak about them in your own words, not in rands.\n"
)

TAIL = (
    "\nMANDATORY OUTPUT CONTRACT — your reply is free-form prose, but it MUST end "
    "with exactly these two lines (machine-parsed; the run is discarded without them):\n"
    "STANCE: <supportive|neutral|concerned|oppose>\n"
    'ECONOMIC: {"impulse": 0.0-1.0, "perceived_cost": "...", "primary_objection": "...", '
    '"reconsider_condition": "..."}\n'
    "The ECONOMIC line must be valid one-line JSON.\n"
)


def load_cast():
    with open(PANEL_DIR / "agentsociety_profiles.json", encoding="utf-8") as f:
        profiles = json.load(f)
    # The stored artifact has mojibake'd en-dashes in fee bands (U+FFFD).
    # Production renders bands from its live store (unmangled); sanitize here
    # so A/D inject exactly what production would have.
    for p in profiles:
        if p.get("fees_band"):
            p["fees_band"] = p["fees_band"].replace("�", "–")
        if p.get("learner_fee_bands"):
            p["learner_fee_bands"] = [b.replace("�", "–") for b in p["learner_fee_bands"]]
    return profiles


def load_cards():
    cards = {}
    for fp in sorted(CARDS_DIR.glob("*.json")):
        with open(fp, encoding="utf-8") as f:
            c = json.load(f)
        if c.get("id"):
            cards[c["id"]] = c
    return cards


def bind_cards(profile, cards):
    """Deterministic binding: card attaches iff persona archetype in segment_tags."""
    arch = profile.get("actor_archetype")
    return [c for c in cards.values() if arch in (c.get("segment_tags") or [])]


def production_budget_block(profile):
    """Verbatim mirror of prompt_reframer._build_budget_reality +
    mode_specs._build_real_numbers_block (production wording)."""
    tier = profile["budget_tier"]
    gloss = TIER_GLOSS.get(tier, TIER_GLOSS["moderate"])
    block = (
        f"YOUR BUDGET REALITY (fixed — set by your real circumstances): "
        f"{tier.upper()}. {gloss}\n"
        "You may WANT something and still not be able to justify the spend."
    )
    lines = []
    inc = profile.get("monthly_household_income_rand")
    if isinstance(inc, (int, float)) and inc > 0:
        lines.append(
            f"- Your household earns about R{int(round(inc)):,}/month (real, surveyed).")
    bands = []
    if profile.get("fees_band"):
        bands.append(profile["fees_band"])
    lb = profile.get("learner_fee_bands")
    if isinstance(lb, (list, tuple)):
        bands.extend(b for b in lb if b)
    elif lb:
        bands.append(lb)
    paid = [b for b in dict.fromkeys(bands) if b and b != "No fees"]
    if paid:
        shown = [b if "year" in b.lower() else f"{b} per year" for b in paid]
        lines.append(
            f"- You pay school fees in the {', '.join(shown)} band "
            "(real, surveyed — that is PER YEAR, not per month)."
        )
    elif bands:
        lines.append("- Your learners are at a no-fee school (you pay no school fees).")
    if lines:
        block += (
            "\n\n=== YOUR REAL NUMBERS (surveyed — reason against THESE, "
            "do not invent figures) ===\n"
            + "\n".join(lines)
            + "\n  Weigh the pitch's cost against these actual figures in your own voice.\n"
            "  These figures describe your economic position — where research context "
            "about people in your situation is provided, reason the way it documents "
            "people in your position actually deciding, not by arithmetic alone.\n"
        )
    return block


def situation_block(profile, version=1):
    """B/C economic channel: compiled lived circumstance, no provenance frame."""
    return (
        "YOUR CIRCUMSTANCES:\n"
        + compile_situation(profile, version=version)
        + "\nYou may WANT something and still not be able to justify the spend."
    )


def identity_head(profile):
    persona = profile.get("persona", "")
    first = persona.split(".")[0].strip() if persona else ""
    head = f"You are {profile['name']}."
    if first:
        head += f" {first}."
    head += (
        "\nRespond in character. Do not speak as an analyst or observer. "
        "Use 'I', 'my', 'my family'. Never speak in generalities about "
        "'the government should'."
    )
    topics = profile.get("interested_topics") or []
    if topics:
        head += f"\n\nYou care deeply about: {topics[0]}."
    return head


def build_prompt(profile, condition):
    head = identity_head(profile)
    if condition in ("A_control", "D_rule_only"):
        econ = production_budget_block(profile)
        ask = JUSTIFY_ASK.format(name=profile["name"])
        rules = RULES + (D_EXTRA_RULE if condition == "D_rule_only" else "")
    elif condition in ("B_block_only", "B2_block_v2"):
        econ = situation_block(profile, version=2 if condition == "B2_block_v2" else 1)
        ask = JUSTIFY_ASK.format(name=profile["name"])
        rules = RULES
    elif condition in ("C_full", "C2_full_v2"):
        econ = situation_block(profile, version=2 if condition == "C2_full_v2" else 1)
        ask = OPEN_ASK.format(name=profile["name"])
        rules = RULES
    else:
        raise ValueError(condition)
    prompt = (
        f"{head}\n\n{econ}\n\nQUESTION:\n\n{FRAMED_PITCH}\n\n{ask}\n{rules}{TAIL}"
    )
    return prompt, econ


# run1: the frozen run-1 design (2026-07-17). run2: block v2 (rewritten loose
# rhythm) under both asks + A control + D replication, scored with the frozen
# v2 lexicon. Output files are kept separate so run 1 is never clobbered.
CONDITION_SETS = {
    "run1": ("A_control", "B_block_only", "C_full", "D_rule_only"),
    "run2": ("A_control", "B2_block_v2", "C2_full_v2", "D_rule_only"),
}
OUTPUT_PATHS = {
    "run1": Path(__file__).parent / "invisible_numbers_pilot_output.json",
    "run2": Path(__file__).parent / "invisible_numbers_run2_output.json",
}


def respond(prompt):
    r = client.chat.completions.create(
        model=SIM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=400,
    )
    return r.choices[0].message.content.strip()


OUT_PATH = OUTPUT_PATHS["run1"]


def _flush(runs, n_repeats, conditions, out_path):
    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({
        "model": SIM_MODEL,
        "pitch": PITCH,
        "framed_pitch": FRAMED_PITCH,
        "n_repeats": n_repeats,
        "conditions": list(conditions),
        "panel_source": str(PANEL_DIR),
        "runs": runs,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(out_path)


def main():
    n_repeats = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    cond_set = sys.argv[2] if len(sys.argv) > 2 else "run1"
    conditions = CONDITION_SETS[cond_set]
    out_path = OUTPUT_PATHS[cond_set]
    cast = load_cast()
    cards = load_cards()

    # Resume: reuse prior VALID responses from the output file; redo errored or
    # missing (repeat, name, condition) triples. A silently-killed run loses
    # only its in-flight call.
    runs = []
    done_keys = set()
    if out_path.exists():
        try:
            prior = json.loads(out_path.read_text(encoding="utf-8"))
            for r in prior.get("runs", []):
                if not r["response"].startswith("__ERROR__"):
                    runs.append(r)
                    done_keys.add((r["repeat"], r["name"], r["condition"]))
            if done_keys:
                print(f"resuming: {len(done_keys)} valid responses reused", flush=True)
        except (json.JSONDecodeError, KeyError):
            pass

    total = len(cast) * len(conditions) * n_repeats
    done = 0
    for rep in range(n_repeats):
        for profile in cast:
            bound = bind_cards(profile, cards)
            for cond in conditions:
                done += 1
                if (rep, profile["name"], cond) in done_keys:
                    continue
                print(f"[{done}/{total}] rep{rep} {profile['name']} {cond}", flush=True)
                prompt, econ = build_prompt(profile, cond)
                try:
                    text = respond(prompt)
                except Exception as e:  # keep the run alive; scorer skips errors
                    text = f"__ERROR__ {e}"
                    time.sleep(2)
                runs.append({
                    "repeat": rep,
                    "name": profile["name"],
                    "archetype": profile.get("actor_archetype"),
                    "budget_tier": profile.get("budget_tier"),
                    "income": profile.get("monthly_household_income_rand"),
                    "condition": cond,
                    "econ_block": econ,
                    "cards_bound": [c["id"] for c in bound],
                    "response": text,
                })
                _flush(runs, n_repeats, conditions, out_path)

    _flush(runs, n_repeats, conditions, out_path)
    print(f"\nSaved {len(runs)} responses -> {out_path}")


if __name__ == "__main__":
    main()
