from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from app.extensions import db
from app.models.notification import PushSubscription
from app.services.push_service import send_push_to_user


push_bp = Blueprint("push", __name__)


@push_bp.route("/subscribe", methods=["POST"])
@login_required
def subscribe():
    payload = request.get_json(silent=True) or {}
    endpoint = payload.get("endpoint")
    keys = payload.get("keys") or {}
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")

    if not endpoint or not p256dh or not auth:
        return jsonify({"success": False, "error": "Invalid subscription payload"}), 400

    try:
        subscription = PushSubscription.query.filter_by(
            user_id=current_user.id,
            endpoint=endpoint,
        ).first()

        if subscription is None:
            subscription = PushSubscription(
                user_id=current_user.id,
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth,
                user_agent=request.headers.get("User-Agent"),
                is_active=True,
            )
            db.session.add(subscription)
        else:
            subscription.p256dh = p256dh
            subscription.auth = auth
            subscription.user_agent = request.headers.get("User-Agent")
            subscription.is_active = True

        db.session.commit()
        return jsonify({"success": True, "data": {"subscribed": True}}), 200
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to subscribe push notifications")
        return jsonify({"success": False, "error": "Unable to save subscription"}), 500


@push_bp.route("/unsubscribe", methods=["DELETE"])
@login_required
def unsubscribe():
    payload = request.get_json(silent=True) or {}
    endpoint = payload.get("endpoint")
    if not endpoint:
        return jsonify({"success": False, "error": "Endpoint required"}), 400

    try:
        subscription = PushSubscription.query.filter_by(
            user_id=current_user.id,
            endpoint=endpoint,
        ).first()
        if subscription is None:
            return jsonify({"success": True, "data": {"unsubscribed": True}}), 200

        subscription.is_active = False
        db.session.commit()
        return jsonify({"success": True, "data": {"unsubscribed": True}}), 200
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to unsubscribe push notifications")
        return jsonify({"success": False, "error": "Unable to unsubscribe"}), 500


@push_bp.route("/status", methods=["GET"])
@login_required
def status():
    active = (
        PushSubscription.query.filter_by(user_id=current_user.id, is_active=True)
        .count()
        > 0
    )
    return jsonify({"success": True, "data": {"active": active}}), 200


@push_bp.route("/test", methods=["POST"])
@login_required
def send_test():
    payload = {
        "title": "RetailMind Test Notification",
        "body": "Push notifications are enabled for your account.",
        "icon": "/static/img/offline-placeholder.svg",
        "badge": "/static/img/offline-placeholder.svg",
        "tag": "retailmind-test",
        "data": {"url": "/dashboard"},
        "actions": [
            {"action": "open", "title": "Open Dashboard"},
        ],
        "requireInteraction": False,
        "vibrate": [200, 100, 200],
    }

    ok = send_push_to_user(current_user.id, payload)
    return jsonify({"success": ok}), 200 if ok else 500


@push_bp.route("/notification-close", methods=["POST"])
@login_required
def notification_close():
    return ("", 204)
