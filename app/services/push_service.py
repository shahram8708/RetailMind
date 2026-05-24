import json

from flask import current_app
from pywebpush import WebPushException, webpush

from app.extensions import db
from app.models.notification import PushSubscription


def _build_vapid_claims():
    subject = current_app.config.get("VAPID_SUBJECT")
    return {"sub": subject} if subject else {}


def send_push_to_user(user_id, payload):
    if not current_app.config.get("PUSH_NOTIFICATIONS_ENABLED"):
        return False

    subscriptions = PushSubscription.query.filter_by(user_id=user_id, is_active=True).all()
    if not subscriptions:
        return False

    vapid_private_key = current_app.config.get("VAPID_PRIVATE_KEY")
    vapid_claims = _build_vapid_claims()

    delivered = False
    for subscription in subscriptions:
        info = {
            "endpoint": subscription.endpoint,
            "keys": {
                "p256dh": subscription.p256dh,
                "auth": subscription.auth,
            },
        }

        try:
            webpush(
                subscription_info=info,
                data=json.dumps(payload),
                vapid_private_key=vapid_private_key,
                vapid_claims=vapid_claims,
            )
            delivered = True
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in {404, 410}:
                subscription.is_active = False
                db.session.add(subscription)
            current_app.logger.warning("Push send failed for user_id=%s status=%s", user_id, status)
        except Exception:
            current_app.logger.exception("Push send failed for user_id=%s", user_id)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    return delivered
