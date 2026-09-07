import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from backtest_panel import parse_answer
from sync_measured_beliefs import sync_person, _BELIEF_PHRASING


@pytest.mark.parametrize("label", ["Some of them", "Don't know/Haven't heard", "Refused", "strongly_agree"])
def test_complete_answer_labels(label):
    assert parse_answer("My view.\nANSWER: " + label.upper(), [label, "other"]) == label


@pytest.mark.parametrize("text", ["ANSWER: Some", "ANSWER: Some of them indeed", "ANSWER: Some of them\nmore text", "ANSWER: other\nANSWER: Some of them", "Nothing"])
def test_reject_ambiguous_or_incomplete_answers(text):
    assert parse_answer(text, ["Some of them", "other"]) is None


def test_belief_sync_preserves_identity_custom_text_and_measured_values():
    phrases = _BELIEF_PHRASING["gov_trust"]
    original = {"income": 123, "name": "Test", "attitudes": [{"topic": "gov_trust", "stance": "high"}],
                "beliefs": [phrases["low"], "My custom belief"], "background_story": "Unchanged"}
    updated = sync_person(original)
    assert updated["beliefs"] == [phrases["high"], "My custom belief"]
    assert {k:v for k,v in updated.items() if k != "beliefs"} == {k:v for k,v in original.items() if k != "beliefs"}
    assert original["beliefs"][0] == phrases["low"]
    assert sync_person(updated) == updated


def test_neutral_removes_stale_strong_belief():
    p = {"attitudes": [{"topic": "gov_trust", "stance": "mid"}],
         "beliefs": [_BELIEF_PHRASING["gov_trust"]["low"]]}
    assert sync_person(p)["beliefs"] == []


def test_prepare_reads_no_truth_and_builds_no_client(tmp_path, monkeypatch):
    import hashlib
    import backtest_panel as panel
    scripts = tmp_path / "scripts"
    out = scripts / "out"
    out.mkdir(parents=True)
    item = {"id":"test", "r9":"Q1", "r10":"Q1", "bucket":"held_out", "framing":"Test?", "answers":["Yes", "No"], "extremes":["Yes","No"]}
    raw = json.dumps({"items":[item]}).encode()
    (out / "r10_ask_scenarios.json").write_bytes(raw)
    (out / "r10_item_lock.json").write_text(json.dumps({"files":{"r10_ask_scenarios.json":hashlib.sha256(raw).hexdigest()}}))
    library = tmp_path / "app/data/persona_library"
    library.mkdir(parents=True)
    (library / "personas.json").write_text(json.dumps({"personas":[{},{}]}))
    monkeypatch.setattr(panel, "_HERE", str(scripts))
    def forbidden(*a, **kw):
        raise AssertionError("Truth/client forbidden during preparation")
    monkeypatch.setattr(panel, "ground_truth", forbidden)
    monkeypatch.setattr(panel, "_sim_client", forbidden)
    result = panel.prepare_r10(40)
    assert result["planned_requests"] == 2
    assert result["model_calls"] == 0
    assert not result["paid_run_ready"]
    (out / "r10_ask_scenarios.json").write_bytes(raw+b" ")
    with pytest.raises(ValueError, match="Frozen"):
        panel.prepare_r10(40)
