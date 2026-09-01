"""LLM-off tests for the operator context block (Step 2).

The operator context is the ONE field a user writes that lands inside what
every persona is asked. It is meant to describe the OFFER — what the product
is, what it costs, who buys it — so the room is briefed once instead of the
user retyping their business into every prompt.

What it must never become is a description of the ROOM. The personas are real
surveyed people carrying measured attitudes and real incomes; the moment a
seller can assert facts about them, the answers stop being research and become
the seller's own assumptions read back. These tests pin the boundary:

  * the block reaches the pitch framing (panel) and the founder announcement
    (sim) with byte-identical wording, from ONE function
  * it carries an explicit instruction to ignore any line claiming what the
    persona earns, owns or believes
  * it is capped, so it cannot crowd out the pitch
  * empty input produces nothing at all

Dependency-light loading (same shape as test_panel_fit.py) so AgentSociety2 —
which demands AGENTSOCIETY_LLM_API_KEY — is never imported.
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
    if "." in modname:
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


class _GraphStorage:
    pass


sys.modules["app.storage"].GraphStorage = _GraphStorage

_load_app("app.config", "config")
_load("app.services.income_seeder", "income_seeder.py", package="app.services")
specs = _load("app.services.mode_specs", "mode_specs.py", package="app.services")
_load("app.services.objections", "objections.py", package="app.services")
_load("app.services.persona_library", "persona_library.py", package="app.services")
_load("app.services.persona_retrieval", "persona_retrieval.py", package="app.services")
panel = _load("app.services.panel_service", "panel_service.py", package="app.services")


CONTEXT = (
    "We build and install home biodigesters in South Africa. R17,000 fitted. "
    "You feed it food and garden waste; it gives back cooking gas and liquid "
    "fertiliser. We install, and we service."
)
PITCH = {"what_it_is": "a home biodigester", "pricing": "R17,000", "problem_solved": "cut cooking fuel costs"}


# ── the block itself ────────────────────────────────────────────────────────

def test_empty_context_produces_nothing():
    for empty in ("", "   ", None):
        assert specs.build_operator_context_block(empty) == ""


def test_block_carries_the_context_and_the_fence():
    block = specs.build_operator_context_block(CONTEXT)
    assert CONTEXT in block
    # It must say whose text this is and what it describes.
    assert "BACKGROUND ON WHAT IS BEING PROPOSED" in block
    assert "describes the OFFER" in block
    # And it must tell the persona to disregard claims about themselves — the
    # label alone was not a guard, it was a caption.
    lowered = block.lower()
    assert "ignore that line" in lowered
    for claim in ("what you earn", "what you own", "you already", "cost is not a problem"):
        assert claim in lowered, f"fence does not name: {claim}"


def test_block_is_capped():
    long_ctx = "x" * 5000
    block = specs.build_operator_context_block(long_ctx)
    assert "x" * specs.OPERATOR_CONTEXT_MAX in block
    assert "x" * (specs.OPERATOR_CONTEXT_MAX + 1) not in block


# ── both paths use the SAME block ───────────────────────────────────────────

def test_panel_and_sim_brief_the_room_identically():
    """Two copies of the fence would drift. One function, one wording."""
    block = specs.build_operator_context_block(CONTEXT)
    framed = panel.frame_pitch("Would you buy one?", "product", operator_context=CONTEXT)
    announced = specs.build_pitch_announcement(PITCH, operator_context=CONTEXT)
    assert block.strip() in framed
    assert block.strip() in announced


def test_context_is_briefing_so_it_comes_before_the_question():
    framed = panel.frame_pitch("Would you buy one?", "product",
                               probes=["What would change your mind?"],
                               operator_context=CONTEXT)
    assert framed.index(CONTEXT) < framed.index("Would you buy one?")
    assert framed.index("Would you buy one?") < framed.index("What would change your mind?")
    assert not framed.startswith("\n")


def test_no_context_leaves_the_framing_untouched():
    """A user who never opens the box must get exactly the old prompt."""
    for mode in ("product", "policy"):
        assert (panel.frame_pitch("Would you buy one?", mode)
                == panel.frame_pitch("Would you buy one?", mode, operator_context=""))
    assert (specs.build_pitch_announcement(PITCH)
            == specs.build_pitch_announcement(PITCH, operator_context=""))


def test_short_reanchor_stays_short():
    """The re-anchor reminder is deliberately terse — the briefing already
    happened at round 0 and repeating it every few rounds would drown the feed."""
    short = specs.build_pitch_announcement(PITCH, short=True, operator_context=CONTEXT)
    assert CONTEXT not in short
    assert len(short) < 200


# ── the boundary this feature exists to hold ────────────────────────────────

def test_context_never_reaches_persona_identity():
    """The block belongs to the PITCH, not to who anyone is. If a future change
    routes it through character_context, this feature becomes the persona-slop
    back door the library rules exist to prevent."""
    import inspect
    agent_src = os.path.join(SERVICES, "opinion_agent.py")
    with open(agent_src, encoding="utf-8") as fh:
        source = fh.read()
    assert "operator_context" not in source, (
        "operator_context reached opinion_agent.py — it must stay in the pitch "
        "framing, never in character_context")
    # And the block builder itself is pure: same input, same output, no state.
    a = specs.build_operator_context_block(CONTEXT)
    b = specs.build_operator_context_block(CONTEXT)
    assert a == b
    assert inspect.signature(specs.build_operator_context_block).parameters.keys() == {"operator_context"}
