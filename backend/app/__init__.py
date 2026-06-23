"""
Fub Simulation Backend - Flask Application Factory
"""

import os
import warnings

# Suppress multiprocessing resource_tracker warnings (from third-party libraries like transformers)
# Must be set before all other imports
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

from flask import Flask, request
from flask_cors import CORS

from .config import Config
from .utils.logger import setup_logger, get_logger


def _setup_agentsociety2_env():
    """Bridge Fub's config to agentsociety2's expected env vars.

    Maps Fub's unified config to the env vars agentsociety2 and its skills
    expect at runtime.
    """
    # LLM config (required by AgentSociety2). The simulation uses the SIM_LLM_*
    # model/key/base when set, falling back to the research LLM_* config.
    _sim_key = os.environ.get("SIM_LLM_API_KEY") or Config.LLM_API_KEY or ""
    _sim_base = os.environ.get("SIM_LLM_BASE_URL") or Config.LLM_BASE_URL or ""
    _sim_model = os.environ.get("SIM_LLM_MODEL") or Config.LLM_MODEL_NAME or ""
    if not os.environ.get("AGENTSOCIETY_NANO_LLM_API_KEY"):
        os.environ["AGENTSOCIETY_NANO_LLM_API_KEY"] = _sim_key
    if not os.environ.get("AGENTSOCIETY_NANO_LLM_API_BASE"):
        os.environ["AGENTSOCIETY_NANO_LLM_API_BASE"] = _sim_base
    if not os.environ.get("AGENTSOCIETY_NANO_LLM_MODEL"):
        os.environ["AGENTSOCIETY_NANO_LLM_MODEL"] = _sim_model
    if not os.environ.get("AGENTSOCIETY_LLM_API_KEY"):
        os.environ["AGENTSOCIETY_LLM_API_KEY"] = _sim_key
    if not os.environ.get("AGENTSOCIETY_LLM_API_BASE"):
        os.environ["AGENTSOCIETY_LLM_API_BASE"] = _sim_base




def create_app(config_class=Config):
    """Flask application factory function"""
    # Ensure agentsociety2 env vars are set before any imports trigger it
    _setup_agentsociety2_env()

    app = Flask(__name__)
    app.config.from_object(config_class)

    # Configure JSON encoding: ensure Chinese displays directly (not as \uXXXX)
    # Flask >= 2.3 uses app.json.ensure_ascii, older versions use JSON_AS_ASCII config
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False

    # Setup logging
    logger = setup_logger('fub')

    # Only print startup info in reloader subprocess (avoid printing twice in debug mode)
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process

    if should_log_startup:
        logger.info("=" * 50)
        logger.info("Fub Simulation Backend starting...")
        logger.info("=" * 50)

    # Enable CORS
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # --- Initialize Graph Storage singleton (DI via app.extensions) ---
    # Single-process server (reloader disabled in run.py), so we always init here.
    # Embedded LadybugDB needs exactly one process holding its file lock.
    from .storage import get_storage, Neo4jStorage, LadybugStorage
    try:
        graph_backend = Config.GRAPH_BACKEND
        graph_storage = get_storage(graph_backend)
        app.extensions['graph_storage'] = graph_storage
        app.extensions['graph_backend'] = graph_backend
        if should_log_startup:
            logger.info("GraphStorage initialized (%s)", graph_backend.upper())
    except Exception as e:
        logger.error("GraphStorage initialization failed: %s", e)
        app.extensions['graph_storage'] = None
        app.extensions['graph_backend'] = Config.GRAPH_BACKEND

    # Register simulation process cleanup function (ensure all simulation processes terminate on server shutdown)
    from .services.simulation_runner import SimulationRunner
    SimulationRunner.register_cleanup()
    if should_log_startup:
        logger.info("Simulation process cleanup function registered")

    # Auth guard: every /api/* request must carry a valid Supabase JWT.
    # Non-/api routes (e.g. /health) and CORS preflight (OPTIONS) are exempt.
    from .auth import verify_request

    @app.before_request
    def require_supabase_auth():
        if request.method == 'OPTIONS':
            return None
        if not request.path.startswith('/api/'):
            return None
        # Paystack calls the webhook server-to-server (no JWT); it's verified by
        # HMAC signature inside the handler instead.
        if request.path == '/api/billing/webhook':
            return None
        return verify_request()

    # Request logging middleware
    @app.before_request
    def log_request():
        logger = get_logger('fub.request')
        logger.debug(f"Request: {request.method} {request.path}")
        if request.content_type and 'json' in request.content_type:
            logger.debug(f"Request body: {request.get_json(silent=True)}")

    @app.after_request
    def log_response(response):
        logger = get_logger('fub.request')
        logger.debug(f"Response: {response.status_code}")
        return response

    # Register blueprints
    from .api import graph_bp, simulation_bp, report_bp, config_bp, research_bp, panel_bp, billing_bp
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')
    app.register_blueprint(config_bp, url_prefix='/api/config')
    app.register_blueprint(research_bp, url_prefix='/api/research')
    app.register_blueprint(panel_bp, url_prefix='/api/panel')
    app.register_blueprint(billing_bp, url_prefix='/api/billing')

    # Health check
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'Fub Simulation Backend'}

    # TEMP diagnostic — confirms the persona library loaded on the host. Remove
    # once verified. Non-/api path so it's auth-exempt.
    @app.route('/debug/library')
    def _debug_library():
        from .services.persona_library import get_library, _default_library_path
        path = _default_library_path()
        info = {
            'library_path': path,
            'path_exists': os.path.exists(path),
            'bucket_env_set': bool(os.environ.get('PERSONA_LIBRARY_BUCKET')),
            'path_env_set': bool(os.environ.get('PERSONA_LIBRARY_PATH')),
            'data_root': os.environ.get('DATA_ROOT'),
        }
        try:
            info['count'] = len(get_library().all())
        except Exception as e:
            info['count'] = f'error: {e}'
        return info

    if should_log_startup:
        logger.info("Fub Simulation Backend startup complete")

    return app

