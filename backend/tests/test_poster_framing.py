"""A poster is met in a feed, not handed over — LLM off.

A poster and a product pitch are different situations, and the panel must be
asked accordingly. These tests pin that difference so a later prompt edit cannot
quietly turn a poster back into a pitch:

  * feed framing — a poster arrives mid-scroll with no obligation to engage.
    Founder framing ("I'm putting this in front of you") hands it over and so
    grants it attention for free, and attention is the main thing under test.
  * poster questions — comprehension, attention, what jars, trust. A poster
    fails at being understood long before it fails at being liked.
  * permission to scroll past. The commonest real reaction to a poster is to
    ignore it; if the prompt cannot express that, the panel is fake.
  * the budget block SURVIVES (income still says whether an offer is relevant)
    but nobody is asked to justify a spend — a poster sells nothing.
  * product and policy wording are untouched when no poster is involved.

Modules are loaded directly against package skeletons (mirrors
test_library_cast.py) to avoid the heavy app.services __init__, which needs
agentsociety2's LLM env vars.
"""

import importlib.util
import os
import sys
import types

HERE = os.path.dirname(__file__)
APP = os.path.normpath(os.path.join(HERE, "..", "app"))
SERVICES = os.path.join(APP, "services")


def _load(modname, filename, package=None):
    if modname in sys.modules:
        return sys.modules[modname]
    spec = importlib.util.spec_from_file_location(modname, os.path.join(SERVICES, filename))
    mod = importlib.util.module_from_spec(spec)
    if package:
        mod.__package__ = package
    sys.modules[modname] = mod
    if package and package in sys.modules:
        setattr(sys.modules[package], modname.rsplit(".", 1)[-1], mod)
    spec.loader.exec_module(mod)
    return mod


