"""
Configuration Management
Loads configuration from .env file in project root directory
"""

import os
from dotenv import load_dotenv

# Load .env file from project root
# Path: Fub Simulation/.env (relative to backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # If no .env in root, try to load environment variables (for production)
    load_dotenv(override=True)


class Config:
    """Flask configuration class"""

    # Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY', 'fub-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'

    # JSON configuration - disable ASCII escaping to display Chinese directly (not as \uXXXX)
    JSON_AS_ASCII = False

    # LLM configuration (unified OpenAI format)
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'http://localhost:11434/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'llama-3.3-70b-versatile')

    # LLM-as-judge: advisory quality scorer (Plus tier). Off by default — each
    # judged setup path costs an extra Plus-tier call, so only enable when you
    # are actively evaluating output quality. Never gates/regenerates; it scores.
    JUDGE_ENABLED = os.environ.get('JUDGE_ENABLED', 'false').lower() == 'true'

    # LLM pricing (USD per 1 million tokens) — used for cost estimation
    # Set these when using paid APIs (DeepSeek, OpenAI, Groq) so simulations
    # can report estimated spend.  If unset, built-in defaults are used.
    LLM_PRICE_PROMPT_PER_1M = os.environ.get('LLM_PRICE_PROMPT_PER_1M')
    LLM_PRICE_COMPLETION_PER_1M = os.environ.get('LLM_PRICE_COMPLETION_PER_1M')

    @staticmethod
    def llm_extra_body() -> dict:
        """
        Provider-specific extra_body parameters for the configured LLM.

        Qwen 3.x models are reasoning-enabled by default — they emit hidden
        "thinking" tokens that count against output usage. For an opinion-
        simulation workload we want concise persona outputs, not chain-of-
        thought, so we disable thinking. For other providers returns {}.

        Per-model opt-in: set ENABLE_LLM_THINKING=1 in the environment to
        force-enable thinking for a specific run (e.g. for a research call
        that benefits from CoT). Default is OFF for qwen — keeps texture
        fast (~10x faster on qwen3.7-plus-2026-05-26).
        """
        if os.environ.get('ENABLE_LLM_THINKING', '').lower() in ('1', 'true', 'yes'):
            return {'enable_thinking': True}
        model = (os.environ.get('LLM_MODEL_NAME') or '').lower()
        if model.startswith('qwen') or 'qwen' in model:
            return {'enable_thinking': False}
        return {}

    # Graph Backend: 'ladybug' (default — embedded, no Docker, persistent),
    # 'neo4j' (server, needs Docker), or 'kglite' (in-memory, dev only)
    GRAPH_BACKEND = os.environ.get('GRAPH_BACKEND', 'ladybug')
    
    # Neo4j configuration
    NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD', 'fub')

    # Embedding configuration
    EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'nomic-embed-text')
    EMBEDDING_BASE_URL = os.environ.get('EMBEDDING_BASE_URL', 'http://localhost:11434')

    # Root for all persisted data (graph DB + uploads). Defaults to the backend
    # dir so local dev is unchanged; set DATA_ROOT=/data on hosts with a mounted
    # volume (e.g. Railway) so data survives redeploys.
    DATA_ROOT = os.environ.get('DATA_ROOT') or os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..')
    )

    # File upload configuration
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(DATA_ROOT, 'uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}

    # Text processing configuration
    DEFAULT_CHUNK_SIZE = 500  # Default chunk size
    DEFAULT_CHUNK_OVERLAP = 50  # Default overlap size

    # Simulation configuration
    # NOTE: currently unreferenced — the actual round count comes from the API
    # max_rounds param / preset, or time_config (total_hours / minutes_per_round).
    MAX_ROUNDS = int(os.environ.get('MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(DATA_ROOT, 'uploads', 'simulations')

    # Panel pitch sessions (library-backed casts, no simulation) live apart from
    # sim dirs so simulation listings never pick them up.
    PANEL_SESSION_DATA_DIR = os.path.join(DATA_ROOT, 'uploads', 'panel_sessions')

    # Coverage simulator configuration — this tool surfaces the RANGE of distinct
    # reactions, not a majority. Convergence is the failure mode. The run stops on
    # COVERAGE SATURATION (no new distinct position for N rounds), never on
    # agreement; positions are clustered stance-first; agents read homophily-biased
    # neighborhoods with a small cross-group leak so distinct objections develop in
    # parallel instead of cascading one direction.
    COVERAGE_SATURATION_ROUNDS = int(os.environ.get('COVERAGE_SATURATION_ROUNDS', '4'))   # stop after N rounds with no new position
    USE_COVERAGE_STOP          = os.environ.get('USE_COVERAGE_STOP', 'true').lower() == 'true'  # False = old sentiment stop
    POSITION_SIM_THRESHOLD     = float(os.environ.get('POSITION_SIM_THRESHOLD', '0.72'))  # cosine/Jaccard: same position (calibrated 2026-06 live: 0.82 over-counted, never matched cross-round)
    NEIGHBORHOOD_SIZE          = int(os.environ.get('NEIGHBORHOOD_SIZE', '5'))             # posts an agent reads per round
    CROSS_GROUP_LEAK           = float(os.environ.get('CROSS_GROUP_LEAK', '0.2'))          # prob. a feed slot pulls a non-similar post
    PITCH_REANCHOR_EVERY       = int(os.environ.get('PITCH_REANCHOR_EVERY', '4'))          # product mode: re-post pitch reminder every N rounds (0 = once at round 0 only)

    # Opinion Space available actions
    OPINION_SPACE_ACTIONS = [
        'EXPRESS_OPINION', 'RESPOND_TO_OPINION', 'SEARCH_TOPIC', 'OBSERVE', 'DO_NOTHING'
    ]

    # Report Agent configuration
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))

    # Firecrawl configuration (used by deep-research-python for full-page scraping)
    FIRECRAWL_API_KEY = os.environ.get('FIRECRAWL_API_KEY', '')

    # Serper configuration (Google Search — used by MCP inline fallback)
    SERPER_API_KEY = os.environ.get('SERPER_API_KEY', '')

    # deep-research-python expects OPENAI_KEY / CUSTOM_MODEL / OPENAI_BASE_URL.
    # _ensure_groq_env() in deep_research_service.py auto-maps LLM_* vars at runtime,
    # so no extra entries are needed here — reading them directly from os.environ.

    @classmethod
    def validate(cls):
        """Validate required configuration"""
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY not configured (set to any non-empty value, e.g. 'ollama')")
        if not cls.NEO4J_URI:
            errors.append("NEO4J_URI not configured")
        if not cls.NEO4J_PASSWORD:
            errors.append("NEO4J_PASSWORD not configured")
        return errors
