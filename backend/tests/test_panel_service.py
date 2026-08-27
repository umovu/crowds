"""Unit tests for segment-aware panel profile stamping (LLM off).

Adds coverage for the "add new personas to a live room" feature:

  * _build_profile stamps segment_id + segment_label only when a real
    segment is given — "everyone" and None must NOT stamp (so a base room
    stays unsegmented and a custom agent never gets a spoofed segment)
  * the stamping is orthogonal to product-mode economics: both can coexist
  * assert_library_cast still accepts segmented cast profiles (the segment
    stamp is library-grounded, not a graph/research identity)

These run with the LLM switched OFF — pure-function / guard assertions only.
The loader mirrors test_library_cast.py so panel_service imports cleanly
without the heavy app.services __init__ (which needs a live LLM env).
"""

import importlib.util
import os
import sys
import types
from typing import Any, Dict, List

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
_load("app.services.agent_profile_generator", "agent_profile_generator.py", package="app.services")
_load("app.services.custom_agent_parser", "custom_agent_parser.py", package="app.services")
panel = _load("app.services.panel_service", "panel_service.py", package="app.services")


# ── _build_profile segment stamping ─────────────────────────────────────────

def test_build_profile_stamps_segment_for_real_segment():
    p = panel._build_profile(
        {"id": "x1", "name": "Test", "actor_archetype": "civic_moderate"},
        0, "policy", segment_id="youth",
    )
    assert p["segment_id"] == "youth"
    assert p["segment_label"] == panel.SEGMENTS["youth"]["label"]


def test_build_profile_no_segment_stamp_for_everyone():
    p = panel._build_profile(
        {"id": "x1", "name": "Test"}, 0, "policy", segment_id="everyone",
    )
    assert "segment_id" not in p
    assert "segment_label" not in p


def test_build_profile_no_segment_stamp_when_none():
    p = panel._build_profile({"id": "x1", "name": "Test"}, 0, "policy")
    assert "segment_id" not in p
    assert "segment_label" not in p


def test_build_profile_segment_and_product_economics_coexist():
    p = panel._build_profile(
        {"id": "x1", "name": "Test", "actor_archetype": "budget_holder"},
        0, "product", segment_id="farmers",
    )
    assert p["segment_id"] == "farmers"
    assert p["segment_label"] == panel.SEGMENTS["farmers"]["label"]
    # budget_tier is product-mode economics, computed from real data only
    assert p["budget_tier"] in ("tight", "moderate", "loose")


def test_build_profile_does_not_mutate_source_with_segment():
    src = {"id": "orig", "name": "Keep", "actor_archetype": "civic_moderate"}
    snapshot = dict(src)
    panel._build_profile(src, 5, "policy", segment_id="youth")
    assert src == snapshot


# ── assert_library_cast accepts segmented profiles ──────────────────────────

def test_assert_library_cast_accepts_segmented_profiles():
    profiles = [
        panel._build_profile(
            {"id": "a", "name": "A", "actor_archetype": "civic_moderate"},
            0, "policy", segment_id="youth",
        ),
        panel._build_profile(
            {"id": "b", "name": "B", "actor_archetype": "budget_holder"},
            1, "policy", segment_id="farmers",
        ),
    ]
    # Must not raise — segmented cast is still 100% library-sourced.
    panel.assert_library_cast(profiles)
