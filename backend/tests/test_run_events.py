"""LLM-off tests for the run-events privacy fence.

Run events exist so the operator can answer "is this user profitable", "how
often do runs fail", "did they come back". They must never let the operator
read what a user actually asked. The fence is `run_events.sanitize`: an
allow-list of scalar, length-capped fields.

These tests pin that boundary. They are the reason the promise ("the log
cannot hold your scenario") can be made out loud:

  * unknown keys are dropped, whatever they are called
  * long strings are cut far below the length of any real pitch or seed
  * non-scalars (dicts, lists, result objects) never pass
  * no allow-listed field is a free-text field

Loaded dependency-light (same shape as test_operator_context.py) so nothing
in the app package — or AgentSociety2 — is imported.
"""

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(__file__)
REPOS = os.path.normpath(os.path.join(HERE, "..", "app", "repositories"))


def _load():
    if "run_events_under_test" in sys.modules:
        return sys.modules["run_events_under_test"]
    spec = importlib.util.spec_from_file_location(
        "run_events_under_test", os.path.join(REPOS, "run_event_repository.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_events_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


run_events = _load()

PITCH = ("A prepaid data bundle for informal traders in Soweto at R49 a month, "
         "bundled with a free business listing and same-day SIM delivery.")


def test_unknown_keys_are_dropped():
    row = run_events.sanitize({
        "user_id": "u1",
        "pitch": PITCH,
        "seed": PITCH,
        "question": PITCH,
        "results": PITCH,
        "notes": PITCH,
    })
    assert row == {"user_id": "u1"}


def test_no_allowed_field_is_free_text():
    """Every allow-listed field is an id, a code, an enum or a number.

    If a future edit adds something like `pitch` or `summary` to the list,
    this fails — which is the intent. The list is the design.
    """
    assert run_events.ALLOWED_FIELDS == {
        "event", "run_id", "user_id", "run_type", "mode", "crowd_size",
        "duration_seconds", "status", "error_code", "model",
        "prompt_tokens", "completion_tokens", "total_tokens", "cost_usd",
    }


def test_long_values_are_capped_below_any_real_scenario():
    row = run_events.sanitize({"error_code": PITCH})
    assert len(row["error_code"]) == run_events.MAX_VALUE_LEN
    assert run_events.MAX_VALUE_LEN < len(PITCH)


def test_non_scalars_never_pass():
    row = run_events.sanitize({
        "run_id": "sim_1",
        "mode": {"pitch": PITCH},
        "status": [PITCH],
        "crowd_size": 12,
    })
    assert row == {"run_id": "sim_1", "crowd_size": 12}


def test_empty_and_none_values_are_ignored():
    assert run_events.sanitize({"mode": None, "status": "   "}) == {}
    assert run_events.sanitize({}) == {}


def test_record_writes_one_json_line_and_never_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setattr(run_events, "_ledger_path",
                        lambda: os.path.join(str(tmp_path), "run_events.jsonl"))

    run_events.record_start(run_id="p1", user_id="u1", run_type="panel",
                            mode="product", crowd_size=8, pitch=PITCH)
    run_events.record_end(run_id="p1", user_id="u1", run_type="panel",
                          status="ok", cost_usd=0.42, duration_seconds=31.5)

    lines = [json.loads(l) for l in
             open(os.path.join(str(tmp_path), "run_events.jsonl"), encoding="utf-8")
             if l.strip()]
    assert len(lines) == 2
    assert lines[0]["event"] == "start" and lines[0]["status"] == "started"
    assert lines[1]["event"] == "end" and lines[1]["cost_usd"] == 0.42
    # The pitch was passed in and must not appear anywhere in the file.
    assert all("pitch" not in row for row in lines)
    blob = open(os.path.join(str(tmp_path), "run_events.jsonl"), encoding="utf-8").read()
    assert "Soweto" not in blob


def test_totals_counts_ends_only(tmp_path, monkeypatch):
    path = os.path.join(str(tmp_path), "run_events.jsonl")
    monkeypatch.setattr(run_events, "_ledger_path", lambda: path)
    monkeypatch.delenv("SUPABASE_URL", raising=False)

    run_events.record_start(run_id="p1", user_id="u1", run_type="panel")
    run_events.record_end(run_id="p1", user_id="u1", status="ok", cost_usd=0.5,
                          total_tokens=100)
    run_events.record_end(run_id="p2", user_id="u1", status="failed",
                          error_code="round_failed", cost_usd=0.1, total_tokens=20)
    run_events.record_end(run_id="p3", user_id="u2", status="ok", cost_usd=9.0)

    mine = run_events.totals("u1")
    assert mine["runs"] == 2
    assert mine["failed"] == 1
    assert mine["total_tokens"] == 120
    assert mine["total_cost_usd"] == 0.6
