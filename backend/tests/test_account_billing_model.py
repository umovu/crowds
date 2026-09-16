"""Accounts and billing tables: the repo SQL, the models and every row the code sends
agree. LLM-off and network-off: requests is faked, nothing reaches Supabase.

Four of these tables used to exist only in the hosted dashboard. A column the code
writes that the table lacks fails at the database; a plan or status value the app does
not know saves fine and quietly changes who can run what.
"""

import glob
import importlib.util
import json
import os
import re

import pytest

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
SQL_DIR = os.path.join(BACKEND, "supabase")
USER = "0f8fad5b-d9cb-469f-a165-70867728950e"

_spec = importlib.util.spec_from_file_location(
    "data_model_for_billing_tests", os.path.join(BACKEND, "app", "services", "data_model.py"))
dm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dm)

TABLE_MODELS = {
    "subscriptions": "subscription", "profiles": "profile", "waitlist_requests": "waitlist_request",
    "access_control": "access_control", "operator_context": "operator_context", "run_events": "run_event",
}


# ── repo SQL and models agree ─────────────────────────────────────────────

def _sql_columns(table):
    with open(os.path.join(SQL_DIR, f"{table}.sql"), encoding="utf-8") as fh:
        sql = fh.read()
    body = re.search(rf"create table if not exists public\.{table} \((.*?)\n\);", sql, re.S).group(1)
    return [line.strip().split()[0] for line in body.splitlines()
            if re.match(r"\s+[a-z_]+ ", line)]


@pytest.mark.parametrize("table,model", sorted(TABLE_MODELS.items()))
def test_repo_sql_and_model_list_the_same_columns(table, model):
    assert sorted(_sql_columns(table)) == sorted(dm.load(model)["fields"])
    assert dm.load(model)["sql"] == f"backend/supabase/{table}.sql"


def test_run_events_allow_list_is_the_table():
    from app.repositories import run_event_repository as run_events
    assert run_events.ALLOWED_FIELDS <= set(dm.load("run_event")["fields"])


# ── every row the code sends fits ─────────────────────────────────────────

class _Resp:
    status_code = 201

    def __init__(self, rows):
        self._rows = rows

    def raise_for_status(self):
        pass

    def json(self):
        return self._rows


@pytest.fixture
def supabase(monkeypatch, tmp_path):
    """Fake Supabase REST: records every call, answers with no rows."""
    import requests
    calls = []

    def fake(method):
        def call(url, params=None, json=None, headers=None, timeout=None):
            calls.append({"method": method, "url": url, "params": params or {}, "json": json})
            return _Resp([])
        return call

    for method in ("get", "post", "patch"):
        monkeypatch.setattr(requests, method, fake(method))
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.delenv("WAITLIST_ENABLED", raising=False)
    from app.repositories import run_event_repository as run_events
    monkeypatch.setattr(run_events, "_ledger_path", lambda: str(tmp_path / "run_events.jsonl"))
    return calls


def _problems(calls):
    out = []
    for call in calls:
        m = re.search(r"/rest/v1/([a-z_]+)", call["url"])
        if not m:
            continue
        model = TABLE_MODELS[m.group(1)]
        if call["json"] is not None:
            out += dm.row_problems(model, call["json"])
        params = dict(call["params"])
        select = params.pop("select", "")
        for key in ("limit", "order"):
            params.pop(key, None)
        out += dm.column_problems(model, [c for c in select.split(",") if c] + list(params))
    return out


def test_billing_rows_fit(supabase, real_module):
    billing = real_module("app.services.billing_service")
    billing.get_entitlement(USER)            # no row -> creates the free default
    billing.increment_panel_used(USER)
    billing.increment_sim_used(USER)
    billing.set_plan(USER, "paid", status="active", paystack_customer_code="CUS_abc")
    billing.set_plan(USER, "free", status="cancelled")
    billing.get_customer_code(USER)
    billing.get_user_by_customer("CUS_abc")
    assert {c["method"] for c in supabase} == {"get", "post", "patch"}
    assert _problems(supabase) == []


