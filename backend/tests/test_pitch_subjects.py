"""The typed reader widens what a pitch is about — it never narrows it.

Measured on 19 realistic pitches, the word lists missed 5 of the 11 that had a
clear subject, and two of those were wrong rather than empty. The reader is
there for those. These tests fix the shape of the help: a floor that cannot be
lowered, a reader that is off by default, and a failure that costs nothing.

Everything here runs with the reader stubbed or off. Nothing calls a model.
"""
import pytest

from app.services import pitch_subjects as ps
from app.services.query_context import detect_subjects


@pytest.fixture(autouse=True)
def reader_off(monkeypatch):
    """Default state for every test: no key, no typed reads."""
    monkeypatch.delenv("FUB_TYPED_SUBJECTS", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)


class _Stub:
    """A typed reader that answers from a fixed table."""

    def __init__(self, probabilities, fail=False):
        self.probabilities = probabilities
        self.fail = fail
        self.asked = []

    def enabled(self):
        return True

    def noul_question(self, instructions, when_true=None, when_false=None):
        return {"type": "noul", "instructions": instructions}

    def ask(self, state, questions):
        if self.fail:
            raise RuntimeError("reader unreachable")
        self.asked.append(sorted(questions))
        return {k: {"noul": self.probabilities.get(k, 0.0)} for k in questions}


def _on(monkeypatch, stub):
    monkeypatch.setenv("FUB_TYPED_SUBJECTS", "1")
    monkeypatch.setattr(ps, "_typesafe", lambda: stub)


# ── off by default ──────────────────────────────────────────────────────

def test_the_reader_is_off_without_the_flag(monkeypatch):
    monkeypatch.setattr(ps, "_typesafe", lambda: _Stub({"power": 1.0}))
    assert not ps.typed_subjects_enabled()
    assert ps.read_subjects("a backup battery for when the lights go out") == set()


def test_the_flag_alone_is_not_enough_without_a_key(monkeypatch):
    monkeypatch.setenv("FUB_TYPED_SUBJECTS", "1")
    assert not ps.typed_subjects_enabled()


# ── it widens, never narrows ────────────────────────────────────────────

def test_the_keyword_answer_is_a_floor(monkeypatch):
    """The reader saying no must not remove a subject the words found."""
    _on(monkeypatch, _Stub({}))
    assert ps.subjects("a clinic booking app", {"health"}) == {"health"}


def test_the_reader_adds_what_the_words_missed(monkeypatch):
    _on(monkeypatch, _Stub({"power": 0.95}))
    assert ps.subjects("a backup battery for when the lights go out", set()) == {"power"}


def test_the_reader_corrects_a_wrong_answer_by_adding_the_right_one(monkeypatch):
    """"helping matriculants find their first pay cheque" reads as cost to the
    word list. The reader cannot delete cost, but it can add work, which is what
    the prompt and the search actually needed."""
    _on(monkeypatch, _Stub({"work": 0.9}))
    out = ps.subjects("helping matriculants find their first pay cheque", {"cost"})
    assert out == {"cost", "work"}


def test_an_unsure_reader_changes_nothing(monkeypatch):
    _on(monkeypatch, _Stub({"safety": ps.MIN_PROBABILITY - 0.01}))
    assert ps.subjects("an app for residents scared to walk home", set()) == set()


# ── it cannot invent, and it cannot break the caller ────────────────────

def test_the_reader_can_only_pick_from_the_vocabulary(monkeypatch):
    stub = _Stub({"health": 1.0, "housing": 1.0})
    _on(monkeypatch, stub)
    out = ps.read_subjects("a clinic pitch", vocabulary=["health", "housing"])
    assert out == {"health"}, "'housing' is not a subject this system has"
    assert "housing" not in stub.asked[0]


def test_a_failed_read_leaves_the_keyword_answer_alone(monkeypatch):
    _on(monkeypatch, _Stub({"power": 1.0}, fail=True))
    assert ps.subjects("a battery pitch", {"cost"}) == {"cost"}


def test_every_subject_is_asked_in_one_request(monkeypatch):
    """Questions share the state, so eight cost barely more than one. A caller
    that loops would pay eight times for the same thing."""
    stub = _Stub({})
    _on(monkeypatch, stub)
    ps.read_subjects("a pitch")
    assert len(stub.asked) == 1
    assert len(stub.asked[0]) == len(ps._SUBJECT_MEANINGS)


# ── the caller behaves the same as before when it is off ────────────────

def test_local_search_subjects_are_unchanged_with_the_reader_off():
    assert detect_subjects("a WhatsApp clinic booking service") == ["health"]
    assert detect_subjects("a backup battery for when the lights go out") == []


def test_local_search_picks_up_a_subject_the_reader_found(monkeypatch):
    _on(monkeypatch, _Stub({"power": 0.95}))
    assert detect_subjects("a backup battery for when the lights go out") == ["power"]


def test_local_search_still_caps_how_many_subjects_it_searches(monkeypatch):
    """Three searches per pitch, so at most two subjects — a reader that finds
    five must not turn one pitch into six searches."""
    _on(monkeypatch, _Stub({s: 0.99 for s in ps._SUBJECT_MEANINGS}))
    assert len(detect_subjects("a pitch about everything")) == 2
