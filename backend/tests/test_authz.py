"""Ownership (IDOR) regression tests — LLM off.

Auth proves WHO the caller is; these pin WHAT they may touch. Before the
ownership guard, any signed-in user could read, delete, or run rounds against
another tenant's panel session or simulation just by knowing its id.

The contract pinned here:

  * owner gets 200; a different user gets 404 (never 403 — a 403 confirms the
    id exists and turns the endpoint into an enumeration oracle)
  * a blocked response leaks none of the resource's content
  * a blocked DELETE leaves the resource on disk
  * ids carried in the JSON body (/start, /interview, …) are guarded too, not
    just ids in the URL
  * legacy records with no stored user_id stay readable (pre-auth data)
  * malformed/traversal ids are rejected as 404, never a 500 or a path escape

Identity is driven by patching billing.current_user_id; AUTH_DISABLED (set in
conftest) bypasses JWT verification so these need no Supabase project.
"""

import json
import os

import pytest


@pytest.fixture(scope="module")
def app():
    # Sibling test modules (test_library_cast, test_mode_detector) hand-register
    # stub "app"/"app.services" entries in sys.modules so their relative imports
    # resolve without pulling in the heavy package. Those stubs have no
    # create_app, so if one of them ran first the import below fails with
    # "unknown location". Drop any stub and import the real package. Modules
    # those tests already hold direct references to keep working.
    import sys
    if "app" in sys.modules and not hasattr(sys.modules["app"], "create_app"):
        for name in [n for n in sys.modules if n == "app" or n.startswith("app.")]:
            del sys.modules[name]

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    from app import create_app
    application = create_app()
    application.testing = True
    return application


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


@pytest.fixture
def as_user(monkeypatch):
    """Switch the acting user for the duration of a test."""
    from app import billing
    current = {"uid": "alice"}
    monkeypatch.setattr(billing, "current_user_id", lambda: current["uid"])

    def _set(uid):
        current["uid"] = uid
    return _set


# ── Panel sessions ──────────────────────────────────────────────────────────
@pytest.fixture
def alice_session(app):
    """A panel session on disk owned by alice, with a minimal roster."""
    from app.config import Config
    sid = "panel_testalice01"
    sdir = os.path.join(Config.PANEL_SESSION_DATA_DIR, sid)
    os.makedirs(sdir, exist_ok=True)
    with open(os.path.join(sdir, "panel_session.json"), "w") as f:
        json.dump({"session_id": sid, "user_id": "alice",
                   "pitch": "CONFIDENTIAL PITCH"}, f)
    with open(os.path.join(sdir, "agentsociety_profiles.json"), "w") as f:
        json.dump([{"id": 0, "name": "Test Person", "age": 30}], f)
    return sid, sdir


def test_owner_can_read_own_session(client, as_user, alice_session):
    sid, _ = alice_session
    as_user("alice")
    assert client.get(f"/api/panel/sessions/{sid}").status_code == 200


def test_other_user_cannot_read_session(client, as_user, alice_session):
    sid, _ = alice_session
    as_user("bob")
    resp = client.get(f"/api/panel/sessions/{sid}")
    assert resp.status_code == 404          # 404, not 403 — no existence oracle
    assert b"CONFIDENTIAL PITCH" not in resp.data


def test_other_user_cannot_delete_session(client, as_user, alice_session):
    sid, sdir = alice_session
    as_user("bob")
    assert client.delete(f"/api/panel/sessions/{sid}").status_code == 404
    assert os.path.isdir(sdir), "victim's session was deleted by another user"


def test_other_user_cannot_pitch_to_session(client, as_user, alice_session):
    sid, _ = alice_session
    as_user("bob")
    resp = client.post(f"/api/panel/sessions/{sid}/pitch", json={"pitch": "x"})
    assert resp.status_code == 404


@pytest.mark.parametrize("bad_id", ["..", "%2e%2e", "foo/../..", "panel_x;rm", "/etc/passwd"])
def test_malformed_session_ids_rejected(client, as_user, bad_id):
    """Traversal attempts must 404 — never 500, never escape the data dir."""
    as_user("bob")
    assert client.get(f"/api/panel/sessions/{bad_id}").status_code in (400, 404, 405)


def test_legacy_ownerless_session_still_readable(client, as_user, app):
    """Sessions created before auth carry no user_id and must not 404."""
    from app.config import Config
    sid = "panel_testlegacy1"
    sdir = os.path.join(Config.PANEL_SESSION_DATA_DIR, sid)
    os.makedirs(sdir, exist_ok=True)
    with open(os.path.join(sdir, "panel_session.json"), "w") as f:
        json.dump({"session_id": sid, "pitch": "old"}, f)
    with open(os.path.join(sdir, "agentsociety_profiles.json"), "w") as f:
        json.dump([{"id": 0, "name": "Legacy Person", "age": 40}], f)
    as_user("bob")
    assert client.get(f"/api/panel/sessions/{sid}").status_code == 200


# ── Simulations ─────────────────────────────────────────────────────────────
@pytest.fixture
def alice_sim(app):
    from app.services.simulation_manager import SimulationManager
    return SimulationManager().create_simulation(
        "proj_test", "graph_test", user_id="alice").simulation_id


@pytest.mark.parametrize("suffix", [
    "", "/profiles", "/posts", "/comments", "/config", "/timeline",
    "/config/download", "/agents",
])
def test_other_user_cannot_read_simulation(client, as_user, alice_sim, suffix):
    as_user("bob")
    assert client.get(f"/api/simulation/{alice_sim}{suffix}").status_code == 404


def test_other_user_cannot_delete_simulation(client, as_user, alice_sim):
    from app.services.simulation_manager import SimulationManager
    as_user("bob")
    assert client.delete(f"/api/simulation/{alice_sim}").status_code == 404
    assert SimulationManager().get_simulation(alice_sim) is not None


@pytest.mark.parametrize("path", [
    "/api/simulation/start", "/api/simulation/stop", "/api/simulation/interview",
    "/api/simulation/interview/all", "/api/simulation/interview/history",
    "/api/simulation/env-status", "/api/simulation/close-env",
    "/api/simulation/prepare",
])
def test_body_carried_simulation_id_is_guarded(client, as_user, alice_sim, path):
    """Ids in the JSON body must be checked too, not just ids in the URL."""
    as_user("bob")
    resp = client.post(path, json={"simulation_id": alice_sim,
                                   "agent_id": 0, "prompt": "hi"})
    assert resp.status_code == 404


def test_owner_still_reaches_own_simulation(client, as_user, alice_sim):
    as_user("alice")
    assert client.get(f"/api/simulation/{alice_sim}").status_code == 200


def test_prepare_status_tolerates_unknown_id(client, as_user):
    """The UI polls /prepare/status before the sim exists — must not 404."""
    as_user("alice")
    resp = client.post("/api/simulation/prepare/status",
                       json={"simulation_id": "sim_doesnotexist"})
    assert resp.status_code != 404


# ── Error hygiene ───────────────────────────────────────────────────────────
def test_error_responses_carry_no_traceback(client, as_user, alice_session):
    sid, _ = alice_session
    as_user("bob")
    assert b"traceback" not in client.get(f"/api/panel/sessions/{sid}").data.lower()
