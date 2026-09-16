"""Follow-up reports, posters, papers, caches, logs and what the screen receives fit
their models in app/data/model. LLM-off.
"""

import glob
import importlib.util
import json
import os
import re

import pytest

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
SESSIONS = os.path.join(BACKEND, "uploads", "panel_sessions")
LIBRARY = os.path.join(BACKEND, "app", "data", "persona_library", "personas.json")

_spec = importlib.util.spec_from_file_location(
    "data_model_for_report_tests", os.path.join(BACKEND, "app", "services", "data_model.py"))
dm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dm)


def _saved(pattern):
    files = glob.glob(pattern)
    if not files:
        pytest.skip(f"no saved {os.path.basename(pattern)}")
    for path in files:
        with open(path, encoding="utf-8") as fh:
            yield path, json.load(fh)


def _capture(monkeypatch, logger):
    warnings = []
    monkeypatch.setattr(logger, "warning", lambda msg, *a: warnings.append(msg % a if a else msg))
    return warnings


# ── follow-up report ───────────────────────────────────────────────────────

def test_saved_follow_up_reports_fit():
    problems = [p for _f, r in _saved(os.path.join(SESSIONS, "*", "hypothesis_report.json"))
                for p in dm.model_problems("hypothesis_report", r)]
    assert not problems, problems[:10]


def test_a_report_built_from_a_saved_session_fits():
    rounds = sorted(glob.glob(os.path.join(SESSIONS, "*", "rounds", "round_001.json")), key=os.path.getmtime)
    if not rounds or not os.path.exists(LIBRARY):
        pytest.skip("no saved panel rounds")
    from app.services import hypothesis_report as hr
    session_id = os.path.basename(os.path.dirname(os.path.dirname(rounds[-1])))
    report = hr.facts(session_id)
    report["hypotheses"] = hr._clean_hypotheses([
        {"claim": "Price is the wall, not trust.", "test": "Re-run with a monthly price."},
        {"claim": "60% would pay.", "test": "Ask again."},
    ])
    report["generated_at"] = "2026-09-14T10:00:00"
    assert dm.model_problems("hypothesis_report", report) == []
    assert len(report["hypotheses"]) == 1, "a hypothesis carrying a figure is dropped"


def test_building_warns_about_an_off_model_report(tmp_path, monkeypatch):
    from app.services import hypothesis_report as hr
    warnings = _capture(monkeypatch, hr.logger)
    monkeypatch.setattr(hr.panel_service, "get_session", lambda sid: {"session_id": sid})
    monkeypatch.setattr(hr.panel_service, "list_rounds", lambda sid, include_results=False: [])
    monkeypatch.setattr(hr.panel_service, "session_dir", lambda sid: str(tmp_path))
    monkeypatch.setattr(hr, "facts", lambda sid: {"session_id": sid, "mode": "sale"})
    hr.build("panel_0123456789ab", refresh=True)
    assert (tmp_path / hr.REPORT_FILE).exists()
    assert any("'sale'" in w for w in warnings)


# ── posters and papers ─────────────────────────────────────────────────────

class _Reader:
    def read(self, image_bytes, mime_type):
        return "A clinic poster: 'Same-day care, R150'."


def test_a_saved_and_read_poster_fits(tmp_path, monkeypatch):
    from app.services import poster_service
    monkeypatch.setattr(poster_service.Config, "POSTER_DATA_DIR", str(tmp_path), raising=False)
    record = poster_service.save_poster(b"\x89PNG fake", "image/png", "clinic.png")
    assert dm.model_problems("poster", record) == []
    record = poster_service.read_poster(record["poster_id"], reader=_Reader())
    assert dm.model_problems("poster", record) == []


def test_the_poster_model_matches_the_upload_rules():
    from app.services import poster_service
    fields = dm.load("poster")["fields"]
    assert fields["mime_type"]["allowed"] == list(poster_service.ALLOWED_MIME)
    assert fields["bytes"]["max"] == poster_service.MAX_BYTES


def test_saved_posters_fit():
    problems = [p for _f, r in _saved(os.path.join(BACKEND, "uploads", "posters", "*", "poster.json"))
                for p in dm.model_problems("poster", r)]
    assert not problems


def test_saved_local_papers_fit(tmp_path, monkeypatch):
    from app.services import literature_service as ls
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    service = ls.LiteratureSearchService()
    service._local_papers.append(ls.Paper(id="W1", title="Clinic choice", authors=["L. Chavalala"],
                                          year=2025, abstract="", source="openalex", url="https://x"))
    service._save_local_papers_metadata()
    with open(tmp_path / "research" / "papers" / "papers.json", encoding="utf-8") as fh:
        assert dm.model_problems("local_papers", json.load(fh)) == []


# ── caches and logs ────────────────────────────────────────────────────────

