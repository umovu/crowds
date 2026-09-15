"""Panel sessions, their context file and the people seated in the room fit
app/data/model (panel_session, panel_context, room_seat). LLM-off.

These files are what the results screen, the report and every later round read back.
Keys drifted with age (mode, slots, filters), and a seat mixes the person with fields
the room adds at build time.
"""

import glob
import importlib.util
import json
import os

import pytest

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
SESSIONS = os.path.join(BACKEND, "uploads", "panel_sessions")
LIBRARY = os.path.join(BACKEND, "app", "data", "persona_library", "personas.json")

_spec = importlib.util.spec_from_file_location(
    "data_model_for_panel_tests", os.path.join(BACKEND, "app", "services", "data_model.py"))
dm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dm)


def _saved(name):
    files = glob.glob(os.path.join(SESSIONS, "*", name))
    if not files:
        pytest.skip("no saved panel sessions in this checkout")
    for path in files:
        with open(path, encoding="utf-8") as fh:
            yield os.path.basename(os.path.dirname(path)), json.load(fh)


# ── saved sessions ─────────────────────────────────────────────────────────

def test_saved_sessions_fit_the_model():
    problems = [p for _sid, meta in _saved("panel_session.json")
                for p in dm.model_problems("panel_session", meta)]
    assert not problems, "\n".join(problems[:20])


def test_saved_context_files_fit_the_model():
    problems = [p for _sid, ctx in _saved("document_context.json")
                for p in dm.model_problems("panel_context", ctx)]
    assert not problems, "\n".join(problems[:20])


def test_saved_rooms_have_valid_room_fields():
    """The person part follows whichever library the room was built from, so older
    rooms are checked on the room's own fields only."""
    problems = [f"{sid}: {p}" for sid, seats in _saved("agentsociety_profiles.json")
                for seat in seats for p in dm.room_seat_problems(seat, check_persona=False)]
    assert not problems, "\n".join(problems[:20])


def test_saved_seats_name_real_groups():
    from app.services.panel_service import SEGMENTS
    unknown = {seat["segment_id"] for _sid, seats in _saved("agentsociety_profiles.json")
               for seat in seats if "segment_id" in seat} - set(SEGMENTS)
    assert not unknown


# ── a room built now ───────────────────────────────────────────────────────

@pytest.fixture
def new_room(tmp_path, monkeypatch):
    if not os.path.exists(LIBRARY):
        pytest.skip("persona library not built in this environment")
    from app.services import panel_service as ps
    warnings = []
    monkeypatch.setattr(ps, "_base_dir", lambda: str(tmp_path))
    monkeypatch.setattr(ps.logger, "warning", lambda msg, *a: warnings.append(msg % a if a else msg))
    # "panel" is the only mode the API sends now (api/panel.py create_session).
    meta = ps.create_session("A homework help app for R200 a month", mode="panel",
                             n=6, seed=1, segments=["guardians"])
    return ps, meta, tmp_path / meta["session_id"], warnings


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_a_new_room_fits_every_model(new_room):
    _ps, meta, sdir, warnings = new_room
    assert dm.model_problems("panel_session", _read(sdir / "panel_session.json")) == []
    assert dm.model_problems("panel_context", _read(sdir / "document_context.json")) == []
    seats = _read(sdir / "agentsociety_profiles.json")
    assert seats
    assert [p for seat in seats for p in dm.room_seat_problems(seat)] == []
    assert not [w for w in warnings if "data model" in w]


def test_adding_a_group_keeps_the_room_on_model(new_room):
    ps, meta, sdir, warnings = new_room
    ps.add_segment(meta["session_id"], "learners", seats=3)
    assert dm.model_problems("panel_session", _read(sdir / "panel_session.json")) == []
    seats = _read(sdir / "agentsociety_profiles.json")
    assert [p for seat in seats for p in dm.room_seat_problems(seat)] == []
    assert not [w for w in warnings if "data model" in w]


# ── the checker catches the mistakes it exists for ────────────────────────

def _meta(**change):
    meta = {"session_id": "panel_0123456789ab", "pitch": "A pitch", "mode": "panel",
            "segment": "everyone", "segment_label": "Everyone", "cast_size": 12,
            "requested_size": 12, "seed": 1, "province": None, "created_at": "2026-09-14",
            "rounds_run": 0, "archetype_distribution": {"learner": 12}, "province_distribution": {}}
    meta.update(change)
    return meta


def test_a_minimal_session_fits():
    assert dm.model_problems("panel_session", _meta()) == []


def test_an_unknown_mode_is_caught():
    assert any("'sale'" in p for p in dm.model_problems("panel_session", _meta(mode="sale")))


def test_a_filter_saved_without_its_pool_size_is_caught():
    problems = dm.model_problems("panel_session", _meta(budget_tier_filter=["loose"]))
    assert any("stored together" in p for p in problems)


def test_a_probe_with_an_unknown_confidence_is_caught():
    slots = {"probes": [{"id": "reaction", "label": "First reaction", "question": "?",
                         "active": True, "confidence": "maybe"}]}
    assert any("'maybe'" in p for p in dm.model_problems("panel_session", _meta(slots=slots)))


def test_a_seat_with_a_budget_the_app_never_computes_is_caught():
    seat = {"id": 0, "budget_tier": "rich"}
    assert any("'rich'" in p for p in dm.room_seat_problems(seat, check_persona=False))


def test_research_text_without_its_citations_is_caught():
    seat = {"id": 0, "research_context": "Cards"}
    assert any("stored together" in p for p in dm.room_seat_problems(seat, check_persona=False))


def test_a_library_seat_is_checked_against_the_persona_model():
    seat = {"id": 0, "library_id": "0123456789abcdef", "source_entity_type": "library_persona",
            "name": "Half a persona"}
    assert any("missing" in p for p in dm.room_seat_problems(seat))


def test_writing_warns_but_still_saves_an_off_model_file(tmp_path, monkeypatch):
    from app.services import panel_service as ps
    warnings = []
    monkeypatch.setattr(ps.logger, "warning", lambda msg, *a: warnings.append(msg % a if a else msg))
    path = str(tmp_path / "panel_session.json")
    ps._write_checked(path, _meta(mode="sale"), ps._meta_problems, "Panel session")
    assert os.path.exists(path)
    assert any("data model" in w for w in warnings)
