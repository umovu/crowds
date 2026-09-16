"""The `subscriptions` table: one row per user, holding the plan and the free-tier counters.

This is the billing source of truth. The backend writes it with the service-role key
(which bypasses RLS); a user can only read their own row.

Every read answers with `None` rather than raising, because billing must fail open:
the service turns a missing answer into an allow-all entitlement, so a Supabase blip
never locks out a paying user. Deciding that is the service's job, not this module's.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..models.accounts import Subscription
from ..utils.logger import get_logger
from . import supabase

logger = get_logger("fub.repo.subscription")

TABLE = "subscriptions"

#: Asked for by name, so a new column cannot silently change what a read returns.
COUNTERS = "plan,panel_used,sim_used,status"


def get(user_id: str) -> Optional[Dict[str, Any]]:
    """The plan and counters for a user, or None when there is no row or the read failed.

    Returns the raw row: the caller needs to tell "no row" (create a default) from
    "could not ask" (fail open), and a partial select cannot build a whole Subscription.
    """
    if not supabase.enabled() or not user_id:
        return None
    try:
        rows = supabase.rows(supabase.select(
            TABLE, {"user_id": f"eq.{user_id}", "select": COUNTERS}))
    except Exception as e:  # noqa: BLE001 - billing reads never raise
        logger.warning("Entitlement lookup failed for %s: %s", user_id, e)
        return None
    return rows[0] if rows else {}


def create_default(user_id: str) -> Dict[str, Any]:
    """Give a user the free row they should have had. Returns what was written."""
    body = {"user_id": user_id, "plan": "free", "panel_used": 0, "sim_used": 0,
            "status": "active"}
    try:
        rows = supabase.rows(supabase.insert(
            TABLE, body, prefer="resolution=merge-duplicates,return=representation"))
        return rows[0] if rows else body
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not create default subscription for %s: %s", user_id, e)
        return body


def set_counter(user_id: str, column: str, value: int) -> None:
    """Write one usage counter. Never raises: a lost count must not fail a run."""
    if not supabase.enabled() or not user_id:
        return
    try:
        supabase.update(TABLE, {"user_id": f"eq.{user_id}"}, {column: value})
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not update %s for %s: %s", column, user_id, e)


def upsert_plan(user_id: str, body: Dict[str, Any]) -> None:
    """Upsert a user's plan row. Raises: a payment update that did not land must be seen."""
    supabase.insert(TABLE, {"user_id": user_id, **body},
                    prefer="resolution=merge-duplicates").raise_for_status()


def customer_code(user_id: str) -> str:
    """The stored Paystack customer code for a user, or ""."""
    if not supabase.enabled() or not user_id:
        return ""
    try:
        rows = supabase.rows(supabase.select(
            TABLE, {"user_id": f"eq.{user_id}", "select": "paystack_customer_code"}))
    except Exception as e:  # noqa: BLE001
        logger.warning("Customer-code lookup failed for %s: %s", user_id, e)
        return ""
    return (rows[0].get("paystack_customer_code") if rows else "") or ""


def find_by_customer(code: str) -> Optional[Dict[str, Any]]:
    """The row for a Paystack customer code, or None (used by the webhook)."""
    if not supabase.enabled() or not code:
        return None
    try:
        rows = supabase.rows(supabase.select(
            TABLE, {"paystack_customer_code": f"eq.{code}", "select": "user_id"}))
    except Exception as e:  # noqa: BLE001
        logger.warning("Lookup by customer %s failed: %s", code, e)
        return None
    return rows[0] if rows else None


def as_model(row: Dict[str, Any]) -> Optional[Subscription]:
    """A full row as a Subscription, or None when it no longer fits (logged, never raised)."""
    try:
        return Subscription.model_validate(row)
    except Exception as e:  # noqa: BLE001
        logger.warning("subscriptions row does not fit its model: %s", e)
        return None