def test_approval_rows_fit(supabase):
    from app.repositories import user_repository
    from app.services import signup_service
    signup_service.invalidate(USER)
    signup_service.is_approved(USER, "thandi@example.org", "Thandi")  # no row -> pending
    signup_service.approve(USER)
    signup_service.profile(USER)
    user_repository.claim_notification(USER)
    assert len(supabase) >= 4
    assert _problems(supabase) == []


def test_waitlist_rows_fit(supabase):
    from app.repositories import user_repository, waitlist_repository
    waitlist_repository.add("thandi@example.org", "Thandi", "Runs clinics")
    user_repository.approved_by_email("thandi@example.org")
    assert _problems(supabase) == []


def test_run_event_rows_fit_both_stores(supabase, tmp_path):
    from app.repositories import run_event_repository as run_events
    run_events.record_start(run_id="panel_0123456789ab", user_id=USER, run_type="panel",
                            mode="panel", crowd_size=12)
    run_events.record_end(run_id="panel_0123456789ab", user_id=USER, run_type="panel",
                          mode="panel", status="ok", duration_seconds=41.2,
                          prompt_tokens=100, completion_tokens=50, total_tokens=150, cost_usd=0.01)
    assert _problems(supabase) == []
    with open(tmp_path / "run_events.jsonl", encoding="utf-8") as fh:
        lines = [json.loads(line) for line in fh]
    assert len(lines) == 2
    assert [p for line in lines for p in dm.model_problems("run_event", line)] == []


def test_operator_context_rows_fit(supabase):
    from app.repositories import operator_context_repository as operator_context
    operator_context.save(USER, "We run three private clinics in Soweto.")
    operator_context.get(USER)
    assert _problems(supabase) == []


# ── saved local files ──────────────────────────────────────────────────────

def test_saved_local_run_events_fit():
    path = os.path.join(BACKEND, "run_events.jsonl")
    if not os.path.exists(path):
        pytest.skip("no local run events in this checkout")
    with open(path, encoding="utf-8") as fh:
        problems = [p for line in fh if line.strip()
                    for p in dm.model_problems("run_event", json.loads(line))]
    assert not problems, problems[:10]


def test_saved_local_operator_context_fits():
    path = os.path.join(BACKEND, "operator_context.json")
    if not os.path.exists(path):
        pytest.skip("no local operator context in this checkout")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    spec = {"type": "object", "values": dm.load("operator_context")["local_file"]["values"]}
    problems = []
    dm._check_value("operator_context.json", data, spec, problems)
    assert problems == []


# ── the checker catches the mistakes it exists for ────────────────────────

def test_a_plan_the_app_does_not_sell_is_caught():
    assert any("'pro'" in p for p in dm.row_problems("subscription", {"user_id": USER, "plan": "pro"}))


def test_a_misspelt_column_is_caught():
    assert any("'panels_used'" in p for p in dm.row_problems("subscription", {"panels_used": 1}))


def test_a_negative_counter_is_caught():
    assert any("below 0" in p for p in dm.row_problems("subscription", {"sim_used": -1}))


def test_selecting_a_column_that_does_not_exist_is_caught():
    assert dm.column_problems("profile", ["approved", "is_admin"]) == [
        "public.profiles: column 'is_admin' does not exist"]


def test_set_plan_warns_about_an_unknown_status_but_still_saves(supabase, monkeypatch, real_module):
    billing = real_module("app.services.billing_service")
    warnings = []
    monkeypatch.setattr(billing.logger, "warning", lambda msg, *a: warnings.append(msg % a if a else msg))
    billing.set_plan(USER, "paid", status="trialing")
    assert any(c["method"] == "post" for c in supabase)
    assert any("'trialing'" in w for w in warnings)
