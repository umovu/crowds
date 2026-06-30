"""
Panel Pitch API — pitch ideas/products directly at library-backed persona casts.

The fast, iterative layer in front of full simulations: create a session
(deterministic cast from the persona library), pitch it, follow up with
individual personas, compare pitch variants across rounds, all in seconds.
No simulation build pipeline involved.
"""

import asyncio
import traceback

from flask import jsonify, request

from . import panel_bp
from .. import billing
from ..config import Config
from ..services import panel_service
from ..services import mode_detector
from ..services.interview_service import InterviewService
from ..utils.logger import get_logger

logger = get_logger("fub.api.panel")


def _interview_service(session_id: str) -> InterviewService:
    return InterviewService(session_id, base_dir=Config.PANEL_SESSION_DATA_DIR)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


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
            "seed": 7                   // Optional: deterministic cast selection
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
        # Mode is inferred from the pitch unless the caller pins one explicitly.
        # Keyword-only detection (no llm_client) — pure, deterministic, cheap.
        mode = data.get('mode')
        if not mode:
            mode = mode_detector.detect(data.get('pitch', '') or '').get('mode', 'product')
        # Free tier: cap the panel cast at 12 (paid may go up to MAX_CAST_SIZE).
        n = data.get('n', panel_service.DEFAULT_CAST_SIZE)
        ent = billing.get_entitlement(billing.current_user_id())
        if ent.get('plan') != 'paid':
            try:
                n = min(int(n), 12)
            except (ValueError, TypeError):
                n = 12
        meta = panel_service.create_session(
            pitch=data.get('pitch', ''),
            mode=mode,
            n=n,
            province=data.get('province'),
            seed=data.get('seed'),
            segment=data.get('segment'),
            segments=data.get('segments'),
            user_id=billing.current_user_id(),
        )
        # Count this panel against the user's quota (no-op on paid / billing off).
        billing.increment_panel_used(billing.current_user_id())
        return jsonify({"success": True, "data": meta}), 201
    except (ValueError, RuntimeError) as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"Panel session creation failed: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


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

        service = _interview_service(session_id)
        framed = panel_service.frame_pitch(pitch_text, meta.get('mode', 'product'))
        result = _run_async(service.batch_impact_interview(
            question=framed,
            agent_ids=agent_ids,
            concurrency=concurrency,
        ))

        round_num = panel_service.save_round(session_id, {
            "pitch": pitch_text,
            "framed_pitch": framed,
            "agent_ids": agent_ids,
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
        logger.error(f"Panel pitch failed for {session_id}: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


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
        logger.error(f"Panel follow-up failed for {session_id}/{agent_id}: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500
