"""Reproduction gate for the objection classifier.

The plan (local-plans/BENCHMARK_EXECUTION_PLAN.md, phase 0.2) requires the
shipped classifier to reproduce the published segment-contrast table. If this
fails, the classifier is wrong, not the report.

Asserted exactly: the three headline rows. The rest of the table is recorded but
allowed to drift with the vocab.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from classify_objections import extract_interviews, per_cast_percentages

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "..", "local-plans",
                       "benchmark-runs", "fixtures", "tymebank_segment_54.json")

HEADLINE_ROWS = {
    "no_human_support": {"tight": 50, "loose": 93, "grant": 60},
    "digital_capability": {"tight": 80, "loose": 50, "grant": 90},
    "identity_biometric": {"tight": 45, "loose": 43, "grant": 20},
}


def test_fixture_has_54_interviews():
    records = extract_interviews(FIXTURE)
    assert len(records) == 54


def test_classifier_reproduces_published_table():
    records = extract_interviews(FIXTURE)
    table = per_cast_percentages(records)
    for otype, expected in HEADLINE_ROWS.items():
        got = {cast: table[cast][otype] for cast in ("tight", "loose", "grant")}
        assert got == expected, (
            f"{otype} reproduced {got} but the report says {expected}")
