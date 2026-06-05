"""
Analysis API routes — post-simulation analytics dashboards.

Provides endpoints for:
- Sentiment timeline with event markers
- Archetype activity heatmap
- Event impact before/after comparisons
- Topic cascade detection
- Radicalism drift tracking
- Non-participation breakdown
"""

import os
import traceback
from typing import Optional

from flask import jsonify, request

from . import analysis_bp
from ..config import Config
from ..services.replay_storage import ReplayStorage
from ..services.post_sim_analytics import PostSimAnalytics
from ..utils.logger import get_logger

logger = get_logger('fub.api.analysis')


def _get_storage() -> Optional[ReplayStorage]:
    """Get or create ReplayStorage instance for the simulation DB."""
    simulation_id = request.view_args.get('simulation_id') if request.view_args else None
    if not simulation_id:
        return None

    # If simulation_id looks like a path, use it directly
    if os.path.sep in simulation_id or simulation_id.endswith('.db'):
        if os.path.exists(simulation_id):
            return ReplayStorage(simulation_id)
        return None

    # Canonical location — where the sim writer actually puts replay.db
    # (Config.OASIS_SIMULATION_DATA_DIR/<id>/opinion_space/replay.db). This is
    # the same dir the rest of the simulation API resolves against; the legacy
    # CWD-relative paths below are kept only as fallbacks.
    possible_paths = [
        os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id, "opinion_space", "replay.db"),
        os.path.join("simulations", simulation_id, "opinion_space", "replay.db"),
        os.path.join("data", "simulations", simulation_id, "opinion_space", "replay.db"),
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return ReplayStorage(path)

    logger.warning(f"No replay.db found for simulation '{simulation_id}' (looked in: {possible_paths})")
    return None


@analysis_bp.route('/<simulation_id>/sentiment-timeline', methods=['GET'])
def get_sentiment_timeline(simulation_id: str):
    """Get per-round sentiment timeline with event markers."""
    try:
        storage = _get_storage()
        if not storage:
            return jsonify({"success": False, "error": "Simulation data not found"}), 404

        analytics = PostSimAnalytics(storage)
        data = analytics.sentiment_timeline(simulation_id)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.error(f"Error in sentiment-timeline: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@analysis_bp.route('/<simulation_id>/archetype-activity', methods=['GET'])
def get_archetype_activity(simulation_id: str):
    """Get per-round archetype activity metrics."""
    try:
        storage = _get_storage()
        if not storage:
            return jsonify({"success": False, "error": "Simulation data not found"}), 404

        analytics = PostSimAnalytics(storage)
        data = analytics.archetype_activity(simulation_id)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.error(f"Error in archetype-activity: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@analysis_bp.route('/<simulation_id>/event-impact/<event_id>', methods=['GET'])
def get_event_impact(simulation_id: str, event_id: str):
    """Get before/after impact comparison for a specific event."""
    try:
        storage = _get_storage()
        if not storage:
            return jsonify({"success": False, "error": "Simulation data not found"}), 404

        analytics = PostSimAnalytics(storage)
        data = analytics.event_impact(simulation_id, event_id)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.error(f"Error in event-impact: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@analysis_bp.route('/<simulation_id>/topic-cascade', methods=['GET'])
def get_topic_cascade(simulation_id: str):
    """Get topic emergence and fade patterns."""
    try:
        storage = _get_storage()
        if not storage:
            return jsonify({"success": False, "error": "Simulation data not found"}), 404

        analytics = PostSimAnalytics(storage)
        data = analytics.topic_cascade(simulation_id)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.error(f"Error in topic-cascade: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@analysis_bp.route('/<simulation_id>/radicalism-drift', methods=['GET'])
def get_radicalism_drift(simulation_id: str):
    """Get per-agent radicalism trajectory."""
    try:
        storage = _get_storage()
        if not storage:
            return jsonify({"success": False, "error": "Simulation data not found"}), 404

        analytics = PostSimAnalytics(storage)
        data = analytics.radicalism_drift(simulation_id)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.error(f"Error in radicalism-drift: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@analysis_bp.route('/<simulation_id>/non-participation', methods=['GET'])
def get_non_participation(simulation_id: str):
    """Get breakdown of why agents didn't participate."""
    try:
        storage = _get_storage()
        if not storage:
            return jsonify({"success": False, "error": "Simulation data not found"}), 404

        analytics = PostSimAnalytics(storage)
        data = analytics.non_participation_breakdown(simulation_id)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.error(f"Error in non-participation: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@analysis_bp.route('/<simulation_id>/event-summary', methods=['GET'])
def get_event_summary(simulation_id: str):
    """Get summary of all injected events."""
    try:
        storage = _get_storage()
        if not storage:
            return jsonify({"success": False, "error": "Simulation data not found"}), 404

        analytics = PostSimAnalytics(storage)
        data = analytics.event_summary(simulation_id)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.error(f"Error in event-summary: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@analysis_bp.route('/<simulation_id>/agent-summary', methods=['GET'])
def get_agent_summary(simulation_id: str):
    """Get summary stats per agent."""
    try:
        storage = _get_storage()
        if not storage:
            return jsonify({"success": False, "error": "Simulation data not found"}), 404

        analytics = PostSimAnalytics(storage)
        data = analytics.agent_summary(simulation_id)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.error(f"Error in agent-summary: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@analysis_bp.route('/<simulation_id>/overview', methods=['GET'])
def get_overview(simulation_id: str):
    """Get complete overview combining key metrics."""
    try:
        storage = _get_storage()
        if not storage:
            return jsonify({"success": False, "error": "Simulation data not found"}), 404

        analytics = PostSimAnalytics(storage)
        meta = storage.get_simulation_meta(simulation_id)

        data = {
            "meta": meta,
            "sentiment_timeline": analytics.sentiment_timeline(simulation_id),
            "event_summary": analytics.event_summary(simulation_id),
            "topic_cascade": analytics.topic_cascade(simulation_id)[:10],
            "agent_summary": analytics.agent_summary(simulation_id)[:20],
        }
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.error(f"Error in overview: {e}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500
