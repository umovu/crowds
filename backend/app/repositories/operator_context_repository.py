"""The `operator_context` table: one saved "about my business" block per user.

Supabase when it is configured, a JSON file under DATA_ROOT otherwise. The fallback
is not a nicety: without it a local save reported success and stored nothing, so the
feature could not be looked at without a hosted database.

Reads fail open — any error returns "" and the run proceeds unbriefed. Writes raise,
because a user who typed something and pressed save must be told if it did not land.

This module stores and returns the raw body only. The prompt wording lives in
`mode_specs.build_operator_context_block`, one copy shared by the panel and sim
paths; a second copy here would drift.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from ..config import Config
from ..models.accounts import OperatorContext
from ..utils.logger import get_logger
from . import supabase

logger = get_logger("fub.repo.operator_context")

TABLE = "operator_context"
MAX_LEN = 1500


# ── local fallback (no Supabase configured) ─────────────────────────────────
def _local_path() -> str:
    return os.path.join(Config.DATA_ROOT, "operator_context.json")


def _local_all() -> Dict[str, str]:
    try:
        with open(_local_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 - a missing or broken file is simply empty
        return {}


def _local_save(user_id: str, body: str) -> None:
    data = _local_all()
    data[user_id] = body
    path = _local_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


# ── the table ───────────────────────────────────────────────────────────────
def get(user_id: str) -> str:
    """The raw body for a user, or "" when there is none or the lookup failed."""
    if not user_id:
        return ""
    if not supabase.enabled():
        return (_local_all().get(user_id) or "").strip()[:MAX_LEN]
    try:
        rows = supabase.rows(supabase.select(
            TABLE, {"user_id": f"eq.{user_id}", "select": "body"}))
    except Exception as e:  # noqa: BLE001 - reads fail open, see the docstring
        logger.warning("operator context read failed for %s: %s (failing open)", user_id, e)
        return ""
    if rows and rows[0].get("body"):
        return (rows[0]["body"] or "").strip()[:MAX_LEN]
    return ""


def save(user_id: str, body: str) -> Dict[str, Any]:
    """Upsert a user's context and return the saved row. Raises if it did not land."""
    if not user_id:
        raise ValueError("user_id is required")
    cleaned = (body or "").strip()[:MAX_LEN]
    if not supabase.enabled():
        _local_save(user_id, cleaned)
        return {"user_id": user_id, "body": cleaned, "updated_at": None}
    try:
        rows = supabase.rows(supabase.insert(
            TABLE, {"user_id": user_id, "body": cleaned},
            prefer="resolution=merge-duplicates,return=representation"))
    except Exception as e:  # noqa: BLE001 - re-raised: the user must be told
        logger.error("operator context save failed for %s: %s", user_id, e)
        raise
    if not rows:
        return {"user_id": user_id, "body": cleaned}
    row = rows[0]
    try:
        OperatorContext.model_validate(row)
    except Exception as e:  # noqa: BLE001 - a drifted row still saved; say so
        logger.warning("operator_context row does not fit its model: %s", e)
    return row
