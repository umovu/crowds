"""Research cards fit app/data/model/mechanism_card.json. LLM-off.

Cards feed every prompt they reach. A misnamed tag binds nobody, a figure slips a
number into reasoning text, and a year written two ways reads as two formats.
"""

import copy
import glob
import importlib.util
import json
import os

import pytest

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
CARDS_DIR = os.path.join(BACKEND, "app", "data", "mechanism_cards")
DRAFTS = os.path.join(BACKEND, "..", "docs", "extraction", "*.card.json")

# By file path: no app.services import while tests are collected (see test_persona_data_model).
_spec = importlib.util.spec_from_file_location(
    "data_model_for_card_tests", os.path.join(BACKEND, "app", "services", "data_model.py"))
dm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dm)
MODEL = dm.load("mechanism_card")


def _cards():
    out = []
    for path in sorted(glob.glob(os.path.join(CARDS_DIR, "*.json"))):
        with open(path, encoding="utf-8") as fh:
            out.append((os.path.basename(path), json.load(fh)))
    return out


def _good():
    return copy.deepcopy(next(c for _n, c in _cards() if c["id"] == "youth-waithood-identity"))


# ── real cards ─────────────────────────────────────────────────────────────

def test_every_shipped_card_fits_the_model():
    cards = _cards()
    assert len(cards) >= 16
    problems = [p for name, card in cards for p in dm.mechanism_card_problems(card, name)]
    assert not problems, "\n".join(problems)


def test_draft_cards_report_what_stops_them_shipping():
    """Drafts live in docs/extraction (local, not in git) while they await sign-off, so
    their gaps are reported here, not failed. A draft is ready when this passes for it."""
    drafts = glob.glob(DRAFTS)
    if not drafts:
        pytest.skip("no draft cards in this checkout")
    problems = []
    for path in drafts:
        with open(path, encoding="utf-8") as fh:
            problems += dm.mechanism_card_problems(json.load(fh))
    if problems:
        pytest.xfail("drafts not ready to ship:\n" + "\n".join(problems))


def test_budget_tags_are_the_app_budget_tiers():
    from app.services.panel_service import BUDGET_TIERS
    assert MODEL["fields"]["economic_tags"]["items"]["allowed"] == list(BUDGET_TIERS)


def test_the_readme_lists_every_card():
    with open(os.path.join(CARDS_DIR, "README.md"), encoding="utf-8") as fh:
        readme = fh.read()
    missing = [c["id"] for _n, c in _cards() if f"`{c['id']}`" not in readme]
    assert not missing


# ── the checker catches the mistakes it exists for ────────────────────────

def _flags(card, text, name=None):
    return any(text in p for p in dm.mechanism_card_problems(card, name))


def test_a_number_in_reasoning_text_is_caught():
    card = _good()
    card["claims"][0]["text"] = "Most (60%) will not pay."
    assert _flags(card, "number in claim")


def test_a_number_in_a_claim_objection_is_caught():
    card = _good()
    card["claims"][0]["objections"] = ["Can I pay R50 a month?"]
    assert _flags(card, "number in claim")


def test_a_segment_tag_that_is_not_a_persona_type_is_caught():
    card = _good()
    card["segment_tags"].append("rural")
    assert _flags(card, "'rural' is not a persona type")


def test_a_claim_without_passages_is_caught():
    card = _good()
    del card["claims"][0]["passages"]
    assert _flags(card, "passages")


def test_a_claim_without_a_rule_is_caught():
    card = _good()
    del card["claims"][0]["needs"]
    assert _flags(card, "needs")


def test_the_old_parallel_lists_are_caught():
    card = _good()
    card["mechanisms"] = ["A claim kept outside claims."]
    assert _flags(card, "'mechanisms' is not in the model")


@pytest.mark.parametrize("year", ["2024–2025", "not specified", "2025 (COVID)"])
def test_a_badly_written_year_is_caught(year):
    card = _good()
    card["year_range"] = year
    assert _flags(card, "year_range does not look right")


def test_more_than_five_claims_is_caught():
    card = _good()
    card["claims"] = card["claims"] * 2
    assert _flags(card, "more than 5 items")


def test_a_who_its_for_rule_with_a_typo_is_caught():
    card = _good()
    card["applies_when"] = [{"employment_status": ["Unemployd"]}]
    assert _flags(card, "not an answer any persona can have")


def test_a_claim_rule_with_a_typo_is_caught():
    card = _good()
    card["claims"][0]["needs"] = [{"lived_poverty": ["lo"]}]
    assert _flags(card, "not an answer any persona can have")


def test_a_claim_rule_naming_a_fact_no_persona_has_is_caught():
    card = _good()
    card["claims"][0]["needs"] = [{"has_chronic_illness": ["yes"]}]
    assert _flags(card, "which no persona carries")


def test_a_budget_tag_the_app_does_not_have_is_caught():
    card = _good()
    card["economic_tags"] = ["rich"]
    assert _flags(card, "'rich'")


def test_a_file_named_differently_from_its_card_is_caught():
    assert _flags(_good(), "should be named", "youth-waithood-identity.card.json")


def test_an_unknown_field_is_caught():
    card = _good()
    card["notes_for_me"] = "x"
    assert _flags(card, "'notes_for_me' is not in the model")


# ── the app says so ───────────────────────────────────────────────────────

def test_loading_warns_about_a_card_that_does_not_fit_but_still_loads_it(tmp_path, monkeypatch):
    from app.services import mechanism_card_service as mcs
    good, bad = _good(), _good()
    bad["id"] = "bad-card"
    bad["segment_tags"] = ["rural"]
    for card in (good, bad):
        (tmp_path / f"{card['id']}.json").write_text(json.dumps(card), encoding="utf-8")
    warnings = []
    monkeypatch.setattr(mcs.logger, "warning", lambda msg, *a: warnings.append(msg % a if a else msg))
    monkeypatch.setattr(mcs, "_cache", None)
    try:
        cards = mcs.load_cards(str(tmp_path))
    finally:
        mcs._cache = None
    assert len(cards) == 2
    assert any("bad-card" in w and "data model" in w for w in warnings)
    assert not any("youth-waithood-identity" in w for w in warnings)
