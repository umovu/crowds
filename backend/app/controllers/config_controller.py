"""Graph backend switching and non-sensitive configuration.

  GET  /api/config/backend   the current graph backend, and what is available
  POST /api/config/backend   switch backend (neo4j, kglite, ladybug)
  GET  /api/config/config    non-sensitive configuration

Swapping the graph backend is app wiring rather than a business rule: it reads and
writes `current_app.extensions`, which only a request can reach. The one piece that
is not wiring — closing a backend cleanly so it releases its file locks — lives in
`app/storage` next to the factory that opens them.
"""

from flask import current_app, jsonify, request

from . import config_bp
from ..config import Config
from ..storage import BACKENDS, close_storage, get_storage
from ..utils.logger import get_logger

logger = get_logger('fub.controller.config')


def _current_backend() -> str:
    return current_app.extensions.get('graph_backend', Config.GRAPH_BACKEND)


@config_bp.route('/backend', methods=['GET'])
def get_backend():
    """Get current graph backend."""
    return jsonify({
        'backend': _current_backend(),
        'available_backends': list(BACKENDS),
    })


@config_bp.route('/backend', methods=['POST'])
def set_backend():
    """Switch graph backend (neo4j, kglite, or ladybug)."""
    data = request.get_json()
    new_backend = data.get('backend', 'neo4j')

    if new_backend not in BACKENDS:
        return jsonify({
            'error': 'Invalid backend. Must be "neo4j", "kglite", or "ladybug"'
        }), 400

    # No-op when switching to the current backend (avoids re-opening a locked file).
    current_backend = _current_backend()
    if new_backend == current_backend:
        return jsonify({
            'success': True,
            'backend': new_backend,
            'message': f'Already using {new_backend.upper()}',
        })

    try:
        # Close the existing storage FIRST so embedded backends release their file
        # locks, then drop the reference so the new one isn't blocked by a dangling
        # instance. Only then is it safe to open the new backend.
        close_storage(current_app.extensions.get('graph_storage'))
        current_app.extensions['graph_storage'] = None

        current_app.extensions['graph_storage'] = get_storage(new_backend)
        current_app.extensions['graph_backend'] = new_backend

        logger.info(f"Switched graph backend: {current_backend} → {new_backend}")
        return jsonify({
            'success': True,
            'backend': new_backend,
            'message': f'Switched to {new_backend.upper()}',
        })
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to switch backend to {new_backend}: {e}")
        return jsonify({'error': f'Failed to initialize {new_backend}: {str(e)}'}), 500


@config_bp.route('/config', methods=['GET'])
def get_config():
    """Get non-sensitive configuration."""
    return jsonify({
        'graph_backend': _current_backend(),
        'llm_model': Config.LLM_MODEL_NAME,
        'llm_base_url': Config.LLM_BASE_URL,
        'embedding_model': Config.EMBEDDING_MODEL,
    })
