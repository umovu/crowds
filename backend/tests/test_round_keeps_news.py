"""A round keeps the news its room was given, so a reopened panel shows it, not today's.

LLM-off: the interview, summary and save are stubbed.
"""

import os

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

from app.services import panel_round_service as prs  # noqa: E402

NEWS = {"enabled": True, "found": True, "as_of": "28 September 2026", "total": 7,
        "points": ["Clinics are short of insulin."], "sources": []}


def test_the_round_saves_the_news_it_was_given(monkeypatch):
    saved = {}

    class Service:
        async def batch_impact_interview(self, **kw):
            return {"results": [{"agent_id": 1, "response": "ok"}], "successful": 1,
                    "total_interviewed": 1}

    monkeypatch.setattr(prs, "interview_service", lambda sid: Service())
    monkeypatch.setattr(prs.panel_service, "frame_pitch", lambda p, m, **kw: p)
    monkeypatch.setattr(prs.panel_service, "synthesize_panel_summary", lambda *a, **kw: "")
    monkeypatch.setattr(prs, "_add_segment_ranking", lambda *a: None)
    monkeypatch.setattr(prs.panel_service, "save_round",
                        lambda sid, rnd: saved.update(rnd) or 1)
    monkeypatch.setattr(prs.sa_context, "news_for_pitch", lambda pitch: NEWS)
    monkeypatch.setattr(prs.run_events, "record_start", lambda **kw: None)
    monkeypatch.setattr(prs.run_events, "record_end", lambda **kw: None)

    out = prs.run_round("panel_000000000000", {"mode": "panel"}, "A R200 diabetes plan.",
                        None, 2, user_id=None)
    assert saved["result"]["news"] == NEWS
    assert out["news"] == NEWS


def test_a_failed_news_read_does_not_fail_the_round(monkeypatch):
    saved = {}

    class Service:
        async def batch_impact_interview(self, **kw):
            return {"results": [{"agent_id": 1, "response": "ok"}], "successful": 1,
                    "total_interviewed": 1}

    def boom(pitch):
        raise RuntimeError("search down")

    monkeypatch.setattr(prs, "interview_service", lambda sid: Service())
    monkeypatch.setattr(prs.panel_service, "frame_pitch", lambda p, m, **kw: p)
    monkeypatch.setattr(prs.panel_service, "synthesize_panel_summary", lambda *a, **kw: "")
    monkeypatch.setattr(prs, "_add_segment_ranking", lambda *a: None)
    monkeypatch.setattr(prs.panel_service, "save_round",
                        lambda sid, rnd: saved.update(rnd) or 1)
    monkeypatch.setattr(prs.sa_context, "news_for_pitch", boom)
    monkeypatch.setattr(prs.run_events, "record_start", lambda **kw: None)
    monkeypatch.setattr(prs.run_events, "record_end", lambda **kw: None)

    prs.run_round("panel_000000000000", {"mode": "panel"}, "A R200 diabetes plan.",
                  None, 2, user_id=None)
    assert "news" not in saved["result"]
