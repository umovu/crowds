"""Card building stops before it spends past its cap. LLM-off: nothing is called.

Card building and the hosted product share one API wallet, so an extraction run must
not be able to empty it: each call is costed from the provider's token counts, and a
call that could take the ledger past CARD_SPEND_CAP_USD is refused before it is made.
"""
import os
import sys
import types
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
import extract_card as ec  # noqa: E402


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "SPEND_LEDGER", tmp_path / ".spend.json")
    monkeypatch.setattr(ec, "_peak", lambda now=None: False)
    return tmp_path / ".spend.json"


def _resp(prompt=1_000_000, cached=0, out=0):
    usage = types.SimpleNamespace(prompt_tokens=prompt, completion_tokens=out, prompt_cache_hit_tokens=cached)
    return types.SimpleNamespace(usage=usage)


def test_a_call_is_costed_from_its_tokens():
    assert ec.call_cost(1_000_000, 0, 0, peak=False) == pytest.approx(0.66)
    assert ec.call_cost(1_000_000, 1_000_000, 0, peak=False) == pytest.approx(0.022)
    assert ec.call_cost(0, 0, 1_000_000, peak=False) == pytest.approx(1.98)
    assert ec.call_cost(0, 0, 1_000_000, peak=True) == pytest.approx(3.96)


def test_peak_hours_are_weekday_utc_windows():
    assert ec._peak(datetime(2026, 9, 28, 7, tzinfo=timezone.utc))      # Monday 07:00
    assert not ec._peak(datetime(2026, 9, 28, 12, tzinfo=timezone.utc))  # Monday noon
    assert not ec._peak(datetime(2026, 9, 26, 7, tzinfo=timezone.utc))  # Saturday


def test_calls_add_up_in_the_ledger(ledger):
    ec._record(_resp(prompt=1_000_000))
    ec._record(_resp(prompt=0, out=1_000_000))
    led = ec.spent()
    assert led["usd"] == pytest.approx(2.64) and led["calls"] == 2


def test_a_call_that_could_pass_the_cap_is_refused(ledger, monkeypatch):
    monkeypatch.setenv("CARD_SPEND_CAP_USD", "0.70")
    ec._record(_resp(prompt=1_000_000))  # 0.66 spent
    with pytest.raises(ec.SpendCapReached):
        ec._check_cap("system", "user", max_tokens=100_000)  # could add ~0.20


def test_a_call_under_the_cap_goes_ahead(ledger, monkeypatch):
    monkeypatch.setenv("CARD_SPEND_CAP_USD", "0.70")
    ec._check_cap("system", "user", max_tokens=1_000)


def test_no_cap_set_means_no_limit(ledger, monkeypatch):
    monkeypatch.delenv("CARD_SPEND_CAP_USD", raising=False)
    ec._record(_resp(prompt=10_000_000))
    ec._check_cap("system", "user", max_tokens=100_000)
