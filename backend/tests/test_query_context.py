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
    # No test reads a real web page; the page reader has its own tests below.
    monkeypatch.setattr(qc, "_read_pages", lambda sources, place, words: [])


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


# ── The pitch's own words, and a report the screen can show ──

def test_pitch_words_drop_filler_and_the_place():
    from app.services.query_context import detect_place, pitch_words
    text = "A new app for chronic medicine delivery in Sunnyside, Pretoria"
    assert pitch_words(text, detect_place(text)) == ["chronic", "medicine", "delivery"]


def test_queries_carry_the_pitch_words():
    from app.services.query_context import search_plan
    plan = search_plan("chronic medicine delivery for a clinic in Sunnyside, Pretoria")
    local = [s["q"] for s in plan["searches"] if s["kind"] == "local"]
    assert len(local) <= 3 and len(plan["queries"]) == len(local) + 2
    assert any("chronic medicine delivery" in q for q in local)
    assert all("Sunnyside, Pretoria" in q for q in local), "the national free-programme search is the only one without the place"


def test_no_place_means_no_plan():
    from app.services.query_context import search_plan
    assert search_plan("an accounting subscription for small business") is None


def test_report_runs_without_the_sim_flag_and_lists_what_it_found(monkeypatch):
    # Panels call local_report directly; QUERY_CONTEXT only gates the sim path.
    from app.services import query_context as qc
    monkeypatch.setattr(qc, "_gather_snippets", lambda q: _snippets())
    monkeypatch.setattr(qc, "_distil_local", lambda s, p: "- The clinic runs shorter hours.")
    r = qc.local_report("a clinic in Sunnyside, Pretoria")
    assert r["status"] == "found"
    assert r["points"] == ["The clinic runs shorter hours."]
    assert r["sources"] == [{"source": "example.com", "link": "https://example.com/a"}]
    assert r["block"].startswith("NEAR YOU")

    again = qc.local_report("a clinic in Sunnyside, Pretoria")
    assert again["status"] == "cached"
    assert again["points"] == r["points"] and again["sources"] == r["sources"]


def test_report_says_when_the_search_was_too_thin(monkeypatch):
    from app.services import query_context as qc
    monkeypatch.setattr(qc, "_gather_snippets", lambda q: _snippets(1))
    r = qc.local_report("a clinic in Sunnyside, Pretoria")
    assert r["status"] == "thin" and r["block"] is None and r["queries"]


def test_a_different_question_about_the_same_place_searches_again(monkeypatch):
    from app.services import query_context as qc
    searches = []
    monkeypatch.setattr(qc, "_gather_snippets", lambda q: searches.append(q) or _snippets())
    monkeypatch.setattr(qc, "_distil_local", lambda s, p: "- x")
    qc.local_report("a clinic in Sunnyside, Pretoria")
    qc.local_report("a taxi rank kiosk in Sunnyside, Pretoria")
    assert len(searches) == 2


# ── Junk sites, and news before the whole web ────────────────

def test_social_and_event_sites_are_junk():
    from app.services.query_context import _is_junk_site
    for link in ("https://www.instagram.com/reel/x", "https://www.facebook.com/v/1",
                 "https://www.youtube.com/watch?v=1", "https://www.worldhealthexpo.com/e"):
        assert _is_junk_site(link), link
    assert not _is_junk_site("https://iol.co.za/news/a")
    assert not _is_junk_site("https://www.msf.org.za/news")


class _FakeSerper:
    def __init__(self, news, web):
        self.news, self.web, self.calls = news, web, []
    def is_available(self):
        return True
    def search(self, q, num_results=6, news=False):
        self.calls.append("news" if news else "web")
        items = self.news if news else self.web
        return {"success": True, "results": items}


def _item(i, site="iol.co.za"):
    return {"snippet": f"Sunnyside clinic fact {i}", "link": f"https://{site}/{i}", "source": site}


def test_news_first_and_web_only_when_news_is_thin(monkeypatch):
    from app.services import query_context as qc, serper_service
    fake = _FakeSerper(news=[_item(i) for i in range(4)], web=[_item(9, "web.co.za")])
    monkeypatch.setattr(serper_service, "SerperService", lambda: fake)
    got = qc._gather_snippets(["q"])
    assert fake.calls == ["news"], "enough news means no web search"
    assert all("iol.co.za" in s["link"] for s in got)

    fake = _FakeSerper(news=[_item(1)], web=[_item(2, "web.co.za"), _item(3, "instagram.com")])
    monkeypatch.setattr(serper_service, "SerperService", lambda: fake)
    got = qc._gather_snippets(["q"])
    assert fake.calls == ["news", "web"]
    assert [s["source"] for s in got] == ["iol.co.za", "web.co.za"], "instagram is dropped"


# ── Search tags, "what people use today", full pages ─────────

def test_each_search_is_tagged_for_its_job():
    from app.services.query_context import search_plan
    plan = search_plan("chronic medicine delivery for a clinic in Sunnyside, Pretoria")
    modes = [(s["mode"], s["kind"]) for s in plan["searches"]]
    assert modes[0] == ("news", "local"), "what is happening there: news only"
    assert modes[1] == ("both", "local"), "the pitch's own words: news and web"
    assert modes[-2:] == [("both", "alternatives")] * 2
    assert plan["searches"][-2]["q"].startswith(
        "where do people in Sunnyside, Pretoria get chronic medicine delivery")
    assert plan["queries"] == [s["q"] for s in plan["searches"]]


