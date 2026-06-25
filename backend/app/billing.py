"""
Billing & entitlements — Supabase-backed plans, Paystack payments.

Source of truth is the `subscriptions` table in Supabase (one row per user,
keyed by the auth user id). The backend reads/writes it with the service-role
key (which bypasses RLS); clients can only read their own row.

Plans:
  free  — 1 panel, no simulations
  paid  — unlimited panels + simulations

Enforcement is fail-open: if SUPABASE_SERVICE_ROLE_KEY isn't set (billing not
configured) or a lookup errors, callers are treated as allowed, so the app
still runs in local/dev and a billing blip never locks paying users out.

Env:
  SUPABASE_URL                  (already used for auth)
  SUPABASE_SERVICE_ROLE_KEY     secret key — server-side only, never shipped
  PAYSTACK_SECRET_KEY           sk_... from Paystack
  PAYSTACK_PLAN_CODE            monthly plan code (recommended)
  PAYSTACK_AMOUNT / PAYSTACK_CURRENCY  one-off fallback if no plan code
  BILLING_CALLBACK_URL          where Paystack redirects after payment
"""

import os
import hmac
import hashlib
import logging

import requests
from flask import g, jsonify

logger = logging.getLogger("fub.billing")

FREE_PANEL_LIMIT = 1
PAYSTACK_BASE = "https://api.paystack.co"


# ── Config helpers ──────────────────────────────────────────────────────────
def _service_key() -> str:
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def _supabase_url() -> str:
    return os.environ.get("SUPABASE_URL", "").rstrip("/")


def _paystack_secret() -> str:
    return os.environ.get("PAYSTACK_SECRET_KEY", "")


def billing_enabled() -> bool:
    return bool(_service_key() and _supabase_url())


def _rest_headers() -> dict:
    key = _service_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def current_user_id():
    user = getattr(g, "user", None)
    return user.get("sub") if user else None


def current_user_email():
    user = getattr(g, "user", None)
    return user.get("email") if user else None


