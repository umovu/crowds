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

_ANSWER_RE = re.compile(r"ANSWER:[ \t]*(.+)", re.IGNORECASE)


def parse_answer(text, answers):
    """Accept one complete, final answer line; never match an option prefix."""
    lines = text.strip().splitlines()
    if not lines:
        return None
    matches = [_ANSWER_RE.fullmatch(line.strip()) for line in lines]
    if sum(m is not None for m in matches) != 1 or matches[-1] is None:
        return None
    value = matches[-1].group(1).strip().casefold()
    options = {answer.casefold(): answer for answer in answers}
    if len(options) != len(answers):
        raise ValueError("Ambiguous answer labels")
    return options.get(value)


def prepare_r10(n):
    """Local, truth-free inventory. Does not load app config or create a client."""
    import hashlib
    from pathlib import Path
    if n <= 0:
        raise ValueError("Room size must be positive")
    out = Path(_HERE) / "out"
    lock = json.loads((out / "r10_item_lock.json").read_text(encoding="utf-8"))
    raw = (out / "r10_ask_scenarios.json").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != lock["files"]["r10_ask_scenarios.json"]:
        raise ValueError("Frozen question file changed")
    items = json.loads(raw)["items"]
    expected = {"id", "r9", "r10", "bucket", "framing", "answers", "extremes"}
    if any(set(item) != expected for item in items):
        raise ValueError("Unexpected fields in blind questions")
    if len({item["id"] for item in items}) != len(items):
        raise ValueError("Duplicate question IDs")
    for item in items:
        for answer in item["answers"]:
            if parse_answer("ANSWER: " + answer, item["answers"]) != answer:
                raise ValueError("Unparseable frozen answer")
    raw_library = (Path(_HERE).parent / "app/data/persona_library/personas.json").read_bytes()
    people = json.loads(raw_library)["personas"]
    buckets = dict(Counter(item["bucket"] for item in items))
    return {"model_calls": 0, "questions_sha256": digest,
            "library_sha256": hashlib.sha256(raw_library).hexdigest(),
            "library_size": len(people), "requested_room": n,
            "actual_room": min(n, len(people)), "question_buckets": buckets,
            "planned_requests": min(n, len(people)) * len(items),
            "full_library_requests": len(people) * len(items),
            "paid_run_ready": False,
            "remaining": ["Separate blind ask and reveal phases",
                          "National weights and subgroup gap reporting",
                          "Provider token accounting and approved spending limit",
                          "Review narrative text against refreshed attitudes",
                          "Verify the running service loads the repaired library"]}



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
    if spec["kind"] == "afrobarometer_r10":
        return r10_distribution(spec["item"]), "Afrobarometer R10, published Total; rounded shares normalized"
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
    return parse_answer(text, scenario["answers"]), text


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



# Predeclared before any R10 model calls. All diagnostics use percentage points.
SPREAD_THRESHOLDS = {"tail_mass_abs_gap_pp": 10.0, "modal_excess_pp": 15.0}


