"""Shared test environment.

Set before any `app` import so tests never depend on the developer's real .env:

  * SECRET_KEY  — Config now refuses to start without one outside debug mode
  * AUTH_DISABLED — skip Supabase JWT verification; ownership tests drive
    identity by patching billing.current_user_id instead
  * DATA_ROOT — keep any file the tests write out of the real data dir
"""

import os
import tempfile

# agentsociety2 raises at *import* time if these are unset. create_app() normally
# populates them, but a test module that imports app.services directly can win the
# race — set them here so import order never decides whether the suite runs.
# Dummy values: no test in this suite calls a model.
os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-key-unused")
os.environ.setdefault("AGENTSOCIETY_LLM_API_BASE", "http://localhost:0/v1")
os.environ.setdefault("AGENTSOCIETY_NANO_LLM_API_KEY", "test-key-unused")
os.environ.setdefault("AGENTSOCIETY_NANO_LLM_API_BASE", "http://localhost:0/v1")
os.environ.setdefault("AGENTSOCIETY_NANO_LLM_MODEL", "test-model")

os.environ.setdefault("SECRET_KEY", "test-only-secret")
os.environ.setdefault("AUTH_DISABLED", "true")
os.environ.setdefault("FLASK_DEBUG", "false")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("DATA_ROOT", tempfile.mkdtemp(prefix="fub_tests_"))
