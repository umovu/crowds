"""Simulation files fit their models in app/data/model (sim_*, ipc_*, report_*). LLM-off.

Sims are the paid tier: state.json holds the billing guard (credit_charged), the action
log holds token cost, and the app and the sim subprocess talk only through these files.
"""

import glob
import importlib.util
import json
import os
import re
import types

import pytest

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
SIMS = os.path.join(BACKEND, "uploads", "simulations")
REPORTS = os.path.join(BACKEND, "uploads", "reports")

_spec = importlib.util.spec_from_file_location(
    "data_model_for_sim_tests", os.path.join(BACKEND, "app", "services", "data_model.py"))
dm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dm)


def _source(rel):
    with open(os.path.join(BACKEND, *rel.split("/")), encoding="utf-8") as fh:
        return fh.read()


def _saved_json(pattern):
    files = glob.glob(pattern)
    if not files:
        pytest.skip(f"no saved files for {os.path.basename(pattern)}")
    for path in files:
        with open(path, encoding="utf-8") as fh:
            yield path, json.load(fh)


def _saved_lines(pattern):
    files = glob.glob(pattern)
    if not files:
        pytest.skip(f"no saved files for {os.path.basename(pattern)}")
    for path in files:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield path, json.loads(line)


# ── saved files ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,pattern", [
    ("sim_state", "*/state.json"),
    ("sim_config", "*/simulation_config.json"),
    ("sim_run_state", "*/run_state.json"),
    ("sim_env_status", "*/env_status.json"),
    ("ipc_response", "*/ipc_responses/*.json"),
    ("ipc_command", "*/ipc_commands/*.json"),
    ("sim_document_context", "*/document_context.json"),
    ("sim_enrichment", "*/enrichment.json"),
])
def test_saved_simulation_files_fit(name, pattern):
    problems = [f"{p}: {x}" for p, obj in _saved_json(os.path.join(SIMS, pattern))
                for x in dm.model_problems(name, obj)]
    assert not problems, "\n".join(problems[:20])


def test_saved_action_logs_fit():
    problems = [x for _p, line in _saved_lines(os.path.join(SIMS, "*", "opinion_space", "actions.jsonl"))
                for x in dm.action_line_problems(line)]
    assert not problems, "\n".join(problems[:20])


@pytest.mark.parametrize("name,file_name", [("sim_replay_db", "replay.db"),
                                            ("sim_opinion_db", "opinion_simulation.db")])
def test_saved_databases_fit(name, file_name):
    files = glob.glob(os.path.join(SIMS, "*", "opinion_space", file_name))
    if not files:
        pytest.skip(f"no saved {file_name}")
    problems = [x for path in files for x in dm.sqlite_problems(name, path)]
    assert not problems, "\n".join(problems[:20])


def test_saved_sim_casts_have_valid_room_fields():
    problems = [x for _p, seats in _saved_json(os.path.join(SIMS, "*", "agentsociety_profiles.json"))
                for seat in seats for x in dm.room_seat_problems(seat, check_persona=False)]
    assert not problems, "\n".join(problems[:20])


@pytest.mark.parametrize("name,pattern", [("sim_report", "*/meta.json"),
                                          ("sim_report_outline", "*/outline.json"),
                                          ("sim_report_progress", "*/progress.json")])
def test_saved_reports_fit(name, pattern):
    problems = [f"{p}: {x}" for p, obj in _saved_json(os.path.join(REPORTS, pattern))
                for x in dm.model_problems(name, obj)]
    assert not problems, "\n".join(problems[:20])


def test_saved_report_logs_fit():
    problems = [x for _p, line in _saved_lines(os.path.join(REPORTS, "*", "agent_log.jsonl"))
                for x in dm.model_problems("report_log_line", line)]
    assert not problems, "\n".join(problems[:20])


# ── what the code writes ───────────────────────────────────────────────────

def test_a_simulation_state_fits():
    from app.services.simulation_manager import SimulationState
    state = SimulationState(simulation_id="sim_0123456789ab", project_id="proj_0123456789ab",
                            graph_id="graph_1", user_id="0f8fad5b-d9cb-469f-a165-70867728950e",
                            credit_charged=True)
    assert dm.model_problems("sim_state", state.to_dict()) == []