def spread(counts: Counter, truth: Dict[str, float], extremes: List[str]) -> Dict[str, Any]:
    """Full-option TVD, extreme-option mass, and largest single-option share.

    Explicit extremes prevent treating don't-know/refusal as an ordinal endpoint.
    An empty or invalid room is not a measurement and must never pass.
    """
    import math
    if (not counts or sum(counts.values()) <= 0
            or any(not math.isfinite(v) or v < 0 for v in counts.values())):
        raise ValueError("spread needs nonnegative finite counts and at least one answer")
    if (not truth or any(not math.isfinite(v) or v < 0 for v in truth.values())
            or not math.isclose(sum(truth.values()), 1.0, abs_tol=1e-6)):
        raise ValueError("truth must be a probability distribution summing to one")
    if len(extremes) != 2 or len(set(extremes)) != 2 or not set(extremes) <= set(truth):
        raise ValueError("declare exactly two distinct substantive extreme options")
    if not set(counts) <= set(truth):
        raise ValueError("unrecognised answers must be reported separately")
    gap, rows = score(counts, truth)
    ours_tail = sum(rows[k][0] for k in extremes) * 100
    real_tail = sum(truth[k] for k in extremes) * 100
    ours_modal = max(v[0] for v in rows.values()) * 100
    real_modal = max(truth.values()) * 100
    return {"tvd_pp": gap, "tail_mass_ours_pct": ours_tail,
            "tail_mass_real_pct": real_tail, "tail_gap_pp": ours_tail - real_tail,
            "modal_ours_pct": ours_modal, "modal_real_pct": real_modal,
            "modal_excess_pp": ours_modal - real_modal,
            "pass": abs(ours_tail - real_tail) <= SPREAD_THRESHOLDS["tail_mass_abs_gap_pp"]
            and ours_modal - real_modal <= SPREAD_THRESHOLDS["modal_excess_pp"]}


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



# R10 phases deliberately keep outcomes out of seal/ask. Raw records stay private.
def _sha(raw):
    import hashlib
    return hashlib.sha256(raw).hexdigest()


def _r10_paths(seed):
    from pathlib import Path
    out = Path(_HERE) / "out"
    return out, out / f"r10_manifest_{seed}.json", out / f"r10_run_{seed}.jsonl"


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _exclusive_json(path, value):
    with path.open("xb") as f:
        f.write(_json_bytes(value))


def _r10_demographics(p):
    from audit_persona_library import LOCATION_MAP, EDUCATION_MAP, RACE_MAP, _age_band
    return {"gender": p.get("gender"), "location": LOCATION_MAP.get(p.get("geotype")),
            "province": p.get("province"), "education": EDUCATION_MAP.get(p.get("education")),
            "age": _age_band(p.get("age")), "race": RACE_MAP.get(p.get("race"))}


def rake_library(rows, targets):
    """Fit full-library margins before drawing the room. Unknowns get zero weight.

    Targets without any library support are explicitly excluded and renormalized.
    Sampling a small room does not guarantee its margins match the full library.
    """
    import math
    valid = [all(row.get(k) in target for k, target in targets.items()) for row in rows]
    weights = [float(v) for v in valid]
    if not any(valid):
        raise ValueError("No complete demographic records for weighting")
    supported, excluded = {}, {}
    for axis, target in targets.items():
        present = {row[axis] for row, ok in zip(rows, valid) if ok}
        supported[axis] = {k: v for k, v in target.items() if k in present and v > 0}
        excluded[axis] = {k: v for k, v in target.items() if k not in present and v > 0}
        total = sum(supported[axis].values())
        supported[axis] = {k: v / total for k, v in supported[axis].items()}
    error = None
    for iteration in range(2000):
        for axis, target in supported.items():
            total = sum(weights)
            observed = Counter()
            for row, w in zip(rows, weights):
                observed[row[axis]] += w
            for i, row in enumerate(rows):
                if weights[i]:
                    weights[i] *= target[row[axis]] * total / observed[row[axis]]
        total = sum(weights)
        error = max(abs(sum(w for row, w in zip(rows, weights) if row[axis] == cat) / total - v)
                    for axis, target in supported.items() for cat, v in target.items())
        if error < 1e-7:
            break
    if error >= 1e-7 or not all(math.isfinite(w) for w in weights):
        raise ValueError("Weight fitting did not converge")
    return weights, {"iterations": iteration + 1, "max_margin_error": error,
                     "excluded_library_records": valid.count(False),
                     "excluded_target_percent": excluded, "supported_targets": supported,
                     "method": "Full-library iterative proportional fitting on audit margins; retain fixed weights in random room."}


