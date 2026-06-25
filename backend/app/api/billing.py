"""
Billing API — plan status, Paystack checkout, and the Paystack webhook.

  GET  /api/billing/status    current plan + usage (drives the upgrade UI)
  POST /api/billing/checkout  start a Paystack payment, returns a redirect URL
  POST /api/billing/cancel    disable the user's Paystack subscription
  POST /api/billing/webhook   Paystack -> us; flips plan on payment events
                              (auth-exempt; verified via HMAC signature instead)
"""

import os

from flask import jsonify, request

from . import billing_bp
from .. import billing
from ..utils.logger import get_logger

logger = get_logger("fub.api.billing")


@billing_bp.route('/status', methods=['GET'])
def status():
    uid = billing.current_user_id()
    ent = billing.get_entitlement(uid)
    plan = ent.get("plan", "free")
    panel_used = int(ent.get("panel_used", 0) or 0)
    return jsonify({"success": True, "data": {
        "plan": plan,
        "status": ent.get("status", "active"),
        "panel_used": panel_used,
        "panel_limit": billing.FREE_PANEL_LIMIT if plan != "paid" else None,
        "can_simulate": plan == "paid",
        "can_create_panel": plan == "paid" or panel_used < billing.FREE_PANEL_LIMIT,
    }})


@billing_bp.route('/checkout', methods=['POST'])
def checkout():
    uid = billing.current_user_id()
    email = billing.current_user_email()
    if not email:
        return jsonify({"success": False, "error": "No email on account"}), 400
    if not billing._paystack_secret():
        return jsonify({"success": False, "error": "Payments are not configured"}), 503
    data = request.get_json(silent=True) or {}
    callback_url = data.get("callback_url") or os.environ.get("BILLING_CALLBACK_URL", "")
    try:
        result = billing.paystack_init_transaction(email, uid, callback_url)
        return jsonify({"success": True, "data": {
            "authorization_url": result.get("authorization_url"),
            "reference": result.get("reference"),
        }})
    except Exception as e:
        logger.error("Paystack init failed: %s", e)
        return jsonify({"success": False, "error": "Could not start checkout"}), 502


@billing_bp.route('/cancel', methods=['POST'])
def cancel():
    uid = billing.current_user_id()
    if not billing._paystack_secret():
        return jsonify({"success": False, "error": "Payments are not configured"}), 503
    customer = billing.get_customer_code(uid)
    if not customer:
        return jsonify({"success": False, "error": "No active subscription found"}), 404
    try:
        ok = billing.paystack_cancel_subscription(customer)
    except Exception as e:
        logger.error("Paystack cancel failed: %s", e)
        return jsonify({"success": False, "error": "Could not cancel subscription"}), 502
    if not ok:
        return jsonify({"success": False, "error": "No active subscription found"}), 404
    # Mark cancelled but keep access until the period ends; the webhook
    # (subscription.disable) downgrades to free at the end of the cycle.
    try:
        billing.set_plan(uid, "paid", status="cancelled")
    except Exception as e:
        logger.warning("Cancel succeeded at Paystack but local status update failed: %s", e)
    return jsonify({"success": True, "data": {"status": "cancelled"}})


@billing_bp.route('/webhook', methods=['POST'])
def webhook():
    raw = request.get_data()
    sig = request.headers.get("x-paystack-signature", "")
    if not billing.verify_paystack_signature(raw, sig):
        return jsonify({"success": False, "error": "bad signature"}), 401

    event = request.get_json(silent=True) or {}
    etype = event.get("event")
    data = event.get("data", {}) or {}
    try:
        if etype == "charge.success":
            uid = (data.get("metadata") or {}).get("user_id")
            customer = (data.get("customer") or {}).get("customer_code")
            if uid:
                billing.set_plan(uid, "paid", status="active",
                                 paystack_customer_code=customer)
                logger.info("Upgraded user %s to paid", uid)
        elif etype == "subscription.not_renew":
            # Cancellation requested — won't renew, but keep access until the
            # current paid cycle ends (Paystack fires subscription.disable then).
            customer = (data.get("customer") or {}).get("customer_code")
            row = billing.get_user_by_customer(customer)
            if row:
                billing.set_plan(row["user_id"], "paid", status="cancelled")
                logger.info("Marked user %s non-renewing (%s)", row["user_id"], etype)
        elif etype in ("subscription.disable", "invoice.payment_failed"):
            # Cycle ended (or renewal failed) — drop to free.
            customer = (data.get("customer") or {}).get("customer_code")
            row = billing.get_user_by_customer(customer)
            if row:
                billing.set_plan(row["user_id"], "free", status="cancelled")
                logger.info("Downgraded user %s to free (%s)", row["user_id"], etype)
    except Exception as e:
        logger.error("Webhook handling failed (%s): %s", etype, e)
        return jsonify({"success": False}), 500
    return jsonify({"success": True}), 200
