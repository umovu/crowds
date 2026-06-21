"""
preview_b2b_persona — THROWAWAY livewire preview of one composed B2B persona.

NOT part of the pipeline. A scratch script to SEE a B2B persona react before any
real wiring: it composes one real QLFS banking decision-maker body + the banking
sector record + the procurement function record (Dataset B), generates B2B-aware
texture, then runs a sample fintech pitch and prints the reaction as a procurement
officer reasoning in the bank's interest.

Everything grounded stays grounded: the body is a real survey row, the mandate is
the authored Dataset B record (LLM never rewrites it). The LLM only writes voice and
the pitch reaction. Delete this file once the real sampler/panel wiring lands.

Run:  python backend/scripts/preview_b2b_persona.py [--pitch "..."] [--seed N]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import persona_sampler as ps

_DATA = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "app", "data", "persona_library"))


def _load_json(name: str) -> dict:
    with open(os.path.join(_DATA, name), "r", encoding="utf-8") as f:
        return json.load(f)


def compose_b2b_skeleton(sector_id: str, function_id: str, seed: int) -> dict:
    """One real QLFS body in the sector's industry + the sector & function mandate.

    The body is sampled (real co-occurrence); the mandate fields are attached frozen.
    Mirrors what the real sample_b2b_skeletons will do — composition, not invention.
    Excludes informal rows: a corporate B2B buyer is formal-sector by definition.
    """
    sectors = _load_json("b2b_sectors.json")["sectors"]
    functions = _load_json("b2b_functions.json")["functions"]
    sector = sectors[sector_id]
    function = functions[function_id]

    df = ps._load(ps._DEFAULT_DTA)
    industry_prefix = sector["qlfs_industry"].split(";")[0]
    pool = df[
        df["Occup"].astype(str).isin(
            ["Legislators; senior officials and managers", "Professionals"])
        & df["Indus"].astype(str).str.startswith(industry_prefix)
        & (df["Infempl"].astype(str).str.contains("Informal") == False)  # noqa: E712
    ]
    if pool.empty:
        raise SystemExit(f"no formal decision-maker bodies for sector '{sector_id}'")
    row = pool.sample(n=1, weights=pool["Weight"], random_state=seed).iloc[0]
    sk = ps._row_to_skeleton(row)

    # Attach the composed B2B identity (all frozen — the LLM may voice, not rewrite).
    sk["actor_archetype"] = f"b2b_{function_id}"
    sk["b2b_sector"] = sector["label"]
    sk["b2b_function"] = function["label"]
    sk["occupation"] = f"{function['label']} — {sector['label']}"
    sk["occupation_provenance"] = "role_assigned"
    sk["mandate"] = function["mandate"]
    sk["decision_criteria"] = function["decision_criteria"]
    sk["dmu_role"] = function.get("dmu_role")
    sk["consensus_behaviour"] = function.get("consensus_behaviour")
    sk["budget_authority_band"] = function["budget_authority_band"]
    sk["sector_governance"] = sector.get("governance_frame")
    sk["sector_in_org_interest"] = sector.get("in_org_interest_means")
    sk["sector_levers"] = sector.get("scoreable_levers")
    sk["decision_lens"] = sector.get("decision_lens", "commercial")
    # Behavioural instinct = the mandate as the person FEELS it, with no framework
    # names. The LLM voice/pitch prompts see ONLY this, never "King IV"/"s76" — same
    # discipline as texture_generator._STANCE_GLOSS (plain consequence, not raw code).
    # Real decision-makers act on the instinct; they don't cite the code in a meeting.
    sk["decision_instinct"] = _instinct(sector_id, function_id, sector)
    return sk


def _instinct(sector_id: str, function_id: str, sector: dict) -> str:
    """Translate governance frameworks into how the person actually thinks/talks —
    no framework names. (In the real pipeline this becomes a B2B gloss table beside
    _STANCE_GLOSS; inlined here for the throwaway preview.)"""
    base = {
        "banking": (
            "You are personally on the hook if a vendor harms customers or the bank's "
            "name — you do not approve anything you couldn't defend later if it went "
            "wrong. A deal has to make money AND keep the regulators and your reputation "
            "safe; one without the other is a no. You think about who you'd answer to if "
            "this blew up."
        ),
        "retail": (
            "You live and die by margin and how fast stock moves. You decide quickly and "
            "transactionally — if it doesn't help the basket or the shelf, it's a no."
        ),
        "mining": (
            "What matters is whether this earns real credit with the host community and "
            "keeps your social licence intact — that's worth more to you than a clever "
            "commercial angle. You answer to the community and the regulator's expectations."
        ),
        "foodbev": (
            "Cost control, reliable supply and food-safety come first — a slick pitch that "
            "risks any of those is not worth it."
        ),
        "ict_telecoms": (
            "You care whether it integrates cleanly and is secure; the technical people who "
            "use it have to buy in or it goes nowhere."
        ),
        "ngo": (
            "Every rand has to stretch and be reportable to funders — you judge this by "
            "impact per rand and whether it serves beneficiaries, not profit."
        ),
        "govt": (
            "Your first question is not 'is this a good deal' but 'will this survive a "
            "tender and an audit'. It has to follow the process, tick the procurement and "
            "empowerment requirements, and leave a clean paper trail — anything that can't "
            "is a non-starter no matter how good it sounds."
        ),
    }
    return base.get(sector_id, "")


def make_voice(sk: dict, client) -> dict:
    """Generate B2B-aware texture. Reuses the texture system prompt's discipline
    (facts are FIXED) but frames the person as an org decision-maker, not a consumer."""
    facts = {k: sk[k] for k in (
        "age", "gender", "province", "education", "occupation", "b2b_sector",
        "b2b_function", "mandate", "decision_criteria", "dmu_role",
        "budget_authority_band",
    ) if sk.get(k)}
    facts["how_they_think"] = sk.get("decision_instinct")
    sys_p = (
        "You write realistic texture for a South African B2B decision-maker in a "
        "business simulation. You are given FIXED demographic facts and a FIXED role "
        "mandate. Write ONLY the human surface (name, persona line, how they speak). "
        "Do NOT change or restate the mandate or decision criteria. This person reasons "
        "in their ORGANISATION's interest, per their mandate — not as a private consumer. "
        "Write how a real person in this seat TALKS — they act on their instincts and "
        "obligations but NEVER name governance codes, laws, or frameworks out loud "
        "(a real buyer says 'I'm the one who answers if this goes wrong', not a statute). "
        "English only. Return ONLY valid JSON."
    )
    user_p = (
        "FIXED FACTS (write texture consistent with exactly these):\n"
        f"{json.dumps(facts, ensure_ascii=False, indent=2)}\n\n"
        "Return JSON with ONLY: name (realistic SA name, not a public figure), "
        "persona (1-2 sentences: who they are at work), voice_guide (2-3 sentences on "
        "how they speak in a vendor meeting — formality, what they reference, what they "
        "push back on). English only."
    )
    raw = client.chat(
        [{"role": "system", "content": sys_p}, {"role": "user", "content": user_p}],
        temperature=0.6, max_tokens=700,
    )
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)


def run_pitch(sk: dict, voice: dict, pitch: str, client) -> str:
    """Run the sample pitch through the composed persona as an org decision-maker."""
    sys_p = (
        f"You ARE {voice['name']}, a {sk['b2b_function']} in {sk['b2b_sector']} in "
        f"South Africa. {voice['persona']} {voice['voice_guide']}\n\n"
        f"YOUR MANDATE: {sk['mandate']}\n"
        f"YOUR DECISION CRITERIA: {', '.join(sk['decision_criteria'])}\n"
        f"YOUR ROLE IN THE BUYING COMMITTEE: {sk.get('dmu_role')}. "
        f"{sk.get('consensus_behaviour') or ''}\n"
        f"YOUR BUDGET AUTHORITY: {sk['budget_authority_band']}\n"
        f"HOW YOU THINK ABOUT A DEAL: {sk.get('decision_instinct')}\n\n"
        "Someone is pitching you the proposal below. React the way THIS person, in THIS "
        "seat, actually would — weigh it against your mandate, your criteria, your budget "
        "authority and your organisation's interest. Be specific and honest: what works, "
        "what stalls it, what you'd need. Do not pretend to be the sole decision-maker.\n"
        "Talk like a real person in a meeting: act on your obligations and instincts but "
        "NEVER name laws, governance codes, regulations or frameworks by name (no 'King "
        "IV', no act numbers) — a real buyer voices the WORRY, not the statute. "
        "2-4 short paragraphs, first person, English only."
    )
    return client.chat(
        [{"role": "system", "content": sys_p},
         {"role": "user", "content": f"The pitch:\n{pitch}"}],
        temperature=0.7, max_tokens=900,
    ).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sector", default="banking")
    ap.add_argument("--function", default="procurement")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--pitch", default=(
        "We're a fintech offering an embedded micro-lending API that lets your retail "
        "banking customers access instant small loans inside your existing app. We take "
        "a revenue share on each loan, no upfront cost to you. It widens access to credit "
        "for thin-file customers and we handle the credit-scoring model."
    ))
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")))
    except Exception:
        pass

    from app.utils.llm_client import LLMClient
    client = LLMClient()

    print(f"\n=== Composing: {args.sector} × {args.function} (seed {args.seed}) ===\n")
    sk = compose_b2b_skeleton(args.sector, args.function, args.seed)
    print("REAL QLFS BODY + ATTACHED MANDATE (grounded, LLM-free):")
    print(json.dumps({k: sk[k] for k in (
        "age", "gender", "province", "education", "b2b_sector", "b2b_function",
        "dmu_role", "budget_authority_band", "decision_lens")}, ensure_ascii=False, indent=2))

    print("\n=== Generating voice (LLM) ===\n")
    voice = make_voice(sk, client)
    print(f"NAME:  {voice['name']}")
    print(f"WHO:   {voice['persona']}")
    print(f"VOICE: {voice['voice_guide']}")

    print(f"\n=== THE PITCH ===\n{args.pitch}\n")
    print("=== REACTION (as org decision-maker) ===\n")
    print(run_pitch(sk, voice, args.pitch, client))
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
