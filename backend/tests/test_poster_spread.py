"""Model-off tests for spread casting (Round 5 carryover / Round 6 isolation).

Order-independent: never replaces an existing `app` / `app.services` package
in sys.modules. Always loads persona_retrieval from the real file on disk.
"""

import importlib.util
import os
import sys
import types

HERE = os.path.dirname(__file__)
APP = os.path.normpath(os.path.join(HERE, "..", "app"))
SERVICES = os.path.join(APP, "services")
RETRIEVAL_PATH = os.path.join(SERVICES, "persona_retrieval.py")


def _ensure_pkg(name: str, path: str) -> types.ModuleType:
    """Create a package shell only if missing. Never clobber a real one."""
    existing = sys.modules.get(name)
    if existing is not None:
        if not hasattr(existing, "__path__"):
            try:
                existing.__path__ = [path]
            except Exception:
                pass
        return existing
    mod = types.ModuleType(name)
    mod.__path__ = [path]
    sys.modules[name] = mod
    return mod


def _ensure_logger() -> None:
    if "app.utils.logger" in sys.modules and hasattr(sys.modules["app.utils.logger"], "get_logger"):
        return
    log = types.ModuleType("app.utils.logger")
    log.get_logger = lambda name: type("L", (), {
        "info": lambda *a, **k: None,
        "warning": lambda *a, **k: None,
        "error": lambda *a, **k: None,
    })()
    sys.modules["app.utils.logger"] = log


def _ensure_persona_library_stub() -> None:
    name = "app.services.persona_library"
    existing = sys.modules.get(name)
    # Other suites may leave a partial SimpleNamespace with only get_library.
    # persona_retrieval imports both PersonaLibrary and get_library.
    if (
        existing is not None
        and hasattr(existing, "get_library")
        and hasattr(existing, "PersonaLibrary")
    ):
        return
    lib = types.ModuleType(name)
    lib.PersonaLibrary = object
    lib.get_library = lambda: _FakeLib([])
    sys.modules[name] = lib


def _load_retrieval():
    """Load the real persona_retrieval from disk, overwriting any stub."""
    _ensure_pkg("app", APP)
    _ensure_pkg("app.services", SERVICES)
    _ensure_pkg("app.utils", os.path.join(APP, "utils"))
    _ensure_logger()
    _ensure_persona_library_stub()

    name = "app.services.persona_retrieval"
    # Drop stubs left by other suites (e.g. lambda *a, **k: []).
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, RETRIEVAL_PATH)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "app.services"
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class _FakeLib:
    def __init__(self, personas):
        self._personas = personas

    def all(self):
        return list(self._personas)


def _library():
    """Enough archetypes/provinces/ages that tilt can collapse and spread can open."""
    arches = [
        "informal_trader", "small_business_owner", "grant_dependent_survivor",
        "unemployed_youth", "urban_professional", "community_leader",
        "civic_moderate", "learner",
    ]
    provinces = [
        "Gauteng", "Western Cape", "KwaZulu-Natal", "Eastern Cape",
        "Limpopo", "Mpumalanga",
    ]
    ages = [22, 28, 35, 42, 55, 63]
    out = []
    n = 0
    for arch in arches:
        for _ in range(6):
            n += 1
            out.append({
                "id": f"p{n}",
                "name": f"Person {n}",
                "actor_archetype": arch,
                "province": provinces[n % len(provinces)],
                "age": ages[n % len(ages)],
            })
    return _FakeLib(out)


pr = _load_retrieval()


def test_spread_true_yields_more_distinct_archetypes_than_tilted():
    lib = _library()
    query = "taxi and spaza informal trade"  # tilts hard toward traders
    n, seed = 12, 7
    tilted = pr.select_for_query(n, query, library=lib, seed=seed, spread=False)
    spread = pr.select_for_query(n, query, library=lib, seed=seed, spread=True)
    assert tilted and spread, f"empty cast tilted={len(tilted)} spread={len(spread)}"
    t_arch = {p.get("actor_archetype") for p in tilted}
    s_arch = {p.get("actor_archetype") for p in spread}
    assert len(s_arch) > len(t_arch), (
        f"spread={len(s_arch)} should beat tilted={len(t_arch)}; "
        f"spread={sorted(s_arch)} tilted={sorted(t_arch)}"
    )


def test_spread_is_deterministic_for_seed():
    lib = _library()
    a = [p["id"] for p in pr.select_for_query(10, "taxi", library=lib, seed=3, spread=True)]
    b = [p["id"] for p in pr.select_for_query(10, "taxi", library=lib, seed=3, spread=True)]
    assert a == b
    assert len(a) == 10


def test_spread_keeps_archetype_floor_after_dimension_swaps():
    """Province/age spread must not undo the distinct-archetype floor."""
    lib = _library()
    cast = pr.select_for_query(12, "taxi spaza", library=lib, seed=11, spread=True)
    arches = {p.get("actor_archetype") for p in cast}
    floor = pr.MIN_DISTINCT_ARCHETYPES + 2
    assert len(arches) >= floor, f"only {len(arches)} archetypes, floor is {floor}"
