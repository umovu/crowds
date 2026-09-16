"""Panel pitch routes — pitch ideas at library-backed persona casts.

  GET    /api/panel/segments/suggest                 suggest groups for a pitch
  GET    /api/panel/segments                          named library slices + counts
  GET    /api/panel/attitudes/<dim>                   counts per stance for one attitude
  POST   /api/panel/affordability                     the affordability lens a pitch implies
  GET    /api/panel/pointers                          the four pointers and their slots
  POST   /api/panel/read                              read one sentence into a study spec
  POST   /api/panel/sessions                          create a session
  GET    /api/panel/sessions                          list sessions
  GET    /api/panel/sessions/<id>                     session metadata + roster
  DELETE /api/panel/sessions/<id>                     delete a session
  POST   /api/panel/sessions/<id>/pitch               run a pitch round
  POST   /api/panel/sessions/<id>/segments            same pitch, different room
  POST   /api/panel/sessions/<id>/coverage-gap        record who we were missing
  GET    /api/panel/sessions/<id>/rounds              round history
  POST   /api/panel/sessions/<id>/agents/<aid>/ask    follow up with one persona
  GET    /api/panel/sessions/<id>/hypothesis          the follow-up report
  POST   /api/panel/posters                           upload a poster, read it to a brief
  GET    /api/panel/posters/<poster_id>               a stored poster and its brief

The fast layer in front of full simulations. The work lives in panel_service,
panel_session_service and panel_round_service; this file reads the request and turns
the answer into JSON.
"""

import traceback
import uuid

from flask import jsonify, request

from . import gates, panel_bp
from ..auth import current_user_id
from ..services import (affordability_service, hypothesis_report, panel_round_service,
                        panel_service, panel_session_service, pointers, poster_service,
                        study_reader)
from ..utils.logger import get_logger

logger = get_logger("fub.controller.panel")


def _server_error(e: Exception, user_message: str):
    """Log the real failure, hand the caller a sentence and a reference code.

    Not `{"error": str(e), "traceback": ...}`: that put Python exception text on the
    user's screen — unreadable to them, and an internals leak — while the thing they
    actually needed (what to do now) was missing. The code is short enough to read
    back over a support message, and it is the key to the full traceback in the log.
    """
    ref = uuid.uuid4().hex[:6].upper()
    logger.error("[ERR-%s] %s\n%s", ref, e, traceback.format_exc())
    return jsonify({"success": False, "error": user_message, "code": f"ERR-{ref}"}), 500


def _ok(data):
    return jsonify({"success": True, "data": data})


def _missing(session_id: str):
    return jsonify({"success": False, "error": f"Session {session_id} not found"}), 404