def _load_app(modname, filename):
    if modname in sys.modules:
        return sys.modules[modname]
    spec = importlib.util.spec_from_file_location(
        modname, os.path.join(APP, *filename.split(".")) + ".py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    parent_name, _, child = modname.rpartition(".")
    if parent_name in sys.modules:
        setattr(sys.modules[parent_name], child, mod)
    spec.loader.exec_module(mod)
    return mod


for pkg_name, pkg_path in [
    ("app", APP),
    ("app.services", SERVICES),
    ("app.models", os.path.join(APP, "models")),
    ("app.utils", os.path.join(APP, "utils")),
    ("app.storage", os.path.join(APP, "storage")),
]:
    if pkg_name not in sys.modules:
        m = types.ModuleType(pkg_name)
        m.__path__ = [pkg_path]
        sys.modules[pkg_name] = m

_load_app("app.config", "config")
_load("app.services.income_seeder", "income_seeder.py", package="app.services")
_load("app.services.mode_specs", "mode_specs.py", package="app.services")
_load("app.services.persona_library", "persona_library.py", package="app.services")
_load("app.services.persona_retrieval", "persona_retrieval.py", package="app.services")
poster_service = _load("app.services.poster_service", "poster_service.py", package="app.services")
reframer_mod = _load("app.services.prompt_reframer", "prompt_reframer.py", package="app.services")
panel = _load("app.services.panel_service", "panel_service.py", package="app.services")

BRIEF = (
    "THE POSTER\n"
    "TEXT ON THE POSTER\n  SAVE R500, GET R7 000 BACK (headline)\n"
    "THE ASK\n  WhatsApp the number before 31 July.\n"
    "PRICE SHOWN\n  R500 per month"
)

# A persona with the real-data fields the budget layer renders from.
PERSONA = {
    "name": "Thandi",
    "occupation": "cashier",
    "actor_archetype": "worker",
    "budget_tier": "tight",
    "monthly_household_income_rand": 4200,
}


def _reframe(**kwargs):
    return reframer_mod.ImpactReframer().reframe(BRIEF, dict(PERSONA), **kwargs)


# ── feed framing (panel_service.frame_pitch) ──────────────────────────────

def test_poster_arrives_mid_scroll():
    framed = panel.frame_pitch(BRIEF, "product", poster=True)
    low = framed.lower()
    assert "scrolling" in low
    assert "feed" in low
    # The situation is a feed, but the cast is still asked how it lands — the
    # run exists to learn that, so the framing must not licence a non-answer.
    assert "how it lands" in low
    # The brief itself still reaches the cast verbatim.
    assert "SAVE R500, GET R7 000 BACK" in framed


def test_poster_framing_does_not_hand_the_poster_over():
    """The founder handover is the specific thing feed framing replaces —
    it grants the poster attention for free, which is what we measure."""
    framed = panel.frame_pitch(BRIEF, "product", poster=True).lower()
    assert "putting this in front of you" not in framed
    assert "honest reaction" not in framed


def test_product_framing_unchanged_without_a_poster():
    framed = panel.frame_pitch("R99/month solar", "product")
    assert "putting this in front of you" in framed.lower()


def test_policy_framing_unchanged_without_a_poster():
    assert panel.frame_pitch("a new grant", "policy") == "a new grant"


# ── poster questions (ImpactReframer layer 4) ─────────────────────────────

def test_all_four_poster_questions_are_asked():
    out = _reframe(mode="product", poster=True)
    for q in poster_service.POSTER_QUESTIONS:
        assert q in out, f"missing poster question: {q}"


def test_poster_questions_are_sourced_from_poster_service():
    """One copy of the wording. The API hands these to the UI; the prompt must
    ask the same four, so the two cannot drift."""
    assert len(poster_service.POSTER_QUESTIONS) == 4
    src = open(os.path.join(SERVICES, "prompt_reframer.py"), encoding="utf-8").read()
    assert "POSTER_QUESTIONS" in src
    # No hand-copied duplicate of the question text in the reframer.
    for q in poster_service.POSTER_QUESTIONS:
        assert q not in src


def test_the_cast_must_answer_rather_than_opt_out():
    """The panel exists to tell the founder how the poster lands. An earlier
    version let a persona reply "I'd just keep scrolling" and stop there —
    honest to real behaviour, useless as a test result."""
    out = _reframe(mode="product", poster=True).lower()
    assert "answer all four" in out
    assert "how it lands" in out
    assert "keep scrolling" not in out


def test_poster_does_not_get_the_product_reaction_wording():
    out = _reframe(mode="product", poster=True)
    assert "React as you actually would" not in out


def test_poster_keeps_the_budget_block_but_asks_no_spend_justification():
    """Income still places the persona — it just is not what they weigh.
    A poster asks for one step (a WhatsApp), never a purchase."""
    out = _reframe(mode="product", poster=True)
    assert "YOUR BUDGET REALITY" in out
    assert "TIGHT" in out
    assert "justify the spend" not in out


def test_a_policy_poster_still_gets_the_budget_block():
    """A public-service poster detects as policy mode, but income still colours
    whether the offer on it is even meant for someone like this persona."""
    out = _reframe(mode="policy", poster=True)
    assert "YOUR BUDGET REALITY" in out
    assert "meant for someone like you" in out
    assert "justify the spend" not in out


def test_poster_suppresses_the_converged_affordability_sub_question():
    out = _reframe(mode="policy", poster=True, secondary_lens="product")
    assert "justify the spend" not in out
    for q in poster_service.POSTER_QUESTIONS:
        assert q in out


def test_a_poster_is_never_cut_down_to_an_extracted_event():
    """_extract_event REPLACES the question with the fragment it matched. On a
    poster that would throw away the headline, the price and the ask — a poster's
    own words are the stimulus, not a hypothetical to be parsed out."""
    conditional = "SAVE R500 if you join before 31 July"
    out = reframer_mod.ImpactReframer().reframe(
        conditional, dict(PERSONA), mode="product", poster=True)
    assert conditional in out
    # Same text without the poster flag does get reduced — that path is unchanged.
    pitched = reframer_mod.ImpactReframer().reframe(
        conditional, dict(PERSONA), mode="product")
    assert conditional not in pitched


def test_poster_keeps_the_identity_and_hard_rules_layers():
    """Poster mode replaces one layer, not the prompt. Identity lock and the
    output constraints must still be there."""
    out = _reframe(mode="product", poster=True)
    assert "Thandi" in out
    assert "HARD RULES" in out


# ── regression: no poster, no change ──────────────────────────────────────

def test_product_reaction_wording_survives_without_a_poster():
    out = _reframe(mode="product")
    assert "React as you actually would" in out
    for q in poster_service.POSTER_QUESTIONS:
        assert q not in out


def test_policy_impact_wording_survives_without_a_poster():
    out = _reframe(mode="policy")
    assert "What does this mean for YOU" in out
    assert "keep scrolling" not in out.lower()


def test_converged_affordability_lens_still_works_without_a_poster():
    out = _reframe(mode="policy", secondary_lens="product")
    assert "justify the spend" in out


# ── session plumbing (poster_id → context → every round) ──────────────────

def test_poster_id_is_recorded_on_the_session_and_its_context():
    """The flag lives on the session, so round 2 asks poster questions too
    without the caller having to say so again."""
    import json
    meta = panel.create_session(pitch=BRIEF, mode="product", n=3, seed=5,
                                poster_id="poster_test_001")
    try:
        assert meta["poster_id"] == "poster_test_001"
        ctx_path = os.path.join(panel.session_dir(meta["session_id"]), panel.CONTEXT_FILE)
        with open(ctx_path, encoding="utf-8") as fh:
            assert json.load(fh)["poster"] is True
    finally:
        panel.delete_session(meta["session_id"])


def test_a_normal_pitch_session_is_not_marked_as_a_poster():
    import json
    meta = panel.create_session(pitch="R99/month solar", mode="product", n=3, seed=5)
    try:
        assert "poster_id" not in meta
        ctx_path = os.path.join(panel.session_dir(meta["session_id"]), panel.CONTEXT_FILE)
        with open(ctx_path, encoding="utf-8") as fh:
            assert json.load(fh)["poster"] is False
    finally:
        panel.delete_session(meta["session_id"])
