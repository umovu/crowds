"""Hypothesis report — what a finished panel session actually told you.

A panel round answers "how did the room react". This composes the next
question: given what they said, what is worth believing, and what would you
run next to find out. It is the thing a user forwards to a colleague after a
session, and the payload behind the follow-up email.

Split, deliberately, the same way every other reading in this repo is split:

  - The FACTS are deterministic. Who was in the room, what they said, who
    moved, the wall they kept hitting, what their real income supports. All
    computed from persisted round JSON and real persona fields, assertable
    with the LLM switched off (`tests/test_hypothesis_report.py` does exactly
    that).
  - The HYPOTHESES are one cheap LLM pass over the reaction text, and they are
    guesses labelled as guesses. They carry no numbers, no counts and no
    "who would buy" score — the prompt forbids it and `_clean_hypotheses`
    drops any that slip through. A failed call returns [] and the factual
    report still stands on its own.

"Who moved" is the reading the room ranking does not give you: a segment that
starts hostile and shifts is an opportunity, not a bad row. Movement is
counted from `stance_before` / `stance_after`, which the interview stack
already records per reaction.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger
from . import objections
from . import panel_service

logger = get_logger("fub.hypothesis_report")

REPORT_FILE = "hypothesis_report.json"

# Worst → best. Panel rounds use support/neutral/oppose; sim-side agents can
# also carry resist/concerned, so both vocabularies live in one order and a
# stance outside it simply doesn't register as movement.
STANCE_ORDER = ["resist", "oppose", "concerned", "neutral", "support"]

MAX_QUOTES = 5
MAX_WALLS = 4


# ── Deterministic facts ────────────────────────────────────────────────────

def _direction(before: Optional[str], after: Optional[str]) -> str:
    """"warmer" / "cooler" / "sideways" for one stance change.

    Anything the order doesn't recognise is "sideways" rather than an error —
    an unknown stance label must never take down the report.
    """
    try:
        delta = STANCE_ORDER.index(after) - STANCE_ORDER.index(before)
    except (ValueError, TypeError):
        return "sideways"
    if delta > 0:
        return "warmer"
    if delta < 0:
        return "cooler"
    return "sideways"


def _movement(session_id: str) -> Dict[str, Any]:
    """Everyone whose stance changed at any point in the session.

    Walks every round rather than the latest-answer union: a persona talked
    round out of a position in round 2 moved, even if round 3 asked them
    something else. Each persona is listed once, on their most recent move.
    """
    moved: Dict[Any, Dict[str, Any]] = {}
    considered = 0
    for rnd in sorted(panel_service.list_rounds(session_id, include_results=True),
                      key=lambda r: r.get("round") or 0):
        for r in ((rnd.get("result") or {}).get("results") or []):
            if "error" in r:
                continue
            considered += 1
            before, after = r.get("stance_before"), r.get("stance_after")
            if not r.get("stance_changed") or not before or not after or before == after:
                continue
            moved[r.get("agent_id")] = {
                "agent_id": r.get("agent_id"),
                "name": r.get("agent_name") or f"Persona {r.get('agent_id')}",
                "from": before,
                "to": after,
                "direction": _direction(before, after),
                "round": rnd.get("round"),
            }
    people = sorted(moved.values(), key=lambda m: (m["direction"], str(m["name"])))
    return {
        "people": people,
        "moved_count": len(people),
        "warmer": len([m for m in people if m["direction"] == "warmer"]),
        "cooler": len([m for m in people if m["direction"] == "cooler"]),
        # The denominator is answers given, not seats — the same honesty rule
        # the impact dashboard uses. A round nobody answered can't imply calm.
        "answers_considered": considered,
    }


def _conditions(results: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Reactions phrased as a condition — "I would, if…".

    These are the most actionable sentences a round produces: the persona has
    already named the change that moves them. Quoted verbatim, never
    paraphrased, so what the user reads is what the persona said.
    """
    out = []
    for r in results:
        text = (r.get("response") or "").strip()
        if not text or "error" in r or not objections.is_condition(text):
            continue
        out.append({
            "name": r.get("agent_name") or f"Persona {r.get('agent_id')}",
            "stance": r.get("stance_after") or "neutral",
            "quote": text if len(text) <= 400 else text[:400].rstrip() + "…",
        })
        if len(out) >= MAX_QUOTES:
            break
    return out


