"""A pitch that names a place gets a room from that place — model off.

The bug this locks down: before metro existed, "a prepaid transport card for
commuters in Pretoria" seated three Western Cape people and two from Gauteng,
because place was a 1.5x weight multiplier on a library where Gauteng is 27%.
A multiplier cannot move a room that far; reserved seats can, and these tests
say so in numbers rather than in a comment.

Everything here runs with no model and no network: the gazetteer is a list and
the cast picker is arithmetic, which is the whole reason place lives in this
layer and not in a prompt.
"""
import collections

import pytest

from app.services.persona_library import get_library
from app.services.persona_retrieval import (MIN_METRO_POOL, PLACE_SHARE,
                                            derive_place, select_for_query,
                                            _metro_of)

SEATS = 12


@pytest.fixture(scope="module")
def library():
    return get_library()


def _room(query, seed=7):
    return select_for_query(SEATS, query, seed=seed)


# ── the gazetteer resolves places to what the surveys actually measured ──

@pytest.mark.parametrize("query,metro,province", [
    ("a transport card for commuters in Pretoria", "GP - City of Tshwane", "Gauteng"),
    ("a spaza delivery app for Sunnyside", "GP - City of Tshwane", "Gauteng"),
    ("a clinic booking service in Soweto", "GP - City of Johannesburg", "Gauteng"),
    ("a stokvel app in Khayelitsha", "WC - City of Cape Town", "Western Cape"),
    # Named, real, and in no metro: the province is the honest answer, and the
    # room must still be tilted rather than left national.
    ("a bakery in Upington", None, "Northern Cape"),
    ("a tutoring service in Mthatha", None, "Eastern Cape"),
    # No place named at all.
    ("a savings product for salaried workers", None, None),
])
def test_gazetteer_resolves_to_metro_or_province(query, metro, province):
    assert derive_place(query) == (metro, province)


def test_suburbs_do_not_invent_a_metro_of_their_own():
    """Local facts go suburb-deep; the cast stays metro-deep. A suburb must
    resolve to its metro, never to something finer the surveys never measured."""
    metro, _ = derive_place("a laundromat in Sunnyside")
    assert metro == "GP - City of Tshwane"
    assert all(_metro_of(p) != "Sunnyside" for p in get_library().all())


# ── the room actually comes from the place ──────────────────────────────

def test_metro_pitch_seats_mostly_that_metro():
    room = _room("a prepaid transport card for commuters in Pretoria")
    from_metro = sum(1 for p in room if _metro_of(p) == "GP - City of Tshwane")
    assert from_metro >= int(SEATS * PLACE_SHARE)


def test_metro_pitch_still_seats_outsiders():
    """Not a filter. The room needs someone who doesn't already care."""
    room = _room("a clinic booking service in Soweto")
    outsiders = [p for p in room if _metro_of(p) != "GP - City of Johannesburg"]
    assert outsiders, "a place-tilted room must keep a minority from elsewhere"


def test_province_pitch_seats_mostly_that_province():
    room = _room("a new water tariff in Limpopo")
    assert sum(1 for p in room if p["province"] == "Limpopo") >= int(SEATS * PLACE_SHARE)


def test_non_metro_town_falls_back_to_its_province():
    """Upington is real and in no metro. Before the fallback it got a room with
    no Northern Cape person in it at all."""
    room = _room("a bakery in Upington")
    assert any(p["province"] == "Northern Cape" for p in room)


def test_placeless_pitch_stays_a_cross_section():
    room = _room("a savings product for salaried workers")
    assert len({p["province"] for p in room}) >= 4


def test_pitch_never_seats_a_metro_outside_its_province():
    for query in ("a transport card in Pretoria", "a clinic in Soweto",
                  "a stokvel app in Khayelitsha"):
        for p in _room(query):
            metro = _metro_of(p)
            if metro:
                assert metro.split(" - ")[0] in _PREFIX[p["province"]]


_PREFIX = {"Western Cape": "WC", "Eastern Cape": "EC", "Northern Cape": "NC",
           "Free State": "FS", "KwaZulu-Natal": "KZN", "North West": "NW",
           "Gauteng": "GP", "Mpumalanga": "MP", "Limpopo": "LP"}


# ── the guards ──────────────────────────────────────────────────────────

def test_thin_metro_falls_back_instead_of_repeating_the_same_faces(library):
    """A metro the library barely covers cannot fill a room. Rather than seat
    the same handful every run, the focus widens to the province."""
    thin = [m for m, count in collections.Counter(
        _metro_of(p) for p in library.all()).items()
        if m and count < MIN_METRO_POOL]
    assert thin, "expected at least one thin metro in a 375-persona library"

    # Buffalo City is thin; an East London pitch must not be all Buffalo City.
    room = _room("a delivery service in East London")
    assert sum(1 for p in room if _metro_of(p) == "EC - Buffalo City") < SEATS


def test_room_is_deterministic_and_has_no_duplicate_names():
    query = "a transport card for commuters in Pretoria"
    first, second = _room(query), _room(query)
    assert [p["id"] for p in first] == [p["id"] for p in second]
    assert len({p["name"] for p in first}) == len(first)


def test_place_focus_survives_an_explicit_override():
    """An LLM query parser (or a panel filter) may pass the place directly."""
    room = select_for_query(SEATS, "a generic pitch with no place in it",
                            metro="GP - City of Tshwane", seed=7)
    from_metro = sum(1 for p in room if _metro_of(p) == "GP - City of Tshwane")
    assert from_metro >= int(SEATS * PLACE_SHARE)


# ── the honesty boundary ────────────────────────────────────────────────

def test_every_imputed_row_says_how_sure_it_is(library):
    """A placement that reads as a fact is the failure mode here. Every drawn
    row carries the pool it came from and that value's share of it."""
    for persona in library.all():
        for row in persona.get("circumstances") or []:
            if row.get("source") == "ghs_2025":
                assert row.get("pool", 0) >= 1
                assert 0.0 < row.get("share", 0) <= 1.0
