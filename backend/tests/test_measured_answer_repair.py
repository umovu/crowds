"""A persona is only told survey answers its own respondent gave.

LLM-off. Pins the per-row rule in scripts/repair_measured_answers.py.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from repair_measured_answers import identify, repaired_rows  # noqa: E402


def _donor(**kw):
    donor = {
        "respondent": "SAF0001",
        "attitudes": {"gov_trust": "low", "social_trust": "high"},
        "attitude_answers": {
            "gov_trust": {"question": "Q37A", "asked": "trust the President",
                          "answer": "Not at all", "answer_band": "low"},
            "social_trust": {"question": "Q86A", "asked": "most people can be trusted",
                             "answer": "A lot"},
        },
    }
    donor.update(kw)
    return donor


def _row(topic, stance, answer=None, quality="exact"):
    row = {"topic": topic, "stance": stance, "source": "afrobarometer_r9_sa",
           "match_quality": quality}
    if answer:
        row.update(measured_answer=answer, measured_question="Q", measured_asked="x")
    return row


def test_a_wrong_persons_answer_is_replaced_with_the_real_one():
    rows, stats = repaired_rows([_row("social_trust", "high", "Just a little")], _donor())
    assert rows[0]["measured_answer"] == "A lot"
    assert stats["answers_corrected"] == 1


def test_an_answer_from_a_different_band_is_removed_not_kept():
    rows, stats = repaired_rows([_row("social_trust", "low", "Just a little")], _donor())
    assert "measured_answer" not in rows[0]
    assert stats["answers_removed"] == 1


def test_a_population_draw_never_carries_a_literal_answer():
    rows, _ = repaired_rows([_row("gov_trust", "low", "Not at all", quality="population_draw")],
                            _donor())
    assert "measured_answer" not in rows[0]


def test_an_answer_pointing_the_opposite_way_to_the_band_is_refused():
    donor = _donor()
    donor["attitude_answers"]["gov_trust"]["answer_band"] = "high"
    rows, _ = repaired_rows([_row("gov_trust", "low")], donor)
    assert "measured_answer" not in rows[0]


def test_no_respondent_means_no_literal_answers():
    rows, stats = repaired_rows([_row("gov_trust", "low", "Not at all")], None)
    assert "measured_answer" not in rows[0]
    assert stats["answers_removed"] == 1


def test_stance_and_other_fields_are_untouched():
    before = _row("gov_trust", "low", "Somewhat")
    rows, _ = repaired_rows([before], _donor())
    assert {k: v for k, v in rows[0].items() if not k.startswith("measured_")} == \
        {k: v for k, v in before.items() if not k.startswith("measured_")}


def test_identify_needs_exactly_one_matching_respondent():
    person = {"attitudes": [_row("gov_trust", "low", "Not at all"),
                            _row("social_trust", "high", "A lot")]}
    assert identify(person, [_donor()])["respondent"] == "SAF0001"
    assert identify(person, [_donor(), _donor(respondent="SAF0002")]) is None
    assert identify({"attitudes": [_row("gov_trust", "low")]}, [_donor()]) is None