def facts(session_id: str) -> Dict[str, Any]:
    """Everything in the report that is computed, not guessed. No LLM."""
    meta = panel_service.get_session(session_id) or {}
    profiles = panel_service._read_json(
        os.path.join(panel_service.session_dir(session_id),
                     panel_service.PROFILES_FILE)) or []
    results = [r for r in panel_service.latest_results(session_id) if "error" not in r]

    stance_split: Dict[str, int] = {}
    for r in results:
        s = r.get("stance_after") or "neutral"
        stance_split[s] = stance_split.get(s, 0) + 1

    rounds = panel_service.list_rounds(session_id, include_results=True)
    last = (rounds[-1].get("result") or {}) if rounds else {}

    return {
        "session_id": session_id,
        "pitch": meta.get("pitch", ""),
        "mode": meta.get("mode", "product"),
        "segment_label": meta.get("segment_label") or "Everyone (representative SA)",
        "created_at": meta.get("created_at"),
        "rounds": len(rounds),
        "room": {
            "seats": len(profiles),
            "heard": len(results),
            "budget_tiers": panel_service._tier_distribution(profiles),
            "coverage": last.get("coverage") or panel_service.coverage_summary(meta),
        },
        "stance_split": stance_split,
        "movement": _movement(session_id),
        "walls": objections.top([r.get("response") or "" for r in results],
                                limit=MAX_WALLS),
        "conditions": _conditions(results),
        "by_segment": last.get("by_segment") or [],
        "room_read": last.get("summary_narrative") or "",
    }


# ── The guesses (one cheap LLM pass, hard-bounded) ─────────────────────────

_NUMBERISH = re.compile(r"\d+\s*%|\bpercent\b|\bper cent\b|\bR\s?\d|\b\d+\s*(?:of|out of)\s*\d+")


def _clean_hypotheses(items: Any) -> List[Dict[str, str]]:
    """Keep only well-formed, number-free hypotheses.

    The prompt already forbids figures; this is the enforcement. A hypothesis
    carrying a percentage or a rand amount is the banned "% who would buy" in
    prose, so it is dropped rather than shown with a caveat.
    """
    out: List[Dict[str, str]] = []
    if not isinstance(items, list):
        return out
    for item in items[:3]:
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim") or "").strip()
        test = str(item.get("test") or "").strip()
        if not claim or not test:
            continue
        if _NUMBERISH.search(claim) or _NUMBERISH.search(test):
            logger.info("Dropped a hypothesis carrying figures")
            continue
        out.append({"claim": claim, "test": test})
    return out


