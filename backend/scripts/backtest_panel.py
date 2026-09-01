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
    if spec["kind"] == "outcome":
        # No share was ever measured — only what actually happened. Returning a
        # distribution here would invent precision the case study does not have.
        return None, f"real outcome — direction only: {spec['direction']}"
    return dict(spec["distribution"]), f"external — {spec.get('confidence', 'see source')}"


def is_partial(scenario: Dict[str, Any]) -> bool:
    """A partial truth documents only SOME answers' shares.

    The remaining probability mass is genuinely unknown, so the missing options
    must not be scored as if their real share were zero — that manufactures gap
    points out of ignorance. Partial scenarios are scored on the documented
    answers alone (see `score`)."""
    return bool(scenario["ground_truth"].get("partial"))


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


def _sim_client(model: Optional[str] = None):
    """SIM-tier client (SIM_LLM_* falling back to LLM_*), mirroring run_simulation_as.

    `model` (from --model) wins over the environment. It has to: app.config calls
    load_dotenv(override=True), so a SIM_LLM_MODEL exported on the command line is
    silently replaced by the .env value the moment app.* is imported. Comparing two
    models needs an override the .env cannot eat."""
    from app.utils.llm_client import LLMClient
    return LLMClient(
        api_key=os.environ.get("SIM_LLM_API_KEY") or os.environ.get("LLM_API_KEY"),
        base_url=os.environ.get("SIM_LLM_BASE_URL") or os.environ.get("LLM_BASE_URL"),
        model=model or os.environ.get("SIM_LLM_MODEL") or os.environ.get("LLM_MODEL_NAME"),
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

def score(counts: Counter, truth: Dict[str, float],
          partial: bool = False) -> Tuple[float, Dict[str, Tuple[float, float]]]:
    """(gap in points, per-answer synthetic vs real shares).

    Full truth -> total variation distance over every answer.
    Partial truth -> mean absolute error over the DOCUMENTED answers only; the
    undocumented ones are still reported (real share shown as None) but never
    scored, because their real share is unknown, not zero."""
    n = sum(counts.values())
    rows = {}
    for key in set(truth) | set(counts):
        got = counts.get(key, 0) / n if n else 0.0
        rows[key] = (got, truth.get(key))
    if partial:
        errs = [abs(rows[k][0] - truth[k]) for k in truth]
        return (sum(errs) / len(errs) * 100 if errs else 0.0), rows
    tvd = sum(abs(got - (want or 0.0)) for got, want in rows.values())
    return tvd / 2 * 100, rows


def _segment_table(by_group: Dict[str, Counter], answers: List[str],
                   min_n: int = 3) -> List[Tuple[str, int, Dict[str, float]]]:
    """Per-archetype answer shares, for archetypes with enough people to mean
    anything. Two personas do not make a segment."""
    out = []
    for group, counts in sorted(by_group.items()):
        n = sum(counts.values())
        if n < min_n:
            continue
        out.append((group, n, {a: counts.get(a, 0) / n for a in answers}))
    return out


def _report_outcome(scenario: Dict[str, Any], seed: int, counts: Counter,
                    by_group: Dict[str, Counter], unparsed: int,
                    cast_size: int) -> Dict[str, Any]:
    """Score a real case study: direction now, discrimination and segmentation
    in the summary. No gap number — the case has no measured share to miss."""
    spec = scenario["ground_truth"]
    want = spec["direction"]
    n = sum(counts.values())
    shares = {a: counts.get(a, 0) / n if n else 0.0 for a in scenario["answers"]}
    lean = max(shares, key=shares.get) if n else None
    passed = lean == want

    print(f"\n  {'answer':16} {'panel':>8}")
    for key in sorted(shares, key=lambda k: -shares[k]):
        mark = "  <- real outcome" if key == want else ""
        print(f"  {key:16} {shares[key] * 100:7.1f}%{mark}")
    print(f"  DIRECTION: {'PASS' if passed else 'FAIL'} "
          f"(panel leans {lean}, reality went {want})"
          f"   |  unparsed answers: {unparsed}/{cast_size}")

    segments = _segment_table(by_group, scenario["answers"])
    if segments:
        spread = (max(s[2][want] for s in segments) -
                  min(s[2][want] for s in segments))
        print(f"  segment spread on '{want}': {spread * 100:.0f} points "
              f"across {len(segments)} archetypes")
        for group, gn, sh in sorted(segments, key=lambda s: -s[2][want]):
            print(f"    {group:32} n={gn:<3} "
                  + "  ".join(f"{a}={sh[a] * 100:.0f}%" for a in scenario["answers"]))
    # The adopt/yes option is answers[0] by convention. Paired cases use different
    # vocabularies (would_use vs would_open), so the pair test compares THIS share
    # rather than the raw distributions — two cases phrased differently are 100
    # points apart no matter what the panel said.
    positive = scenario["answers"][0]
    return {"id": scenario["id"], "seed": seed, "kind": "outcome",
            "direction_ok": passed, "lean": lean, "want": want,
            "shares": shares, "unparsed": unparsed, "n": cast_size,
            "pair": scenario.get("pair"),
            "positive_share": shares.get(positive, 0.0),
            "really_positive": want == positive,
            "segment_spread": (spread if segments else None)}


def run_scenario(scenario: Dict[str, Any], args, seed: int,
                 responses_fh=None) -> Optional[Dict[str, Any]]:
    truth, provenance = ground_truth(scenario)
    sub = scenario.get("subgroup") or {}
    cast = build_cast(args.n, seed, sub.get("province"))

    print(f"\n{'=' * 74}\n{scenario['id']} — {scenario['event']}   [seed {seed}]")
    print(f"  contamination risk : {scenario['contamination']}")
    print(f"  ground truth       : {provenance}")
    is_outcome = scenario["ground_truth"]["kind"] == "outcome"
    if truth:
        print("                       " +
              "  ".join(f"{k}={v * 100:.1f}%" for k, v in sorted(truth.items())))
    elif is_outcome:
        split = scenario["ground_truth"].get("expected_split")
        if split:
            print(f"  expected split     : {split}")
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

    client = _sim_client(getattr(args, "model", None))
    counts: Counter = Counter()
    by_group: Dict[str, Counter] = defaultdict(Counter)
    unparsed = 0
    for i, profile in enumerate(cast, 1):
        answer, _raw = ask(profile, scenario, client)
        if responses_fh:
            import json as _json
            responses_fh.write(_json.dumps({
                "scenario": scenario["id"],
                "seed": seed,
                "i": i,
                "name": profile.get("name"),
                "archetype": profile.get("actor_archetype"),
                "segment": profile.get("segment"),
                "answer": answer,
                "text": _raw,
            }, ensure_ascii=False) + "\n")
            responses_fh.flush()
        if answer is None:
            unparsed += 1
        else:
            counts[answer] += 1
            by_group[profile.get("actor_archetype", "?")][answer] += 1
        if i % 10 == 0:
            print(f"    {i}/{len(cast)}")

    # A run where most calls failed is an outage, not a result. Scoring it would
    # let a dead API masquerade as a panel verdict (the "no comment" signature).
    if unparsed > len(cast) / 2:
        print(f"\n  VOID — {unparsed}/{len(cast)} calls failed or returned no "
              f"answer. Not scored. Re-run this scenario.")
        return None

    if is_outcome:
        return _report_outcome(scenario, seed, counts, by_group, unparsed, len(cast))

    partial = is_partial(scenario)
    gap, rows = score(counts, truth, partial)
    print(f"\n  {'answer':14} {'panel':>8} {'real':>8} {'diff':>8}")
    for key, (got, want) in sorted(rows.items(), key=lambda kv: -(kv[1][1] or -1)):
        if want is None and partial:
            print(f"  {key:14} {got * 100:7.1f}% {'n/a':>8} {'not scored':>10}")
        elif want is None:
            # Full truth: an answer nobody real chose. Real share IS zero, and the
            # TVD counts it — say so rather than printing a misleading "n/a".
            print(f"  {key:14} {got * 100:7.1f}% {0.0:7.1f}% {got * 100:+7.1f}")
        else:
            print(f"  {key:14} {got * 100:7.1f}% {want * 100:7.1f}% {(got - want) * 100:+7.1f}")
    label = "documented-answer gap (MAE)" if partial else "distribution gap (TVD)"
    print(f"  {label}: {gap:.1f} points"
          f"   |  unparsed answers: {unparsed}/{len(cast)}")
    return {"id": scenario["id"], "seed": seed, "gap": gap, "partial": partial,
            "unparsed": unparsed, "n": len(cast),
            "shares": {k: v[0] for k, v in rows.items()}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", help="run one scenario by id")
    ap.add_argument("--n", type=int, default=30, help="cast size per scenario")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--seeds", default=None,
                    help="comma-separated seeds, e.g. 1,2,3. Each seed draws a "
                         "DIFFERENT cast; the summary reports the spread across "
                         "them. A single run can never separate a real gap from "
                         "temperature noise.")
    ap.add_argument("--model", default=None,
                    help="SIM-tier model id, overriding SIM_LLM_MODEL. Needed "
                         "because app.config reloads .env with override=True and "
                         "would otherwise undo an exported env var.")
    ap.add_argument("--dry-run", action="store_true",
                    help="assemble cast + compute ground truth, make NO LLM calls")
    ap.add_argument("--out-responses", metavar="PATH", default=None,
                    help="append each persona's full answer to a JSONL file")
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

    seeds = ([int(s) for s in args.seeds.split(",") if s.strip()]
             if args.seeds else [args.seed])

    results: List[Dict[str, Any]] = []
    responses_fh = open(args.out_responses, "a", encoding="utf-8") if args.out_responses else None
    try:
        for scenario in scenarios:
            for seed in seeds:
                r = run_scenario(scenario, args, seed, responses_fh)
                if r:
                    results.append(r)
    finally:
        if responses_fh:
            responses_fh.close()

    if results:
        by_id: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in results:
            by_id[r["id"]].append(r)

        surveys = {k: v for k, v in by_id.items() if v[0].get("kind") != "outcome"}
        cases = {k: v for k, v in by_id.items() if v[0].get("kind") == "outcome"}

        if surveys:
            print(f"\n{'=' * 74}\nSURVEY SCENARIOS (lower gap = closer to reality)")
            print(f"{'scenario':30} {'median':>8} {'spread':>16} {'runs':>5} {'unparsed':>10}")
            for sid, runs in sorted(surveys.items(),
                                    key=lambda kv: sorted(r["gap"] for r in kv[1])[len(kv[1]) // 2]):
                gaps = sorted(r["gap"] for r in runs)
                median = gaps[len(gaps) // 2]
                print(f"{sid:30} {median:8.1f} {f'{gaps[0]:.1f}-{gaps[-1]:.1f}':>16}"
                      f" {len(runs):>5} {sum(r['unparsed'] for r in runs):>7}"
                      f"/{sum(r['n'] for r in runs)}")

        if cases:
            print(f"\n{'=' * 74}\nCASE STUDIES — test 1: DIRECTION")
            print(f"{'case':32} {'passes':>8} {'panel leans':>16} {'reality':>16}")
            for sid, runs in sorted(cases.items()):
                ok = sum(1 for r in runs if r["direction_ok"])
                leans = "/".join(sorted({str(r["lean"]) for r in runs}))
                print(f"{sid:32} {f'{ok}/{len(runs)}':>8} {leans:>16} {runs[0]['want']:>16}")

            print(f"\n{'=' * 74}\nCASE STUDIES — test 2: DISCRIMINATION (paired cases)")
            seen = set()
            for sid, runs in cases.items():
                other = runs[0].get("pair")
                if not other or other not in cases or (other, sid) in seen:
                    continue
                seen.add((sid, other))
                a_runs, b_runs = runs, cases[other]
                a = sum(r["positive_share"] for r in a_runs) / len(a_runs)
                b = sum(r["positive_share"] for r in b_runs) / len(b_runs)
                a_won, b_won = a_runs[0]["really_positive"], b_runs[0]["really_positive"]
                if a_won == b_won:
                    print(f"{sid} vs {other}: not an opposite-outcome pair, skipped")
                    continue
                # The case that really succeeded must draw MORE enthusiasm.
                margin = (a - b if a_won else b - a) * 100
                winner = sid if a_won else other
                if margin >= 15:
                    verdict = "PASS"
                elif margin > 0:
                    verdict = "WEAK — right order, too small to trust"
                else:
                    verdict = "FAIL — panel prefers the case that flopped"
                print(f"{sid} {a * 100:.0f}% vs {other} {b * 100:.0f}% enthusiasm"
                      f"  ({winner} really succeeded, margin {margin:+.0f}) -> {verdict}")

            print(f"\n{'=' * 74}\nCASE STUDIES — test 3: SEGMENTATION")
            print(f"{'case':32} {'segment spread on the real answer':>36}")
            for sid, runs in sorted(cases.items()):
                spreads = [r["segment_spread"] for r in runs
                           if r["segment_spread"] is not None]
                if not spreads:
                    print(f"{sid:32} {'no archetype had 3+ people':>36}")
                    continue
                med = sorted(spreads)[len(spreads) // 2] * 100
                verdict = "PASS" if med >= 20 else "FAIL — room answers as one"
                print(f"{sid:32} {f'{med:.0f} points  -> {verdict}':>36}")

        if len(seeds) > 1:
            print("\nJudge a scenario by its SPREAD, not its median. A gap smaller "
                  "than the spread is noise.")
        else:
            print("\nSingle seed — this cannot separate a real gap from noise. "
                  "Use --seeds 1,2,3.")
        print("Read the PATTERN, not one row. A panel of this size cannot "
              "distinguish a 10-point difference from noise.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
