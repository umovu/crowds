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


def _disable_thinking_on_litellm():
    """Disable reasoning "thinking" on the in-process agentsociety2 path.

    Interviews and panels run answer_external_question() *inside the Flask
    process* (InterviewService), which reaches the LLM through agentsociety2's
    litellm client — not our LLMClient. So Config.llm_extra_body() never touches
    them. The sim subprocess already wraps litellm.acompletion to strip thinking
    (run_simulation_as.py); this mirrors that wrap for the Flask process.

    Reasoning models (Qwen 3.x, DeepSeek V4) default thinking ON — DeepSeek V4
    returns the answer in reasoning_content with an empty content field, which
    surfaces as an empty/failed interview ("I have no comment on that."). Forcing
    thinking off fixes both the correctness bug and the token cost.

    Provider-specific flag shape (sending the wrong one can 400):
        Qwen      → extra_body={"enable_thinking": False}
        DeepSeek  → extra_body={"thinking": {"type": "disabled"}}
    """
    model = (os.environ.get("SIM_LLM_MODEL") or Config.LLM_MODEL_NAME or "").lower()
    if "qwen" in model:
        nt_key, nt_val = "enable_thinking", False
    elif "deepseek" in model:
        nt_key, nt_val = "thinking", {"type": "disabled"}
    else:
        print(f"[thinking-guard] model={model!r} not a reasoning model — no wrap")
        return

    try:
        import litellm
    except Exception as e:
        print(f"[thinking-guard] litellm import failed, cannot wrap: {e}")
        return

    if getattr(litellm.acompletion, "_fub_no_thinking", False):
        return  # already wrapped (idempotent across re-inits)

    _orig_acompletion = litellm.acompletion

    async def _acompletion_no_thinking(*args, **kwargs):
        eb = dict(kwargs.get("extra_body") or {})
        eb.setdefault(nt_key, nt_val)
        kwargs["extra_body"] = eb
        return await _orig_acompletion(*args, **kwargs)

    _acompletion_no_thinking._fub_no_thinking = True
    litellm.acompletion = _acompletion_no_thinking
    print(f"[thinking-guard] litellm.acompletion wrapped: extra_body.{nt_key}={nt_val} (model={model})")




def _log_storage_persistence(logger):
    """Report where persisted data lands, and whether it survives redeploys.

    Panels, sims and the graph DB all live under Config.DATA_ROOT. On hosts like
    Railway that must point at a mounted volume (via the DATA_ROOT env var) or the
    data is written to the ephemeral container filesystem and wiped on every
    redeploy. This prints the resolved paths + a clear verdict so the persistence
    state is visible in the deploy logs — no dashboard spelunking required.
    """
    data_root = Config.DATA_ROOT
    env_set = bool(os.environ.get("DATA_ROOT"))

    # Confirm the directory is actually writable (a mount can exist but be RO).
    writable = False
    try:
        os.makedirs(data_root, exist_ok=True)
        probe = os.path.join(data_root, ".write_probe")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
        writable = True
    except Exception as e:  # pragma: no cover - environment dependent
        logger.error("DATA_ROOT write probe failed: %s", e)

    logger.info("Storage: DATA_ROOT = %s (writable=%s)", data_root, writable)
    logger.info("Storage: panels   -> %s", Config.PANEL_SESSION_DATA_DIR)
    logger.info("Storage: sims     -> %s", Config.OASIS_SIMULATION_DATA_DIR)
    if env_set:
        logger.info(
            "Storage: DATA_ROOT is set via env -> data should persist on the "
            "mounted volume across redeploys."
        )
    else:
        logger.warning(
            "Storage: DATA_ROOT is NOT set -> using the ephemeral container path. "
            "Panels, sims and the graph DB will be WIPED on every redeploy. "
            "Set DATA_ROOT to your Railway volume mount path (e.g. /data)."
        )


def _log_auth_config(logger):
    """Report the Supabase auth config so token-rejection (401) causes are visible.

    Every /api/* request must carry a Supabase JWT verified against the project's
    JWKS (needs SUPABASE_URL) or the legacy HS256 secret (SUPABASE_JWT_SECRET). If
    neither is set — or SUPABASE_URL points at a different project than the one the
    frontend signs against — every token is rejected with 401 and the app bounces
    users to the login page. Surfacing this in the deploy logs turns a silent
    "nothing loads" into an obvious misconfiguration.
    """
    disabled = os.environ.get("AUTH_DISABLED", "").lower() == "true"
    url = os.environ.get("SUPABASE_URL", "")
    has_secret = bool(os.environ.get("SUPABASE_JWT_SECRET"))

    if disabled:
        logger.warning("Auth: AUTH_DISABLED=true -> ALL requests bypass auth (dev only)")
        return
    logger.info("Auth: SUPABASE_URL = %s | SUPABASE_JWT_SECRET set = %s",
                url or "(UNSET!)", has_secret)
    from .approval import waitlist_enabled
    logger.info("Auth: waitlist gate = %s (approve users in the profiles table)",
                "ON" if waitlist_enabled() else "off")
    if not url and not has_secret:
        logger.error(
            "Auth: neither SUPABASE_URL nor SUPABASE_JWT_SECRET is set -> every "
            "token will be rejected with 401 and users can't stay logged in. Set "
            "SUPABASE_URL to your project URL (e.g. https://<ref>.supabase.co)."
        )


def create_app(config_class=Config):
    """Flask application factory function"""
    # Ensure agentsociety2 env vars are set before any imports trigger it
    _setup_agentsociety2_env()
    # Strip reasoning "thinking" from the in-process interview/panel LLM path
    _disable_thinking_on_litellm()

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
        _log_storage_persistence(logger)
        _log_auth_config(logger)

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
    from .approval import verify_approved

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
        # The waitlist request form is the front door for people with no
        # account at all, so it can't require one.
        if request.path.startswith('/api/waitlist/'):
            return None
        failed = verify_request()
        if failed is not None:
            return failed
        # Waitlist: a verified-but-unapproved account gets 403 everywhere except
        # the account status route, which is what tells the UI to show the
        # waitlist screen.
        if request.path.startswith('/api/account/'):
            return None
        return verify_approved()

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
    from .api import (graph_bp, simulation_bp, report_bp, config_bp, research_bp,
                      panel_bp, billing_bp, account_bp, waitlist_bp)
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')
    app.register_blueprint(config_bp, url_prefix='/api/config')
    app.register_blueprint(research_bp, url_prefix='/api/research')
    app.register_blueprint(panel_bp, url_prefix='/api/panel')
    app.register_blueprint(billing_bp, url_prefix='/api/billing')
    app.register_blueprint(account_bp, url_prefix='/api/account')
    app.register_blueprint(waitlist_bp, url_prefix='/api/waitlist')
    # Non-/api on purpose: tapped from a Telegram link with no session, and
    # authenticated by ADMIN_APPROVE_TOKEN in the URL instead of a JWT.
    from .admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

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