# ── Entitlements (Supabase subscriptions table) ─────────────────────────────
def get_entitlement(user_id) -> dict:
    """Return {'plan', 'panel_used', 'status'} for a user.

    Fail-open: returns an allow-all ('paid') entitlement when billing isn't
    configured or a lookup errors. Creates a default free row when missing.
    """
    if not billing_enabled() or not user_id:
        return {"plan": "paid", "panel_used": 0, "status": "active"}
    url = f"{_supabase_url()}/rest/v1/subscriptions"
    try:
        resp = requests.get(
            url,
            params={"user_id": f"eq.{user_id}", "select": "plan,panel_used,status"},
            headers=_rest_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
        if rows:
            return rows[0]
        return _create_default(user_id)
    except Exception as e:
        logger.warning("Entitlement lookup failed for %s: %s (failing open)", user_id, e)
        return {"plan": "paid", "panel_used": 0, "status": "active"}


def _create_default(user_id) -> dict:
    url = f"{_supabase_url()}/rest/v1/subscriptions"
    body = {"user_id": user_id, "plan": "free", "panel_used": 0, "status": "active"}
    try:
        resp = requests.post(
            url,
            json=body,
            headers={**_rest_headers(),
                     "Prefer": "resolution=merge-duplicates,return=representation"},
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if rows else body
    except Exception as e:
        logger.warning("Could not create default subscription for %s: %s", user_id, e)
        return body


def increment_panel_used(user_id) -> None:
    if not billing_enabled() or not user_id:
        return
    ent = get_entitlement(user_id)
    new_count = int(ent.get("panel_used", 0) or 0) + 1
    try:
        requests.patch(
            f"{_supabase_url()}/rest/v1/subscriptions",
            params={"user_id": f"eq.{user_id}"},
            json={"panel_used": new_count},
            headers=_rest_headers(),
            timeout=10,
        )
    except Exception as e:
        logger.warning("Could not increment panel_used for %s: %s", user_id, e)


def set_plan(user_id, plan: str, **extra) -> None:
    """Upsert a user's plan. Used by the Paystack webhook."""
    body = {"user_id": user_id, "plan": plan, **extra}
    resp = requests.post(
        f"{_supabase_url()}/rest/v1/subscriptions",
        json=body,
        headers={**_rest_headers(), "Prefer": "resolution=merge-duplicates"},
        timeout=10,
    )
    resp.raise_for_status()


def get_customer_code(user_id):
    """Return the stored Paystack customer code for a user (or '')."""
    if not billing_enabled() or not user_id:
        return ""
    try:
        resp = requests.get(
            f"{_supabase_url()}/rest/v1/subscriptions",
            params={"user_id": f"eq.{user_id}", "select": "paystack_customer_code"},
            headers=_rest_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
        return (rows[0].get("paystack_customer_code") if rows else "") or ""
    except Exception as e:
        logger.warning("Customer-code lookup failed for %s: %s", user_id, e)
        return ""


def get_user_by_customer(customer_code: str):
    """Find a subscription row by Paystack customer code (for downgrades)."""
    if not billing_enabled() or not customer_code:
        return None
    try:
        resp = requests.get(
            f"{_supabase_url()}/rest/v1/subscriptions",
            params={"paystack_customer_code": f"eq.{customer_code}", "select": "user_id"},
            headers=_rest_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if rows else None
    except Exception as e:
        logger.warning("Lookup by customer %s failed: %s", customer_code, e)
        return None


# ── Enforcement (call at the top of a route; returns a response or None) ─────
def require_paid():
    ent = get_entitlement(current_user_id())
    if ent.get("plan") != "paid":
        return jsonify({
            "success": False,
            "error": "Simulations are a paid feature. Upgrade to run simulations.",
            "code": "upgrade_required",
        }), 402
    return None


def check_panel_quota():
    ent = get_entitlement(current_user_id())
    if ent.get("plan") == "paid":
        return None
    if int(ent.get("panel_used", 0) or 0) >= FREE_PANEL_LIMIT:
        return jsonify({
            "success": False,
            "error": (f"The free plan includes {FREE_PANEL_LIMIT} panel. "
                      "Upgrade for unlimited panels and simulations."),
            "code": "upgrade_required",
        }), 402
    return None


# ── Paystack ─────────────────────────────────────────────────────────────────
def paystack_init_transaction(email: str, user_id, callback_url: str) -> dict:
    """Initialize a Paystack transaction; returns data incl. authorization_url."""
    body = {
        "email": email,
        "metadata": {"user_id": user_id},
    }
    if callback_url:
        body["callback_url"] = callback_url
    # Paystack's transaction/initialize requires an amount even when a plan is
    # supplied — plan-only returns "Invalid Amount Sent". (minor units: R80 = 8000)
    body["amount"] = int(os.environ.get("PAYSTACK_AMOUNT", "8000"))
    plan_code = os.environ.get("PAYSTACK_PLAN_CODE", "")
    if plan_code:
        body["plan"] = plan_code
    else:
        body["currency"] = os.environ.get("PAYSTACK_CURRENCY", "ZAR")
    resp = requests.post(
        f"{PAYSTACK_BASE}/transaction/initialize",
        json=body,
        headers={"Authorization": f"Bearer {_paystack_secret()}",
                 "Content-Type": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["data"]


def paystack_cancel_subscription(customer_code: str) -> bool:
    """Disable the customer's active Paystack subscription (stops future billing).

    Paystack's /subscription/disable needs the subscription's `code` and
    `email_token`, which we look up live from the customer. Returns True if a
    subscription was found and disabled. Paystack then fires
    `subscription.not_renew` (access runs to period end) and, at the end of the
    cycle, `subscription.disable` (handled by the webhook).
    """
    secret = _paystack_secret()
    if not secret or not customer_code:
        return False
    headers = {"Authorization": f"Bearer {secret}",
               "Content-Type": "application/json"}
    # Find the customer's subscription(s).
    resp = requests.get(
        f"{PAYSTACK_BASE}/subscription",
        params={"customer": customer_code},
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    subs = resp.json().get("data", []) or []
    # Prefer an active subscription; fall back to the first returned.
    target = next((s for s in subs if s.get("status") == "active"), None) \
        or (subs[0] if subs else None)
    if not target:
        return False
    code = target.get("subscription_code")
    token = target.get("email_token")
    if not code or not token:
        return False
    dis = requests.post(
        f"{PAYSTACK_BASE}/subscription/disable",
        json={"code": code, "token": token},
        headers=headers,
        timeout=15,
    )
    dis.raise_for_status()
    return True


def verify_paystack_signature(raw_body: bytes, signature: str) -> bool:
    secret = _paystack_secret().encode()
    computed = hmac.new(secret, raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(computed, signature or "")
