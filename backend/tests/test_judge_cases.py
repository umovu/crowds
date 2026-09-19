"""The SA-context judge must keep catching bad blocks. Costs real LLM calls.

Skipped unless JUDGE_EVAL=1, because every case is one Plus-tier call — the rest
of the suite stays LLM-off. Run it by hand after touching the judge criteria:

    JUDGE_EVAL=1 python -m pytest tests/test_judge_cases.py

scripts/check_judge_cases.py prints which cases the judge missed.
"""

import importlib.util
import os

import pytest

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(BACKEND, "scripts", "check_judge_cases.py")

# Every bad block in the sheet must be caught: one bad block reaches every persona
# prompt for the day, so "mostly caught" is not good enough.
MIN_CAUGHT_SHARE = 1.0


@pytest.mark.skipif(os.environ.get("JUDGE_EVAL") != "1",
                    reason="costs a Plus-tier call per case; set JUDGE_EVAL=1 to run")
def test_the_judge_catches_bad_context_blocks():
    spec = importlib.util.spec_from_file_location("check_judge_cases", SCRIPT)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    caught, bad_total, wrong, good_total = checker.score()
    assert bad_total, "answer sheet has no bad blocks to catch"
    assert caught >= bad_total * MIN_CAUGHT_SHARE, (
        f"judge caught only {caught} of {bad_total} bad blocks; "
        "run scripts/check_judge_cases.py to see which")
    assert wrong == 0, f"judge wrongly failed {wrong} of {good_total} good blocks"
