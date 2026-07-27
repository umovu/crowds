"""
backtest_panel — score synthetic panels against things that actually happened.

The question this answers: **does a panel of our personas reproduce the answers real
South Africans gave?**

Everything else we measure is internal (do marginals match, does provenance trace).
This is the only test that looks outward. It puts a question with a KNOWN answer to a
panel and reports the gap.

Two kinds of ground truth (`backtest_scenarios.json`):

  * `afrobarometer` — computed EXACTLY from a held-out column of the .sav at runtime.
    Only questions NOT fused into personas qualify (fusing one would make its own
    answer an input, which is circular). These are the defensible scenarios: the
    truth is a number we derive here, not a figure quoted from memory.
  * `external` — a documented real-world outcome (e-toll non-payment, a withdrawn
    tax rise). Approximate by nature; each carries a source and a confidence note.

Contamination warning
---------------------
The model may already know famous outcomes from training. Framings therefore avoid
naming the event, date, or organisation, and each scenario is rated. A `high` rating
means the result proves little alone. The subgroup breakdown matters more than the
headline number for exactly this reason: a model may recall a national result but is
far less likely to recall how it split by province or income.

What this can and cannot show
-----------------------------
Small panels have wide error bars — 30 personas cannot distinguish 70% from 80%.
This detects large misses and wrong directions, not fine calibration. Read the
pattern across scenarios, never a single row.

LLM-free until you drop --dry-run. Uses the SIM tier (SIM_LLM_*), not the research
tier, because it exercises the sim/panel path.

Usage:
  python backend/scripts/backtest_panel.py --dry-run           # assemble + truth, no spend
  python backend/scripts/backtest_panel.py --scenario eskom-privatisation --n 30
  python backend/scripts/backtest_panel.py --n 40              # whole benchmark set
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCENARIOS = os.path.join(_HERE, "backtest_scenarios.json")
_SAV = os.path.join(_HERE, "..", "data", "microdata", "attitudes", "afrobarometer_r9_sa.sav")

# Sentinels meaning "no usable answer" — same set the donor adapter drops.
_MISSING = {-1.0, 7.0, 8.0, 9.0, 94.0, 98.0, 99.0}

_ANSWER_RE = re.compile(r"ANSWER:\s*([A-Za-z_]+)", re.IGNORECASE)


# ── ground truth ────────────────────────────────────────────────────────────

def _truth_from_afrobarometer(spec: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """Weighted answer distribution for a held-out .sav column.

    Survey-weighted (withinwt_hh) so the target is the POPULATION distribution, not
    the raw sample — the same reason the fusion benchmark post-stratifies.
    """
    if not os.path.exists(_SAV):
        return None
    import pyreadstat

    col = spec["column"]
    df, _meta = pyreadstat.read_sav(_SAV, usecols=[col, "withinwt_hh"])
    mapping = {float(k): v for k, v in spec["map"].items()}
    acc: Dict[str, float] = defaultdict(float)
    total = 0.0
    for _, row in df.iterrows():
        code = row.get(col)
        weight = row.get("withinwt_hh")
        if code is None or code != code or code in _MISSING:
            continue
        if weight is None or weight != weight or weight <= 0:
            continue
        label = mapping.get(float(code))
        if label is None:
            continue
        acc[label] += float(weight)
        total += float(weight)
    return {k: v / total for k, v in acc.items()} if total else None


def ground_truth(scenario: Dict[str, Any]) -> Tuple[Optional[Dict[str, float]], str]:
    """(distribution, provenance-note). None when the source data is unavailable."""
    spec = scenario["ground_truth"]
    if spec["kind"] == "afrobarometer":
        dist = _truth_from_afrobarometer(spec)
        note = f"Afrobarometer {spec['column']}, survey-weighted (exact)"
        return dist, note
    return dict(spec["distribution"]), f"external — {spec.get('confidence', 'see source')}"


# ── cast ────────────────────────────────────────────────────────────────────

def build_cast(n: int, seed: int, province: Optional[str]) -> List[Dict[str, Any]]:
    """Assemble a cast through the REAL panel path so the test exercises what ships:
    library personas -> _build_profile -> mechanism cards -> library-cast guard."""
    from app.services import panel_service, mechanism_card_service
    from app.services.persona_library import PersonaLibrary

    personas = PersonaLibrary().all()
    if province:
        personas = [p for p in personas if p.get("province") == province]
    if not personas:
        raise SystemExit(f"no personas match province={province!r}")

    import random
    picked = random.Random(seed).sample(personas, min(n, len(personas)))
    profiles = [panel_service._build_profile(p, i + 1, "policy")
                for i, p in enumerate(picked)]
    panel_service.assert_library_cast(profiles)
    for prof in profiles:
        mechanism_card_service.attach_research_context(prof)
    return profiles


# ── asking ──────────────────────────────────────────────────────────────────

def _footer(answers: List[str]) -> str:
    opts = " | ".join(answers)
    return (
        "\n\n=== ANSWER CHECK ===\n"
        "Answer in 1-3 sentences in your own voice, then end with ONE final line, "
        "exactly in this format:\n"
        f"ANSWER: <{opts}>\n"
        "Pick the option closest to your real position. Do not explain the line."
    )


def _sim_client():
    """SIM-tier client (SIM_LLM_* falling back to LLM_*), mirroring run_simulation_as."""
    from app.utils.llm_client import LLMClient
    return LLMClient(
        api_key=os.environ.get("SIM_LLM_API_KEY") or os.environ.get("LLM_API_KEY"),
        base_url=os.environ.get("SIM_LLM_BASE_URL") or os.environ.get("LLM_BASE_URL"),
        model=os.environ.get("SIM_LLM_MODEL") or os.environ.get("LLM_MODEL_NAME"),
    )


async def _character_context(profile: Dict[str, Any]) -> str:
    """Render the persona exactly as the sim does — beliefs, cards and all."""
    from app.services.opinion_agent import OpinionCitizenAgent
    agent = OpinionCitizenAgent(
        id=profile.get("id", 1), profile=profile, name=profile.get("name", "agent"),
        interested_topics=profile.get("interested_topics", []),
        stance="neutral", activity_level=0.6, active_hours=list(range(8, 23)),
        actor_archetype=profile.get("actor_archetype"),
    )
    return await agent.character_context(detail="full")


def ask(profile: Dict[str, Any], scenario: Dict[str, Any], client) -> Tuple[Optional[str], str]:
    """One persona, one scenario. Returns (parsed_answer | None, raw_text)."""
    import asyncio
    context = asyncio.run(_character_context(profile))
    prompt = (
        f"You are {profile.get('name')}.\n{context}\n\n"
        f"Someone asks you:\n{scenario['framing']}"
        f"{_footer(scenario['answers'])}"
    )
    try:
        raw = client.chat(
            messages=[
                {"role": "system", "content":
                 "You are this South African person. Answer as yourself, from your own "
                 "circumstances and beliefs. Do not hedge into a survey voice."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7, max_tokens=220,
        )
    except Exception as e:  # noqa: BLE001 — one failure must not kill the run
        return None, f"[error] {e}"
    text = raw if isinstance(raw, str) else str(raw)
    m = _ANSWER_RE.search(text)
    if not m:
        return None, text
    got = m.group(1).strip().lower()
    return (got if got in scenario["answers"] else None), text


# ── scoring ─────────────────────────────────────────────────────────────────

def score(counts: Counter, truth: Dict[str, float]) -> Tuple[float, Dict[str, Tuple[float, float]]]:
    """(total variation distance in points, per-answer synthetic vs real shares)."""
    n = sum(counts.values())
    rows = {}
    tvd = 0.0
    for key in set(truth) | set(counts):
        got = counts.get(key, 0) / n if n else 0.0
        want = truth.get(key, 0.0)
        rows[key] = (got, want)
        tvd += abs(got - want)
    return tvd / 2 * 100, rows


def run_scenario(scenario: Dict[str, Any], args) -> Optional[Dict[str, Any]]:
    truth, provenance = ground_truth(scenario)
    sub = scenario.get("subgroup") or {}
    cast = build_cast(args.n, args.seed, sub.get("province"))

    print(f"\n{'=' * 74}\n{scenario['id']} — {scenario['event']}")
    print(f"  contamination risk : {scenario['contamination']}")
    print(f"  ground truth       : {provenance}")
    if truth:
        print("                       " +
              "  ".join(f"{k}={v * 100:.1f}%" for k, v in sorted(truth.items())))
    else:
        print("                       UNAVAILABLE (microdata missing) — skipping")
        return None
    print(f"  cast               : {len(cast)} personas"
          + (f", province={sub['province']}" if sub.get("province") else ""))

    if args.dry_run:
        print("  [dry run] no LLM calls made. Prompt preview:\n")
        print("  " + scenario["framing"][:200].replace("\n", "\n  "))
        print("  " + _footer(scenario["answers"]).strip().replace("\n", "\n  "))
        return None

    client = _sim_client()
    counts: Counter = Counter()
    by_group: Dict[str, Counter] = defaultdict(Counter)
    unparsed = 0
    for i, profile in enumerate(cast, 1):
        answer, _raw = ask(profile, scenario, client)
        if answer is None:
            unparsed += 1
        else:
            counts[answer] += 1
            by_group[profile.get("actor_archetype", "?")][answer] += 1
        if i % 10 == 0:
            print(f"    {i}/{len(cast)}")

    tvd, rows = score(counts, truth)
    print(f"\n  {'answer':14} {'panel':>8} {'real':>8} {'diff':>8}")
    for key, (got, want) in sorted(rows.items(), key=lambda kv: -kv[1][1]):
        print(f"  {key:14} {got * 100:7.1f}% {want * 100:7.1f}% {(got - want) * 100:+7.1f}")
    print(f"  distribution gap (TVD): {tvd:.1f} points"
          f"   |  unparsed answers: {unparsed}/{len(cast)}")
    return {"id": scenario["id"], "tvd": tvd, "unparsed": unparsed, "n": len(cast)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", help="run one scenario by id")
    ap.add_argument("--n", type=int, default=30, help="cast size per scenario")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true",
                    help="assemble cast + compute ground truth, make NO LLM calls")
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.abspath(os.path.join(_HERE, "..", "..", ".env")))
    except Exception:  # noqa: BLE001
        pass

    with open(_SCENARIOS, "r", encoding="utf-8") as f:
        scenarios = json.load(f)["scenarios"]
    if args.scenario:
        scenarios = [s for s in scenarios if s["id"] == args.scenario]
        if not scenarios:
            raise SystemExit(f"no scenario with id {args.scenario!r}")

    results = [r for r in (run_scenario(s, args) for s in scenarios) if r]

    if results:
        print(f"\n{'=' * 74}\nSUMMARY (lower gap = closer to reality)")
        print(f"{'scenario':30} {'gap (pts)':>10} {'unparsed':>10}")
        for r in sorted(results, key=lambda x: x["tvd"]):
            print(f"{r['id']:30} {r['tvd']:10.1f} {r['unparsed']:>7}/{r['n']}")
        print("\nRead the PATTERN, not one row. A panel of this size cannot "
              "distinguish a 10-point difference from noise.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
