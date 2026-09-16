"""The one place the app talks to Supabase.

Every table read and write goes through here, so the URL, the service-role key and
the headers are written once. Callers are repositories: they turn what comes back
into models and decide what a failure means.

This module answers with `requests.Response` and lets network errors raise. That is
deliberate — "what does a timeout mean here?" is a different answer for a billing
lookup (let the user through) than for a password reset (send nothing), so the
decision belongs to the repository, not to the transport.

Env:
  SUPABASE_URL                 https://<ref>.supabase.co
  SUPABASE_SERVICE_ROLE_KEY    server-side only; bypasses RLS, never shipped to a client
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests

TIMEOUT = 10


def url() -> str:
    return os.environ.get("SUPABASE_URL", "").rstrip("/")


def _key() -> str:
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def enabled() -> bool:
    """False in local dev with no Supabase configured. Callers must cope with that."""
    return bool(url() and _key())


def headers(prefer: Optional[str] = None) -> Dict[str, str]:
    key = _key()
    out = {"apikey": key,
           "Authorization": f"Bearer {key}",
           "Content-Type": "application/json"}
    if prefer:
        out["Prefer"] = prefer
    return out


# ── tables (PostgREST) ──────────────────────────────────────────────────────
def select(table: str, params: Dict[str, Any]) -> requests.Response:
    return requests.get(f"{url()}/rest/v1/{table}", params=params,
                        headers=headers(), timeout=TIMEOUT)


def insert(table: str, body: Any, prefer: Optional[str] = None) -> requests.Response:
    return requests.post(f"{url()}/rest/v1/{table}", json=body,
                         headers=headers(prefer), timeout=TIMEOUT)


def update(table: str, params: Dict[str, Any], body: Any,
           prefer: Optional[str] = None) -> requests.Response:
    return requests.patch(f"{url()}/rest/v1/{table}", params=params, json=body,
                          headers=headers(prefer), timeout=TIMEOUT)


# ── auth (GoTrue) ───────────────────────────────────────────────────────────
def auth_post(path: str, body: Any, params: Optional[Dict[str, Any]] = None) -> requests.Response:
    """A Supabase auth call, e.g. auth_post("recover", {"email": ...}).

    Auth endpoints take the key as `apikey` and no bearer token.
    """
    return requests.post(f"{url()}/auth/v1/{path.lstrip('/')}", json=body, params=params,
                         headers={"apikey": _key(), "Content-Type": "application/json"},
                         timeout=TIMEOUT)


def rows(resp: requests.Response) -> list:
    """The rows in a PostgREST response, or [] when it carried no list."""
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, list) else []
