"""Running one pitch round against a panel cast.

One round is: frame the pitch, interview the cast in parallel, decide whether enough
people answered to call it a read of the room, add a qualitative summary and (when
several groups are in play) a segment ranking, then save it.

`/pitch` and `/sessions/<id>/segments` share this, so taking the same pitch to a new
room is the same round in every respect — same framing, same refusal rules, same saved
shape — differing only in WHO hears it and one carried-over question. Two code paths
would drift, and the whole point of the compare strip is that rooms are comparable.

No Flask here. A round that collapses comes back as `Refused` and the controller turns
that into a 503; every other failure is recorded against the run and re-raised.

This deliberately does NOT live in panel_service: `test_library_cast.py` loads that
module by file path with only a few modules pre-registered, so a new module-level
import there breaks the guard that pins the no-LLM-personas contract.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..config import Config
from ..repositories import run_event_repository as run_events
from ..utils.logger import get_logger
from . import panel_service, pointers
from .interview_service import InterviewService

logger = get_logger("fub.panel_round")

#: A re-pitch is ranked by segment only once there are at least this many real groups.
MIN_SEGMENTS_FOR_RANKING = 2


@dataclass
class Refused:
    """Too few people answered for this round to be an honest read of the room.

    The round is NOT saved, so nothing is spent and a retry is clean. The real cause
    stays in the log; the caller gets a plain sentence.
    """
    answered: int
    interviewed: int

    @property
    def message(self) -> str:
        if not self.answered:
            return ("We could not reach the room. This is on us, not your "
                    "pitch. Nothing was counted — try again.")
        return (f"Only {self.answered} of {self.interviewed} "
                "people could be reached, too few for an honest read. "
                "Nothing was counted — try again.")


def interview_service(session_id: str) -> InterviewService:
    return InterviewService(session_id, base_dir=Config.PANEL_SESSION_DATA_DIR)


def list_agents(session_id: str) -> List[Dict[str, Any]]:
    """The session's roster, with provenance and economic fields."""
    return interview_service(session_id).list_agents()


def ask_agent(session_id: str, agent_id: int, question: str) -> Dict[str, Any]:
    """Follow-up question to one persona, seeded with their latest reaction.

    The chat has memory: it starts from the persona's answer in the most recent pitch
    round and remembers earlier follow-ups. Pitch rounds stay stateless so variants
    remain comparable.
    """
    seed = panel_service.latest_round_exchange(session_id, agent_id)
    return _run_async(interview_service(session_id).interview_agent(
        agent_id=agent_id, question=question, memory_seed=seed))


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _probes(meta: Dict[str, Any], carried_probe: Optional[str]) -> List[str]:
    """The confirmed study-chip probes, plus the wall the previous room hit."""
    slots = meta.get("slots") or {}
    probes = [p.get("question") for p in (slots.get("probes") or [])
              if isinstance(p, dict) and p.get("active") and (p.get("question") or "").strip()]
    if carried_probe:
        probes = probes + [carried_probe]
    return probes


def run_round(session_id: str, meta: Dict[str, Any], pitch_text: str,
              agent_ids: Optional[List[int]], concurrency: int, *,
              user_id: Optional[str], carried_probe: Optional[str] = None):
    """Run one pitch round. Returns the payload dict, or `Refused`.

    Records a run event on every path — ok, refused, not-found and server error — then
    re-raises anything the caller has to turn into a status code.
    """
    started = time.time()
    run_events.record_start(
        run_id=session_id,
        user_id=user_id,
        run_type="panel",
        mode=meta.get("mode"),
        crowd_size=len(agent_ids) if agent_ids else len(meta.get("agents") or []),
    )

    def _end(status: str, **kw):
        run_events.record_end(
            run_id=session_id, user_id=user_id, run_type="panel",
            status=status, duration_seconds=round(time.time() - started, 2), **kw)

    try:
        service = interview_service(session_id)
        framed = panel_service.frame_pitch(
            pitch_text, meta.get('mode', 'product'),
            probes=_probes(meta, carried_probe),
            operator_context=meta.get('operator_context') or "")
        result = _run_async(service.batch_impact_interview(
            question=framed, agent_ids=agent_ids, concurrency=concurrency))

        # A partly-collapsed round drawn as a normal one is the worst failure this
        # product can have: it looks like a result. Refuse rather than save it.
        if result.get("unusable") or result.get("all_failed"):
            logger.error(
                "Panel round refused for %s: %d of %d answered. Cause: %s",
                session_id, result.get("successful", 0),
                result.get("total_interviewed", 0),
                result.get("failure_reason", "unknown"),
            )
            _end("failed", mode=meta.get("mode"), error_code="round_failed")
            return Refused(answered=result.get("successful", 0),
                           interviewed=result.get("total_interviewed", 0))

        # One cheap LLM pass: a qualitative read (objections + what would move them).
        # Real counts stay deterministic; this is themes only, never a buy score.
        # Failure leaves the deterministic summary standing.
        try:
            result["summary_narrative"] = panel_service.synthesize_panel_summary(
                pitch_text, result.get("results", []), meta.get('mode', 'product'),
                session_id=session_id,
                # Rendered here so panel_service stays import-free of pointers.
                summary_contract=pointers.summary_contract(
                    meta.get('pointer'), meta.get('slots') or {}),
            )
        except Exception as e:  # noqa: BLE001 - a missing summary must not fail the round
            logger.warning(f"Panel summary synthesis skipped for {session_id}: {e}")

        _add_segment_ranking(session_id, meta, result)

        round_num = panel_service.save_round(session_id, {
            "pitch": pitch_text,
            "framed_pitch": framed,
            "agent_ids": agent_ids,
            "carried_probe": carried_probe,
            "result": result,
        })

        payload = {"session_id": session_id, "round": round_num,
                   "pitch": pitch_text, **result}
        if meta.get('mode') in ('product', 'panel'):
            payload["budget_tier_distribution"] = meta.get("budget_tier_distribution", {})

        _end("ok", mode=meta.get("mode"), crowd_size=result.get("successful"))
        return payload

    except FileNotFoundError:
        _end("failed", error_code="not_found")
        raise
    except Exception:
        _end("failed", error_code="server_error")
        raise


def _add_segment_ranking(session_id: str, meta: Dict[str, Any],
                         result: Dict[str, Any]) -> None:
    """Add a segment-ranked read when the session holds several real groups.

    Deterministic, real fields only, no LLM. Ranked over the whole SESSION rather than
    this round: a re-pitch interviews only the new room, and the strip compares rooms.
    Older answers first, this round's on top, so a persona re-interviewed in this round
    contributes their newest answer once.
    """
    concrete = [s for s in (meta.get("segments") or []) if s and s != "everyone"]
    if len(concrete) < MIN_SEGMENTS_FOR_RANKING:
        return

    union = {r["agent_id"]: r for r in panel_service.latest_results(session_id)
             if r.get("agent_id") is not None}
    union.update({r["agent_id"]: r for r in result.get("results", [])
                  if r.get("agent_id") is not None})
    result["by_segment"] = panel_service.rank_by_segment(
        session_id, meta, list(union.values()))
    # Say the scope out loud: the ranking is bounded by our library, not the market.
    result["coverage"] = panel_service.coverage_summary(meta)
