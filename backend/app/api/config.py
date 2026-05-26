"""
Config API Routes

Endpoints for managing application configuration including graph backend switching.
"""

import logging
from flask import current_app, request, jsonify
from . import config_bp
from ..config import Config
from ..storage import get_storage

logger = logging.getLogger('fub.config')


@config_bp.route('/backend', methods=['GET'])
def get_backend():
    """Get current graph backend."""
    backend = current_app.extensions.get('graph_backend', Config.GRAPH_BACKEND)
    return jsonify({
        'backend': backend,
        'available_backends': ['neo4j', 'kglite', 'ladybug']
    })


@config_bp.route('/backend', methods=['POST'])
def set_backend():
    """Switch graph backend (neo4j, kglite, or ladybug)."""
    data = request.get_json()
    new_backend = data.get('backend', 'neo4j')

    if new_backend not in ['neo4j', 'kglite', 'ladybug']:
        return jsonify({'error': 'Invalid backend. Must be "neo4j", "kglite", or "ladybug"'}), 400

    # No-op when switching to the current backend (avoids re-opening a locked file)
    current_backend = current_app.extensions.get('graph_backend', Config.GRAPH_BACKEND)
    if new_backend == current_backend:
        return jsonify({
            'success': True,
            'backend': new_backend,
            'message': f'Already using {new_backend.upper()}'
        })

    try:
        # Close the existing storage FIRST so embedded backends release their file locks
        old_storage = current_app.extensions.get('graph_storage')
        if old_storage and hasattr(old_storage, 'close'):
            try:
                old_storage.close()
            except Exception as close_err:
                logger.warning(f"Failed to close old storage cleanly: {close_err}")
        # Clear the reference so the new one isn't blocked by a dangling instance
        current_app.extensions['graph_storage'] = None

        # Now safe to open the new backend
        new_storage = get_storage(new_backend)
        current_app.extensions['graph_storage'] = new_storage
        current_app.extensions['graph_backend'] = new_backend

        logger.info(f"Switched graph backend: {current_backend} → {new_backend}")

        return jsonify({
            'success': True,
            'backend': new_backend,
            'message': f'Switched to {new_backend.upper()}'
        })
    except Exception as e:
        logger.error(f"Failed to switch backend to {new_backend}: {e}")
        return jsonify({
            'error': f'Failed to initialize {new_backend}: {str(e)}'
        }), 500


@config_bp.route('/config', methods=['GET'])
def get_config():
    """Get non-sensitive configuration."""
    return jsonify({
        'graph_backend': current_app.extensions.get('graph_backend', Config.GRAPH_BACKEND),
        'llm_model': Config.LLM_MODEL_NAME,
        'llm_base_url': Config.LLM_BASE_URL,
        'embedding_model': Config.EMBEDDING_MODEL,
    })
