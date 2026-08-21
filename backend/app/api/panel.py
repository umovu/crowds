"""
Panel Pitch API — pitch ideas/products directly at library-backed persona casts.

The fast, iterative layer in front of full simulations: create a session
(deterministic cast from the persona library), pitch it, follow up with
individual personas, compare pitch variants across rounds, all in seconds.
No simulation build pipeline involved.
"""

import asyncio
import traceback
import uuid

from flask import jsonify, request

from . import panel_bp
from .. import billing
from ..config import Config
from ..services import panel_service
from ..services import mode_detector
from ..services import poster_service
from ..services import pointers
from ..services import study_reader
from ..services.interview_service import InterviewService
from ..utils.logger import get_logger

logger = get_logger("fub.api.panel")


def _interview_service(session_id: str) -> InterviewService:
    return InterviewService(session_id, base_dir=Config.PANEL_SESSION_DATA_DIR)


def _server_error(e: Exception, user_message: str):
    """Log the real failure, hand the caller a sentence and a reference code.

    Replaces the old `{"error": str(e), "traceback": ...}` shape. That put Python
    exception text on the user's screen — unreadable to them, and an internals
    leak — while the thing they actually needed (what to do now) was missing. The
    code is short enough to read back over a support message, and it's the key to
    finding the full traceback in the log.
    """
    ref = uuid.uuid4().hex[:6].upper()
    logger.error("[ERR-%s] %s\n%s", ref, e, traceback.format_exc())
    return jsonify({"success": False, "error": user_message, "code": f"ERR-{ref}"}), 500


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@panel_bp.route('/segments/suggest', methods=['GET'])
def suggest_segments():
    """Suggest segments for a pitch (?pitch=...). Deterministic keyword match,
    no LLM. Returns {"suggested": ["farmers"]} — empty list when no match."""
    try:
        pitch = request.args.get('pitch', '')
        return jsonify({"success": True,
                        "data": {"suggested": panel_service.suggest_segments(pitch)}})
    except Exception as e:
        logger.error(f"Segment suggestion failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@panel_bp.route('/segments', methods=['GET'])
def list_segments():
    """Named library slices ("Unemployed", "Grant recipients", …) with live
    counts — deterministic predicates over real persona fields, for the UI's
    group picker."""
    try:
        return jsonify({"success": True, "data": {"segments": panel_service.list_segments()}})
    except Exception as e:
        logger.error(f"Failed to list segments: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@panel_bp.route('/pointers', methods=['GET'])
def list_pointers():
    """The four pointers with the scaffold each one asks for.

    Pure dict read off `pointers.POINTERS` — no LLM, no I/O. The home screen
    reveals these slot hints under each pointer row, so the hints the user
    reads are the same ones the seed is assembled from and cannot drift.
    `summary_contract` and `seed_slots` stay server-side; they are prompt
    internals, not UI copy.
    """
    try:
        out = [
            {
                "id": pid,
                "label": p["label"],
                "blurb": p["blurb"],
                "slots": [
                    {"key": s["key"], "label": s["label"],
                     "hint": s["hint"], "required": s["required"]}
                    for s in p["slots"]
                ],
            }
            for pid, p in pointers.POINTERS.items()
        ]
        return jsonify({"success": True, "data": {"pointers": out}})
    except Exception as e:
        logger.error(f"Failed to list pointers: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@panel_bp.route('/read', methods=['POST'])
def read_study():
    """Read one plain sentence into a structured study spec for the chips.

    Deterministic structural pre-processing (keyword + regex, no LLM): what's
    being tested, the mode, the audience suggestion, the price, the worry, and
    the probes to ask the panel. The UI shows this spec as editable chips and
    only sends the approved version on run. The reader authors nothing — it
    only labels what the sentence did or didn't say.

    Request (JSON): {"pitch": "...", "lens": "land"|"breaks"|"fit"|"ab"}
    """
    try:
        data = request.get_json() or {}
        text = (data.get('pitch') or '').strip()
        if not text:
            return jsonify({"success": False, "error": "Type one sentence to test before we read it."}), 400
        lens = (data.get('lens') or 'land').strip().lower()
        if lens not in pointers.POINTERS:
            lens = 'land'
        return jsonify({"success": True, "data": study_reader.read_study(text, lens=lens)})
    except Exception as e:
        return _server_error(e, "Could not read that sentence. Try again.")


def _read_page_text(url: str, limit: int = 6000) -> str:
    """A web page -> the readable words on it, or "" if it can't be read.

    Thin wrapper over the existing Jina reader. Trimmed to `limit` characters:
    the room reacts to the page's message, and a whole site's markdown would
    bury it. No LLM here — this is a fetch, not a summary.
    """
    try:
        from ..services.jina_service import JinaService
        res = JinaService().scrape(url)
        if not res.get('success'):
            return ""
        text = (res.get('content') or res.get('text') or '').strip()
        return text[:limit]
    except Exception as e:
        logger.warning(f"Page read failed for {url}: {e}")
        return ""


@panel_bp.route('/sessions', methods=['POST'])
def create_session():
    """Create a panel session.

    Request (JSON):
        {
            "pitch": "R99/month solar subscription for townships",  // Required
            "mode": "product",          // Optional: "product" (default) | "policy"
            "n": 12,                    // Optional: cast size (1-50)
            "segments": ["unemployed", "informal_traders"],
                                        // Optional: groups to mix (seats split
                                        // evenly, deduped); default "everyone"
            "segment": "unemployed",    // Optional: single-group shorthand
            "province": "Gauteng",      // Optional: province focus
            "seed": 7,                  // Optional: deterministic cast selection
            "budget_tiers": ["moderate", "loose"]
                                        // Optional affordability lens: only
                                        // personas whose deterministic budget
                                        // tier (real income data) is in the set
        }

    Session creation is LLM-free: cast selection, grant detection and budget
    tiers are computed from real persona data.
    """
    # Free plan: capped at FREE_PANEL_LIMIT panels; paid: unlimited.
    gate = billing.check_panel_quota()
    if gate is not None:
        return gate
    try:
        data = request.get_json() or {}
        pointer = data.get('pointer')
        slots = data.get('slots') or {}
        # Pointer scaffold: must fill required slots before we run a junk seed.
        if pointer:
            missing = pointers.missing_required(pointer, slots)
            if missing:
                return jsonify({
                    "success": False,
                    "error": f"Missing required field(s): {', '.join(missing)}",
                }), 400
        # An assembled seed stands in for the pitch when none sent. An explicit
        # pitch always wins.
        pitched = (data.get('pitch') or '').strip()
        # The website pointer takes an address, but a person can't react to a
        # URL. Read the page into text first and let that stand in as the slot
        # value, so the cast only ever sees words — the same rule the poster
        # path follows with its vision read.
        if pointer == 'website' and (slots.get('url') or '').strip():
            page = _read_page_text(slots['url'].strip())
            if not page:
                return jsonify({
                    "success": False,
                    "error": "Couldn't read that page. Check the address, or paste the text instead.",
                }), 400
            slots = {**slots, 'url': page}
        if pointer and not pitched:
            pitched = pointers.assemble_seed(pointer, slots)
        # Mode is inferred from the (possibly assembled) pitch unless the caller
        # pins one explicitly. Keyword-only detection — pure, deterministic, cheap.
        mode = data.get('mode')
        if not mode:
            mode = mode_detector.detect(pitched or '').get('mode', 'product')
        # Free tier: cap the panel cast at 12 (paid may go up to MAX_CAST_SIZE).
        n = data.get('n', panel_service.DEFAULT_CAST_SIZE)
        ent = billing.get_entitlement(billing.current_user_id())
        if ent.get('plan') != 'paid':
            try:
                n = min(int(n), 12)
            except (ValueError, TypeError):
                n = 12
        # Auto-route the segment from the seed when the caller didn't pick one.
        # An explicit segment choice always wins.
        routed_segments = data.get('segments')
        if not routed_segments and data.get('segment'):
            routed_segments = [data.get('segment')]
        if pointer and not routed_segments:
            routed = pointers.route_segments(pointer, pitched)
            if routed:
                routed_segments = routed
        meta = panel_service.create_session(
            pitch=pitched,
            mode=mode,
            n=n,
            province=data.get('province'),
            seed=data.get('seed'),
            segment=routed_segments[0] if len(routed_segments or []) == 1 else None,
            segments=routed_segments,
            budget_tiers=data.get('budget_tiers'),
            user_id=billing.current_user_id(),
            pointer=pointer,
            slots=slots if pointer else None,
        )
        # Count this panel against the user's quota (no-op on paid / billing off).
        billing.increment_panel_used(billing.current_user_id())
        return jsonify({"success": True, "data": meta}), 201
    except (ValueError, RuntimeError) as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return _server_error(e, "Could not set up the panel. Try again.")


@panel_bp.route('/sessions', methods=['GET'])
def list_sessions():
    try:
        return jsonify({"success": True, "data": {"sessions": panel_service.list_sessions(billing.current_user_id())}})
    except Exception as e:
        logger.error(f"Failed to list panel sessions: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@panel_bp.route('/sessions/<session_id>', methods=['GET'])
def get_session(session_id: str):
    """Session metadata plus the full roster (provenance + economic fields)."""
    try:
        meta = panel_service.get_session(session_id)
        if not meta:
            return jsonify({"success": False, "error": f"Session {session_id} not found"}), 404
        agents = _interview_service(session_id).list_agents()
        return jsonify({"success": True, "data": {**meta, "agents": agents}})
    except Exception as e:
        logger.error(f"Failed to get panel session {session_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@panel_bp.route('/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id: str):
    try:
        if not panel_service.delete_session(session_id):
            return jsonify({"success": False, "error": f"Session {session_id} not found"}), 404
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Failed to delete panel session {session_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@panel_bp.route('/sessions/<session_id>/pitch', methods=['POST'])
def pitch(session_id: str):
    """Run a pitch round against the cast.

    Request (JSON):
        {
            "pitch": "...",        // Optional: defaults to the session pitch.
                                   // Pass a different text to test a variant
                                   // against the SAME cast.
            "agent_ids": [0, 3],   // Optional: subset, defaults to all
            "concurrency": 6       // Optional: parallel interviews (1-10)
        }

    Returns per-persona reactions plus the aggregate dashboard. In product mode
    each reaction carries the persona's computed budget_tier ("can afford it",
    real data) separate from the response ("wants it", LLM) — never merged,
    never a buy score.
    """
    try:
        meta = panel_service.get_session(session_id)
        if not meta:
            return jsonify({"success": False, "error": f"Session {session_id} not found"}), 404

        data = request.get_json() or {}
        pitch_text = (data.get('pitch') or meta.get('pitch') or '').strip()
        if not pitch_text:
            return jsonify({"success": False, "error": "No pitch text on the request or the session"}), 400
        agent_ids = data.get('agent_ids')
        concurrency = max(1, min(int(data.get('concurrency', 6)), 10))
        return _run_round(session_id, meta, pitch_text, agent_ids, concurrency)

    except FileNotFoundError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        return _server_error(e, "The room could not be reached. Nothing was counted — try again.")


def _run_round(session_id: str, meta, pitch_text: str, agent_ids,
               concurrency: int, carried_probe: str = None):
    """Run one pitch round and return the Flask response.

    Shared by `/pitch` and `/segments`, so a re-pitch at a new room is the same
    round in every respect — same framing, same refusal rules, same saved shape
    — differing only in WHO hears it and one carried-over question. Two code
    paths here would drift, and the whole point of the compare strip is that the
    rooms are comparable.
    """
    try:
        service = _interview_service(session_id)
        # The confirmed probes from the study chips become explicit follow-ups
        # the cast is asked, on top of the base reaction (see frame_pitch).
        slots = meta.get("slots") or {}
        probes = [p.get("question") for p in (slots.get("probes") or [])
                  if isinstance(p, dict) and p.get("active") and (p.get("question") or "").strip()]
        # The wall the previous room hit, carried over as one more question.
        if carried_probe:
            probes = probes + [carried_probe]
        framed = panel_service.frame_pitch(
            pitch_text, meta.get('mode', 'product'), probes=probes)
        result = _run_async(service.batch_impact_interview(
            question=framed,
            agent_ids=agent_ids,
            concurrency=concurrency,
        ))

        # Too few people answered for this to be a read of the room. Refuse it
        # rather than saving and rendering it: a partly-collapsed round drawn as
        # a normal one is the worst failure this product can have — it looks like
        # a result. The round is NOT saved, so nothing is spent and a retry is
        # clean. The real cause stays in the log; the user gets a plain sentence.
        if result.get("unusable") or result.get("all_failed"):
            logger.error(
                "Panel round refused for %s: %d of %d answered. Cause: %s",
                session_id, result.get("successful", 0),
                result.get("total_interviewed", 0), result.get("failure_reason", "unknown"),
            )
            answered = result.get("successful", 0)
            return jsonify({
                "success": False,
                "code": "round_failed",
                "error": ("We could not reach the room. This is on us, not your "
                          "pitch. Nothing was counted — try again."
                          if not answered else
                          f"Only {answered} of {result.get('total_interviewed', 0)} "
                          "people could be reached, too few for an honest read. "
                          "Nothing was counted — try again."),
            }), 503

        # One cheap LLM pass: a qualitative read of the room (objections + what
        # would move them). Real counts stay deterministic; this is themes only,
        # and never a buy/validation score. Persisted with the round so it
        # survives reload. Failure leaves the deterministic summary standing.
        try:
            result["summary_narrative"] = panel_service.synthesize_panel_summary(
                pitch_text, result.get("results", []), meta.get('mode', 'product'),
                session_id=session_id,
                # Contract text is rendered here (this module already imports
                # pointers) so panel_service stays import-free of pointers.
                summary_contract=pointers.summary_contract(
                    meta.get('pointer'), meta.get('slots') or {}),
            )
        except Exception as _e:
            logger.warning(f"Panel summary synthesis skipped for {session_id}: {_e}")

        # `fit` surfaces a segment-ranked read (one row per segment) instead of
        # one flat room. Deterministic, real fields only — no LLM. Persisted with
        # the round so a reload of a saved session shows the same ranking.
        concrete_segments = [s for s in (meta.get("segments") or []) if s and s != "everyone"]
        if len(concrete_segments) >= 2:
            # Ranked over the whole SESSION, not just this round: a re-pitch
            # interviews only the new room, and the strip compares rooms. Older
            # answers first, this round's on top — so a persona re-interviewed
            # in this round contributes their newest answer, once.
            union = {r["agent_id"]: r
                     for r in panel_service.latest_results(session_id)
                     if r.get("agent_id") is not None}
            union.update({r["agent_id"]: r for r in result.get("results", [])
                          if r.get("agent_id") is not None})
            result["by_segment"] = panel_service.rank_by_segment(
                session_id, meta, list(union.values()))
            # Say the scope out loud — the ranking is bounded by our library,
            # not by the market.
            result["coverage"] = panel_service.coverage_summary(meta)

        round_num = panel_service.save_round(session_id, {
            "pitch": pitch_text,
            "framed_pitch": framed,
            "agent_ids": agent_ids,
            "carried_probe": carried_probe,
            "result": result,
        })

        payload = {
            "session_id": session_id,
            "round": round_num,
            "pitch": pitch_text,
            **result,
        }
        if meta.get('mode') == 'product':
            payload["budget_tier_distribution"] = meta.get("budget_tier_distribution", {})
        return jsonify({"success": True, "data": payload})

    except FileNotFoundError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        return _server_error(e, "The room could not be reached. Nothing was counted — try again.")


@panel_bp.route('/sessions/<session_id>/segments', methods=['POST'])
def add_segment(session_id: str):
    """Take the SAME pitch to a different room.

    Request (JSON):
        {
            "segment_id": "guardians",         // required, a library segment
            "seats": 6,                        // optional, default 6
            "carry_objection": "fee_sensitivity",  // optional objection type id
            "abandoned": ["professionals"],    // optional, for the coverage log
            "concurrency": 6
        }

    The pitch is never rewritten — that is the point. Only the audience changes,
    plus one carried-over question about the wall the last room hit. Rounds are
    append-only, so both rooms stay on screen and stay comparable.

    Returns the same shape as `/pitch`, with the ranking recomputed across every
    room in the session.
    """
    try:
        data = request.get_json() or {}
        segment_id = (data.get('segment_id') or '').strip()
        if not segment_id:
            return jsonify({"success": False, "error": "No segment_id given"}), 400

        try:
            meta, agent_ids = panel_service.add_segment(
                session_id, segment_id, seats=int(data.get('seats', 6)))
        except ValueError as e:
            # A real, user-facing answer: the group is unknown, or everyone in
            # it is already in the room. Neither is a server fault.
            return jsonify({"success": False, "error": str(e)}), 400

        # Learn from the switch itself, not only from the escape hatch — a user
        # walking away from a room is the same demand signal, silently given.
        panel_service.log_coverage_gap(
            session_id, meta, chosen=segment_id,
            abandoned=data.get('abandoned') or [])

        pitch_text = (meta.get('pitch') or '').strip()
        if not pitch_text:
            return jsonify({"success": False, "error": "This session has no pitch to re-run"}), 400

        return _run_round(
            session_id, meta, pitch_text, agent_ids,
            max(1, min(int(data.get('concurrency', 6)), 10)),
            carried_probe=panel_service.carry_probe(data.get('carry_objection')),
        )

    except FileNotFoundError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        return _server_error(e, "We could not take the pitch to that group. Try again.")


@panel_bp.route('/sessions/<session_id>/coverage-gap', methods=['POST'])
def coverage_gap(session_id: str):
    """"None of these are my people" — record who we were missing.

    Request (JSON): {"note": "rural clinic nurses", "abandoned": ["learners"]}

    Writes to the coverage log and returns success. Deliberately cheap and
    unconditional: this is our roadmap input, and a user who bothers to tell us
    should never see it fail.
    """
    try:
        meta = panel_service.get_session(session_id)
        if not meta:
            return jsonify({"success": False, "error": f"Session {session_id} not found"}), 404
        data = request.get_json() or {}
        panel_service.log_coverage_gap(
            session_id, meta,
            abandoned=data.get('abandoned') or [],
            note=(data.get('note') or '').strip())
        return jsonify({"success": True, "data": {"recorded": True}})
    except Exception as e:
        return _server_error(e, "We could not record that. Try again.")


@panel_bp.route('/posters', methods=['POST'])
def upload_poster():
    """Upload a poster (multipart, field name "image") and read it into a brief.

    One vision call per poster, here — not once per persona. The returned brief
    is the `pitch` string the rest of the panel flow already takes, so the cast
    only ever sees text.

    Pass ?read=0 to store the image without calling the model.
    """
    try:
        upload = request.files.get('image')
        if upload is None:
            return jsonify({"success": False, "error": "No file on the request (field name: image)"}), 400

        image_bytes = upload.read()
        mime = (upload.mimetype or '').lower()
        record = poster_service.save_poster(image_bytes, mime, upload.filename or '')

        if request.args.get('read', '1') != '0':
            record = poster_service.read_poster(record["poster_id"])

        return jsonify({"success": True, "data": _poster_payload(record)})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return _server_error(e, "Could not read that poster. Try a clearer photo, or type it instead.")


@panel_bp.route('/posters/<poster_id>', methods=['GET'])
def get_poster(poster_id: str):
    """The stored poster and its brief, if it has been read."""
    record = poster_service.get_poster(poster_id)
    if not record:
        return jsonify({"success": False, "error": f"Poster {poster_id} not found"}), 404
    return jsonify({"success": True, "data": _poster_payload(record)})


def _poster_payload(record: dict) -> dict:
    """Public shape — never leaks the on-disk path."""
    return {
        "poster_id": record["poster_id"],
        "filename": record.get("filename"),
        "bytes": record.get("bytes"),
        "created_at": record.get("created_at"),
        "brief": record.get("brief"),
        "questions": poster_service.POSTER_QUESTIONS,
    }


@panel_bp.route('/sessions/<session_id>/rounds', methods=['GET'])
def list_rounds(session_id: str):
    """Round history for variant comparison. ?full=1 includes per-agent results."""
    try:
        if not panel_service.get_session(session_id):
            return jsonify({"success": False, "error": f"Session {session_id} not found"}), 404
        full = request.args.get('full', '0').lower() in ('1', 'true')
        rounds = panel_service.list_rounds(session_id, include_results=full)
        return jsonify({"success": True, "data": {"session_id": session_id, "rounds": rounds}})
    except Exception as e:
        logger.error(f"Failed to list rounds for {session_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@panel_bp.route('/sessions/<session_id>/agents/<int:agent_id>/ask', methods=['POST'])
def ask_agent(session_id: str, agent_id: int):
    """Follow-up question to a single persona in the cast.

    The chat has memory: it starts from the persona's reaction in the latest
    pitch round and remembers earlier follow-ups (persisted server-side).
    Pitch rounds themselves stay stateless so variants remain comparable.

    Request (JSON): { "question": "What would the price have to be?" }
    """
    try:
        if not panel_service.get_session(session_id):
            return jsonify({"success": False, "error": f"Session {session_id} not found"}), 404
        data = request.get_json() or {}
        question = (data.get('question') or '').strip()
        if not question:
            return jsonify({"success": False, "error": "Provide 'question'"}), 400

        service = _interview_service(session_id)
        seed = panel_service.latest_round_exchange(session_id, agent_id)
        result = _run_async(service.interview_agent(
            agent_id=agent_id, question=question, memory_seed=seed,
        ))
        return jsonify({"success": True, "data": result})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        return _server_error(e, "That question did not go through. Try again.")
