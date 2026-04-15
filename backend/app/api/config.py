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
        'available_backends': ['neo4j', 'kglite']
    })


@config_bp.route('/backend', methods=['POST'])
def set_backend():
    """Switch graph backend (neo4j or kglite)."""
    data = request.get_json()
    new_backend = data.get('backend', 'neo4j')
    
    if new_backend not in ['neo4j', 'kglite']:
        return jsonify({'error': 'Invalid backend. Must be "neo4j" or "kglite"'}), 400
    
    try:
        new_storage = get_storage(new_backend)
        old_storage = current_app.extensions.get('graph_storage')
        
        if old_storage and hasattr(old_storage, 'close'):
            old_storage.close()
        
        current_app.extensions['graph_storage'] = new_storage
        current_app.extensions['graph_backend'] = new_backend
        
        logger.info(f"Switched graph backend to: {new_backend}")
        
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
