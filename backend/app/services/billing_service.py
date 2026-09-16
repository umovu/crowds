"""What a user is allowed to run, and what they have used.

Plans:
  free  — a few panels and a short simulation trial
  paid  — unlimited panels and simulations

Enforcement fails open. If Supabase is not configured, or a lookup errors, the caller
is treated as paid: the app still runs in local dev, and a billing blip never locks a
paying user out. Only a row that actually says "free" with the trial spent blocks
anything.

No Flask here. The quota checks answer with a `Gate` and the controller turns a refusal
into a 402 — so the rules can be tested without a request in flight.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

from ..repositories import subscription_repository
from ..utils.logger import get_logger

logger = get_logger("fub.billing")

FREE_PANEL_LIMIT = 4
# Closed-beta trial: the free plan may run this many simulations before the paywall.
# Lets us hand out access for user testing while Paystack approval is pending.
FREE_SIM_LIMIT = 2

PAYSTACK_BASE = "https://api.paystack.co"

#: What a caller gets when billing cannot be consulted: everything allowed.
ALLOW_ALL = {"plan": "paid", "panel_used": 0, "sim_used": 0, "status": "active"}


@dataclass(frozen=True)
class Gate:
    """A quota decision. `allowed` is the answer; `message` is why not."""
    allowed: bool
    message: str = ""
    code: str = "upgrade_required"


def _paystack_secret() -> str:
    return os.environ.get("PAYSTACK_SECRET_KEY", "")


def payments_configured() -> bool:
    return bool(_paystack_secret())


# ── entitlements ────────────────────────────────────────────────────────────
def get_entitlement(user_id) -> Dict[str, Any]:
    """{'plan', 'panel_used', 'sim_used', 'status'} for a user. Fails open."""
    row = subscription_repository.get(user_id)
    if row is None:
        return dict(ALLOW_ALL)          # no Supabase, or the lookup failed
    if row == {}:
        return subscription_repository.create_default(user_id)
    return row


def _used(user_id, column: str) -> int:
    return int(get_entitlement(user_id).get(column, 0) or 0)


def increment_panel_used(user_id) -> None:
    subscription_repository.set_counter(user_id, "panel_used", _used(user_id, "panel_used") + 1)


def increment_sim_used(user_id) -> None:
    subscription_repository.set_counter(user_id, "sim_used", _used(user_id, "sim_used") + 1)


def set_plan(user_id, plan: str, **extra) -> None:
    """Upsert a user's plan. Used by the Paystack webhook."""
    body = {"plan": plan, **extra}
    # Callers pass free-form keyword columns. A misspelt one fails at the database; a
    # plan or status the app does not know saves fine and silently changes who can do
    # what, so the row is checked first and the mismatch logged.
    try:
        from . import data_model
        problems = data_model.row_problems("subscription", {"user_id": user_id, **body})
    except Exception as e:  # noqa: BLE001 — a check must never block a payment update
        problems = [f"could not check: {e}"]
    if problems:
        logger.warning("Subscription write does not match its data model: %s",
                       "; ".join(problems[:3]))
    subscription_repository.upsert_plan(user_id, body)


def get_customer_code(user_id) -> str:
    return subscription_repository.customer_code(user_id)


def get_user_by_customer(code: str) -> Optional[Dict[str, Any]]:
    return subscription_repository.find_by_customer(code)


# ── quota gates ─────────────────────────────────────────────────────────────
def check_sim_quota(user_id) -> Gate:
    """Gate a simulation. Paid = unlimited; free = FREE_SIM_LIMIT trial runs."""
    ent = get_entitlement(user_id)
    if ent.get("plan") == "paid":
        return Gate(True)
    if int(ent.get("sim_used", 0) or 0) >= FREE_SIM_LIMIT:
        plural = "" if FREE_SIM_LIMIT == 1 else "s"
        return Gate(False, f"Your free trial of {FREE_SIM_LIMIT} simulation{plural} is "
                           "used up. Upgrade for unlimited simulations.")
    return Gate(True)


def check_panel_quota(user_id) -> Gate:
    """Gate a panel. Paid = unlimited; free = FREE_PANEL_LIMIT panels."""
    ent = get_entitlement(user_id)
    if ent.get("plan") == "paid":
        return Gate(True)
    if int(ent.get("panel_used", 0) or 0) >= FREE_PANEL_LIMIT:
        plural = "" if FREE_PANEL_LIMIT == 1 else "s"
        return Gate(False, f"The free plan includes {FREE_PANEL_LIMIT} panel{plural}. "
                           "Upgrade for unlimited panels and simulations.")
    return Gate(True)


