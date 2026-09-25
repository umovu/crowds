"""The readings checks catch bad readings. LLM-off: the model calls are stubbed.

A reading is only worth having if it stays inside what the paper said. These feed the
checks readings that invent a motive, state a purchase, cite the wrong quotes, carry a
figure, or all point the same way, and prove each one is caught.
"""
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "scripts")))

import extract_readings as er  # noqa: E402

PASSAGES = {
    "P1": "We have incentives. You will get a certain thing so she would set a certain target for herself.",
    "P2": "I try to set my own standards just to motivate her. When she targets sixty I target higher.",
    "P9": "I get from work late sometimes I find the child sleeping.",
}
CLAIM = {"chain_id": "C2", "passages": ["P1", "P2"],
         "text": "Parents set targets and incentives that trigger the child's own goal-setting."}
GOOD = {"text": "Someone who already sets targets and incentives would weigh a new offer by whether it "
                "keeps the child's own goal-setting.", "passages": ["P1", "P2"]}


def _flags(readings):
    return er.problems(readings, CLAIM, PASSAGES)


def test_a_reading_from_the_quotes_passes():
    other = {"text": "If a parent already sets the standards, they would see less need for a new offer "
                     "that sets targets for the child.", "passages": ["P2"]}
    assert _flags([GOOD, other]) == []


def test_an_invented_motive_is_caught():
    bad = {"text": "Someone who distrusts the price would wait for a discount at month end.", "passages": ["P1"]}
    assert any("which the finding and its quotes do not" in p for p in _flags([GOOD, bad]))


def test_a_purchase_decision_is_caught():
    bad = {"text": "Someone who sets targets would buy it straight away.", "passages": ["P1"]}
    assert any("purchase decision" in p for p in _flags([GOOD, bad]))


def test_quotes_from_another_finding_are_caught():
    bad = {"text": "Someone who sets targets would weigh a new offer by the time it takes.", "passages": ["P9"]}
    assert any("another finding" in p for p in _flags([GOOD, bad]))


def test_a_figure_is_caught():
    bad = {"text": "Someone who sets targets of sixty percent or 60 would weigh it.", "passages": ["P2"]}
    assert any("number" in p for p in _flags([GOOD, bad]))


def test_one_reading_is_not_enough():
    assert any("readings (want 2-4)" in p for p in _flags([GOOD]))


def test_a_reading_the_judge_says_adds_something_is_caught():
    labels = [{"i": 0, "follows": True, "direction": "open"},
              {"i": 1, "follows": False, "adds": "distrust of apps", "direction": "less"}]
    assert any("adds what the quotes do not say" in p for p in er.judge_problems(labels, CLAIM))


def test_readings_that_all_point_one_way_are_caught():
    labels = [{"i": 0, "follows": True, "direction": "open"}, {"i": 1, "follows": True, "direction": "open"}]
    assert any("same way" in p for p in er.judge_problems(labels, CLAIM))
    mixed = [{"i": 0, "follows": True, "direction": "open"}, {"i": 1, "follows": True, "direction": "less"}]
    assert er.judge_problems(mixed, CLAIM) == []


def test_a_failed_draft_is_redrafted_with_the_failures(monkeypatch):
    bad = [GOOD, {"text": "Someone would buy it.", "passages": ["P1"]}]
    fixed = [GOOD, {"text": "If a parent already sets the standards, they would see less need for a new "
                            "offer that sets targets.", "passages": ["P2"]}]
    drafts, feedback_seen = [bad, fixed], []

    def fake_draft(client, model, claim, passages, feedback=""):
        feedback_seen.append(feedback)
        return drafts.pop(0)

    monkeypatch.setattr(er, "draft", fake_draft)
    monkeypatch.setattr(er, "judge", lambda *a: [{"i": 0, "follows": True, "direction": "open"},
                                                 {"i": 1, "follows": True, "direction": "less"}])
    readings, _labels, issues = er.read_claim(None, None, CLAIM, PASSAGES)
    assert readings == fixed and issues == []
    assert feedback_seen[0] == "" and "purchase decision" in feedback_seen[1]
