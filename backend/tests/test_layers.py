"""The layer rules, enforced.

The app is moving to one job per layer:

    view -> controller -> service -> repository
                  |           |
                  +-- model --+

    app/models/        data classes only. No web framework, no network, no storage.
    app/repositories/  the ONLY place that talks to Supabase, files or SQLite.
    app/services/      rules and calculations. No Flask, no storage calls.
    app/controllers/   thin Flask routes: read the request, call a service, answer.
    app/api/           routes not moved yet. Shrinks each pass, then goes away.

The allowlists below are the migration debt, named file by file. They may only get
shorter: adding a Supabase call to a new service, or a new route under app/api/,
fails here. That is the point — the list is the to-do list.
"""

from __future__ import annotations

import os
import re

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")

# Empty on purpose: no service may reach Supabase any more. Every one of them now
# asks a repository. This is a rule, not a to-do list.
SERVICES_STILL_CALLING_SUPABASE: set = set()

# Empty on purpose: no model file touches storage any more. `ProjectManager` was the
# last one and its file work now lives in repositories/project_repository.py, leaving
# the Project dataclass behind. TaskManager never did any — it is a threading
# singleton holding a dict, and was listed here by mistake in the first pass.
MODELS_STILL_DOING_IO: set = set()

_SUPABASE = re.compile(r"/rest/v1|/storage/v1|SUPABASE_SERVICE_ROLE_KEY")
_IMPORTS_FLASK = re.compile(r"^\s*(from flask\b|import flask\b)", re.MULTILINE)
_IMPORTS_REQUESTS = re.compile(r"^\s*(from requests\b|import requests\b)", re.MULTILINE)
_TOUCHES_STORAGE = re.compile(r"\bopen\(|\bsqlite3\b|json\.load\(|json\.dump\(")


def _files(layer):
    d = os.path.join(APP, layer)
    if not os.path.isdir(d):
        return []
    return [(f, open(os.path.join(d, f), encoding="utf-8").read())
            for f in sorted(os.listdir(d))
            if f.endswith(".py")]


def test_models_are_only_data():
    """A model describes what the app stores. It does not fetch, serve or save it."""
    for name, src in _files("models"):
        assert not _IMPORTS_FLASK.search(src), f"models/{name} imports Flask"
        assert not _IMPORTS_REQUESTS.search(src), f"models/{name} imports requests"
        assert not _SUPABASE.search(src), f"models/{name} talks to Supabase"
        if name not in MODELS_STILL_DOING_IO:
            assert not _TOUCHES_STORAGE.search(src), \
                f"models/{name} reads or writes storage — that belongs in a repository"


def test_services_hold_no_web_layer():
    """Rules must be callable without a request in flight, so they stay testable."""
    for name, src in _files("services"):
        assert not _IMPORTS_FLASK.search(src), \
            f"services/{name} imports Flask — move request handling to a controller"


def test_only_known_services_still_reach_supabase():
    """Storage moves to repositories one service at a time. No new ones."""
    offenders = {name for name, src in _files("services") if _SUPABASE.search(src)}
    assert offenders <= SERVICES_STILL_CALLING_SUPABASE, (
        "new service(s) calling Supabase directly: "
        f"{sorted(offenders - SERVICES_STILL_CALLING_SUPABASE)}. "
        "Put the call in app/repositories/ and have the service ask for it."
    )


def test_allowlists_name_real_files():
    """A fixed allowlist is only honest while its files exist."""
    service_names = {name for name, _ in _files("services")}
    assert SERVICES_STILL_CALLING_SUPABASE <= service_names
    model_names = {name for name, _ in _files("models")}
    assert MODELS_STILL_DOING_IO <= model_names


def test_repositories_stay_below_the_rules():
    """A repository answers with models. It never decides anything."""
    for name, src in _files("repositories"):
        assert not _IMPORTS_FLASK.search(src), f"repositories/{name} imports Flask"
        assert "from ..services" not in src and "from app.services" not in src, \
            f"repositories/{name} imports a service — the arrow points the other way"


def test_controllers_carry_no_storage_or_rules():
    """A controller reads the request, calls a service and answers. Nothing else."""
    for name, src in _files("controllers"):
        assert not _IMPORTS_REQUESTS.search(src), f"controllers/{name} imports requests"
        assert not _SUPABASE.search(src), f"controllers/{name} talks to Supabase"
        assert not _TOUCHES_STORAGE.search(src), f"controllers/{name} touches storage"
