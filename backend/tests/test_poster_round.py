"""Model-off tests for poster multi-question round shaping."""

import importlib.util
import os
import sys
import types

HERE = os.path.dirname(__file__)
APP = os.path.normpath(os.path.join(HERE, "..", "app"))
SERVICES = os.path.join(APP, "services")


def _shell():
    if "app" not in sys.modules:
        m = types.ModuleType("app")
        m.__path__ = [APP]
        sys.modules["app"] = m
    if "app.services" not in sys.modules:
        m = types.ModuleType("app.services")
        m.__path__ = [SERVICES]
        sys.modules["app.services"] = m
    if "app.utils" not in sys.modules:
        m = types.ModuleType("app.utils")
        m.__path__ = [os.path.join(APP, "utils")]
        sys.modules["app.utils"] = m
    if "app.utils.logger" not in sys.modules:
        log = types.ModuleType("app.utils.logger")
        log.get_logger = lambda name: type("L", (), {
            "info": lambda *a, **k: None,
            "warning": lambda *a, **k: None,
            "error": lambda *a, **k: None,
        })()
        sys.modules["app.utils.logger"] = log


def _load_panel_bits():
    _shell()
    # Load poster_scoring first (no deps)
    name_s = "app.services.poster_scoring"
    if name_s not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            name_s, os.path.join(SERVICES, "poster_scoring.py")
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name_s] = mod
        spec.loader.exec_module(mod)

    # Minimal poster_service with constants used by build_poster_round_payload
    name_p = "app.services.poster_service"
    if name_p not in sys.modules:
        # Use the real poster_service via the brief test loader path
        from test_poster_brief import ps as real_ps
        sys.modules[name_p] = real_ps

    # Load only the merge helpers by exec'ing a tiny extract — instead, load
    # panel_service is heavy. Copy the pure functions by importing source pieces.
    # We re-implement the contract test against functions defined inline by
    # reading and executing just the helper section is fragile. Prefer loading
    # a thin module path: import merge from a duplicated pure path.
    #
    # Practical approach: exec the helper functions from panel_service source
    # text between known markers — too brittle. Instead import panel_service
    # functions by loading file with mocked deps.

    stubs = {
        "app.config": types.SimpleNamespace(Config=types.SimpleNamespace(
            PANEL_SESSION_DATA_DIR=os.path.join(HERE, "_tmp_panels"),
            POSTER_DATA_DIR=os.path.join(HERE, "_tmp_posters"),
        )),
        "app.services.income_seeder": types.SimpleNamespace(
            detect_grant=lambda p: (False, None), GRANT_PROVENANCE="x"
        ),
        "app.services.mode_specs": types.SimpleNamespace(budget_tier=lambda *a, **k: "moderate"),
        "app.services.mechanism_card_service": types.SimpleNamespace(
            attach_research_context=lambda p: None
        ),
        "app.services.persona_library": types.SimpleNamespace(
            get_library=lambda: types.SimpleNamespace(is_empty=lambda: True, all=lambda: [])
        ),
        "app.services.persona_retrieval": types.SimpleNamespace(
            select_for_query=lambda *a, **k: []
        ),
    }
    for k, v in stubs.items():
        if k not in sys.modules:
            if isinstance(v, types.SimpleNamespace) and k == "app.config":
                m = types.ModuleType(k)
                m.Config = v.Config
                sys.modules[k] = m
            else:
                m = types.ModuleType(k)
                for attr, val in vars(v).items():
                    if not attr.startswith("_"):
                        setattr(m, attr, val)
                sys.modules[k] = m

    name = "app.services.panel_service"
    if name in sys.modules and hasattr(sys.modules[name], "merge_question_answers"):
        return sys.modules[name]
    # Force reload if a partial module exists
    if name in sys.modules:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, os.path.join(SERVICES, "panel_service.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


panel = _load_panel_bits()


def test_merge_keys_by_stable_id_not_index():
    per_q = {
        "ask": [
            {"agent_id": 0, "agent_name": "A", "actor_archetype": "youth", "response": "sign up"},
            {"agent_id": 1, "agent_name": "B", "actor_archetype": "trader", "response": "buy it"},
        ],
        "attention": [
            {"agent_id": 0, "response": "I would stop scrolling"},
            {"agent_id": 1, "response": "keep going"},
        ],
        "off": [
            {"agent_id": 0, "response": "price high"},
            {"agent_id": 1, "response": "nothing"},
        ],
        "trust": [
            {"agent_id": 0, "response": "not sure"},
            {"agent_id": 1, "response": "maybe"},
        ],
    }
    rows = panel.merge_question_answers(per_q, ["ask", "attention", "off", "trust"])
    assert len(rows) == 2
    assert set(rows[0]["answers"].keys()) == {"ask", "attention", "off", "trust"}
    assert rows[0]["answers"]["ask"] == "sign up"
    assert "0" not in rows[0]["answers"]  # not index-keyed


def test_poster_round_payload_findings():
    per_q = {
        "ask": [
            {"agent_id": 0, "agent_name": "A", "actor_archetype": "youth",
             "response": "It wants me to subscribe"},
            {"agent_id": 1, "agent_name": "B", "actor_archetype": "trader",
             "response": "It wants me to visit the shop"},
        ],
        "attention": [
            {"agent_id": 0, "response": "I would stop scrolling"},
            {"agent_id": 1, "response": "keep going"},
        ],
        "off": [
            {"agent_id": 0, "response": "fees feel off"},
            {"agent_id": 1, "response": "ok"},
        ],
        "trust": [
            {"agent_id": 0, "response": "I do not trust the brand yet"},
            {"agent_id": 1, "response": "need a real company name"},
        ],
    }
    poster = {
        "poster_id": "poster_x",
        "ask_label_primary": "sign_up",
        "ask_label_secondary": "buy",
        "channel": "whatsapp",
        "fields": {"claims_implied": "a December payout"},
        "brief_edited": True,
    }
    out = panel.build_poster_round_payload(
        brief="BRIEF",
        per_question_results=per_q,
        poster=poster,
    )
    assert out["total_interviewed"] == 2
    assert out["findings"]["understood"] == 1
    assert out["findings"]["total"] == 2
    assert out["findings"]["brief_edited"] is True
    assert out["results"][0]["answers"]["ask"]
    assert out["poster_id"] == "poster_x"