def test_the_sa_context_cache_fits(tmp_path, monkeypatch):
    from app.services import sa_context
    monkeypatch.setattr(sa_context, "_cache_path", lambda: str(tmp_path / "cache" / "sa_context.json"))
    sa_context._write_cache("- Unemployment is 33.6% [Q2 2026, news24.com]")
    with open(tmp_path / "cache" / "sa_context.json", encoding="utf-8") as fh:
        assert dm.model_problems("sa_context_cache", json.load(fh)) == []


def test_a_snapshot_the_formatter_reads_fits():
    from app.services import sa_context
    snapshot = {"as_of": "14 September 2026", "fetched_at": 1789000000.0,
                "claims": [{"text": "No load shedding since May 2025.", "date": "2026-09-01",
                            "source": "eskom.co.za", "scope": "national", "expires_at": None}]}
    assert dm.model_problems("sa_context_snapshot", snapshot) == []
    assert sa_context.format_snapshot(snapshot)


def test_saved_caches_fit():
    problems = [p for _f, c in _saved(os.path.join(BACKEND, "cache", "sa_context.json"))
                for p in dm.model_problems("sa_context_cache", c)]
    assert not problems


def test_a_judge_log_line_fits(tmp_path, monkeypatch):
    from app.services import judge_service as js
    monkeypatch.setattr(js.Config, "DATA_ROOT", str(tmp_path), raising=False)
    js.record_judgement("seed", js.JudgeResult(score=8, pass_=True, reasoning="ok", evidence="e"), run_id="sim_1")
    with open(tmp_path / "judge_log.jsonl", encoding="utf-8") as fh:
        assert dm.model_problems("judge_log_line", json.loads(fh.readline())) == []


def test_legacy_persona_cache_entries_fit_their_legacy_model():
    problems = [p for _f, e in _saved(os.path.join(BACKEND, "uploads", "persona_cache", "*.json"))
                for p in dm.model_problems("persona_cache_entry", e)]
    assert not problems
    assert dm.load("persona_cache_entry")["legacy"] is True


# ── what the screen receives ───────────────────────────────────────────────

def test_the_group_cards_fit():
    if not os.path.exists(LIBRARY):
        pytest.skip("persona library not built")
    from app.services import panel_service
    rows = panel_service.list_segments()
    assert rows
    assert [p for r in rows for p in dm.model_problems("api_segment", r, r["id"])] == []
    topics = {t["id"] for t in panel_service.SEGMENT_TOPICS}
    assert set(dm.load("api_segment")["fields"]["topics"]["items"]["allowed"]) == topics


def test_the_room_agent_list_fits(real_module):
    files = sorted(glob.glob(os.path.join(SESSIONS, "*", "agentsociety_profiles.json")), key=os.path.getmtime)
    if not files:
        pytest.skip("no saved rooms")
    InterviewService = real_module("app.services.interview_service").InterviewService
    service = InterviewService.__new__(InterviewService)
    with open(files[-1], encoding="utf-8") as fh:
        service.profiles = json.load(fh)
    service.sim_dir = os.path.join(BACKEND, "no-such-sim")
    agents = service.list_agents()
    assert agents
    assert [p for a in agents for p in dm.model_problems("api_agent_entry", a)] == []


def test_the_persona_picker_list_fits(real_module):
    if not os.path.exists(LIBRARY):
        pytest.skip("persona library not built")
    from flask import Flask
    # Borrowed through real_module: another test file leaves a stub app.controllers
    # in sys.modules that carries only `gates`.
    personas = real_module("app.controllers.persona_controller")
    with Flask("model-test").app_context():
        body = personas.list_personas().get_json()
    assert body["success"]
    assert [p for e in body["personas"] for p in dm.model_problems("api_persona_list_entry", e)] == []


# ── the checker catches the mistakes it exists for ────────────────────────

def test_an_unsupported_poster_type_is_caught():
    assert any("'image/gif'" in p for p in dm.model_problems("poster", {"mime_type": "image/gif"}))


def test_a_movement_direction_the_report_never_writes_is_caught():
    movement = {"people": [{"agent_id": 1, "name": "A", "from": "neutral", "to": "support",
                            "direction": "up", "round": 1}],
                "moved_count": 1, "warmer": 1, "cooler": 0, "answers_considered": 1}
    assert any("'up'" in p for p in dm.model_problems("hypothesis_report", {"movement": movement}))


def test_a_picker_row_with_an_unknown_level_is_caught():
    assert any("'guess'" in p for p in dm.model_problems("api_persona_list_entry", {"level": "guess"}))


def test_every_model_file_loads_and_names_where_it_lives():
    names = [os.path.basename(p)[:-5] for p in glob.glob(os.path.join(BACKEND, "app", "data", "model", "*.json"))]
    assert len(names) >= 48
    for name in names:
        model = dm.load(name)
        assert model.get("about"), name
        shaped = ("fields", "values", "tables", "answer_row")
        assert any(key in model for key in shaped), name
