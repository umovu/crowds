"""Affordability is derived from the pitch's own price — with the model off.

The whole point of `parse_price` / `price_to_tiers` is that money never depends
on an LLM re-reading the text. These tests assert that literally: they import
the pure functions and never touch a model.
"""
import pytest

from app.services.panel_service import (
    BUDGET_TIERS,
    parse_price,
    price_to_tiers,
    derive_budget_tiers,
)


@pytest.mark.parametrize("pitch, amount, monthly", [
    ("A home biodigester, R40 000 fitted", 40000, False),
    ("R40,000 installed", 40000, False),
    ("It costs R17000 once off", 17000, False),
    ("R199/month, cancel anytime", 199, True),
    ("R199 per month", 199, True),
    ("Only R899 p.m.", 899, True),
    ("R1 500 deposit then R250 pm", 1500, False),   # largest figure wins
])
def test_reads_the_price_out_of_the_pitch(pitch, amount, monthly):
    price = parse_price(pitch)
    assert price == {"amount": float(amount), "monthly": monthly}


@pytest.mark.parametrize("pitch", [
    "A free tool for spaza shops",
    "We help people compost at home",
    "",
])
def test_no_price_means_no_filter(pitch):
    assert parse_price(pitch) is None
    assert derive_budget_tiers(pitch) is None


def test_same_pitch_gives_the_same_answer_every_time():
    pitch = "R40 000 fitted, or R900 p.m. over four years"
    assert [parse_price(pitch) for _ in range(5)] == [parse_price(pitch)] * 5


def test_a_big_once_off_needs_the_top_tier():
    assert price_to_tiers(40000) == ["loose"]


def test_a_mid_once_off_excludes_only_the_tightest():
    assert price_to_tiers(5000) == ["moderate", "loose"]


def test_a_cheap_once_off_filters_nobody():
    assert price_to_tiers(300) == list(BUDGET_TIERS)
    assert derive_budget_tiers("Just R300 once off") is None


def test_monthly_bites_harder_than_once_off():
    # The same rand figure is a bigger ask when it recurs.
    assert price_to_tiers(900, monthly=True) == ["loose"]
    assert price_to_tiers(900, monthly=False) == list(BUDGET_TIERS)


def test_derive_reports_the_number_it_used():
    out = derive_budget_tiers("R40 000 fitted")
    assert out == {"amount": 40000.0, "monthly": False, "tiers": ["loose"]}


def test_tiers_are_always_a_contiguous_top_slice():
    # "Can afford" is a floor, never a band with a hole in it — otherwise the
    # filter would exclude people who can obviously pay.
    for amount in (100, 2000, 15000, 99999):
        for monthly in (False, True):
            tiers = price_to_tiers(amount, monthly)
            assert tiers == list(BUDGET_TIERS[len(BUDGET_TIERS) - len(tiers):])
