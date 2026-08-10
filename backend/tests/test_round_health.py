"""Round-health rules — a failed interview must never read as an opinion.

Both rules here exist because a broken round used to render as a plausible one:
the per-agent fallback ("I have no comment on that.") looks like a considered
answer, and it carries the persona's starting stance, so failures were silently
counted as "did not move".

Everything asserted here is pure — no LLM, no network, no disk.
"""

import os

import pytest

# The engine raises at IMPORT time if no key is set, and importing it is
# unavoidable here (interview_service pulls in opinion_agent -> agentsociety2).
# A dummy satisfies the check; nothing in this file ever makes a call.
os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-key-not-used")
os.environ.setdefault("AGENTSOCIETY_NANO_LLM_API_KEY", "test-key-not-used")

from app.services.interview_service import (  # noqa: E402
    InterviewService,
    MIN_ANSWERED_SHARE,
    round_is_unusable,
)


# ── The refusal threshold ───────────────────────────────────────────────────

def test_full_round_is_usable():
    assert round_is_unusable(12, 12) is False


def test_one_failure_still_usable():
    """A short room is reported, not refused — the read still holds."""
    assert round_is_unusable(11, 12) is False


def test_exactly_at_threshold_is_usable():
    """8 of 12 is exactly 2/3 — the boundary counts as good enough."""
    assert round_is_unusable(8, 12) is False


def test_below_threshold_is_refused():
    assert round_is_unusable(7, 12) is True


def test_total_collapse_is_refused():
    assert round_is_unusable(0, 12) is True


def test_empty_cast_is_not_a_failure():
    """No seats booked is not a broken round; nothing was promised."""
    assert round_is_unusable(0, 0) is False


def test_threshold_is_two_thirds():
    assert MIN_ANSWERED_SHARE == pytest.approx(2 / 3)


# ── Dashboard counts are per ANSWERED person, not per seat ──────────────────

def _dashboard(results):
    """Call the aggregator without booting the service (no disk, no profiles)."""
    svc = object.__new__(InterviewService)
    return InterviewService._build_impact_dashboard(svc, results)


def _ok(agent_id, stance="support", changed=True):
    return {"agent_id": agent_id, "stance_after": stance, "stance_changed": changed,
            "impact_metadata": {}, "internal_state": {}}


def _failed(agent_id):
    return {"agent_id": agent_id, "error": "connection reset", "failed": True,
            "response": "I have no comment on that."}


def test_failures_are_excluded_from_counts():
    d = _dashboard([_ok(1), _ok(2), _failed(3)])
    assert d["answered"] == 2
    assert sum(d["stance_distribution"].values()) == 2


def test_failures_do_not_deflate_the_change_rate():
    """The bug this guards: 2 of 2 answered and both moved is 100%, not 66%.

    Dividing by the seat count made a broken round look like a calm one — the
    more interviews errored, the more settled the room appeared.
    """
    d = _dashboard([_ok(1), _ok(2), _failed(3)])
    assert d["stance_changed_count"] == 2
    assert d["stance_changed_rate"] == pytest.approx(1.0)


def test_all_failed_round_reports_nothing_rather_than_zeroes():
    d = _dashboard([_failed(1), _failed(2)])
    assert d["answered"] == 0
    assert d["stance_distribution"] == {}
    # No division by zero, and no invented "0% changed their mind".
    assert d["stance_changed_rate"] == 0