def seal_r10(n, seed):
    import asyncio
    import random
    import socket
    from pathlib import Path
    from unittest.mock import patch
    from datetime import datetime, timezone
    inventory = prepare_r10(n)
    out, manifest_path, run_path = _r10_paths(seed)
    method_path = out / f"r10_method_{seed}.json"
    if manifest_path.exists() or method_path.exists() or run_path.exists():
        raise ValueError("Existing sealed run; refusing to overwrite")
    items = json.loads((out / "r10_ask_scenarios.json").read_bytes())["items"]
    original_connect = socket.socket.connect
    def local_only(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect(sock, address)
        raise RuntimeError("External network forbidden during seal")
    with patch.object(socket.socket, "connect", local_only):
        import app
        app._setup_agentsociety2_env()
        from app.services import panel_service, mechanism_card_service
        from app.services.persona_library import PersonaLibrary
        from sync_measured_beliefs import sync_person
        from audit_persona_library import NATIONAL, _race_benchmark
        library_path = Path(_HERE).parent / "app/data/persona_library/personas.json"
        before = library_path.read_bytes()
        with patch("app.services.persona_library._seed_from_storage", return_value=False):
            people = PersonaLibrary(str(library_path)).all()
        if any(sync_person(p).get("beliefs") != p.get("beliefs") for p in people):
            raise ValueError("Measured belief sentences are inconsistent")
        demographics = [_r10_demographics(p) for p in people]
        weights, weighting = rake_library(demographics, {**NATIONAL, "race": _race_benchmark()})
        indices = random.Random(seed).sample(range(len(people)), min(n, len(people)))
        profiles = [panel_service._build_profile(people[index], i + 1, "policy") for i, index in enumerate(indices)]
        panel_service.assert_library_cast(profiles)
        participants = []
        for index, profile in zip(indices, profiles):
            mechanism_card_service.attach_research_context(profile)
            context = asyncio.run(_character_context(profile))
            participants.append({"slot": profile["id"], "name": profile.get("name"),
                                 "context": context, "profile": profile,
                                 "demographics": demographics[index], "weight": weights[index]})
        if library_path.read_bytes() != before:
            raise ValueError("Library changed during seal")
    # The entire method is frozen before any responses exist. No R10 outcomes read.
    method = {"created_utc": datetime.now(timezone.utc).isoformat(), "seed": seed,
              "room_size": len(participants), "items": len(items), "planned_requests": len(items)*len(participants),
              "model": "deepseek-v4-pro-0813", "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
              "temperature": 0.7, "max_tokens": 220, "enable_thinking": False,
              "concurrency": 4, "retries": 0, "timeout_seconds": 60,
              "cost_ceiling_usd": 10.0, "estimate_input_usd_per_million": 1.32,
              "estimate_output_usd_per_million": 3.96,
              "price_note": "Upper listed Singapore snapshot rates, estimate only; billing discounts/tier timing not verified.",
              "price_source": "https://www.alibabacloud.com/help/en/model-studio/deepseek-v4-pro",
              "library_sha256": _sha(before), "questions_sha256": inventory["questions_sha256"],
              "runner_sha256": _sha(Path(__file__).read_bytes()), "weighting": weighting,
              "scoring": "Full-option TVD, normalize printed totals only when all cells known and sum within 0.5pp of 100; otherwise unavailable. Missing model answers excluded and counted separately.",
              "subgroups": "Urban minus Rural and Men minus Women; preselected focus answer; raw published pp; minimum 5 parsed per group. All options also reported. Weighted and unweighted.",
              "spread_thresholds": SPREAD_THRESHOLDS,
              "limitations": ["40-person single-seed smoke, not population accuracy proof",
                              "Full-library weights do not make the 40-person sample representative",
                              "Held-out from fused survey fields, not guaranteed absent from model training or narrative prose",
                              "Narrative prose retained without semantic validation; deterministic belief sentences checked",
                              "Local repaired library loaded fresh; deployed service not tested"]}
    manifest = {"method": method, "items": items, "participants": participants,
                "system": "You are this South African person. Answer as yourself, from your own circumstances and beliefs. Do not hedge into a survey voice."}
    _exclusive_json(manifest_path, manifest)
    _exclusive_json(method_path, {**method, "manifest_sha256": _sha(manifest_path.read_bytes())})
    print(json.dumps({"sealed": str(manifest_path), "model_calls": 0,
                      "room": len(participants), "requests": method["planned_requests"],
                      "weighting_exclusions": weighting["excluded_library_records"],
                      "gender": dict(Counter(p["demographics"]["gender"] for p in participants)),
                      "location": dict(Counter(p["demographics"]["location"] for p in participants))}, indent=2))


def _r10_messages(manifest, person, item):
    prompt = (f"You are {person['name']}.\n{person['context']}\n\n"
              f"Someone asks you:\n{item['framing']}{_footer(item['answers'])}")
    return [{"role": "system", "content": manifest["system"]}, {"role": "user", "content": prompt}]


def ask_r10(seed):
    """Read only sealed prompts, method and credentials; persist every attempted call."""
    import requests
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from pathlib import Path
    from dotenv import dotenv_values
    out, manifest_path, run_path = _r10_paths(seed)
    raw = manifest_path.read_bytes()
    seal = json.loads((out / f"r10_method_{seed}.json").read_bytes())
    if _sha(raw) != seal["manifest_sha256"]:
        raise ValueError("Manifest differs from pre-call seal")
    manifest = json.loads(raw)
    method = manifest["method"]
    if _sha(Path(__file__).read_bytes()) != method["runner_sha256"]:
        raise ValueError("Runner changed after seal")
    env = dotenv_values(Path(_HERE).parents[1] / ".env")
    if env.get("SIM_LLM_MODEL") != method["model"] or env.get("SIM_LLM_BASE_URL", "").rstrip("/") != method["base_url"]:
        raise ValueError("SIM settings differ from sealed model/provider")
    key = env.get("SIM_LLM_API_KEY")
    if not key:
        raise ValueError("SIM key missing")
    tasks = [(p, i) for i in manifest["items"] for p in manifest["participants"]]
    upper_input = sum(sum(len(m["content"].encode("utf-8")) + 64 for m in _r10_messages(manifest, p, i)) for p, i in tasks)
    upper_cost = (upper_input * method["estimate_input_usd_per_million"] + len(tasks)*method["max_tokens"]*method["estimate_output_usd_per_million"])/1e6
    if upper_cost > method["cost_ceiling_usd"]:
        raise ValueError("Conservative text-size cost estimate exceeds sealed ceiling")
    def one(person, item):
        record = {"type": "response", "slot": person["slot"], "item_id": item["id"], "answer": None}
        try:
            response = requests.post(method["base_url"] + "/chat/completions",
                headers={"Authorization": "Bearer " + key},
                json={"model": method["model"], "messages": _r10_messages(manifest, person, item),
                      "temperature": method["temperature"], "max_tokens": method["max_tokens"], "enable_thinking": False},
                timeout=method["timeout_seconds"])
            record["http_status"] = response.status_code
            if response.status_code != 200:
                record["error"] = "provider_http_error"
                return record
            data = response.json()
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
            record.update(raw=text, usage=data.get("usage"), returned_model=data.get("model"),
                          finish_reason=choice.get("finish_reason"), provider_id=data.get("id"))
            if data.get("model") != method["model"]:
                record["error"] = "unexpected_model"
            elif choice.get("finish_reason") != "stop":
                record["error"] = "incomplete_generation"
            else:
                record["answer"] = parse_answer(text, item["answers"])
        except Exception as exc:
            # Never save error strings that could include headers/keys.
            record["error"] = type(exc).__name__
        return record
    with run_path.open("x", encoding="utf-8") as f:
        def save(record):
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        save({"type": "header", "manifest_sha256": _sha(raw), "method_sha256": _sha(_json_bytes(method)),
              "planned_requests": len(tasks), "conservative_estimate_usd": upper_cost})
        total_usage = Counter()
        completed = parsed = errors = 0
        # Batches cap outstanding work at four. No auto-retries after errors.
        with ThreadPoolExecutor(max_workers=method["concurrency"]) as pool:
            for start in range(0, len(tasks), method["concurrency"]):
                futures = []
                for person, item in tasks[start:start+method["concurrency"]]:
                    save({"type":"attempt", "slot":person["slot"], "item_id":item["id"]})
                    futures.append(pool.submit(one, person, item))
                for future in as_completed(futures):
                    record = future.result()
                    save(record)
                    completed += 1
                    parsed += record["answer"] is not None
                    errors += bool(record.get("error"))
                    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                        total_usage[k] += (record.get("usage") or {}).get(k, 0)
                if completed % 40 == 0:
                    print(json.dumps({"completed":completed,"planned":len(tasks),"parsed":parsed,"errors":errors,"usage":dict(total_usage)}),flush=True)
                if errors >= 8:
                    print("Stopped after eight provider/incomplete-generation errors; no retries.",flush=True)
                    break
        save({"type":"end", "completed":completed,"planned":len(tasks),"parsed":parsed,"errors":errors,"usage":dict(total_usage)})
    receipt = {"run_sha256": _sha(run_path.read_bytes()), "manifest_sha256": _sha(raw),
               "completed": completed, "parsed": parsed, "errors": errors, "usage": dict(total_usage)}
    _exclusive_json(out / f"r10_receipt_{seed}.json", receipt)
    print(json.dumps(receipt,indent=2))


def r10_distribution(item, group="Total"):
    col = item["r10_columns"].index(group)
    values = {a: item["r10_rows"][a][col] for a in item["answers"]}
    if any(v is None for v in values.values()):
        return None
    total = sum(values.values())
    if abs(total-100) > 0.5:
        return None
    return {a: v/total for a,v in values.items()}


def r10_gap(rows, people, item, axis, groups, answer, weighted=False):
    shares, sizes = [], []
    for group in groups:
        part = [r for r in rows if r.get("answer") and people[r["slot"]]["demographics"].get(axis) == group
                and (not weighted or people[r["slot"]]["weight"] > 0)]
        sizes.append(len(part))
        counts = Counter()
        for row in part:
            counts[row["answer"]] += people[row["slot"]]["weight"] if weighted else 1
        shares.append(counts.get(answer,0)/sum(counts.values())*100 if counts else None)
    truth_groups = groups if axis == "location" else ("Men", "Women")
    real = [item["r10_rows"][answer][item["r10_columns"].index(g)] for g in truth_groups]
    if min(sizes) < 5 or any(v is None for v in real):
        return {"n":sizes,"available":False}
    predicted, actual = shares[0]-shares[1], real[0]-real[1]
    sign = lambda v: 0 if abs(v)<1e-9 else (1 if v>0 else -1)
    return {"n":sizes,"available":True,"predicted_pp":predicted,"real_pp":actual,
            "absolute_error_pp":abs(predicted-actual),"sign_correct":sign(predicted)==sign(actual)}


def reveal_r10(seed):
    import statistics
    out, manifest_path, run_path = _r10_paths(seed)
    receipt = json.loads((out / f"r10_receipt_{seed}.json").read_bytes())
    if _sha(run_path.read_bytes()) != receipt["run_sha256"] or _sha(manifest_path.read_bytes()) != receipt["manifest_sha256"]:
        raise ValueError("Saved run/manifest changed after asking")
    manifest = json.loads(manifest_path.read_bytes())
    records = [json.loads(line) for line in run_path.read_text(encoding="utf-8").splitlines()]
    rows = [r for r in records if r["type"] == "response"]
    if len({(r["slot"],r["item_id"]) for r in rows}) != len(rows):
        raise ValueError("Duplicate responses")
    lock = json.loads((out / "r10_item_lock.json").read_bytes())
    raw_truth = (out / "r10_item_list.json").read_bytes()
    if _sha(raw_truth) != lock["files"]["r10_item_list.json"]:
        raise ValueError("Frozen truth changed")
    truth_items = json.loads(raw_truth)["items"]
    lookup = {f"{i['r9']}_{i['r10']}":i for i in truth_items}
    people = {p["slot"]:p for p in manifest["participants"]}
    results = []
    for blind in manifest["items"]:
        item = lookup[blind["id"]]
        local = [r for r in rows if r["item_id"] == blind["id"]]
        counts, weighted = Counter(), Counter()
        for r in local:
            if r.get("answer"):
                if r["answer"] not in blind["answers"]:
                    raise ValueError("Unexpected parsed option")
                counts[r["answer"]] += 1
                weighted[r["answer"]] += people[r["slot"]]["weight"]
        truth = r10_distribution(item)
        result = {"id":blind["id"],"bucket":blind["bucket"],"question":blind["framing"],
                  "attempted":len(local),"parsed":sum(counts.values()),"planned":len(people),
                  "unparsed":len(local)-sum(counts.values()),"unweighted_counts":dict(counts),
                  "weighted_counts":dict(weighted),"truth":truth,
                  "unweighted":spread(counts,truth,item["extremes"]) if truth and counts else None,
                  "weighted":spread(weighted,truth,item["extremes"]) if truth and sum(weighted.values()) else None,
                  "focus_answer":item["subgroup_focus_answer"],"gaps":{}}
        for axis,groups in [("location",("Urban","Rural")),("gender",("Male","Female"))]:
            result["gaps"][axis] = {}
            for w in [False,True]:
                result["gaps"][axis]["weighted" if w else "unweighted"] = {
                    answer:r10_gap(local,people,item,axis,groups,answer,w) for answer in item["answers"]}
        results.append(result)
    method=manifest["method"]
    usage=receipt["usage"]
    estimate=(usage.get("prompt_tokens",0)*method["estimate_input_usd_per_million"]+usage.get("completion_tokens",0)*method["estimate_output_usd_per_million"])/1e6
    sw=[p["weight"] for p in people.values()]
    report={"seed":seed,"model":method["model"],"room_size":len(people),"receipt":receipt,
            "reported_token_cost_upper_estimate_usd":estimate,
            "usage_missing_responses":sum(r.get("usage") is None for r in rows),
            "sample_weight_effective_n":sum(sw)**2/sum(w*w for w in sw),
            "results":results,"summary":{},"limitations":method["limitations"],
            "weighting":method["weighting"]}
    for bucket in ("held_out","seen"):
        selected=[r for r in results if r["bucket"]==bucket]
        report["summary"][bucket]={}
        for mode in ("unweighted","weighted"):
            gaps=[r[mode]["tvd_pp"] for r in selected if r[mode]]
            focus=[r["gaps"]["location"][mode][r["focus_answer"]] for r in selected]
            eligible=[g for g in focus if g["available"]]
            report["summary"][bucket][mode]={"scorable_items":len(gaps),"mean_tvd_pp":statistics.mean(gaps) if gaps else None,
                "median_tvd_pp":statistics.median(gaps) if gaps else None,
                "urban_rural_focus_sign_correct":sum(g["sign_correct"] for g in eligible),"urban_rural_focus_scorable":len(eligible)}
    _exclusive_json(out/f"r10_results_{seed}.json",report)
    lines=["# R10 paid smoke trial", "",f"Model: `{method['model']}` via DashScope. Room: {len(people)}. Seed: {seed}.","",
           f"Completed calls: {receipt['completed']}/{method['planned_requests']}. Parsed answers: {receipt['parsed']}. Errors: {receipt['errors']}.",
           f"Provider-reported tokens: {usage}. Listed-rate upper estimate for reported usage: US${estimate:.4f}; not an invoice.",
           f"Responses without usage: {report['usage_missing_responses']}. Weighted effective sample size: {report['sample_weight_effective_n']:.1f}.","",
           "Distribution gap is total variation distance in percentage points. Lower is closer. No overall validation score.","",
           "| Item | Group | Parsed | Raw gap (pp) | Weighted gap (pp) |", "|---|---|---:|---:|---:|"]
    fmt=lambda v: f"{v:.2f}" if v is not None else "unavailable"
    for r in results:
        lines.append(f"| {r['id']} | {r['bucket']} | {r['parsed']}/{r['planned']} | {fmt(r['unweighted']['tvd_pp'] if r['unweighted'] else None)} | {fmt(r['weighted']['tvd_pp'] if r['weighted'] else None)} |")
    lines += ["","## Held-out and control summaries","", "```json",json.dumps(report["summary"],indent=2),"```","", "## Primary subgroup gaps","",
              "Positive means Urban exceeds Rural, or Men exceeds Women. These use the frozen focus answer, not a result-picked option.","",
              "| Item | Comparison | Focus answer | Raw predicted | Weighted predicted | Real | Raw sign correct |", "|---|---|---|---:|---:|---:|---|"]
    for r in results:
        for axis in ("location","gender"):
            a=r["gaps"][axis]["unweighted"][r["focus_answer"]]
            b=r["gaps"][axis]["weighted"][r["focus_answer"]]
            lines.append(f"| {r['id']} | {axis} | {r['focus_answer']} | {fmt(a.get('predicted_pp'))} | {fmt(b.get('predicted_pp'))} | {fmt(a.get('real_pp'))} | {a.get('sign_correct','unavailable')} |")
    lines += ["","## Spread and full answer distributions","", "The JSON report includes every subgroup option, raw counts, weighted counts and spread measures."]
    for r in results:
        lines += ["",f"### {r['id']}","",r["question"],"",f"Spread, unweighted: `{json.dumps(r['unweighted'])}`",f"Spread, weighted: `{json.dumps(r['weighted'])}`","",
                  "| Answer | Raw count | Weighted share | Real share |","|---|---:|---:|---:|"]
        total=sum(r["weighted_counts"].values())
        for answer in lookup[r['id']]["answers"]:
            lines.append(f"| {answer} | {r['unweighted_counts'].get(answer,0)} | {fmt(100*r['weighted_counts'].get(answer,0)/total if total else None)} | {fmt(100*r['truth'][answer] if r['truth'] else None)} |")
    lines += ["","## Limitations","",*["- "+v for v in method["limitations"]],
              "- Missing R10 cells are not zero. Incomplete national tables are not scored.",
              "- Missing model answers are excluded from shares and counted separately; this may bias the result.",
              "- Published percentages are rounded. Full known national rows are normalized to sum to one.",
              "- Weighting exclusions and unsupported target categories are recorded in the JSON; weighted results cover supported groups only.",
              "- Previous identical-people diagnostic remains 15/15 directions, one health-service warning; this trial does not erase it.","",
              "## Blind record","",f"Manifest SHA256: `{receipt['manifest_sha256']}`",f"Saved run SHA256: `{receipt['run_sha256']}`",
              "Raw answers and prompts stay local. Ask wrote the receipt before reveal loaded the frozen outcome file."]
    with (out/f"r10_results_{seed}.md").open("x",encoding="utf-8") as f:
        f.write("\n".join(lines)+"\n")
    print(json.dumps({"summary":report["summary"],"usage":usage,"estimated_usd":estimate,"report":str(out/f'r10_results_{seed}.md')},indent=2))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", choices=["prepare", "seal", "ask", "reveal"], help="free R10 readiness inventory")
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
    if args.phase in {"seal", "ask", "reveal"}:
        if args.phase == "seal":
            seal_r10(args.n, args.seed)
        elif args.phase == "ask":
            ask_r10(args.seed)
        else:
            reveal_r10(args.seed)
        return 0
    if args.phase == "prepare":
        print(json.dumps(prepare_r10(args.n), indent=2))
        return 0

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
