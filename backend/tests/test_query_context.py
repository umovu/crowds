"""Place detection for the query-scoped context block. No LLM, no network."""

import os

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

from app.services.query_context import detect_place  # noqa: E402


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """Point the local-context cache at a temp dir for every test in this file.

    Without this a test reads the developer's real cache/query_context, so a
    leftover entry from a live run makes "did it search?" assertions pass or
    fail depending on what happened to be on disk.
    """
    from app.services import query_context as qc
    # Patch the Config object query_context itself resolved, not a fresh import
    # of app.config: another test file stubs modules in sys.modules, so the two
    # are not always the same object — and when they differ, the cache quietly
    # stays pointed at the real one.
    monkeypatch.setattr(qc.Config, "DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("QUERY_CONTEXT", raising=False)


def test_suburb_beats_city():
    p = detect_place("A clinic in Sunnyside, Pretoria offering diabetes screening")
    assert p["name"] == "Sunnyside"
    assert p["label"] == "Sunnyside, Pretoria"
    assert p["province"] == "Gauteng"


def test_suburb_alone_gets_its_default_parent():
    p = detect_place("a stokvel app for Khayelitsha residents")
    assert p["label"] == "Khayelitsha, Cape Town"


def test_named_city_corrects_an_ambiguous_suburb():
    # There is a Sunnyside in Johannesburg too; the text should win.
    p = detect_place("our Sunnyside branch in Johannesburg")
    assert p["label"] == "Sunnyside, Johannesburg"


def test_city_when_no_suburb():
    p = detect_place("a delivery service for small shops in Polokwane")
    assert p["label"] == "Polokwane"
    assert p["province"] == "Limpopo"


def test_province_when_no_city():
    p = detect_place("a bursary scheme across Mpumalanga")
    assert p["label"] == "Mpumalanga"


def test_multiword_place_wins_over_fragment():
    p = detect_place("a taxi rank kiosk in Mitchells Plain")
    assert p["name"] == "Mitchells Plain"


def test_no_place_returns_none():
    assert detect_place("a subscription service for small business accounting") is None
    assert detect_place("") is None
    assert detect_place(None) is None


def test_place_name_inside_a_word_does_not_match():
    # "George" the city must not fire on a person called George.
    assert detect_place("Georgetown loyalty cards") is None


# ── Subjects and queries ─────────────────────────────────────

def test_subjects_come_from_the_shared_topic_rules():
    from app.services.query_context import detect_subjects
    assert detect_subjects("a clinic in Sunnyside for diabetes patients") == ["health"]
    assert detect_subjects("cheap electricity prepaid meters in Soweto") == ["cost", "power"]
    assert detect_subjects("a weekend sports fixtures list") == []


def test_subject_order_is_stable_so_the_cache_key_is():
    from app.services.query_context import detect_subjects
    a = detect_subjects("electricity and prices in Tembisa")
    b = detect_subjects("prices and electricity in Tembisa")
    assert a == b


def test_queries_name_the_place_and_cap_at_three():
    from app.services.query_context import build_queries, detect_place, detect_subjects
    text = "a same-day clinic in Khayelitsha, with electricity and price concerns"
    qs = build_queries(detect_place(text), detect_subjects(text))
    assert len(qs) <= 3
    assert all("Khayelitsha, Cape Town" in q for q in qs)


# ── Fail-safe ────────────────────────────────────────────────

def test_disabled_by_default():
    from app.services import query_context as qc
    assert qc.local_context("a clinic in Sunnyside, Pretoria") is None


def test_no_place_means_no_search(monkeypatch):
    from app.services import query_context as qc
    monkeypatch.setenv("QUERY_CONTEXT", "1")
    called = []
    monkeypatch.setattr(qc, "_gather_snippets", lambda q: called.append(q) or [])
    assert qc.local_context("an accounting subscription for small business") is None
    assert called == []


def test_no_snippets_means_no_block(monkeypatch):
    from app.services import query_context as qc
    monkeypatch.setenv("QUERY_CONTEXT", "1")
    monkeypatch.setattr(qc, "_gather_snippets", lambda q: [])
    assert qc.local_context("a clinic in Sunnyside, Pretoria") is None


def test_failed_distil_means_no_block(monkeypatch):
    from app.services import query_context as qc
    monkeypatch.setenv("QUERY_CONTEXT", "1")
    monkeypatch.setattr(qc, "_gather_snippets",
                        lambda q: [{"snippet": "Clinic queues are long.", "link": "", "source": "x"}])
    monkeypatch.setattr(qc, "_distil_local", lambda s, p: None)
    assert qc.local_context("a clinic in Sunnyside, Pretoria") is None


# ── Cache and rendering, with the model switched off ─────────

def test_block_is_cached_and_reused(monkeypatch):
    from app.services import query_context as qc
    monkeypatch.setenv("QUERY_CONTEXT", "1")
    searches = []
    monkeypatch.setattr(qc, "_gather_snippets",
                        lambda q: searches.append(q) or
                        [{"snippet": f"Sunnyside clinic fact {i}.",
                          "link": "https://example.com/a", "source": "example.com"}
                         for i in range(4)])
    monkeypatch.setattr(qc, "_distil_local",
                        lambda s, p: "- The Sunnyside clinic runs shorter hours.")

    first = qc.local_context("a clinic in Sunnyside, Pretoria")
    second = qc.local_context("another idea for a clinic in Sunnyside, Pretoria")
    assert first == second
    assert len(searches) == 1, "the second run must be a cache hit"


def test_block_is_headed_local_and_disclaims_household_income(monkeypatch):
    from app.services import query_context as qc
    monkeypatch.setenv("QUERY_CONTEXT", "1")
    monkeypatch.setattr(qc, "_gather_snippets",
                        lambda q: [{"snippet": f"local fact {i}", "link": "https://example.com/a",
                                    "source": "example.com"} for i in range(4)])
    monkeypatch.setattr(qc, "_distil_local", lambda s, p: "- The clinic runs shorter hours.")
    block = qc.local_context("a clinic in Sunnyside, Pretoria")
    assert block.startswith("NEAR YOU (Sunnyside, Pretoria")
    assert "not about your own household" in block
    assert "example.com" in block, "every local block cites where it came from"


# ── Junk snippets never reach the model ──────────────────────

def test_weather_and_listings_are_dropped():
    from app.services.query_context import _is_junk
    assert _is_junk("Sunnyside September weather: daily highs of 87°, lows of 52°")
    assert _is_junk("3 bedroom house for sale in Sunnyside, Pretoria")
    assert _is_junk("Book a room at this Sunnyside guest house on Booking.com")
    assert _is_junk("Sunnyside is a suburb of Pretoria, South Africa - Wikipedia")


def test_real_local_news_is_kept():
    from app.services.query_context import _is_junk
    assert not _is_junk("The Sunnyside clinic has cut its operating hours after staff cuts.")
    assert not _is_junk("Businesses in Sunnyside closed during the anti-immigration march.")


def test_a_thin_search_produces_no_block(monkeypatch):
    from app.services import query_context as qc
    monkeypatch.setenv("QUERY_CONTEXT", "1")
    distilled = []
    monkeypatch.setattr(qc, "_gather_snippets",
                        lambda q: [{"snippet": "one lonely fact", "link": "", "source": "x"}])
    monkeypatch.setattr(qc, "_distil_local", lambda s, p: distilled.append(1) or "- x")
    assert qc.local_context("a clinic in Sunnyside, Pretoria") is None
    assert distilled == [], "a thin search must not reach the model at all"


# ── A judge-failed local block is dropped ────────────────────

def _fake_judge(monkeypatch, *, pass_, errored=False, score=3):
    """Force judge_best_of to return a given verdict, with no LLM call."""
    from app.services import judge_service as js

    class R:
        def __init__(self):
            self.pass_, self.errored, self.score = pass_, errored, score
            self.reasoning = "test"
        def to_dict(self):
            return {"pass": self.pass_, "score": self.score}

    monkeypatch.setattr(js, "sa_context_judge_enabled", lambda: True)
    monkeypatch.setattr(js, "get_judge_service", lambda cheap=False: object())
    monkeypatch.setattr(js, "judge_best_of",
                        lambda generate, judge: ("- a local bullet", R(), False))
    monkeypatch.setattr(js, "record_judgement", lambda *a, **k: None)


def _snippets(n=5):
    return [{"snippet": f"local fact {i}", "link": "https://example.com/a",
             "source": "example.com"} for i in range(n)]


def test_judge_failure_drops_the_local_block(monkeypatch):
    from app.services import query_context as qc
    monkeypatch.setenv("QUERY_CONTEXT", "1")
    monkeypatch.setattr(qc.Config, "LLM_API_KEY", "k")
    monkeypatch.setattr(qc.Config, "LLM_MODEL_NAME", "m")
    monkeypatch.setattr(qc, "_gather_snippets", lambda q: _snippets())
    _fake_judge(monkeypatch, pass_=False)
    assert qc.local_context("a clinic in Sunnyside, Pretoria") is None


def test_a_broken_judge_call_does_not_drop_the_block(monkeypatch, tmp_path):
    # A judge that ERRORED judged nothing; treating that as a failure would
    # silently disable the feature whenever the judge tier is down.
    from app.config import Config
    from app.services import query_context as qc
    monkeypatch.setenv("QUERY_CONTEXT", "1")
    monkeypatch.setattr(Config, "DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(Config, "LLM_API_KEY", "k")
    monkeypatch.setattr(Config, "LLM_MODEL_NAME", "m")
    monkeypatch.setattr(qc, "_gather_snippets", lambda q: _snippets())
    _fake_judge(monkeypatch, pass_=False, errored=True)
    block = qc.local_context("a clinic in Sunnyside, Pretoria")
    assert block and "NEAR YOU" in block
