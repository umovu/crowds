"""
Fub Simulation Backend Entry Point
"""

import os
import sys
import subprocess
import time

# Solve Windows console Chinese character encoding issue: set UTF-8 encoding before all imports
if sys.platform == 'win32':
    # Set environment variable to ensure Python uses UTF-8
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    # Reconfigure standard output stream to UTF-8
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Load .env BEFORE any agentsociety2 imports (which require env vars at import time)
from dotenv import load_dotenv
load_dotenv()

# Set agentsociety2 required env vars early.
# Research/persona model = LLM_* ; simulation model = SIM_LLM_* (falls back to LLM_* if blank).
_llm_key = os.environ.get('LLM_API_KEY', '')
_llm_base = os.environ.get('LLM_BASE_URL', '')
_sim_key = os.environ.get('SIM_LLM_API_KEY', '') or _llm_key
_sim_base = os.environ.get('SIM_LLM_BASE_URL', '') or _llm_base
_sim_model = os.environ.get('SIM_LLM_MODEL', '') or os.environ.get('LLM_MODEL_NAME', '')
os.environ.setdefault('AGENTSOCIETY_LLM_API_KEY', _sim_key)
os.environ.setdefault('AGENTSOCIETY_LLM_API_BASE', _sim_base)
os.environ.setdefault('AGENTSOCIETY_NANO_LLM_API_KEY', _sim_key)
os.environ.setdefault('AGENTSOCIETY_NANO_LLM_API_BASE', _sim_base)
os.environ.setdefault('AGENTSOCIETY_NANO_LLM_MODEL', _sim_model)
os.environ.setdefault('WEB_SEARCH_API_TOKEN', 'local-dev-token')

# Add project root directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.config import Config


def _get_version() -> str:
    version_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "VERSION")
    try:
        with open(version_file) as f:
            return f.read().strip()
    except FileNotFoundError:
        return "0.0.0"


def main():
    """Main function"""
    import argparse
    parser = argparse.ArgumentParser(description="Fub Simulation backend server")
    parser.add_argument("-v", "--version", action="version", version=f"crowds v{_get_version()}")
    parser.parse_args()

    # Validate configuration
    errors = Config.validate()
    if errors:
        print("Configuration errors:")
        for err in errors:
            print(f"  - {err}")
        print("\nPlease check configuration in .env file")
        sys.exit(1)

    # Create application
    app = create_app()

    # Get runtime configuration
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 5001))
    debug = Config.DEBUG

    # Start service.
    # use_reloader=False: the Werkzeug auto-reloader spawns a second process,
    # and embedded LadybugDB allows only ONE process to hold its file lock.
    # Two processes → lock conflict → GraphStorage fails to init. Disabling the
    # reloader keeps us single-process and stable. (Manually restart after code
    # changes; debug error pages still work.)
    app.run(host=host, port=port, debug=debug, threaded=True, use_reloader=False)


if __name__ == '__main__':
    main()

