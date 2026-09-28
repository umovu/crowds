"""Shared test helpers."""

import importlib
import sys

import pytest


@pytest.fixture(autouse=True)
def _typed_readers_off(monkeypatch):
    """No test reaches the typed (Jev) reader unless it turns it on itself.

    Config loads the repo .env at import, and a developer's .env turns the readers on
    (FUB_TYPED_SUBJECTS, FUB_TYPED_CARDS). Left on, tests called the live API: slow,
    billed, and non-deterministic — test_query_context failed on it for weeks, and
    card-routing tests saw cards the reader added. Tests of the readers set the flag
    and stub the client themselves.
    """
    monkeypatch.setenv("FUB_TYPED_SUBJECTS", "0")
    monkeypatch.setenv("FUB_TYPED_CARDS", "0")
    monkeypatch.setenv("FUB_TYPED_AUDIENCE", "0")


def _is_stub(module) -> bool:
    """A module a test built by hand (types.ModuleType), not one loaded from a file."""
    return not getattr(module, "__file__", None)


@pytest.fixture
def real_module():
    """Import the real module even when another test file left a stub in sys.modules.

    test_sim_start_and_credits stubs app.auth, app.controllers.gates,
    app.services.billing_service and the interview service while tests are collected,
    so its own imports stay light. A test that needs the real code borrows it through
    this fixture; the stubs are put back afterwards so that file keeps what it expects.
    """
    saved = {}

    def load(name):
        # Every stubbed module in the same top-level package goes, not only the
        # ones on this name's path: the real module's own imports reach siblings
        # (app.controllers.config_controller -> app.storage) that may be stubbed too.
        root = name.split(".")[0]
        for key in [k for k in sys.modules if k == root or k.startswith(root + ".")]:
            if _is_stub(sys.modules[key]) and key not in saved:
                saved[key] = sys.modules.pop(key)
        return importlib.import_module(name)

    yield load
    for prefix, stub in saved.items():
        sys.modules[prefix] = stub
        parent, _, child = prefix.rpartition(".")
        if parent in sys.modules:
            setattr(sys.modules[parent], child, stub)
