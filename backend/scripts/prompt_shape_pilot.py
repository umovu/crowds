"""Prompt-shape pilot — does moving structure out of the prose (and rendering the
qual identity prominently) kill the response-template collapse without losing
economic discipline?

Holds GROUNDING constant (same 12 real personas from panel_07eb044c9c55, same
production mechanism cards, same real income/fees figures, same Thuto pitch) and
varies only the PROMPT SHAPE:

  A  production — faithful reconstruction of the prompt_reframer panel prompt:
     identity = persona first sentence only, 3-beat question, 2-4 sentence cap,
     research context NOT rendered (profile-JSON burial, flag-off behaviour).
  B  free+grounded — voice_guide, beliefs and research cards rendered as prompt
     layers; open question ("lead with whatever hits you first"); hard guardrails
     kept (no invented figures, wanting!=affording, no buy-%, own-record referents
     only); structure pushed into mandatory STANCE/ECONOMIC tail.
  C  = B minus the rendered research cards (isolates unburying-cards vs
     unscripting-question).

Score with score_prompt_shape.py (deterministic, LLM-off).

Run (36 calls per repeat on the sim tier):
  D:/Fub-agentsociety/backend/.venv/Scripts/python.exe backend/scripts/prompt_shape_pilot.py [n_repeats]
"""

import json
import os
import sys
import time
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

MAIN_REPO_ROOT = Path("D:/Fub-agentsociety")
load_dotenv(MAIN_REPO_ROOT / ".env")

SIM_API_KEY = os.environ.get("SIM_LLM_API_KEY") or os.environ.get("LLM_API_KEY")
SIM_BASE_URL = os.environ.get("SIM_LLM_BASE_URL") or os.environ.get("LLM_BASE_URL")
SIM_MODEL = os.environ.get("SIM_LLM_MODEL") or os.environ.get("LLM_MODEL_NAME")

client = OpenAI(api_key=SIM_API_KEY, base_url=SIM_BASE_URL)

PANEL_DIR = MAIN_REPO_ROOT / "backend/uploads/panel_sessions/panel_07eb044c9c55"
CARDS_DIR = MAIN_REPO_ROOT / "backend/app/data/mechanism_cards"

PITCH = (
    "I'm building Thuto.io , Thuto.io is an innovative South African EdTech platform "
    "designed to boost high school student motivation by transforming study efforts "
    "into actual financial rewards . how would you feel about paying a 50rand per "
    "month subscription for Thuto ?"
)

# Budget tiers as computed deterministically at the original cast build
# (REPORT.md cast table — real-data derived, not re-derived here).
BUDGET_TIER = {
    "Nomfundo Mthembu": "moderate", "Siphosethu Mhlontlo": "moderate",
    "Thulani Mkhize": "moderate", "Lukhanyo Mthini": "moderate",
    "Jaco Botes": "loose", "Slindile Cele": "tight",
    "Kelebogile Tlhape": "tight", "Nolwandle Makhaphela": "loose",
    "Themba Mpondo": "moderate", "Sibusiso Nkosi": "moderate",
    "Thandiwe Mkhize": "moderate", "Palesa Molefe": "tight",
}

TIER_GLOSS = {
    "tight": "Every rand is spoken for; a new cost must displace an existing essential.",
    "moderate": "Some headroom exists, but a recurring cost competes with real essentials.",
    "loose": "Budget is not the main obstacle; the question is whether it's worth it.",
}


def load_cast():
    with open(PANEL_DIR / "agentsociety_profiles.json", encoding="utf-8") as f:
        return json.load(f)


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


def real_numbers_block(profile):
    lines = []
    inc = profile.get("monthly_household_income_rand")
    if inc:
        lines.append(f"- Household income: R{inc:,.0f}/month")
    fees = profile.get("fees_band")
    if fees:
        lines.append(f"- School fees band: {fees} per year")
    if not lines:
        return ""
    return "YOUR REAL NUMBERS (surveyed — never invent others):\n" + "\n".join(lines)


def budget_block(profile):
    tier = BUDGET_TIER.get(profile["name"], "moderate")
    block = (
        f"YOUR BUDGET REALITY (fixed — set by your real circumstances): {tier.upper()}. "
        f"{TIER_GLOSS[tier]}\n"
        "You may WANT something and still not be able to justify the spend.\n"
        f"{real_numbers_block(profile)}"
    )
    return block


def research_block(bound_cards):
    if not bound_cards:
        return ""
    parts = ["HOW PEOPLE IN YOUR SITUATION ARE DOCUMENTED TO DECIDE (research context):"]
    for c in bound_cards:
        for m in (c.get("mechanisms") or [])[:3]:
            parts.append(f"- {m}")
        obj = c.get("objection_patterns") or []
        if obj:
            parts.append(f"- Questions people like you tend to ask: {'; '.join(obj[:2])}")
    parts.append(
        "Let these shape HOW you weigh the pitch if they fit you; never quote them "
        "as research or mention studies."
    )
    return "\n".join(parts)


TAIL = (
    "\nMANDATORY OUTPUT CONTRACT — your reply is free-form prose, but it MUST end "
    "with exactly these two lines (machine-parsed; the run is discarded without them):\n"
    "STANCE: <supportive|neutral|concerned|oppose>\n"
    'ECONOMIC: {"impulse": 0.0-1.0, "perceived_cost": "...", "primary_objection": "...", '
    '"reconsider_condition": "..."}\n'
    "The ECONOMIC line must be valid one-line JSON.\n"
)

# Unlicensed-texture scrub (condition D): remove sentences whose referents no
# survey field licenses — the deterministic preview of the library texture
# rebuild. Grant-talk is scrubbed only when the record says receives_grant is
# falsy (texture contradicting the persona's own data).
import re as _re