def hypotheses(report_facts: Dict[str, Any],
               results: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Two or three testable guesses about WHY the room reacted this way.

    Each is a claim plus the next run that would check it — so the report ends
    with something to do, not a verdict. Returns [] on any failure; the facts
    above are the report, this is the commentary.
    """
    reactions = [r for r in (results or []) if r.get("response") and "error" not in r]
    if not reactions:
        return []

    roster = "\n".join(
        f"- {r.get('agent_name') or 'Persona'} [{r.get('stance_after') or 'neutral'}]: "
        f"{(r.get('response') or '').strip()[:280]}"
        for r in reactions[:24])
    walls = ", ".join(w["label"] for w in report_facts.get("walls", [])) or "none recorded"
    mv = report_facts.get("movement", {})
    movement = (f"{mv.get('warmer', 0)} people warmed, {mv.get('cooler', 0)} cooled"
                if mv.get("moved_count") else "nobody changed position")

    subject = "pitch" if report_facts.get("mode") == "product" else "announcement"
    system = (
        "You help someone plan their NEXT round of research after a panel of real "
        f"people reacted to their {subject}. Propose two or three hypotheses: a "
        "plausible explanation for what you see in the reactions, each paired with "
        "the concrete next run that would test it (a different room to ask, or a "
        "changed line in the pitch). Ground every claim in the reactions given. "
        "Hard rules: no numbers, counts, percentages, prices or rand figures; no "
        "'who would buy', conversion, validation or likelihood score; never state a "
        "hypothesis as a finding. Reply with ONLY a JSON array of objects with keys "
        '"claim" and "test", each one or two plain sentences.'
    )
    user = (f"The {subject}:\n{report_facts.get('pitch', '')}\n\n"
            f"The room: {report_facts.get('segment_label')}\n"
            f"Walls they kept hitting: {walls}\n"
            f"Movement: {movement}\n\n"
            f"The reactions:\n{roster}\n\nThe hypotheses:")

    raw = _chat(system, user, max_tokens=420)
    if not raw:
        return []
    # Models like to wrap JSON in prose or a fence; take the first array.
    match = re.search(r"\[.*\]", raw, re.S)
    if not match:
        return []
    try:
        return _clean_hypotheses(json.loads(match.group(0)))
    except json.JSONDecodeError:
        logger.warning("Hypothesis pass returned unparseable JSON")
        return []


def _chat(system: str, user: str, max_tokens: int = 400) -> str:
    """One SIM-tier chat call. Returns "" when unconfigured or on any failure.

    Uses SIM_LLM_* (the cheap runtime tier), not the research tier — this is a
    short pass over text we already have. The thinking-suppression flag is
    provider-shaped and retried plain, matching `synthesize_panel_summary`.
    """
    api_key = os.environ.get("SIM_LLM_API_KEY") or os.environ.get("LLM_API_KEY") or ""
    base_url = os.environ.get("SIM_LLM_BASE_URL") or os.environ.get("LLM_BASE_URL") or ""
    model = os.environ.get("SIM_LLM_MODEL") or os.environ.get("LLM_MODEL_NAME") or ""
    if not (api_key and base_url and model):
        return ""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        kwargs = dict(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.3,
            max_tokens=max_tokens,
        )
        _m = (model or "").lower()
        if "qwen" in _m:
            _no_think = {"enable_thinking": False}
        elif "deepseek" in _m:
            _no_think = {"thinking": {"type": "disabled"}}
        else:
            _no_think = None
        try:
            resp = (client.chat.completions.create(extra_body=_no_think, **kwargs)
                    if _no_think else client.chat.completions.create(**kwargs))
        except Exception:
            resp = client.chat.completions.create(**kwargs)
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning(f"Hypothesis LLM pass failed: {e}")
        return ""


# ── Build + cache ──────────────────────────────────────────────────────────

def build(session_id: str, refresh: bool = False) -> Dict[str, Any]:
    """The full report, cached beside the session.

    Cached on the round count: opening the report twice must not spend a second
    LLM call, but running another round must not leave a stale read on screen.
    `refresh=True` forces a rebuild.
    """
    meta = panel_service.get_session(session_id)
    if not meta:
        raise FileNotFoundError(f"Session {session_id} not found")

    path = os.path.join(panel_service.session_dir(session_id), REPORT_FILE)
    rounds = len(panel_service.list_rounds(session_id))
    if not refresh:
        cached = panel_service._read_json(path)
        if isinstance(cached, dict) and cached.get("rounds") == rounds:
            return cached

    report = facts(session_id)
    if rounds:
        results = [r for r in panel_service.latest_results(session_id) if "error" not in r]
        report["hypotheses"] = hypotheses(report, results)
    else:
        report["hypotheses"] = []
    report["generated_at"] = datetime.now().isoformat(timespec="seconds")

    try:
        panel_service._write_json(path, report)
    except OSError as e:
        # A read-only or full volume must not cost the user their report.
        logger.warning(f"Could not cache hypothesis report for {session_id}: {e}")
    return report


# ── Rendering ──────────────────────────────────────────────────────────────

def render_markdown(report: Dict[str, Any]) -> str:
    """The report as forwardable Markdown. Deterministic, no LLM."""
    mv = report.get("movement", {})
    room = report.get("room", {})
    lines = [
        "# What this room told you",
        "",
        f"**You asked:** {report.get('pitch', '')}",
        f"**Who you asked:** {report.get('segment_label')} · "
        f"{room.get('heard', 0)} of {room.get('seats', 0)} people answered",
        f"**Rounds:** {report.get('rounds', 0)} · "
        f"Generated {report.get('generated_at', '')}",
        "",
    ]

    if report.get("room_read"):
        lines += ["## The read", "", report["room_read"], ""]

    lines += ["## Where they landed", ""]
    split = report.get("stance_split") or {}
    if split:
        lines += [f"- {k}: {v}" for k, v in sorted(split.items(), key=lambda kv: -kv[1])]
    else:
        lines.append("- Nobody answered yet.")
    lines.append("")

    lines += ["## Who changed their mind", ""]
    if mv.get("moved_count"):
        lines.append(f"{mv['moved_count']} of {mv.get('answers_considered', 0)} answers "
                     f"changed position — {mv.get('warmer', 0)} warmed, "
                     f"{mv.get('cooler', 0)} cooled.")
        lines.append("")
        lines += [f"- **{p['name']}** — {p['from']} → {p['to']} ({p['direction']})"
                  for p in mv.get("people", [])]
    else:
        lines.append("Nobody moved. A room that doesn't budge is a finding: either "
                     "the pitch didn't touch what they care about, or you haven't "
                     "answered them back yet.")
    lines.append("")

    lines += ["## The wall they kept hitting", ""]
    walls = report.get("walls") or []
    lines += ([f"- {w['label']} — raised by {w['count']}" for w in walls]
              or ["- No recurring objection stood out."])
    lines.append("")

    if report.get("conditions"):
        lines += ["## What they said would change their mind", ""]
        for c in report["conditions"]:
            lines += [f"> {c['quote']}", f"> — {c['name']} ({c['stance']})", ""]

    tiers = room.get("budget_tiers") or {}
    if tiers:
        lines += ["## What their real income supports", "",
                  "Computed from each person's real household income — never "
                  "estimated. It is what they can afford, not a forecast of "
                  "what they will purchase.", ""]
        lines += [f"- {k}: {v}" for k, v in sorted(tiers.items())]
        lines.append("")

    lines += ["## What to test next", ""]
    hyps = report.get("hypotheses") or []
    if hyps:
        lines.append("These are guesses, not findings. Each one names the run "
                     "that would check it.")
        lines.append("")
        for i, h in enumerate(hyps, 1):
            lines += [f"**{i}. {h['claim']}**", f"Test it: {h['test']}", ""]
    else:
        lines += ["No hypotheses were generated for this session.", ""]

    cov = room.get("coverage") or {}
    if cov.get("segments_available"):
        lines += ["---", "",
                  f"*Compared across {cov.get('segments_compared', 0)} of "
                  f"{cov['segments_available']} groups in our library. This answer "
                  f"is bounded by that coverage, not by the whole market.*"]
    return "\n".join(lines)