# ── library reads (deterministic, no LLM) ───────────────────────────────────────
@panel_bp.route('/segments/suggest', methods=['GET'])
def suggest_segments():
    """Suggest segments for a pitch (?pitch=...). Deterministic keyword match, no LLM.
    Returns {"suggested": ["farmers"]} — empty list when no match."""
    try:
        pitch = request.args.get('pitch', '')
        return _ok({
            "suggested": panel_service.suggest_segments(pitch),
            # Attitude groups worth offering as a narrowing on top of those — a
            # different question ("who cares enough"), so a separate field.
            "narrowing": panel_service.suggest_narrowing(pitch),
        })
    except Exception as e:  # noqa: BLE001
        logger.error(f"Segment suggestion failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@panel_bp.route('/segments', methods=['GET'])
def list_segments():
    """Named library slices ("Unemployed", "Grant recipients", …) with live counts —
    deterministic predicates over real persona fields, for the UI's group picker."""
    try:
        return _ok({
            "segments": panel_service.list_segments(),
            # The topic groups the picker files those cards under, in order.
            "topics": panel_service.SEGMENT_TOPICS,
        })
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to list segments: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@panel_bp.route('/attitudes/<dim>', methods=['GET'])
def attitude_options(dim: str):
    """Live counts per stance for one measured attitude dimension, crossed with budget
    tier — so the picker can show how many real people are left before a run is paid
    for. Deterministic read over the library; no LLM."""
    try:
        return _ok({"dimension": dim, "options": panel_service.attitude_options(dim)})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to read attitude options for {dim}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@panel_bp.route('/affordability', methods=['POST'])
def affordability_preview():
    """The affordability lens the pitch implies, before a run is paid for.

    Deterministic read of the operator's own words. Returns null when no price is
    stated, in which case no filter runs."""
    try:
        data = request.get_json() or {}
        return _ok({"affordability":
                    affordability_service.derive_budget_tiers(data.get('pitch') or '')})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to derive affordability: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@panel_bp.route('/pointers', methods=['GET'])
def list_pointers():
    """The four pointers with the scaffold each one asks for.

    Pure dict read, no LLM and no I/O. The home screen reveals these slot hints under
    each pointer row, so the hints the user reads are the same ones the seed is
    assembled from and cannot drift. `summary_contract` and `seed_slots` stay
    server-side; they are prompt internals, not UI copy.
    """
    try:
        out = [{
            "id": pid,
            "label": p["label"],
            "blurb": p["blurb"],
            "slots": [{"key": s["key"], "label": s["label"],
                       "hint": s["hint"], "required": s["required"]}
                      for s in p["slots"]],
        } for pid, p in pointers.POINTERS.items()]
        return _ok({"pointers": out})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to list pointers: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@panel_bp.route('/read', methods=['POST'])
def read_study():
    """Read one plain sentence into a structured study spec for the chips.

    Deterministic structural pre-processing (keyword + regex, no LLM). The UI shows the
    spec as editable chips and only sends the approved version on run. The reader
    authors nothing — it only labels what the sentence did or didn't say.
    """
    try:
        data = request.get_json() or {}
        text = (data.get('pitch') or '').strip()
        if not text:
            return jsonify({"success": False,
                            "error": "Type one sentence to test before we read it."}), 400
        lens = (data.get('lens') or 'land').strip().lower()
        if lens not in pointers.POINTERS:
            lens = 'land'
        return _ok(study_reader.read_study(text, lens=lens))
    except Exception as e:  # noqa: BLE001
        return _server_error(e, "Could not read that sentence. Try again.")


# ── sessions ────────────────────────────────────────────────────────────────────
@panel_bp.route('/sessions', methods=['POST'])
def create_session():
    """Create a panel session (deterministic cast from the persona library).

    Session creation is LLM-free: cast selection, grant detection and budget tiers are
    computed from real persona data. Optional lenses select people who ALREADY hold a
    measured stance or budget tier; they never assign one.
    """
    # Free plan: capped at FREE_PANEL_LIMIT panels; paid: unlimited.
    gate = gates.panel_quota(current_user_id())
    if gate is not None:
        return gate
    try:
        meta = panel_session_service.create(request.get_json() or {}, current_user_id())
        return jsonify({"success": True, "data": meta}), 201
    except panel_session_service.MissingSlots as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except (ValueError, RuntimeError) as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        return _server_error(e, "Could not set up the panel. Try again.")


@panel_bp.route('/sessions', methods=['GET'])
def list_sessions():
    try:
        return _ok({"sessions": panel_service.list_sessions(current_user_id())})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to list panel sessions: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@panel_bp.route('/sessions/<session_id>', methods=['GET'])
def get_session(session_id: str):
    """Session metadata plus the full roster (provenance + economic fields)."""
    try:
        meta = panel_service.get_session(session_id)
        if not meta:
            return _missing(session_id)
        return _ok({**meta, "agents": panel_round_service.list_agents(session_id)})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to get panel session {session_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@panel_bp.route('/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id: str):
    try:
        if not panel_service.delete_session(session_id):
            return _missing(session_id)
        return jsonify({"success": True})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to delete panel session {session_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ── rounds ──────────────────────────────────────────────────────────────────────
def _round_response(result):
    """Turn a round result into JSON. A refused round is a 503, not a result."""
    if isinstance(result, panel_round_service.Refused):
        return jsonify({"success": False, "code": "round_failed",
                        "error": result.message}), 503
    return _ok(result)


@panel_bp.route('/sessions/<session_id>/pitch', methods=['POST'])
def pitch(session_id: str):
    """Run a pitch round against the cast.

    Pass a different `pitch` to test a variant against the SAME cast. Returns
    per-persona reactions plus the aggregate dashboard. Each reaction carries the
    persona's computed budget_tier ("can afford it", real data) separate from the
    response ("wants it", LLM) — never merged, never a buy score.
    """
    try:
        meta = panel_service.get_session(session_id)
        if not meta:
            return _missing(session_id)

        data = request.get_json() or {}
        pitch_text = (data.get('pitch') or meta.get('pitch') or '').strip()
        if not pitch_text:
            return jsonify({"success": False,
                            "error": "No pitch text on the request or the session"}), 400

        return _round_response(panel_round_service.run_round(
            session_id, meta, pitch_text, data.get('agent_ids'),
            max(1, min(int(data.get('concurrency', 6)), 10)),
            user_id=current_user_id()))

    except FileNotFoundError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:  # noqa: BLE001
        return _server_error(
            e, "The room could not be reached. Nothing was counted — try again.")


@panel_bp.route('/sessions/<session_id>/segments', methods=['POST'])
def add_segment(session_id: str):
    """Take the SAME pitch to a different room.

    The pitch is never rewritten — that is the point. Only the audience changes, plus
    one carried-over question about the wall the last room hit. Rounds are append-only,
    so both rooms stay on screen and stay comparable. Same shape as `/pitch`, with the
    ranking recomputed across every room in the session.
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
            # The group is unknown, or everyone in it is already in the room.
            # Neither is a server fault.
            return jsonify({"success": False, "error": str(e)}), 400

        # Learn from the switch itself, not only from the escape hatch — a user
        # walking away from a room is the same demand signal, silently given.
        panel_service.log_coverage_gap(
            session_id, meta, chosen=segment_id,
            abandoned=data.get('abandoned') or [])

        pitch_text = (meta.get('pitch') or '').strip()
        if not pitch_text:
            return jsonify({"success": False,
                            "error": "This session has no pitch to re-run"}), 400

        return _round_response(panel_round_service.run_round(
            session_id, meta, pitch_text, agent_ids,
            max(1, min(int(data.get('concurrency', 6)), 10)),
            user_id=current_user_id(),
            carried_probe=panel_service.carry_probe(data.get('carry_objection'))))

    except FileNotFoundError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:  # noqa: BLE001
        return _server_error(e, "We could not take the pitch to that group. Try again.")


@panel_bp.route('/sessions/<session_id>/coverage-gap', methods=['POST'])
def coverage_gap(session_id: str):
    """"None of these are my people" — record who we were missing.

    Deliberately cheap and unconditional: this is our roadmap input, and a user who
    bothers to tell us should never see it fail.
    """
    try:
        meta = panel_service.get_session(session_id)
        if not meta:
            return _missing(session_id)
        data = request.get_json() or {}
        panel_service.log_coverage_gap(
            session_id, meta,
            abandoned=data.get('abandoned') or [],
            note=(data.get('note') or '').strip())
        return _ok({"recorded": True})
    except Exception as e:  # noqa: BLE001
        return _server_error(e, "We could not record that. Try again.")


@panel_bp.route('/sessions/<session_id>/rounds', methods=['GET'])
def list_rounds(session_id: str):
    """Round history for variant comparison. ?full=1 includes per-agent results."""
    try:
        if not panel_service.get_session(session_id):
            return _missing(session_id)
        full = request.args.get('full', '0').lower() in ('1', 'true')
        return _ok({"session_id": session_id,
                    "rounds": panel_service.list_rounds(session_id, include_results=full)})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to list rounds for {session_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@panel_bp.route('/sessions/<session_id>/agents/<int:agent_id>/ask', methods=['POST'])
def ask_agent(session_id: str, agent_id: int):
    """Follow-up question to a single persona in the cast."""
    try:
        if not panel_service.get_session(session_id):
            return _missing(session_id)
        data = request.get_json() or {}
        question = (data.get('question') or '').strip()
        if not question:
            return jsonify({"success": False, "error": "Provide 'question'"}), 400
        return _ok(panel_round_service.ask_agent(session_id, agent_id, question))
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:  # noqa: BLE001
        return _server_error(e, "That question did not go through. Try again.")


@panel_bp.route('/sessions/<session_id>/hypothesis', methods=['GET'])
def hypothesis(session_id: str):
    """The follow-up report for a finished session: what the room told you, and what to
    run next.

    Facts (who was in the room, where they landed, who moved, the wall they kept
    hitting, what their real income supports) are computed. The hypotheses are one
    cheap LLM pass, labelled as guesses and stripped of any figure, so this can never
    become a "% who would buy".

    Query: format=md renders forwardable Markdown; refresh=1 rebuilds the report.
    """
    try:
        report = hypothesis_report.build(
            session_id, refresh=request.args.get('refresh') in ('1', 'true'))
        if request.args.get('format') == 'md':
            return (hypothesis_report.render_markdown(report), 200,
                    {'Content-Type': 'text/markdown; charset=utf-8'})
        return _ok(report)
    except FileNotFoundError:
        return _missing(session_id)
    except Exception as e:  # noqa: BLE001
        return _server_error(e, "The report could not be assembled. Try again.")


# ── posters ─────────────────────────────────────────────────────────────────────
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


@panel_bp.route('/posters', methods=['POST'])
def upload_poster():
    """Upload a poster (multipart, field name "image") and read it into a brief.

    One vision call per poster, here — not once per persona. The returned brief is the
    `pitch` string the rest of the panel flow already takes, so the cast only ever sees
    text. Pass ?read=0 to store the image without calling the model.
    """
    try:
        upload = request.files.get('image')
        if upload is None:
            return jsonify({"success": False,
                            "error": "No file on the request (field name: image)"}), 400

        record = poster_service.save_poster(
            upload.read(), (upload.mimetype or '').lower(), upload.filename or '')
        if request.args.get('read', '1') != '0':
            record = poster_service.read_poster(record["poster_id"])
        return _ok(_poster_payload(record))

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        return _server_error(
            e, "Could not read that poster. Try a clearer photo, or type it instead.")


@panel_bp.route('/posters/<poster_id>', methods=['GET'])
def get_poster(poster_id: str):
    """The stored poster and its brief, if it has been read."""
    record = poster_service.get_poster(poster_id)
    if not record:
        return jsonify({"success": False, "error": f"Poster {poster_id} not found"}), 404
    return _ok(_poster_payload(record))
