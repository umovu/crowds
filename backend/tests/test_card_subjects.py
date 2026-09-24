"""The typed reader widens which cards a pitch admits — it never narrows it.

Measured on the R150 clinic panel: the topic tags admitted four health cards and
dropped the phone-cost card, whose research is about what using a phone for
something costs the person doing it. The pitch opens "You book on WhatsApp".

These tests fix the shape of the help: a floor that cannot be lowered, a reader
that is off by default, a failure that costs nothing, and one read per room
rather than one per persona.

Everything here runs with the reader stubbed or off. Nothing calls a model.
"""
import pytest

from app.services import card_subjects as cs
from app.services import mechanism_card_service as mcs

PITCH = ("A private clinic chain wants to launch a R150 pay-per-visit nurse service. "
         "You book on WhatsApp and see a nurse the same day, with no queue.")

CLINIC = {"id": "clinic-card", "topic_tags": ["clinic", "nurse"],
          "claims": [{"text": "queues"}]}
PHONE = {"id": "phone-card", "topic_tags": ["phone", "airtime"],
         "subject": "what it costs someone to use their phone for something",
         "claims": [{"text": "data is rationed"}]}
FARM = {"id": "farm-card", "topic_tags": ["cattle", "grazing"],
        "claims": [{"text": "herds"}]}
CARDS = [CLINIC, PHONE, FARM]