def test_both_mode_always_reads_the_web_too(monkeypatch):
    from app.services import query_context as qc, serper_service
    fake = _FakeSerper(news=[_item(i) for i in range(5)], web=[_item(9, "health.gov.za")])
    monkeypatch.setattr(serper_service, "SerperService", lambda: fake)
    got = qc._gather_snippets([{"q": "q", "mode": "both", "kind": "alternatives"}])
    assert fake.calls == ["news", "web"]
    assert {s["kind"] for s in got} == {"alternatives"}
    assert any(s["source"] == "health.gov.za" for s in got)


def test_what_people_use_today_is_its_own_section(monkeypatch):
    from app.services import query_context as qc
    snippets = ([dict(_item(i), kind="local") for i in range(4)]
                + [dict(_item(i, "health.gov.za"), kind="alternatives") for i in range(5, 8)])
    monkeypatch.setattr(qc, "_gather_snippets", lambda s: snippets)
    monkeypatch.setattr(qc, "_distil_local", lambda s, p: "- Clinic queues are long.")
    seen = {}
    def alts(s, p, w):
        seen["n"] = len(s)
        return "- Free pickup points hand out pre-packed chronic medicine."
    monkeypatch.setattr(qc, "_distil_alternatives", alts)
    r = qc.local_report("chronic medicine delivery for a clinic in Sunnyside, Pretoria")
    assert seen["n"] == 3, "only the alternatives search feeds the alternatives list"
    assert r["points"] == ["Clinic queues are long."]
    assert r["alternatives"] == ["Free pickup points hand out pre-packed chronic medicine."]
    assert "WHAT PEOPLE THERE USE TODAY" in r["block"]

    again = qc.local_report("chronic medicine delivery for a clinic in Sunnyside, Pretoria")
    assert again["status"] == "cached" and again["alternatives"] == r["alternatives"]


def test_alternatives_alone_still_make_a_block(monkeypatch):
    from app.services import query_context as qc
    snippets = [dict(_item(i, "health.gov.za"), kind="alternatives") for i in range(3)]
    monkeypatch.setattr(qc, "_gather_snippets", lambda s: snippets)
    monkeypatch.setattr(qc, "_distil_alternatives", lambda s, p, w: "- A free pickup point.")
    r = qc.local_report("chronic medicine delivery for a clinic in Sunnyside, Pretoria")
    assert r["status"] == "found" and r["points"] == [] and r["alternatives"]


def test_page_reader_keeps_only_paragraphs_about_the_place_or_pitch(monkeypatch):
    from app.services import query_context as qc, jina_service
    import importlib
    real = importlib.reload(qc)._read_pages  # the autouse stub replaced it

    class FakeJina:
        def is_available(self):
            return True
        def scrape(self, url, timeout=30.0):
            return {"success": True, "content": (
                "Menu Home News Sport\n\n"
                "*   [Menu](https://x.co.za/sunnyside-chronic-medicine/#)\n"
                "*   [Search](https://x.co.za/sunnyside-chronic-medicine/?s=)\n\n"
                "Patients in Sunnyside now collect chronic medicine from a pickup point "
                "instead of queuing at the clinic for hours.\n\n"
                "The weather this weekend will be sunny with highs of 28 degrees in the city.")}

    monkeypatch.setattr(jina_service, "JinaService", FakeJina)
    place = qc.detect_place("a clinic in Sunnyside, Pretoria")
    got = real([_item(1)], place, ["chronic", "medicine"])
    assert len(got) == 1
    assert "pickup point" in got[0]["snippet"]
    assert "weather" not in got[0]["snippet"] and "Menu" not in got[0]["snippet"]


def test_job_adverts_are_junk():
    from app.services.query_context import _is_junk
    assert _is_junk("Mediclinic Medforum in Sunnyside is hiring a Technical Assistant")
    assert _is_junk("Nursing vacancies at the Sunnyside clinic - apply now")


def test_sources_about_the_place_are_listed_first():
    from app.services.query_context import _source_list
    got = _source_list([
        {"snippet": "Chiefs win at the stadium", "link": "https://goal.com/a", "source": "goal.com"},
        {"snippet": "Polokwane taxi fares rise by R5", "link": "https://iol.co.za/b", "source": "iol.co.za"},
    ], place="Polokwane")
    assert got[0]["source"] == "iol.co.za"


def test_the_use_today_list_is_judged_by_its_own_rules(monkeypatch):
    # The local rules fail any national fact; a national free programme is exactly
    # what belongs in "what people there use today".
    from app.services.judge_service import JudgeService
    seen = {}
    monkeypatch.setattr(JudgeService, "judge",
                        lambda self, criteria, block, ctx: seen.setdefault("c", criteria))
    svc = JudgeService.__new__(JudgeService)
    svc.judge_sa_context("- x", ["s"], place="Sunnyside, Pretoria", alternatives=True)
    assert "national programme counts" in seen["c"]
    seen.clear()
    svc.judge_sa_context("- x", ["s"], place="Sunnyside, Pretoria")
    assert "NOT a national fact" in seen["c"]
