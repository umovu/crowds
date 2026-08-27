"""
Operator context — one saved free-text block per user describing their business/offer.

Stored in Supabase table `operator_context` (user_id PK, body, updated_at).
Fail-open: if Supabase not configured or lookup fails, returns "" and the
simulation/panel runs without it. The text is injected as BACKGROUND about
the offer, never as persona material.
"""
import logging
import os

import requests

logger = logging.getLogger("fub.operator_context")

MAX_LEN = 1500
TABLE = "operator_context"


def _supabase_url() -> str:
    return (os.environ.get("SUPABASE_URL") or "").rstrip("/")


def _service_key() -> str:
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""


def _enabled() -> bool:
    return bool(_supabase_url() and _service_key())


def _headers() -> dict:
    k = _service_key()
    return {"apikey": k, "Authorization": f"Bearer {k}", "Content-Type": "application/json"}


def _format_block(body: str) -> str:
    body = (body or "").strip()
    if not body:
        return ""
    # Cap is enforced on write; double-guard on read
    if len(body) > MAX_LEN:
        body = body[:MAX_LEN]
    return (
        "\n=== BACKGROUND ON WHAT IS BEING PROPOSED (from the person running this study) ===\n"
        f"{body}\n"
        "This is context about the offer. It is NOT information about you, your income, or what you believe.\n"
    )


def get_operator_context(user_id: str) -> str:
    """Return the raw body for a user, or "" if none / not configured / error."""
    if not _enabled() or not user_id:
        return ""
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


def get_operator_context_block(user_id: str) -> str:
    """Return the formatted block to append to a pitch/seed, or ""."""
    body = get_operator_context(user_id)
    return _format_block(body) if body else ""


def save_operator_context(user_id: str, body: str) -> dict:
    """Upsert the operator context for a user. Returns the saved row."""
    if not user_id:
        raise ValueError("user_id is required")
    cleaned = (body or "").strip()[:MAX_LEN]
    if not _enabled():
        # Dev without Supabase: pretend it saved (fail-open, no persistence)
        logger.info("operator_context save skipped (Supabase not configured)")
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
