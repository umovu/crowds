"""The founder's "who it's for" becomes a room of people who are ALL of it. LLM-off.

Picking three group chips seats anyone in any of the three. A described audience
("city workers without medical aid") is one group, so the room must be the people
who match every fact, and anything the library cannot match must be said out loud.
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(__file__)
BACKEND = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(BACKEND, "scripts"))
LIBRARY = os.path.join(BACKEND, "app", "data", "persona_library", "personas.json")

from app.services import audience_reader as ar  # noqa: E402

NTOMBI = ("These individuals live predominantly in urban provinces, earn between R7 500 and "
          "R30 000 per month, and are often younger workers or informal entrepreneurs who "
          "rely on pay-as-you-go healthcare.")


# ── reading the words ────────────────────────────────────────────────────────

def test_the_answer_sheet_passes_with_the_model_off():
    # Raise this if the sheet grows; never lower it to make a change pass.
    import check_audience_cases
    out = check_audience_cases.score(ar.read)
    failed = [r for r in out["rows"] if not r["ok"]]
    assert not failed, failed
    assert out["total"] >= 44 and out["held_out_total"] >= 12


def test_a_product_feature_is_not_read_as_the_buyer():
    got = ar.read("A nurse the same day for R150, with no queue and no medical aid needed.")
    assert got["facts"] == [] and got["provinces"] == []


def test_what_the_library_cannot_match_is_said_not_guessed():
    got = ar.read(NTOMBI)
    assert set(got["facts"]) == {"city", "working", "no_medical_aid", "young"}
    said = " ".join(got["unmatched"])
    assert "income" in said and "informal" in said


def test_a_narrower_fact_beats_the_broader_one_it_sits_inside():
    assert ar.read("Cover for homeowners paying off a bond.")["facts"] == ["bond"]


def test_an_age_range_reads_as_every_band_it_touches():
    assert ar.read("For renters aged 25-35.")["facts"] == ["renters", "age_25_34", "middle_aged"]


def test_an_unknown_fact_is_refused():
    with pytest.raises(ValueError):
        ar.rule(["billionaires"])


# ── matching people ──────────────────────────────────────────────────────────

def test_facts_on_different_fields_must_all_hold():
    person = {"geotype": "Urban", "employment_status": "Employed", "medical_aid": True, "age": 30}
    assert ar.matches(person, ar.rule(["city", "working"]))
    assert not ar.matches(person, ar.rule(["city", "working", "no_medical_aid"]))


def test_facts_on_the_same_field_are_either():
    renter = {"circumstances": [{"field": "housing_tenure", "value": "rent"}]}
    assert ar.matches(renter, ar.rule(["renters", "homeowners"]))


def test_a_fact_the_person_does_not_carry_does_not_match():
    assert not ar.matches({"geotype": "Urban"}, ar.rule(["no_medical_aid"]))


# ── the room ─────────────────────────────────────────────────────────────────

@pytest.fixture
def ps(tmp_path, monkeypatch):
    if not os.path.exists(LIBRARY):
        pytest.skip("persona library not built in this environment")
    from app.services import panel_service
    monkeypatch.setattr(panel_service, "_base_dir", lambda: str(tmp_path))
    return panel_service


def test_every_seat_is_all_of_the_audience(ps, tmp_path):
    facts = ["city", "working", "no_medical_aid"]
    meta = ps.create_session("A R150 nurse visit.", mode="panel", n=12, seed=3,
                             audience={"facts": facts})
    seats = json.load(open(tmp_path / meta["session_id"] / "agentsociety_profiles.json", encoding="utf-8"))
    by_id = {p["id"]: p for p in ps.get_library().all()}
    wanted = ar.rule(facts)
    assert len(seats) == 12
    assert all(ar.matches(by_id[s["library_id"]], wanted) for s in seats)
    assert meta["audience_pool_size"] == ar.count(facts) < len(by_id)
    assert meta["segment_label"] == "Lives in a city or town · Has a job · No medical aid"


def test_an_audience_nobody_is_says_so(ps):
    with pytest.raises(ValueError, match="No one in the library"):
        ps.create_session("A pitch.", mode="panel", n=12, seed=1,
                          audience={"facts": ["learners", "older"]})


def test_the_chip_shows_the_facts_and_the_count_instead_of_group_guesses():
    if not os.path.exists(LIBRARY):
        pytest.skip("persona library not built in this environment")
    from app.services import study_reader
    spec = study_reader.read_study("An app for working mothers in Joburg, R99 a month.")
    aud = spec["audience"]
    assert aud["facts"] == ["working", "women", "parents"] and aud["provinces"] == ["Gauteng"]
    assert aud["segments"] == []
    assert aud["count"] == ar.count(aud["facts"], aud["provinces"]) > 0


def test_a_described_audience_is_not_re_split_into_keyword_groups():
    from app.services import panel_session_service as pss
    pitch = "An app for teachers and parents."
    assert pss._audience({"audience": {"facts": ["working"]}}, "land", pitch) is None
    assert pss._audience({"audience": {"facts": ["working"]}, "segments": ["employed"]},
                         "land", pitch) == ["employed"]  # an explicit pick still wins


# ── the typed reader (stubbed: nothing calls a model) ────────────────────────

class _Stub:
    def __init__(self, yes=(), fail=False):
        self.yes, self.fail, self.reads = set(yes), fail, 0

    def enabled(self):
        return True

    def noul_question(self, instructions, when_true=None, when_false=None):
        return {"instructions": instructions}

    def ask(self, state, questions):
        if self.fail:
            raise RuntimeError("unreachable")
        self.reads += 1
        ids = list(ar.READER_DEFS)
        return {q: {"noul": 0.95 if ids[int(q.split("_")[1])] in self.yes else 0.0} for q in questions}


@pytest.fixture
def reader(monkeypatch):
    from app.utils import typesafe_client
    def on(stub):
        monkeypatch.setenv("FUB_TYPED_AUDIENCE", "1")
        monkeypatch.setattr(typesafe_client, "enabled", stub.enabled)
        monkeypatch.setattr(typesafe_client, "noul_question", stub.noul_question)
        monkeypatch.setattr(typesafe_client, "ask", stub.ask)
        ar._reader_memo.clear()
        return stub
    yield on
    ar._reader_memo.clear()


def test_every_fact_is_defined_for_the_reader():
    assert set(ar.READER_DEFS) == set(ar.OPTIONS)
    assert all(len(d) == 3 and all(d) for d in ar.READER_DEFS.values())


def test_the_reader_is_off_by_default():
    assert not ar.reader_enabled()


def test_the_reader_adds_a_wording_the_keywords_miss(reader):
    reader(_Stub(yes={"no_medical_aid"}))
    assert ar.read("For people who don't belong to any medical scheme.")["facts"] == ["no_medical_aid"]


def test_the_reader_cannot_remove_what_the_keywords_found(reader):
    reader(_Stub(yes=set()))
    assert ar.read("Car insurance for young drivers.")["facts"] == ["car_owners", "young"]


def test_a_failed_read_leaves_the_keywords(reader):
    reader(_Stub(fail=True))
    assert ar.read("A funeral policy for pensioners in rural Limpopo.")["facts"] == ["rural", "older"]


def test_a_text_is_read_once(reader):
    stub = reader(_Stub())
    for _ in range(5):
        ar.read("For people who hire rather than own the place they live in.")
    assert stub.reads == 1


def test_a_product_with_no_people_sentence_is_never_sent_to_the_reader(reader):
    stub = reader(_Stub(yes={"no_medical_aid"}))
    assert ar.read("A nurse the same day with no queue.")["facts"] == []
    assert stub.reads == 0


def test_a_fee_paying_room_seats_no_one_from_a_no_fee_school(ps, tmp_path):
    meta = ps.create_session("A R100 a month learning app.", mode="panel", n=12, seed=5,
                             audience={"facts": ["parents", "fee_paying"]})
    seats = json.load(open(tmp_path / meta["session_id"] / "agentsociety_profiles.json", encoding="utf-8"))
    by_id = {p["id"]: p for p in ps.get_library().all()}
    tiers = {ps._fee_tier(by_id[s["library_id"]]) for s in seats}
    assert tiers <= {"low_fee", "high_fee"}
