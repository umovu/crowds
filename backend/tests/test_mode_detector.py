"""Unit tests for mode_detector + the additive secondary lens in prompt_reframer.

These run with the LLM switched OFF — they are the primary safety net for the
auto-detect-mode feature and must stay assertable without a model.

To avoid executing the heavy app.services package __init__ (which needs LLM env
vars), we load the dependency-light modules directly by file path and register the
ones with relative imports under their real package names.
"""

import importlib.util
import os
import sys
import types

HERE = os.path.dirname(__file__)
SERVICES = os.path.normpath(os.path.join(HERE, "..", "app", "services"))


def _load(modname, filename, package=None):
    spec = importlib.util.spec_from_file_location(modname, os.path.join(SERVICES, filename))
    mod = importlib.util.module_from_spec(spec)
    if package:
        mod.__package__ = package
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


# Stand up a minimal `app.services` package so prompt_reframer's
# `from .mode_specs import BUDGET_TIER_GLOSS` resolves without the real __init__.
if "app" not in sys.modules:
    sys.modules["app"] = types.ModuleType("app")
if "app.services" not in sys.modules:
    pkg = types.ModuleType("app.services")
    pkg.__path__ = [SERVICES]
    sys.modules["app.services"] = pkg

md = _load("mode_detector", "mode_detector.py")
_load("app.services.mode_specs", "mode_specs.py", package="app.services")
pr = _load("app.services.prompt_reframer", "prompt_reframer.py", package="app.services")


# --- score_modes ---------------------------------------------------------------

def test_pure_policy_seed_scores_policy_high():
    s = md.score_modes(
        "The government announced it will deploy the army to the Cape Flats. "
        "How do citizens and the community react to this policy announcement?"
    )
    assert s["policy_score"] > 0.8
    assert s["product_score"] < 0.2


def test_pure_product_seed_scores_product_high():
    s = md.score_modes(
        "Would customers pay R99/month for our app? We want to test the price, "
        "the launch, and willingness to pay in the market."
    )
    assert s["product_score"] > 0.8
    assert s["policy_score"] < 0.2


def test_no_signal_is_even_split():
    s = md.score_modes("the cat sat on the mat")
    assert s["policy_score"] == 0.5
    assert s["product_score"] == 0.5


# --- decide_mode ---------------------------------------------------------------

def test_clear_policy_decision():
    d = md.decide_mode(md.score_modes(
        "Government announcement: new regulation banning X. How do citizens and the "
        "community and voters react to this policy?"
    ))
    assert d["mode"] == "policy"
    assert d["converged"] is False
    assert d["secondary_lens"] is None
    assert d["confidence"] == "clear"


def test_clear_product_decision():
    d = md.decide_mode(md.score_modes(
        "New subscription app, R49/month. Test the price, launch, customer adoption "
        "and willingness to pay in the market."
    ))
    assert d["mode"] == "product"
    assert d["converged"] is False
    assert d["secondary_lens"] is None


def test_strong_both_converges_with_correct_lens():
    d = md.detect(
        "Government is launching a state-subsidised R99/month data bundle for students. "
        "Citizens react to the policy announcement; we also want customer adoption and "
        "whether they would subscribe to the product at that price in the market — and "
        "how the community and voters feel about the regulation."
    )
    assert d["converged"] is True
    # primary is whichever scored higher; the lens is always the other
    assert {d["mode"], d["secondary_lens"]} == {"policy", "product"}


def test_stray_product_words_do_not_converge():
    # A policy seed that happens to mention "price" once must NOT converge — the
    # conservative bar needs >= MIN_FAMILIES distinct families per mode.
    d = md.decide_mode(md.score_modes(
        "The government announced a new policy; citizens and the community and voters "
        "are reacting to the regulation. Some mention the price of bread."
    ))
    assert d["converged"] is False
    assert d["mode"] == "policy"


def test_thin_margin_flags_confidence_thin():
    d = md.decide_mode({
        "policy_score": 0.52, "product_score": 0.48,
        "families": {"policy": 1, "product": 1},
    })
    assert d["confidence"] == "thin"
    assert d["converged"] is False


# --- llm_tiebreak (LLM off) ----------------------------------------------------

def test_llm_tiebreak_passthrough_without_client():
    decision = {"mode": "policy", "converged": False, "secondary_lens": None,
                "confidence": "thin", "scores": {"policy": 0.5, "product": 0.5}}
    out = md.llm_tiebreak("seed", "", decision, llm_client=None, model_name="x")
    assert out is decision  # unchanged, same object


def test_detect_sets_used_llm_tiebreak_false_when_off():
    d = md.detect("government policy citizens community", "")
    assert d["used_llm_tiebreak"] is False


# --- seed-vs-doc conflict ------------------------------------------------------

def test_seed_outweighs_conflicting_document():
    # Seed is clearly policy; document leans product. Seed weighting (1.0 vs 0.5)
    # should keep the decision on policy.
    seed = ("The minister announced a new regulation. Citizens, the community and "
            "voters react to this government policy announcement.")
    doc = ("product app subscription price launch customer market churn adoption "
           "willingness to pay") * 2
    d = md.detect(seed, doc)
    assert d["mode"] == "policy"


# --- secondary lens in prompt_reframer (LLM off, deterministic) -----------------

def test_policy_primary_with_product_lens_adds_budget_and_keeps_policy_question():
    reframer = pr.ImpactReframer()
    profile = {"name": "Thandi", "budget_tier": "tight",
               "occupation": "domestic worker", "interested_topics": ["jobs"]}
    out = reframer.reframe(
        "The government will introduce a R20 daily transport levy.",
        profile, mode="policy", secondary_lens="product",
    )
    # budget reality block present (computed from real tier, not the LLM)
    assert "BUDGET REALITY" in out
    assert "TIGHT" in out
    # primary policy question still present
    assert "What does this mean for YOU" in out
    # additive affordability sub-question present
    assert "justify the spend" in out
    # never emits a buy-% / probability
    assert "%" not in out
    assert "probability" not in out.lower()


def test_no_lens_policy_reframe_has_no_budget_block():
    reframer = pr.ImpactReframer()
    profile = {"name": "Sipho", "budget_tier": "tight", "occupation": "teacher"}
    out = reframer.reframe("New schooling policy.", profile, mode="policy")
    assert "BUDGET REALITY" not in out
    assert "justify the spend" not in out
