"""The room picker must not get worse on the answer sheet. LLM-off.

tests/data/cast_cases.json says who belongs in the room for each pitch;
scripts/check_cast_cases.py scores it. Run the script to see which cases fail.
Raise BASELINE when a change lifts the score; never lower it to make a change pass.
"""

import importlib.util
import os

import pytest

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
LIBRARY = os.path.join(BACKEND, "app", "data", "persona_library", "personas.json")
SCRIPT = os.path.join(BACKEND, "scripts", "check_cast_cases.py")

BASELINE = 20


def test_room_picker_score_does_not_drop():
    if not os.path.exists(LIBRARY):
        pytest.skip("persona library not built in this environment")
    spec = importlib.util.spec_from_file_location("check_cast_cases", SCRIPT)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    passed, total = checker.score()
    assert passed >= BASELINE, (
        f"room picker scored {passed} of {total}, below {BASELINE}; "
        "run scripts/check_cast_cases.py to see which cases broke")
