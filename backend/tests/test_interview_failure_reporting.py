"""A collapsed interview round must report itself as failed — LLM off.

Regression test for a real incident. When every interview errored (expired key /
wrong base_url), `do_impact_interview` returned its fallback with the error nested
under `impact_metadata`, while `batch_impact_interview` counted failures by looking
for a TOP-LEVEL "error" key. Result: 25 auth failures were reported as
`successful: 25, failed: 0`, and the caller saw a full panel of
"I have no comment on that." with no error anywhere.

That is worse than a silent failure — the telemetry actively said success, and it
was read as "the personas had nothing to say" rather than "nothing ran".
"""

import asyncio
import os
import sys

import pytest

HERE = os.path.dirname(__file__)


def _load_opinion_agent():
    """Import as a package member — opinion_agent uses relative imports, so
    spec_from_file_location cannot load it standalone. agentsociety2 demands its key
    at import time; a dummy is fine since no call is made."""
    os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "sk-test")
    sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..")))
    try:
        from app.services import opinion_agent
    except Exception as e:  # pragma: no cover - agentsociety2 unavailable
        pytest.skip(f"opinion_agent not importable: {e}")
    return opinion_agent


def test_impact_interview_fallback_carries_a_top_level_error():
    """The bug in one assertion: the fallback must be countable as a failure.

    `batch_impact_interview` does `len([r for r in results if "error" in r])`, so an
    error only reachable at `result["impact_metadata"]["error"]` is invisible to it.
    """
    mod = _load_opinion_agent()

    # Call the real method against a stub `self`. Subclassing is not possible —
    # OpinionCitizenAgent inherits a read-only `id` property from PersonAgent — and a
    # stub keeps the test to the failure path without the heavy agent construction.
    class _Stub:
        id = 1
        init_state = {"stance": "neutral"}

        def _get_dominant_emotion(self):
            return ("neutral", 0)

        async def answer_external_question(self, **_kw):
            raise RuntimeError("Error code: 401 - invalid api key")

    result = asyncio.run(mod.OpinionCitizenAgent.do_impact_interview(
        _Stub(), reframed_question="q", original_question="q", t=None, mode="product"))

    assert "error" in result, (
        "fallback has no TOP-LEVEL 'error' — batch_impact_interview will count this "
        "failed interview as successful")
    assert "401" in result["error"]
    # The nested copy stays for existing consumers.
    assert "error" in result.get("impact_metadata", {})


def test_counting_logic_treats_a_collapsed_round_as_failed():
    """Pins the aggregation contract independently of the heavy service import."""
    failed = [
        {"response": "I have no comment on that.", "error": "401 invalid api key",
         "impact_metadata": {"error": "401 invalid api key"}}
        for _ in range(25)
    ]
    successful = len([r for r in failed if "error" not in r])
    failures = [r for r in failed if "error" in r]

    assert successful == 0, "a fully collapsed round must report zero successes"
    assert len(failures) == 25
    assert len(failures) == len(failed), "all_failed must be detectable"


def test_healthy_round_is_not_flagged():
    healthy = [{"response": "Real answer.", "stance_after": "concerned"} for _ in range(5)]
    failures = [r for r in healthy if "error" in r]
    assert not failures
    assert not (healthy and len(failures) == len(healthy))
