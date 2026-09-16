"""Plan status, Paystack checkout, and the Paystack webhook.

  GET  /api/billing/status    current plan + usage (drives the upgrade UI)
  POST /api/billing/checkout  start a Paystack payment, returns a redirect URL
  POST /api/billing/cancel    disable the user's Paystack subscription
  POST /api/billing/webhook   Paystack -> us; flips the plan on payment events
                              (auth-exempt; verified by HMAC signature instead)

The signature check and the raw-body read stay here: they are properties of the
request, not billing rules. Everything else is billing_service.
"""

import os

from flask import jsonify, request

from . import billing_bp
from ..auth import current_user_email, current_user_id
from ..services import billing_service
from ..utils.logger import get_logger

logger = get_logger("fub.controller.billing")


@billing_bp.route('/status', methods=['GET'])
def status():
    return jsonify({"success": True, "data": billing_service.status_for(current_user_id())})


@billing_bp.route('/checkout', methods=['POST'])
def checkout():
    email = current_user_email()
    if not email:
        return jsonify({"success": False, "error": "No email on account"}), 400
    if not billing_service.payments_configured():
        return jsonify({"success": False, "error": "Payments are not configured"}), 503
    data = request.get_json(silent=True) or {}
    callback_url = data.get("callback_url") or os.environ.get("BILLING_CALLBACK_URL", "")
    try:
        result = billing_service.start_checkout(email, current_user_id(), callback_url)
    except Exception as e:  # noqa: BLE001 - Paystack is someone else's uptime
        logger.error("Paystack init failed: %s", e)
        return jsonify({"success": False, "error": "Could not start checkout"}), 502
    return jsonify({"success": True, "data": {
        "authorization_url": result.get("authorization_url"),
        "reference": result.get("reference"),
    }})


@billing_bp.route('/cancel', methods=['POST'])
def cancel():
    user_id = current_user_id()
    if not billing_service.payments_configured():
        return jsonify({"success": False, "error": "Payments are not configured"}), 503
    customer = billing_service.get_customer_code(user_id)
    if not customer:
        return jsonify({"success": False, "error": "No active subscription found"}), 404
    try:
        cancelled = billing_service.cancel_subscription(customer)
    except Exception as e:  # noqa: BLE001
        logger.error("Paystack cancel failed: %s", e)
        return jsonify({"success": False, "error": "Could not cancel subscription"}), 502
    if not cancelled:
        return jsonify({"success": False, "error": "No active subscription found"}), 404
    # Mark cancelled but keep access until the period ends; the webhook
    # (subscription.disable) downgrades to free at the end of the cycle.
    try:
        billing_service.set_plan(user_id, "paid", status="cancelled")
    except Exception as e:  # noqa: BLE001
        logger.warning("Cancelled at Paystack but the local status update failed: %s", e)
    return jsonify({"success": True, "data": {"status": "cancelled"}})


@billing_bp.route('/webhook', methods=['POST'])
def webhook():
    raw = request.get_data()
    signature = request.headers.get("x-paystack-signature", "")
    if not billing_service.verify_paystack_signature(raw, signature):
        return jsonify({"success": False, "error": "bad signature"}), 401

    event = request.get_json(silent=True) or {}
    try:
        billing_service.apply_webhook(event.get("event"), event.get("data") or {})
    except Exception as e:  # noqa: BLE001
        logger.error("Webhook handling failed (%s): %s", event.get("event"), e)
        return jsonify({"success": False}), 500
    return jsonify({"success": True}), 200
