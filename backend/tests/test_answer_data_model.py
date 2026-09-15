"""Answer rows the real interview code writes, and rounds already saved, fit
app/data/model/answer.json. LLM-off: only the model call is replaced.

Why: the results screen, the follow-up report and the segment ranking all read these
rows by key name. A key written under one name and read under another (library
monthly_household_income_rand vs the room's monthly_income_rand) fails silently.
"""

import asyncio
import glob
import importlib.util
import json
import os

import pytest

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
BANK_PITCH = "A digital bank account with no monthly fees."

# By file path, and app.services only inside tests: importing that package while
# tests are collected pins SimulationRunner to the real data root before
# test_sim_start_and_credits points it at a temp one.
_spec = importlib.util.spec_from_file_location(
    "data_model_under_test", os.path.join(BACKEND, "app", "services", "data_model.py"))
dm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dm)

PROFILE = {
    "id": 0, "name": "Test Person", "age": 40, "gender": "Female", "province": "Gauteng",
    "occupation": "Clerks", "actor_archetype": "civic_moderate", "group_affiliation": "",
    "persona": "A clerk who lives in Soweto.", "library_id": "0123456789abcdef",
    "budget_tier": "moderate", "monthly_income_rand": 9000,
    "research_context": "STORED", "research_citations": [{"card_id": "fintech-adoption-trust"}],
}


def _real_interview_service():
    """The real module, even when test_sim_start_and_credits has left its stub in
    sys.modules. The stub is put back afterwards so that file keeps what it expects."""
    import importlib
    import sys
    name = "app.services.interview_service"
    current = sys.modules.get(name)
    if hasattr(getattr(current, "InterviewService", None), "_build_impact_dashboard"):
        return current
    sys.modules.pop(name, None)
    try:
        return importlib.import_module(name)
    finally:
        if current is not None:
            sys.modules[name] = current
            if "app.services" in sys.modules:
                setattr(sys.modules["app.services"], "interview_service", current)


def _run(reply, agent_ids=None):
    """The real batch_impact_interview and do_impact_interview on a one-seat room.

    Only the model call and the skill store are replaced. The agent is not a
    subclass: PersonAgent's read-only `id` and heavy construction get in the way
    (same approach as test_interview_failure_reporting).
    """
    from app.services import mechanism_card_service as mcs
    from app.services.opinion_agent import OpinionCitizenAgent
    InterviewService = _real_interview_service().InterviewService

    class _Agent:
        id = 0

        def __init__(self):
            self.init_state = {"stance": "neutral", "attitudes": {}}

        def set_skill_state(self, *_a, **_kw):
            pass

        async def answer_external_question(self, **_kw):
            if isinstance(reply, Exception):
                raise reply
            return reply

    for name, attr in vars(OpinionCitizenAgent).items():
        if not name.startswith("__") and not isinstance(attr, property) and name not in vars(_Agent):
            setattr(_Agent, name, attr)

    class _Service:
        simulation_id = "panel_test"
        mode = "panel"
        secondary_lens = None
        converged = False
        _is_panel = True
        profiles = [dict(PROFILE)]
        _build_impact_dashboard = InterviewService._build_impact_dashboard
        batch_impact_interview = InterviewService.batch_impact_interview

        def get_agent_profile(self, aid):
            return next((p for p in self.profiles if p["id"] == aid), None)

        def _create_agent(self, _profile):
            return _Agent()

    mcs._cache = None
    return asyncio.run(_Service().batch_impact_interview(BANK_PITCH, agent_ids=agent_ids))


def _answered_row():
    return _run("No monthly fee is good for me. I'd try it.\nSTANCE: support")["results"][0]


# ── rows the code writes ──────────────────────────────────────────────────

def test_an_answered_row_fits_the_model():
    row = _answered_row()
    assert "error" not in row, row.get("error")
    assert dm.answer_problems(row) == []


def test_research_cards_used_are_real_card_ids():
    from app.services import mechanism_card_service as mcs
    row = _answered_row()
    assert row["research_cards_used"] == ["fintech-adoption-trust"]
    assert set(row["research_cards_used"]) <= {c["id"] for c in mcs.load_cards()}


def test_a_failed_interview_row_fits_the_model():
    row = _run(RuntimeError("Error code: 401 - invalid api key"))["results"][0]
    assert row["failed"] is True
    assert dm.answer_problems(row) == []


def test_a_missing_seat_row_fits_the_model():
    row = _run("unused", agent_ids=[99])["results"][0]
    assert row["failed"] is True
    assert dm.answer_problems(row) == []


def test_the_saved_round_shape_fits_the_model():
    result = _run("I'd try it.\nSTANCE: support")
    round_file = {"round": 1, "timestamp": "2026-09-13T10:00:00", "pitch": BANK_PITCH,
                  "framed_pitch": BANK_PITCH, "agent_ids": None, "result": result}
    assert dm.round_problems(round_file) == []


# ── rounds already on disk ────────────────────────────────────────────────

def test_saved_rounds_fit_the_model():
    files = glob.glob(os.path.join(BACKEND, "uploads", "panel_sessions", "*", "rounds", "round_*.json"))
    if not files:
        pytest.skip("no saved panel rounds in this checkout")
    problems = []
    for path in files:
        with open(path, encoding="utf-8") as fh:
            problems += [f"{os.path.basename(os.path.dirname(os.path.dirname(path)))}: {p}"
                         for p in dm.round_problems(json.load(fh))]
    assert not problems, f"{len(problems)} problem(s):\n" + "\n".join(problems[:20])


# ── the checker catches the mistakes it exists for ────────────────────────

def test_the_library_income_name_on_a_row_is_caught():
    row = _answered_row()
    row["monthly_household_income_rand"] = 9000
    assert any("monthly_household_income_rand" in p for p in dm.answer_problems(row))


def test_a_failed_flag_without_an_error_is_caught():
    row = _answered_row()
    row["failed"] = True
    assert any("only for failed" in p for p in dm.answer_problems(row))


def test_an_unknown_stance_is_caught():
    row = _answered_row()
    row["stance_after"] = "interested"
    assert any("'interested'" in p for p in dm.answer_problems(row))


def test_a_money_tier_the_app_never_computes_is_caught():
    row = _answered_row()
    row["budget_tier"] = "rich"
    assert any("'rich'" in p for p in dm.answer_problems(row))


# ── the app says so when a round drifts ───────────────────────────────────

def test_save_round_warns_but_still_saves_a_drifted_round(tmp_path, monkeypatch):
    from app.services import panel_service as ps
    warnings = []
    monkeypatch.setattr(ps, "session_dir", lambda _sid: str(tmp_path))
    monkeypatch.setattr(ps, "write_session_report", lambda _sid: None)
    monkeypatch.setattr(ps.logger, "warning", lambda msg, *a: warnings.append(msg % a if a else msg))
    result = _run("I'd try it.\nSTANCE: support")
    result["results"][0]["monthly_household_income_rand"] = 9000
    n = ps.save_round("panel_test", {"pitch": BANK_PITCH, "framed_pitch": BANK_PITCH,
                                     "agent_ids": None, "result": result})
    assert os.path.exists(tmp_path / "rounds" / f"round_{n:03d}.json")
    assert any("answer model" in w for w in warnings)