def test_a_run_state_with_actions_fits():
    from app.services.simulation_runner import AgentAction, RunnerStatus, SimulationRunState
    state = SimulationRunState(simulation_id="sim_0123456789ab", runner_status=RunnerStatus.RUNNING,
                               total_rounds=10, current_round=3, process_pid=4242)
    state.add_action(AgentAction(round_num=3, timestamp="2026-09-14T10:00:00", platform="opinion_space",
                                 agent_id=1, agent_name="Thandi", action_type="EXPRESS_OPINION",
                                 action_args={"content": "Too expensive", "topics": ["price"]},
                                 prompt_tokens=120, completion_tokens=40, estimated_cost_usd=0.0004))
    assert dm.model_problems("sim_run_state", state.to_detail_dict()) == []


def test_a_generated_config_fits():
    from app.services.simulation_config_generator import AgentActivityConfig, SimulationParameters
    params = SimulationParameters(simulation_id="sim_0123456789ab", project_id="proj_0123456789ab",
                                  graph_id="graph_1", simulation_requirement="A clinic pitch",
                                  llm_model="deepseek-v4-flash", llm_base_url="https://api.example.com")
    params.agent_configs.append(AgentActivityConfig(agent_id=0, entity_uuid="", entity_name="Thandi",
                                                    entity_type="library_persona"))
    assert dm.model_problems("sim_config", params.to_dict()) == []


def test_ipc_files_fit_and_enums_match_the_models():
    from app.services.simulation_ipc import CommandStatus, CommandType, IPCCommand, IPCResponse
    for command_type in CommandType:
        cmd = IPCCommand(command_id="c1", command_type=command_type, args={"agent_id": 1})
        assert dm.model_problems("ipc_command", cmd.to_dict()) == []
    for status in CommandStatus:
        resp = IPCResponse(command_id="c1", status=status, result={"ok": True})
        assert dm.model_problems("ipc_response", resp.to_dict()) == []
    assert dm.load("ipc_command")["fields"]["command_type"]["allowed"] == [c.value for c in CommandType]


def test_status_lists_match_the_code():
    from app.services.report_agent import ReportStatus
    from app.services.simulation_manager import SimulationStatus
    from app.services.simulation_runner import RunnerStatus
    assert dm.load("sim_state")["fields"]["status"]["allowed"] == [s.value for s in SimulationStatus]
    assert dm.load("sim_run_state")["fields"]["runner_status"]["allowed"] == [s.value for s in RunnerStatus]
    assert dm.load("sim_report")["fields"]["status"]["allowed"] == [s.value for s in ReportStatus]
    used = set(re.findall(r'update_progress\(\s*report_id,\s*"(\w+)"', _source("app/services/report_agent.py")))
    assert used and used <= set(dm.load("sim_report_progress")["fields"]["status"]["allowed"])


def test_the_action_log_writer_fits(tmp_path):
    from app.services.agentsociety_output_writer import AgentSocietyOutputWriter
    writer = AgentSocietyOutputWriter(str(tmp_path))
    writer.write_action(1, 0, "Thandi", {"action_type": "RESPOND_TO_OPINION", "reason": "r",
                                         "action_args": {"target_opinion_id": 3, "content": "No"},
                                         "prompt_tokens": 90, "completion_tokens": 30})
    writer.write_round_end(1, 0.5)
    writer.write_simulation_end(1, {"model": "deepseek-v4-flash", "total_tokens": 120})
    with open(tmp_path / "actions.jsonl", encoding="utf-8") as fh:
        lines = [json.loads(line) for line in fh]
    assert len(lines) == 3
    assert [x for line in lines for x in dm.action_line_problems(line)] == []


def test_the_sim_subprocess_heartbeat_keys_are_in_the_model():
    source = _source("scripts/run_simulation_as.py")
    keys = set()
    for block in re.findall(r"update_status\(\s*\"\w+\",\s*\{(.*?)\}\)", source, re.S):
        keys |= set(re.findall(r'"(\w+)"\s*:', block))
    assert keys and keys <= set(dm.load("sim_env_status")["fields"])


def test_a_new_replay_database_fits(tmp_path):
    from app.services.replay_storage import ReplayStorage
    path = str(tmp_path / "replay.db")
    ReplayStorage(path)
    assert dm.sqlite_problems("sim_replay_db", path) == []


@pytest.mark.parametrize("rel,name", [("app/services/replay_storage.py", "sim_replay_db"),
                                      ("app/services/agentsociety_opinion_block.py", "sim_opinion_db")])
def test_database_code_only_writes_model_columns(rel, name):
    tables = dm.load(name)["tables"]
    source = _source(rel)
    created = dict(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\s*\);", source, re.S))
    for table, body in created.items():
        columns = [line.strip().split()[0] for line in body.splitlines()
                   if re.match(r"\s*[a-z_]+\s+[A-Z]", line)]
        assert sorted(columns) == sorted(tables[table]), table
    for table, cols in re.findall(r"INSERT (?:OR \w+ )?INTO (\w+)\s*\(?[\"\s]*\(([^)]*)\)", source):
        written = [c.strip() for c in cols.replace('"', "").split(",") if c.strip()]
        assert set(written) <= set(tables[table]), (table, set(written) - set(tables[table]))


