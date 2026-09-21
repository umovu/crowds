"""The answer sheet's score, pinned.

`scripts/check_reaction_cases.py` scores the word reader against 42 hand-written
cases built on real library personas. This guards the number so the sheet cannot
quietly rot: a case that starts failing, a persona the library drops, or a cue
edit that trades one wall for another all move it.

LLM-free by construction — `score()` reads with the typed reader off, so this
runs offline and never bills.

The number is 28, not 42, and that is the point: the 14 failures are the measured
gap the typed reader exists to close (see `--typed`). Raise this when a rule fix
genuinely earns it; never by loosening a case.
"""

import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(BACKEND, "scripts"))

import check_reaction_cases  # noqa: E402


WORD_READER_PASSES = 28


def test_every_case_names_a_real_persona_and_at_least_one_wall():
    for case in check_reaction_cases.load_cases():
        assert check_reaction_cases._persona(case["persona"]) is not None, (
            f"{case['id']} names {case['persona']}, who is not in the library")
        assert case.get("want") or case.get("avoid"), (
            f"{case['id']} asserts nothing")


def test_word_reader_score_has_not_moved():
    passed, total = check_reaction_cases.score()
    assert total == 42, f"the sheet changed size: {total} cases"
    assert passed == WORD_READER_PASSES, (
        f"word reader now scores {passed}/{total}, pinned at {WORD_READER_PASSES}. "
        "If a rule fix earned this, update WORD_READER_PASSES.")


def test_the_typed_reader_stays_off_by_default():
    """The flag guards the network, so an unset environment must read offline."""
    from app.services import objections

    os.environ.pop("FUB_TYPED_WALLS", None)
    assert objections.typed_reading_enabled() is False
    assert objections.read_walls_typed(["anything at all"]) is None