@pytest.fixture(autouse=True)
def reader_off(monkeypatch):
    """Default state for every test: no key, no flag, no typed reads."""
    monkeypatch.delenv("FUB_TYPED_CARDS", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    cs.reset_memo()


class _Stub:
    """A typed reader that answers from a fixed table."""

    def __init__(self, probabilities, fail=False):
        self.probabilities = probabilities
        self.fail = fail
        self.reads = 0

    def enabled(self):
        return True

    def noul_question(self, instructions, when_true=None, when_false=None):
        return {"type": "noul", "instructions": instructions}

    def ask(self, state, questions):
        if self.fail:
            raise RuntimeError("reader unreachable")
        self.reads += 1
        return {k: {"noul": self.probabilities.get(k, 0.0)} for k in questions}


def _on(monkeypatch, stub):
    monkeypatch.setenv("FUB_TYPED_CARDS", "1")
    monkeypatch.setattr(cs, "_typesafe", lambda: stub)
    return stub


# ── The floor ────────────────────────────────────────────────────────────────

def test_reader_is_off_without_the_flag(monkeypatch):
    stub = _Stub({"phone-card": 1.0})
    monkeypatch.setattr(cs, "_typesafe", lambda: stub)  # key present, flag absent
    assert cs.read_cards(PITCH, CARDS) == set()
    assert stub.reads == 0


def test_reader_cannot_remove_a_card_the_tags_found(monkeypatch):
    # The reader is certain the clinic card is irrelevant. It does not matter:
    # the tags found it, and this module only ever adds.
    _on(monkeypatch, _Stub({"clinic-card": 0.0}))
    assert cs.widen(PITCH, CARDS, {"clinic-card"}) >= {"clinic-card"}


def test_a_failed_read_costs_nothing(monkeypatch):
    _on(monkeypatch, _Stub({}, fail=True))
    assert cs.widen(PITCH, CARDS, {"clinic-card"}) == {"clinic-card"}


def test_an_unsure_reader_adds_nothing(monkeypatch):
    _on(monkeypatch, _Stub({"phone-card": cs.MIN_PROBABILITY - 0.01}))
    assert cs.widen(PITCH, CARDS, {"clinic-card"}) == {"clinic-card"}


# ── The help ─────────────────────────────────────────────────────────────────

def test_reader_adds_a_card_the_tags_missed(monkeypatch):
    # "book on WhatsApp" never says phone, airtime or data.
    assert not mcs.topic_matches(PHONE, PITCH)
    _on(monkeypatch, _Stub({"phone-card": 0.83}))
    assert cs.widen(PITCH, CARDS, {"clinic-card"}) == {"clinic-card", "phone-card"}


def test_a_card_the_reader_rejects_stays_out(monkeypatch):
    _on(monkeypatch, _Stub({"phone-card": 0.83, "farm-card": 0.01}))
    assert "farm-card" not in cs.widen(PITCH, CARDS, {"clinic-card"})


def test_a_written_subject_is_what_the_reader_is_asked(monkeypatch):
    assert cs.describe(PHONE) == PHONE["subject"]
    assert cs.describe(CLINIC) == "clinic, nurse"  # no subject line: tags, weakly


# ── One read per room ────────────────────────────────────────────────────────

def test_the_same_pitch_is_read_once(monkeypatch):
    stub = _on(monkeypatch, _Stub({"phone-card": 0.9}))
    for _ in range(12):  # a room of twelve
        cs.read_cards(PITCH, CARDS)
    assert stub.reads == 1


def test_a_different_pitch_is_read_again(monkeypatch):
    stub = _on(monkeypatch, _Stub({"phone-card": 0.9}))
    cs.read_cards(PITCH, CARDS)
    cs.read_cards("Something else entirely about school fees.", CARDS)
    assert stub.reads == 2


# ── The wiring ───────────────────────────────────────────────────────────────

def _profile(*card_ids):
    return {"name": "Someone",
            "research_citations": [{"card_id": c} for c in card_ids]}


def test_cards_for_question_is_unchanged_with_the_reader_off(monkeypatch):
    monkeypatch.setattr(mcs, "_cache", CARDS)
    got = mcs.cards_for_question(_profile("clinic-card", "phone-card"), PITCH)
    assert [c["id"] for c in got] == ["clinic-card"]


def test_cards_for_question_admits_what_the_reader_added(monkeypatch):
    monkeypatch.setattr(mcs, "_cache", CARDS)
    _on(monkeypatch, _Stub({"phone-card": 0.9}))
    got = mcs.cards_for_question(_profile("clinic-card", "phone-card"), PITCH)
    assert sorted(c["id"] for c in got) == ["clinic-card", "phone-card"]


def test_a_room_reads_once_for_every_persona(monkeypatch):
    monkeypatch.setattr(mcs, "_cache", CARDS)
    stub = _on(monkeypatch, _Stub({"phone-card": 0.9}))
    touched = mcs.subjects_touched(PITCH, CARDS)
    for _ in range(12):
        mcs.cards_for_question(_profile("clinic-card", "phone-card"), PITCH,
                               touched=touched)
    assert stub.reads == 1


def test_an_unbound_card_is_never_admitted_by_the_reader(monkeypatch):
    # The reader is sure the farm card fits the pitch. The persona is not bound
    # to it, so it must still never reach their prompt.
    monkeypatch.setattr(mcs, "_cache", CARDS)
    _on(monkeypatch, _Stub({"farm-card": 1.0}))
    got = mcs.cards_for_question(_profile("clinic-card"), PITCH)
    assert [c["id"] for c in got] == ["clinic-card"]


# ── Claims with an `about` line ──────────────────────────────────────────────

SCOPED = {"id": "clinic-card", "topic_tags": ["clinic"],
          "claims": [{"chain_id": "C1", "text": "queues"},
                     {"chain_id": "C2", "text": "judged", "about": "sexual health",
                      "about_tags": ["contraception"]}]}


def test_claim_reader_is_off_without_the_flag(monkeypatch):
    stub = _Stub({"claim_0": 1.0})
    monkeypatch.setattr(cs, "_typesafe", lambda: stub)
    assert cs.read_claims(PITCH, [("clinic-card#C2", "sexual health")]) == set()
    assert stub.reads == 0


def test_claim_reader_adds_a_claim_the_words_missed(monkeypatch):
    _on(monkeypatch, _Stub({"claim_0": 0.9}))
    assert mcs.claims_touched("A clinic visit about starting a family.", [SCOPED]) \
        == {"clinic-card#C2"}


def test_a_claim_the_words_found_stays_whatever_the_reader_says(monkeypatch):
    _on(monkeypatch, _Stub({"claim_0": 0.0}))
    assert mcs.claims_touched("A clinic for contraception.", [SCOPED]) == {"clinic-card#C2"}


def test_a_failed_claim_read_leaves_the_words_to_decide(monkeypatch):
    _on(monkeypatch, _Stub({}, fail=True))
    assert mcs.claims_touched(PITCH, [SCOPED]) == set()


def test_the_same_pitch_reads_its_claims_once(monkeypatch):
    stub = _on(monkeypatch, _Stub({"claim_0": 0.9}))
    for _ in range(12):
        cs.read_claims(PITCH, [("clinic-card#C2", "sexual health")])
    assert stub.reads == 1