def status_for(user_id) -> Dict[str, Any]:
    """What the upgrade UI shows: the plan, the counters and what is still allowed."""
    ent = get_entitlement(user_id)
    plan = ent.get("plan", "free")
    panel_used = int(ent.get("panel_used", 0) or 0)
    sim_used = int(ent.get("sim_used", 0) or 0)
    paid = plan == "paid"
    return {
        "plan": plan,
        "status": ent.get("status", "active"),
        "panel_used": panel_used,
        "panel_limit": None if paid else FREE_PANEL_LIMIT,
        "sim_used": sim_used,
        "sim_limit": None if paid else FREE_SIM_LIMIT,
        "can_simulate": paid or sim_used < FREE_SIM_LIMIT,
        "can_create_panel": paid or panel_used < FREE_PANEL_LIMIT,
    }


# ── Paystack ────────────────────────────────────────────────────────────────
def start_checkout(email: str, user_id, callback_url: str) -> Dict[str, Any]:
    """Initialize a Paystack transaction; returns its data incl. authorization_url."""
    body: Dict[str, Any] = {"email": email, "metadata": {"user_id": user_id}}
    if callback_url:
        body["callback_url"] = callback_url
    # transaction/initialize requires an amount even when a plan is supplied —
    # plan-only answers "Invalid Amount Sent". Minor units: R80 = 8000.
    body["amount"] = int(os.environ.get("PAYSTACK_AMOUNT", "8000"))
    plan_code = os.environ.get("PAYSTACK_PLAN_CODE", "")
    if plan_code:
        body["plan"] = plan_code
    else:
        body["currency"] = os.environ.get("PAYSTACK_CURRENCY", "ZAR")
    resp = requests.post(f"{PAYSTACK_BASE}/transaction/initialize", json=body,
                         headers=_paystack_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json()["data"]


def cancel_subscription(customer_code: str) -> bool:
    """Disable the customer's active Paystack subscription, stopping future billing.

    Paystack's /subscription/disable needs the subscription's `code` and `email_token`,
    looked up live from the customer. True when one was found and disabled. Paystack
    then fires `subscription.not_renew` (access runs to period end) and, at the end of
    the cycle, `subscription.disable` (handled by the webhook).
    """
    if not payments_configured() or not customer_code:
        return False
    resp = requests.get(f"{PAYSTACK_BASE}/subscription", params={"customer": customer_code},
                        headers=_paystack_headers(), timeout=15)
    resp.raise_for_status()
    subs = resp.json().get("data", []) or []
    target = next((s for s in subs if s.get("status") == "active"), None) \
        or (subs[0] if subs else None)
    if not target:
        return False
    code, token = target.get("subscription_code"), target.get("email_token")
    if not code or not token:
        return False
    done = requests.post(f"{PAYSTACK_BASE}/subscription/disable",
                         json={"code": code, "token": token},
                         headers=_paystack_headers(), timeout=15)
    done.raise_for_status()
    return True


def verify_paystack_signature(raw_body: bytes, signature: str) -> bool:
    computed = hmac.new(_paystack_secret().encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(computed, signature or "")


def apply_webhook(event_type: str, data: Dict[str, Any]) -> None:
    """Move a user's plan in response to a Paystack event."""
    customer = (data.get("customer") or {}).get("customer_code")
    if event_type == "charge.success":
        user_id = (data.get("metadata") or {}).get("user_id")
        if user_id:
            set_plan(user_id, "paid", status="active", paystack_customer_code=customer)
            logger.info("Upgraded user %s to paid", user_id)
    elif event_type == "subscription.not_renew":
        # Cancellation requested: will not renew, but access runs to the end of the
        # paid cycle (Paystack fires subscription.disable then).
        row = get_user_by_customer(customer)
        if row:
            set_plan(row["user_id"], "paid", status="cancelled")
            logger.info("Marked user %s non-renewing (%s)", row["user_id"], event_type)
    elif event_type in ("subscription.disable", "invoice.payment_failed"):
        row = get_user_by_customer(customer)
        if row:
            set_plan(row["user_id"], "free", status="cancelled")
            logger.info("Downgraded user %s to free (%s)", row["user_id"], event_type)


def _paystack_headers() -> Dict[str, str]:
    return {"Authorization": f"Bearer {_paystack_secret()}",
            "Content-Type": "application/json"}
