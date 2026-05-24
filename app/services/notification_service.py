from datetime import datetime

from flask import current_app

from app.extensions import db
from app.models.notification import Notification
from app.models.user import User


def _property_id_for_user(user_id):
    user = User.query.get(user_id)
    if user is None:
        return None
    return user.property_id


def create_notification(
    user_id,
    title,
    message,
    notification_type="system",
    severity="info",
    action_url=None,
    property_id=None,
    push_payload=None,
):
    try:
        resolved_property_id = property_id
        if resolved_property_id is None:
            resolved_property_id = _property_id_for_user(user_id)

        notification = Notification(
            user_id=user_id,
            property_id=resolved_property_id,
            title=title,
            message=message,
            notification_type=notification_type,
            severity=severity,
            action_url=action_url,
            created_at=datetime.utcnow(),
            is_read=False,
        )
        db.session.add(notification)
        db.session.commit()

        if push_payload:
            try:
                from app.services.push_service import send_push_to_user

                send_push_to_user(user_id, push_payload)
            except Exception:
                current_app.logger.exception("Failed to send push notification for user_id=%s", user_id)
        return notification
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to create notification for user_id=%s", user_id)
        return None


def get_unread_count(user_id):
    try:
        property_id = _property_id_for_user(user_id)
        query = Notification.query.filter_by(user_id=user_id, is_read=False)
        if property_id is not None:
            query = query.filter_by(property_id=property_id)
        return int(query.count())
    except Exception:
        current_app.logger.exception("Failed to fetch unread notification count for user_id=%s", user_id)
        return 0


def get_recent_notifications(user_id, limit=10, notification_type=None):
    try:
        property_id = _property_id_for_user(user_id)
        query = Notification.query.filter_by(user_id=user_id)
        if property_id is not None:
            query = query.filter_by(property_id=property_id)
        if notification_type:
            query = query.filter_by(notification_type=notification_type)

        return (
            query.order_by(Notification.created_at.desc())
            .limit(limit)
            .all()
        )
    except Exception:
        current_app.logger.exception("Failed to fetch recent notifications for user_id=%s", user_id)
        return []


def mark_as_read(notification_id, user_id):
    try:
        property_id = _property_id_for_user(user_id)
        query = Notification.query.filter_by(id=notification_id, user_id=user_id)
        if property_id is not None:
            query = query.filter_by(property_id=property_id)

        notification = query.first()
        if notification is None:
            return False

        notification.is_read = True
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Failed to mark notification as read notification_id=%s user_id=%s",
            notification_id,
            user_id,
        )
        return False


def mark_all_read(user_id):
    try:
        property_id = _property_id_for_user(user_id)
        query = Notification.query.filter_by(user_id=user_id, is_read=False)
        if property_id is not None:
            query = query.filter_by(property_id=property_id)

        query.update({"is_read": True}, synchronize_session=False)
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to mark all notifications as read for user_id=%s", user_id)
        return False


def get_paginated_notifications(user_id, page=1, per_page=20, notification_type=None):
    try:
        property_id = _property_id_for_user(user_id)
        query = Notification.query.filter_by(user_id=user_id)
        if property_id is not None:
            query = query.filter_by(property_id=property_id)
        if notification_type:
            query = query.filter_by(notification_type=notification_type)

        return query.order_by(Notification.created_at.desc()).paginate(
            page=page,
            per_page=per_page,
            error_out=False,
        )
    except Exception:
        current_app.logger.exception("Failed to paginate notifications for user_id=%s", user_id)
        return Notification.query.filter_by(user_id=-1).paginate(
            page=page,
            per_page=per_page,
            error_out=False,
        )
