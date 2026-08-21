"""LLM-off tests for the study reader (backend/app/services/study_reader.py).

The reader is pure string + keyword logic — no network, no model, no Flask.
It is the deterministic pre-processor behind the confirmation chips, so every
field it produces has a pinned contract:

  * `find_price` extracts a literal price and normalises it; returns None when
    the sentence states none (a price is never inferred).
  * probes: a matched theme is a strong-data probe, the base probe is always
    present, a no-match sentence gets a thin-data lens fallback probe.
  * audience confidence: concrete keyword match -> strong-data; no match
    (default South African mix) -> thin-data (Option B rule).
  * worry is derived only from a strong-data probe — never invented.
  * mode reuses the deterministic keyword detector; the "not set" price signal
    exists so the UI can prompt for one in product mode.
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
    spec = importlib.util.spec_from_file_location(modname, os.path.join(APP, *filename.split(".")) + ".py")
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


storage_stub = sys.modules["app.storage"]
storage_stub.GraphStorage = _GraphStorage

_load_app("app.config", "config")
_load("app.services.income_seeder", "income_seeder.py", package="app.services")
_load("app.services.mode_specs", "mode_specs.py", package="app.services")
_load("app.services.persona_library", "persona_library.py", package="app.services")
_load("app.services.persona_retrieval", "persona_retrieval.py", package="app.services")
_load("app.services.panel_service", "panel_service.py", package="app.services")
_load("app.services.mode_detector", "mode_detector.py", package="app.services")
reader = _load("app.services.study_reader", "study_reader.py", package="app.services")


# ── price ──────────────────────────────────────────────────────────────────

def test_find_price_plain():
    assert reader.find_price("invest from R50 a month with no fees") == "R50/month"


def test_find_price_slash():
    assert reader.find_price("a R99.99/month app") == "R99.99/month"


def test_find_price_comma_thousands():
    assert reader.find_price("costs R1,500 once") == "R1,500/once"


def test_find_price_spaced_rand():
    assert reader.find_price("priced at R 50 per month") == "R50/month"


def test_find_price_none_when_absent():
    assert reader.find_price("a free app for everyone") is None


def test_find_price_none_on_empty_text():
    assert reader.find_price("") is None
    assert reader.find_price(None) is None


# ── probes ─────────────────────────────────────────────────────────────────

def test_base_probe_always_present():
    probes = reader.infer_probes("a brand new app", "land")
    assert probes[0]["id"] == "reaction"
    assert probes[0]["base"] is True


def test_matched_theme_is_strong_data():
    probes = reader.infer_probes("would people trust an app that charges R50/month", "land")
    ids = {p["id"]: p for p in probes}
    assert ids["trust"]["confidence"] == "strong-data"
    assert ids["money"]["confidence"] == "strong-data"


def test_no_match_gets_thin_data_lens_fallback():
    probes = reader.infer_probes("completely generic sentence", "breaks")
    non_base = [p for p in probes if not p["base"]]
    assert len(non_base) == 1
    assert non_base[0]["id"] == "dealbreaker"
    assert non_base[0]["confidence"] == "thin-data"


def test_breaks_fallback_is_blocker_framed():
    probes = reader.infer_probes("generic text", "breaks")
    non_base = [p for p in probes if not p["base"]][0]
    assert "stop" in non_base["question"].lower()


# ── the read ───────────────────────────────────────────────────────────────

def test_read_study_product_with_price():
    spec = reader.read_study(
        "A mobile app that lets South Africans invest from R50 a month with no fees, "
        "aimed at young professionals in cities",
        lens="land")
    assert spec["mode"] == "product"
    assert spec["price"] == "R50/month"
    assert spec["what"]
    assert spec["audience"]["segments"]
    assert spec["audience"]["confidence"] == "strong-data"
    assert any(p["active"] for p in spec["probes"])


def test_read_study_thin_audience_on_generic_text():
    spec = reader.read_study("a completely generic announcement for the whole country", lens="land")
    assert spec["audience"]["confidence"] == "thin-data"


def test_read_study_policy_has_no_price():
    spec = reader.read_study(
        "Government announces a national permit verification drive for employers", lens="land")
    assert spec["mode"] == "policy"
    assert spec["price"] is None


def test_read_study_policy_price_never_extracted_even_if_mentioned():
    # R50 mention inside a policy seed is not a product price — mode is policy,
    # so price must stay None regardless of the token.
    spec = reader.read_study(
        "Government freezes bus fares at R50 and requires new permits", lens="land")
    assert spec["mode"] == "policy"
    assert spec["price"] is None


def test_read_study_worry_from_strong_probe():
    spec = reader.read_study(
        "people are worried about hidden fees in the new app", lens="breaks")
    assert spec["worry"] == "Trust"
    assert spec["mode_confidence"] in ("clear", "thin")


def test_read_study_worry_none_without_strong_signal():
    spec = reader.read_study("a very generic sentence with nothing specific", lens="land")
    assert spec["worry"] is None


def test_read_study_default_lens_accepts_unknown_lens():
    spec = reader.read_study("an app", lens="nope")
    assert spec["lens"] == "nope"
    assert spec["probes"]


# ── shape contract ─────────────────────────────────────────────────────────

def test_read_study_has_all_chip_fields():
    spec = reader.read_study("an app that costs R30/month", lens="fit")
    for key in ("lens", "what", "mode", "mode_confidence", "price",
                "worry", "audience", "probes"):
        assert key in spec
    assert "segments" in spec["audience"]
    assert "confidence" in spec["audience"]