def test_a_report_and_its_progress_fit(tmp_path, monkeypatch):
    from app.services.report_agent import (Report, ReportManager, ReportOutline, ReportSection,
                                           ReportStatus)
    outline = ReportOutline(title="Clinic pitch", summary="Mostly wary",
                            sections=[ReportSection(title="Money", content="Tight budgets")])
    report = Report(report_id="report_0123456789ab", simulation_id="sim_0123456789ab", graph_id="g",
                    simulation_requirement="A clinic pitch", status=ReportStatus.COMPLETED,
                    outline=outline, markdown_content="# Clinic", created_at="t", completed_at="t")
    assert dm.model_problems("sim_report", report.to_dict()) == []
    monkeypatch.setattr(ReportManager, "_ensure_report_folder", classmethod(lambda cls, rid: None))
    monkeypatch.setattr(ReportManager, "_get_progress_path", classmethod(lambda cls, rid: str(tmp_path / "p.json")))
    ReportManager.update_progress("report_0123456789ab", "failed", -1, "failed", completed_sections=["Money"])
    with open(tmp_path / "p.json", encoding="utf-8") as fh:
        assert dm.model_problems("sim_report_progress", json.load(fh)) == []


def test_a_report_log_line_fits(tmp_path):
    from datetime import datetime
    from app.services.report_agent import ReportLogger
    log = ReportLogger.__new__(ReportLogger)
    log.report_id, log.log_file_path, log.start_time = "report_1", str(tmp_path / "agent_log.jsonl"), datetime.now()
    log.log_planning_start()
    with open(tmp_path / "agent_log.jsonl", encoding="utf-8") as fh:
        assert dm.model_problems("report_log_line", json.loads(fh.readline())) == []


# ── the checker catches the mistakes it exists for ────────────────────────

def test_an_unknown_sim_status_is_caught():
    assert any("'done'" in p for p in dm.model_problems("sim_state", {"status": "done"}))


def test_an_unknown_action_type_is_caught():
    assert any("'SHOUT'" in p for p in dm.action_line_problems({"action_type": "SHOUT"}))


def test_a_database_missing_a_column_is_caught(tmp_path):
    import sqlite3
    path = str(tmp_path / "replay.db")
    con = sqlite3.connect(path)
    con.execute("create table simulation_meta (simulation_id text)")
    con.close()
    problems = dm.sqlite_problems("sim_replay_db", path)
    assert any("missing column 'started_at'" in p for p in problems)
    assert any("missing table 'opinion_actions'" in p for p in problems)


def test_heartbeat_status_stays_open():
    """CLAUDE.md: readers accept alive/running/paused; the model must not tighten it."""
    assert "allowed" not in dm.load("sim_env_status")["fields"]["status"]
    assert dm.model_problems("sim_env_status", {"status": "alive", "timestamp": "t"}) == []


# ── the app says so ───────────────────────────────────────────────────────

def test_saving_a_simulation_state_warns_but_still_saves(tmp_path, monkeypatch):
    from app.services import simulation_manager as sm
    warnings = []
    monkeypatch.setattr(sm.logger, "warning", lambda msg, *a: warnings.append(msg % a if a else msg))
    monkeypatch.setattr(sm.SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path), raising=False)
    manager = sm.SimulationManager.__new__(sm.SimulationManager)
    manager._simulations = {}
    state = sm.SimulationState(simulation_id="sim_x", project_id="p", graph_id="g")
    state.status = types.SimpleNamespace(value="done")
    manager._save_simulation_state(state)
    assert (tmp_path / "sim_x" / "state.json").exists()
    assert any("'done'" in w for w in warnings)


def test_the_action_log_writer_warns_once_per_run(tmp_path, monkeypatch):
    import logging
    from app.services.agentsociety_output_writer import AgentSocietyOutputWriter
    warnings = []
    monkeypatch.setattr(logging.getLogger("fub.agentsociety_output_writer"), "warning",
                        lambda msg, *a: warnings.append(msg % a if a else msg))
    writer = AgentSocietyOutputWriter(str(tmp_path))
    writer.write_action(1, 0, "A", {"action_type": "SHOUT"})
    writer.write_action(1, 1, "B", {"action_type": "SHOUT"})
    assert len(warnings) == 1
    with open(tmp_path / "actions.jsonl", encoding="utf-8") as fh:
        assert len(fh.readlines()) == 2
