import hashlib
import hmac
import os
import time

import razorpay


PLAN_PRICES_INR = {
    "starter": {"monthly": 49999, "annual": 39999},
    "professional": {"monthly": 149999, "annual": 119999},
    "enterprise": {"monthly": None, "annual": None},
}

PLAN_DISPLAY_NAMES = {
    "starter": "RetailMind Starter",
    "professional": "RetailMind Professional",
    "enterprise": "RetailMind Enterprise",
}


def get_razorpay_client():
    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise ValueError("Razorpay credentials not configured in .env")
    return razorpay.Client(auth=(key_id, key_secret))


def create_order(amount_inr, plan_name, property_id, billing_cycle="monthly"):
    try:
        amount_paise = int(float(amount_inr) * 100)
        receipt_id = f"rm_prop_{property_id}_{plan_name}_{billing_cycle}_{int(time.time())}"
        order_data = {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt_id[:40],
            "notes": {
                "property_id": str(property_id),
                "plan_name": str(plan_name),
                "billing_cycle": str(billing_cycle),
                "platform": "RetailMind",
            },
        }
        client = get_razorpay_client()
        return client.order.create(data=order_data)
    except Exception as exc:
        raise Exception(f"Failed to create Razorpay order: {exc}") from exc


def verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")
    if not key_secret:
        raise ValueError("Razorpay key secret not configured")

    message = f"{razorpay_order_id}|{razorpay_payment_id}"
    expected_signature = hmac.new(
        key_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_signature, razorpay_signature)


def get_payment_details(razorpay_payment_id):
    try:
        client = get_razorpay_client()
        return client.payment.fetch(razorpay_payment_id)
    except Exception:
        return None
