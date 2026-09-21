"""Model-off tests for poster brief parsing."""

import importlib.util
import os
import sys

HERE = os.path.dirname(__file__)
APP = os.path.normpath(os.path.join(HERE, "..", "app"))
SERVICES = os.path.join(APP, "services")


def _load_poster_service():
    # Avoid heavy app.services __init__ (agentsociety2 env).
    for pkg, path in [
        ("app", APP),
        ("app.services", SERVICES),
        ("app.config", os.path.join(APP, "config.py")),
        ("app.utils", os.path.join(APP, "utils")),
        ("app.utils.logger", os.path.join(APP, "utils", "logger.py")),
        ("app.utils.llm_client", os.path.join(APP, "utils", "llm_client.py")),
        ("app.utils.token_counter", os.path.join(APP, "utils", "token_counter.py")),
    ]:
        if pkg in sys.modules:
            continue
        if pkg.endswith(".py") or os.path.isfile(path):
            # handled below for modules
            pass
    # Minimal package shells
    import types
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

    def load(name, file_path):
        if name in sys.modules:
            return sys.modules[name]
        spec = importlib.util.spec_from_file_location(name, file_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        # Stub heavy deps before poster_service import
        return mod

    # Stub logger + config + llm so poster_service imports cleanly
    if "app.utils.logger" not in sys.modules:
        log = types.ModuleType("app.utils.logger")
        log.get_logger = lambda name: type("L", (), {"info": lambda *a, **k: None, "warning": lambda *a, **k: None, "error": lambda *a, **k: None})()
        sys.modules["app.utils.logger"] = log
    if "app.config" not in sys.modules:
        cfg = types.ModuleType("app.config")
        class Config:
            POSTER_DATA_DIR = os.path.join(HERE, "_tmp_posters")
            LLM_API_KEY = "x"
            LLM_BASE_URL = "http://localhost"
            LLM_MODEL_NAME = "x"
            VISION_API_KEY = "x"
            VISION_BASE_URL = "http://localhost"
            VISION_MODEL = "x"
        cfg.Config = Config
        sys.modules["app.config"] = cfg
    if "app.utils.llm_client" not in sys.modules:
        llm = types.ModuleType("app.utils.llm_client")
        class LLMClient:
            @classmethod
            def for_vision(cls):
                return cls()
            def chat(self, *a, **k):
                return ""
            def get_stats(self):
                return {"prompt_tokens": 0, "completion_tokens": 0, "estimated_cost_usd": 0}
            @staticmethod
            def image_message(*a, **k):
                return {}
        llm.LLMClient = LLMClient
        sys.modules["app.utils.llm_client"] = llm

    name = "app.services.poster_service"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, os.path.join(SERVICES, "poster_service.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ps = _load_poster_service()


def test_stub_brief_parses_all_seven_fields():
    brief = ps.StubPosterReader().read(b"", "image/png")
    fields = ps.parse_brief(brief)
    for key in ("text", "pictured", "layout", "claims_stated", "claims_implied", "ask", "price"):
        assert fields[key], f"{key} should be non-empty"


def test_missing_price_is_empty_string():
    text = (
        "TEXT ON THE POSTER\nHello\n\n"
        "WHAT IS PICTURED\nNothing\n\n"
        "LAYOUT\nTop\n\n"
        "CLAIMS\nStates A\n\n"
        "THE ASK\nSign up\n"
    )
    fields = ps.parse_brief(text)
    assert fields["price"] == ""
    assert fields["text"] == "Hello"


def test_headings_out_of_order_still_found():
    text = (
        "THE ASK\nCall now\n\n"
        "TEXT ON THE POSTER\nBIG SALE\n\n"
        "PRICE SHOWN\nR10\n\n"
        "WHAT IS PICTURED\nLogo\n\n"
        "LAYOUT\nCentre\n\n"
        "CLAIMS\nIt states outright cheap, and separately, what it only implies: quality\n"
    )
    fields = ps.parse_brief(text)
    assert fields["ask"] == "Call now"
    assert fields["text"] == "BIG SALE"
    assert fields["price"] == "R10"
    assert "cheap" in fields["claims_stated"].lower()
    assert "quality" in fields["claims_implied"].lower()


def test_raw_brief_unchanged_by_parse():
    brief = ps.StubPosterReader().read(b"", "image/png")
    before = brief
    ps.parse_brief(brief)
    assert brief == before
