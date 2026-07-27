"""Geotype-aware mechanism-card binding — LLM off, deterministic.

A broad archetype (grant_dependent_survivor) bundles two lives: an urban township
grant recipient with no land, and a rural subsistence grower who lives inside the
farming mechanisms. Binding on archetype alone handed farming cards to both — a
KwaMashu grant recipient got "price taker / market surplus" reasoning she has no
use for (measured: 57 mis-bindings across the farm cards).

The guard drops a rural-scoped card for an urban NON-farmer, and keeps it for a
farmer (any setting) or a rurally-settled persona (the subsistence overlap).
"""

import importlib.util
import os

HERE = os.path.dirname(__file__)
SERVICES = os.path.normpath(os.path.join(HERE, "..", "app", "services"))


def _load_service():
    spec = importlib.util.spec_from_file_location(
        "mechanism_card_service", os.path.join(SERVICES, "mechanism_card_service.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mcs = _load_service()


def setup_function(_fn):
    mcs._cache = None
    os.environ.pop("RESEARCH_CONTEXT_ENABLED", None)


def _rural_scoped_ids():
    return {c["id"] for c in mcs.load_cards() if mcs._is_rural_scoped(c)}


def test_there_is_at_least_one_rural_scoped_card():
    # If this is empty the whole guard is a no-op and the other tests prove nothing.
    assert _rural_scoped_ids(), "expected at least one farmer/rural card in the set"


def test_urban_nonfarmer_loses_rural_scoped_cards():
    urban = mcs.cards_for_archetype("grant_dependent_survivor", cap=99, geotype="Urban")
    assert not (_rural_scoped_ids() & {c["id"] for c in urban}), \
        "an urban grant recipient should not bind a farming card"


def test_rural_nonfarmer_keeps_rural_scoped_cards():
    # The subsistence overlap the guard must preserve: a rural grant recipient often
    # grows food and genuinely lives inside the farming mechanisms.
    for geo in ("Traditional", "Farms"):
        rural = mcs.cards_for_archetype("grant_dependent_survivor", cap=99, geotype=geo)
        assert _rural_scoped_ids() & {c["id"] for c in rural}, \
            f"a {geo} grant recipient should still bind a rural-scoped card"


def test_farmer_keeps_rural_scoped_cards_regardless_of_setting():
    for geo in ("Urban", "Traditional", "Farms", None):
        farmer = mcs.cards_for_archetype("smallholder_emerging_farmer", cap=99, geotype=geo)
        assert _rural_scoped_ids() & {c["id"] for c in farmer}, \
            f"a farmer should bind a rural-scoped card even when geotype={geo!r}"


def test_unknown_geotype_does_not_tighten():
    # Backward-compat: a pre-rebuild persona with no geotype binds exactly as before.
    with_none = {c["id"] for c in mcs.cards_for_archetype("grant_dependent_survivor", cap=99, geotype=None)}
    legacy = {c["id"] for c in mcs.cards_for_archetype("grant_dependent_survivor", cap=99)}
    assert with_none == legacy, "geotype=None must not change binding"


def test_non_rural_cards_are_never_dropped_by_geotype():
    """The guard must be surgical: only rural-scoped cards are affected. An urban
    persona keeps every non-rural card it bound before."""
    rural_ids = _rural_scoped_ids()
    legacy = {c["id"] for c in mcs.cards_for_archetype("grant_dependent_survivor", cap=99)}
    urban = {c["id"] for c in mcs.cards_for_archetype("grant_dependent_survivor", cap=99, geotype="Urban")}
    dropped = legacy - urban
    assert dropped, "expected the guard to drop at least one card for an urban grant recipient"
    assert dropped <= rural_ids, f"guard dropped non-rural cards: {dropped - rural_ids}"
