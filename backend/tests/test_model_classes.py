"""The Python data models in app/model: the source of truth for their JSON files, they
build real objects from real data, and they refuse bad data. LLM-off.
"""

import glob
import json
import os
import subprocess
import sys

import pytest

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
LIBRARY = os.path.join(BACKEND, "app", "data", "persona_library", "personas.json")
SESSIONS = os.path.join(BACKEND, "uploads", "panel_sessions")


def _library():
    if not os.path.exists(LIBRARY):
        pytest.skip("persona library not built in this environment")
    with open(LIBRARY, encoding="utf-8") as fh:
        return json.load(fh)["personas"]


# ── the classes are the source of the JSON ─────────────────────────────────

def test_exported_json_matches_the_classes():
    from app.model import EXPORTS
    for name, export in EXPORTS.items():
        with open(os.path.join(BACKEND, "app", "data", "model", f"{name}.json"), encoding="utf-8") as fh:
            assert json.load(fh) == export(), f"app/data/model/{name}.json is stale: run scripts/export_data_models.py"


def test_every_model_file_comes_from_a_class():
    from app.model import EXPORTS
    files = {os.path.basename(p)[:-5] for p in glob.glob(os.path.join(BACKEND, "app", "data", "model", "*.json"))}
    assert files == set(EXPORTS), f"JSON-only models left: {sorted(files - set(EXPORTS))}"


def test_saved_panel_sessions_build_as_objects():
    from app.model.uploads import PanelContext, PanelSession
    files = glob.glob(os.path.join(SESSIONS, "*", "panel_session.json"))
    if not files:
        pytest.skip("no saved panel sessions")
    for path in files:
        with open(path, encoding="utf-8") as fh:
            session = PanelSession.model_validate(json.load(fh))
        assert session.session_id.startswith("panel_")
        with open(os.path.join(os.path.dirname(path), "document_context.json"), encoding="utf-8") as fh:
            assert PanelContext.model_validate(json.load(fh)).panel_session is True


def test_reference_files_build_as_objects():
    from app.model.reference import EventRules, GrantSchedule
    with open(os.path.join(BACKEND, "data", "sa_grant_amounts.json"), encoding="utf-8") as fh:
        grants = GrantSchedule.model_validate(json.load(fh))
    assert grants.grants["generic"].monthly_amount > 0
    with open(os.path.join(BACKEND, "app", "config", "event_rules.json"), encoding="utf-8") as fh:
        rules = EventRules.model_validate(json.load(fh))
    assert rules.rules[0].trigger.type


def test_the_export_script_reports_nothing_stale():
    result = subprocess.run([sys.executable, os.path.join("scripts", "export_data_models.py"), "--check"],
                            cwd=BACKEND, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


# ── real data builds real objects ──────────────────────────────────────────

def test_every_library_persona_builds_as_an_object():
    from app.model import LibraryPersona
    people = [LibraryPersona.model_validate(p) for p in _library()]
    assert len(people) == len(_library())
    first = people[0]
    assert first.attitudes and first.attitudes[0].topic
    assert first.circumstances and first.circumstances[0].field


def test_saved_rounds_build_as_objects():
    from app.model import RoundFile
    files = glob.glob(os.path.join(SESSIONS, "*", "rounds", "round_*.json"))
    if not files:
        pytest.skip("no saved panel rounds")
    for path in files:
        with open(path, encoding="utf-8") as fh:
            round_file = RoundFile.model_validate(json.load(fh))
        assert round_file.result.results is not None


def test_a_room_seat_builds_from_what_the_room_adds():
    from app.model import LibraryPersona, RoomSeat
    persona = _library()[0]
    seat = {"id": 0, "library_id": persona["id"], "stance": "neutral", "is_institutional": False,
            "country": "South Africa", "budget_tier": "moderate"}
    assert RoomSeat.model_validate(seat).budget_tier == "moderate"
    assert LibraryPersona.model_validate(persona).name == persona["name"]


# ── bad data is refused ─────────────────────────────────────────────────────

def test_a_wrong_answer_is_refused_when_building():
    from pydantic import ValidationError
    from app.model import LibraryPersona
    with pytest.raises(ValidationError):
        LibraryPersona.model_validate({**_library()[0], "geotype": "Rural"})


def test_rules_across_fields_are_enforced_when_building():
    from pydantic import ValidationError
    from app.model import AnswerRow
    with pytest.raises(ValidationError, match="only for failed"):
        AnswerRow.model_validate({"agent_id": 0, "response": "Yes", "original_question": "q",
                                  "stance_before": "neutral", "stance_after": "support",
                                  "stance_changed": True, "internal_state": {}, "impact_metadata": {},
                                  "reframed_question": "q", "agent_name": "A", "actor_archetype": None,
                                  "group_affiliation": None, "question_archetype": "general",
                                  "timestamp": "t", "failed": True})


def test_types_are_not_quietly_converted():
    from pydantic import ValidationError
    from app.model import RoomSeat
    with pytest.raises(ValidationError):
        RoomSeat.model_validate({"id": "5"})
    with pytest.raises(ValidationError):
        RoomSeat.model_validate({"id": 0, "is_institutional": 1})


def test_check_raises_in_strict_mode_and_logs_otherwise(monkeypatch):
    from app.model import DataModelError, RoomSeat, check
    bad = {"id": 0, "budget_tier": "rich"}
    monkeypatch.setenv("DATA_MODEL_STRICT", "1")
    with pytest.raises(DataModelError) as err:
        check(RoomSeat, bad, "seat 0")
    assert any("'rich'" in p for p in err.value.problems)

    monkeypatch.delenv("DATA_MODEL_STRICT")
    warnings = []

    class _Log:
        def warning(self, msg, *a):
            warnings.append(msg % a)

    assert check(RoomSeat, bad, "seat 0", _Log())
    assert any("'rich'" in w for w in warnings)


def test_panel_saves_refuse_off_model_data_in_strict_mode(tmp_path, monkeypatch):
    from app.model import DataModelError
    from app.services import panel_service as ps
    monkeypatch.setenv("DATA_MODEL_STRICT", "1")
    path = str(tmp_path / "panel_session.json")
    with pytest.raises(DataModelError):
        ps._write_checked(path, {"mode": "sale"}, ps._meta_problems, "Panel session")
    assert not os.path.exists(path), "strict mode refuses before anything is written"


def test_the_checker_uses_the_classes():
    import importlib.util
    spec = importlib.util.spec_from_file_location("dm_class_check", os.path.join(BACKEND, "app", "services", "data_model.py"))
    dm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dm)
    from app.model import LibraryPersona, problems_of
    bad = {**_library()[0], "geotype": "Rural"}
    assert dm.persona_problems(bad) == problems_of(LibraryPersona, bad, bad["name"])