_UNLICENSED_PAT = _re.compile(
    r"load[- ]?shedding|power cuts?|taps? run dry|water (outage|cuts?|interruption)|no water",
    _re.I,
)
_GRANT_PAT = _re.compile(r"\bgrants?\b|sassa", _re.I)


def scrub_text(text, profile):
    if not text:
        return text
    keep = []
    for sent in _re.split(r"(?<=[.!?])\s+", text):
        if _UNLICENSED_PAT.search(sent):
            continue
        if _GRANT_PAT.search(sent) and not profile.get("receives_grant"):
            continue
        keep.append(sent)
    return " ".join(keep)


def scrubbed_profile(profile):
    p = dict(profile)
    for k in ("persona", "background_story", "voice_guide", "behavioral_tendencies"):
        p[k] = scrub_text(p.get(k) or "", profile)
    return p


def prompt_A(profile, bound_cards):
    """Faithful reconstruction of the production panel prompt shape."""
    persona = profile.get("persona", "")
    first_sentence = persona.split(".")[0] if persona else f"You are {profile['name']}."
    topics = profile.get("interested_topics") or []
    stake = f"You care deeply about: {topics[0]}." if topics else ""
    return (
        f"You are {profile['name']}. {first_sentence.strip()}.\n"
        "Respond in character. Do not speak as an analyst or observer. "
        "Use 'I', 'my', 'my family'. Never speak in generalities about 'the government should'.\n"
        f"\n{stake}\n"
        f"\n{budget_block(profile)}\n"
        "\nQUESTION:\n\n"
        f"{PITCH}\n\n"
        f"How do you react to this pitch, {profile['name']}? "
        "Be specific: what works for you, what puts you off, and what would have to "
        "change for you to reconsider. Be honest about whether you could justify the "
        "spend — wanting it and affording it are different things.\n"
        "\nRULES:\n"
        "1. Answer in first person ('I', 'my family', 'my street').\n"
        "2. Reference specific details from your background.\n"
        "3. Do not speak in generalities. Speak from YOUR experience.\n"
        "4. Keep it to 2-4 sentences. Be specific, not vague.\n"
        "5. Do NOT invent facts not in your background story.\n"
        + TAIL
    )


def prompt_B(profile, bound_cards, render_research=True):
    """Free prose on top of fully rendered truth: identity, voice, beliefs, budget,
    research — hard guardrails on facts, no choreography of the response shape."""
    beliefs = "\n".join(f"- {b}" for b in (profile.get("beliefs") or [])[:3])
    research = research_block(bound_cards) if render_research else ""
    return (
        f"You are {profile['name']}.\n"
        f"{profile.get('persona', '')}\n\n"
        f"YOUR STORY: {profile.get('background_story', '')}\n\n"
        f"HOW YOU SPEAK: {profile.get('voice_guide', '')}\n\n"
        f"WHAT YOU BELIEVE:\n{beliefs}\n\n"
        f"{budget_block(profile)}\n\n"
        f"{research}\n\n"
        "Someone puts this in front of you:\n"
        f"\"{PITCH}\"\n\n"
        f"React as you actually would, {profile['name']} — in your own voice, leading "
        "with whatever hits you first. One concern is allowed to dominate; you do not "
        "need to cover everything.\n"
        "\nHARD RULES (facts, not style):\n"
        "- Never state a rand amount that is not in YOUR REAL NUMBERS or the pitch itself.\n"
        "- Wanting it and affording it are different things — never merge them.\n"
        "- Never give a purchase probability or a 'would buy' verdict.\n"
        "- Speak only from what is in your own record and briefing above — do not bring "
        "in outside conditions (electricity, water, crime) unless they appear there.\n"
        + TAIL
    )


def respond(prompt):
    r = client.chat.completions.create(
        model=SIM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=400,
    )
    return r.choices[0].message.content.strip()


OUT_PATH = Path(__file__).parent / "prompt_shape_pilot_output.json"


def _flush(runs, n_repeats):
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({
        "model": SIM_MODEL,
        "pitch": PITCH,
        "n_repeats": n_repeats,
        "panel_source": str(PANEL_DIR),
        "runs": runs,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(OUT_PATH)


def main():
    n_repeats = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    cast = load_cast()
    cards = load_cards()

    runs = []
    total = len(cast) * 4 * n_repeats
    done = 0
    for rep in range(n_repeats):
        for profile in cast:
            bound = bind_cards(profile, cards)
            prompts = {
                "A_production": prompt_A(profile, bound),
                "B_free_grounded": prompt_B(profile, bound, render_research=True),
                "C_free_nocards": prompt_B(profile, bound, render_research=False),
                "D_free_scrubbed": prompt_B(scrubbed_profile(profile), bound, render_research=True),
            }
            for cond, prompt in prompts.items():
                done += 1
                print(f"[{done}/{total}] rep{rep} {profile['name']} {cond}", flush=True)
                try:
                    text = respond(prompt)
                except Exception as e:  # keep the run alive; scorer skips errors
                    text = f"__ERROR__ {e}"
                    time.sleep(2)
                runs.append({
                    "repeat": rep,
                    "name": profile["name"],
                    "archetype": profile.get("actor_archetype"),
                    "budget_tier": BUDGET_TIER.get(profile["name"]),
                    "cards_bound": [c["id"] for c in bound],
                    "condition": cond,
                    "response": text,
                })
                # Incremental save: a killed run keeps everything done so far.
                _flush(runs, n_repeats)

    _flush(runs, n_repeats)
    print(f"\nSaved {len(runs)} responses -> {OUT_PATH}")


if __name__ == "__main__":
    main()
