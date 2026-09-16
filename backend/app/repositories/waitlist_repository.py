"""The `waitlist_requests` table: strangers asking for access.

Nothing here creates an auth user. A row is a request the operator reviews, so the
operator decides who ever gets an account.

Only the columns we actually write are sent. `id`, `status` and `created_at` are filled
in by Postgres, so building a whole WaitlistRequest on the way in would fail validation
for no reason; what comes back is validated instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..models.accounts import WaitlistRequest
from ..utils.logger import get_logger
from . import supabase

logger = get_logger("fub.repo.waitlist")

TABLE = "waitlist_requests"


@dataclass(frozen=True)
class Saved:
    """`ok` is whether the request is on file at all; `is_new` is False on a repeat."""
    ok: bool
    is_new: bool
    request: Optional[WaitlistRequest] = None


def add(email: str, full_name: str, note: str) -> Saved:
    """File a request. A repeat is a success, not a failure."""
    if not supabase.enabled():
        logger.error("Waitlist request received but Supabase is not configured")
        return Saved(ok=False, is_new=False)
    body = {"email": email, "full_name": full_name, "note": note}
    try:
        resp = supabase.insert(
            TABLE, body,
            # Re-applying must not error, and must not wipe an existing 'invited'
            # status either, so we only ever insert.
            prefer="resolution=ignore-duplicates,return=representation")
        # PostgREST cannot always infer the conflict target for ignore-duplicates and
        # answers 409 instead of swallowing it. Same meaning as an empty list below:
        # already queued.
        if resp.status_code == 409:
            return Saved(ok=True, is_new=False)
        rows = supabase.rows(resp)
    except Exception as e:  # noqa: BLE001
        logger.error("Could not save waitlist request for %s: %s", email, e)
        return Saved(ok=False, is_new=False)
    if not rows:
        return Saved(ok=True, is_new=False)
    return Saved(ok=True, is_new=True, request=_as_model(rows[0]))


def pending(limit: int = 100) -> List[WaitlistRequest]:
    """Requests the operator has not invited yet, oldest first."""
    if not supabase.enabled():
        return []
    try:
        rows = supabase.rows(supabase.select(
            TABLE, {"status": "eq.pending", "order": "created_at.asc",
                    "limit": str(limit), "select": "*"}))
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not list waitlist requests: %s", e)
        return []
    return [m for m in (_as_model(r) for r in rows) if m is not None]


def _as_model(row: dict) -> Optional[WaitlistRequest]:
    """The row as a model, or None when it no longer fits (logged, never raised)."""
    try:
        return WaitlistRequest.model_validate(row)
    except Exception as e:  # noqa: BLE001 - a drifted row must not break the request
        logger.warning("waitlist_requests row does not fit its model: %s", e)
        return None
