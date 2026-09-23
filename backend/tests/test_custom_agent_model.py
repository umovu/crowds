"""Custom agents and projects fit app/data/model/custom_agent.json and project.json. LLM-off.

Custom agents are the app's outside data: uploaded documents, JSON files and the manual
form, often parsed by a model. Projects store them. No project on disk holds an agent
yet, so the parser's own output is what these tests pin.
"""

import glob
import importlib.util
import json
import os

import pytest

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

_spec = importlib.util.spec_from_file_location(
    "data_model_for_agent_tests", os.path.join(BACKEND, "app", "services", "data_model.py"))
dm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dm)

FORM_AGENT = {
    "name": "Thandi Mokoena", "age": 42, "gender": "female", "occupation": "Spaza owner",
    "bio": "Runs a spaza shop in Soweto.", "background_story": "Opened the shop in 2015.",
    "stance": "concerned", "province": "Gauteng",
    "attitudes": [{"topic": "crime", "rating": 8, "description": "Worried about break-ins"}],
    "beliefs": "Crime is rising\nPolice come late",
    "needs": {"safety_physical": 70},
}
DOCUMENT = """# Agents
```json
[{"name": "Sipho Dube", "persona": "A taxi owner in Durban.", "age": 51, "stance": "oppose"},
 {"name": "Lindiwe Khumalo", "persona": "A nurse at a public clinic.", "age": 34}]
```
"""


def _parser():
    """No LLM client needed for the form and JSON paths."""
    from app.services.custom_agent_parser import CustomAgentParser
    return CustomAgentParser.__new__(CustomAgentParser)


def _stored(profiles):
    return [p.to_agentsociety_format() for p in profiles]


# ── what the parser writes ────────────────────────────────────────────────

def test_a_form_agent_fits_the_model():
    stored = _stored(_parser().parse_raw([FORM_AGENT]))
    # parse_raw only relabels types that do not already start with "custom", and
    # _dict_to_profile always sets "custom", so form agents are stored as "custom".
    assert stored[0]["source_entity_type"] == "custom"
    assert dm.model_problems("custom_agent", stored[0]) == []


def test_document_agents_fit_the_model():
    from app.services.custom_agent_parser import CustomAgentParser
    stored = _stored(CustomAgentParser._try_parse_json_block(DOCUMENT))
    assert [a["name"] for a in stored] == ["Sipho Dube", "Lindiwe Khumalo"]
    for agent in stored:
        assert dm.model_problems("custom_agent", agent) == []


# ── the checker catches the mistakes it exists for ────────────────────────

def _agent(**change):
    agent = _stored(_parser().parse_raw([FORM_AGENT]))[0]
    agent.update(change)
    return agent


def _flags(agent, text):
    return any(text in p for p in dm.model_problems("custom_agent", agent))


def test_a_stance_no_room_understands_is_caught():
    assert _flags(_agent(stance="angry"), "'angry'")


def test_an_attitude_rating_off_the_scale_is_caught():
    assert _flags(_agent(attitudes=[{"topic": "crime", "rating": 15, "description": ""}]), "above 10")


def test_a_story_long_enough_to_flood_a_prompt_is_caught():
    assert _flags(_agent(background_story="x" * 7000), "longer than 6000")


def test_a_custom_agent_posing_as_a_library_persona_is_caught():
    assert _flags(_agent(source_entity_type="library_persona"), "'library_persona'")


def test_a_nameless_agent_is_caught():
    assert _flags(_agent(name=""), "too short")


def test_the_parser_warns_but_keeps_an_off_model_agent(monkeypatch):
    from app.services import custom_agent_parser as cap
    warnings = []
    monkeypatch.setattr(cap.logger, "warning", lambda msg, *a: warnings.append(msg % a if a else msg))
    profiles = _parser().parse_raw([{"name": "Odd One", "stance": "angry"}])
    assert len(profiles) == 1
    assert any("Odd One" in w and "data model" in w for w in warnings)


# ── projects ───────────────────────────────────────────────────────────────

def _project(**change):
    from app.models.project import Project, ProjectStatus
    project = Project(project_id="proj_0123456789ab", name="Test", status=ProjectStatus.CREATED,
                      created_at="2026-09-14T10:00:00", updated_at="2026-09-14T10:00:00")
    for key, value in change.items():
        setattr(project, key, value)
    return project


def test_saved_projects_fit_the_model():
    files = glob.glob(os.path.join(BACKEND, "uploads", "projects", "*", "project.json"))
    if not files:
        pytest.skip("no saved projects in this checkout")
    problems = []
    for path in files:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        problems += dm.model_problems("project", data, data.get("project_id"))
    assert not problems, "\n".join(problems[:20])


def test_a_new_project_fits_the_model():
    assert dm.model_problems("project", _project().to_dict()) == []


def test_a_project_with_agents_and_papers_fits_the_model():
    from app.services.research_service import slim_paper
    paper = slim_paper({"id": "W123", "title": "Clinic choice in Limpopo", "authors": "L. Chavalala",
                        "year": 2025, "source": "openalex", "url": "https://example.org"})
    project = _project(custom_agents=_stored(_parser().parse_raw([FORM_AGENT])),
                       custom_agents_enabled=True, saved_papers=[paper])
    assert dm.model_problems("project", project.to_dict()) == []


def test_a_project_holding_a_broken_agent_is_caught():
    project = _project(custom_agents=[_agent(stance="angry")])
    assert any("'angry'" in p for p in dm.model_problems("project", project.to_dict()))


def test_an_unknown_project_status_is_caught():
    assert any("'done'" in p for p in dm.model_problems("project", _project(status="done").to_dict()))


def test_saving_warns_but_still_saves_an_off_model_project(tmp_path, monkeypatch, real_module):
    from app.models import project as project_module
    # Borrowed through real_module: test_sim_start_and_credits leaves a stub
    # app.repositories.project_repository in sys.modules that carries only `get`.
    repo = real_module("app.repositories.project_repository")
    warnings = []
    monkeypatch.setattr(repo, "PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr(project_module.logger, "warning", lambda msg, *a: warnings.append(msg % a if a else msg))
    (tmp_path / "proj_0123456789ab").mkdir()
    repo.save(_project(status="done"))
    assert (tmp_path / "proj_0123456789ab" / "project.json").exists()
    assert any("data model" in w for w in warnings)
