"""
Operator context — one saved free-text block per user describing their business/offer.

Stored in Supabase table `operator_context` (user_id PK, body, updated_at).
When Supabase isn't configured — local dev — it falls back to a JSON file under
DATA_ROOT, the same place sims and panels already live. Without that fallback a
local save reported success and stored nothing, so the feature could not be
looked at without a hosted database.

Reads still fail open: any error returns "" and the run proceeds unbriefed.

The text is injected as BACKGROUND about the offer, never as persona material.
The prompt wording lives in `mode_specs.build_operator_context_block` — one
copy, shared by the panel and sim paths. This module stores and returns the raw
body only; it must not grow its own copy of that block.
"""
import json
import logging
import os

import requests

from ..config import Config

logger = logging.getLogger("fub.operator_context")

MAX_LEN = 1500
TABLE = "operator_context"


def _local_path() -> str:
    return os.path.join(Config.DATA_ROOT, "operator_context.json")


def _local_all() -> dict:
    try:
        with open(_local_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _local_get(user_id: str) -> str:
    return (_local_all().get(user_id) or "").strip()[:MAX_LEN]


def _local_save(user_id: str, body: str) -> None:
    data = _local_all()
    data[user_id] = body
    path = _local_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _supabase_url() -> str:
    return (os.environ.get("SUPABASE_URL") or "").rstrip("/")


def _service_key() -> str:
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""


def _enabled() -> bool:
    return bool(_supabase_url() and _service_key())


def _headers() -> dict:
    k = _service_key()
    return {"apikey": k, "Authorization": f"Bearer {k}", "Content-Type": "application/json"}


def get_operator_context(user_id: str) -> str:
    """Return the raw body for a user, or "" if none / error."""
    if not user_id:
        return ""
    if not _enabled():
        return _local_get(user_id)
    url = f"{_supabase_url()}/rest/v1/{TABLE}"
    try:
        resp = requests.get(
            url,
            params={"user_id": f"eq.{user_id}", "select": "body"},
            headers=_headers(),
            timeout=8,
        )
        resp.raise_for_status()
        rows = resp.json()
        if rows and isinstance(rows, list) and rows[0].get("body"):
            return (rows[0]["body"] or "").strip()[:MAX_LEN]
        return ""
    except Exception as e:
        logger.warning("get_operator_context failed for %s: %s (failing open)", user_id, e)
        return ""


def save_operator_context(user_id: str, body: str) -> dict:
    """Upsert the operator context for a user. Returns the saved row."""
    if not user_id:
        raise ValueError("user_id is required")
    cleaned = (body or "").strip()[:MAX_LEN]
    if not _enabled():
        # Local dev: persist to DATA_ROOT so a save actually survives a reload.
        _local_save(user_id, cleaned)
        return {"user_id": user_id, "body": cleaned, "updated_at": None}
    url = f"{_supabase_url()}/rest/v1/{TABLE}"
    payload = {"user_id": user_id, "body": cleaned}
    try:
        resp = requests.post(
            url,
            json=payload,
            headers={**_headers(), "Prefer": "resolution=merge-duplicates,return=representation"},
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
        if isinstance(rows, list) and rows:
            return rows[0]
        return payload
    except Exception as e:
        logger.error("save_operator_context failed for %s: %s", user_id, e)
        raise
