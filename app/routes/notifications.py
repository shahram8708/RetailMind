from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from app.extensions import db
from app.models.notification import Notification
from app.services import notification_service


notifications_bp = Blueprint("notifications", __name__)


ALLOWED_FILTERS = {
    "inventory_alert",
    "campaign_opportunity",
    "facility_alert",
    "agent_action",
    "system",
    "billing",
}


@notifications_bp.route("", methods=["GET"])
@notifications_bp.route("/", methods=["GET"])
@login_required
def index():
    page = request.args.get("page", 1, type=int)
    filter_type = request.args.get("type", None)

    if filter_type not in ALLOWED_FILTERS:
        filter_type = None

    notifications = notification_service.get_paginated_notifications(
        current_user.id,
        page=page,
        per_page=20,
        notification_type=filter_type,
    )
    unread_count = notification_service.get_unread_count(current_user.id)

    return render_template(
        "notifications/index.html",
        notifications=notifications,
        filter_type=filter_type,
        unread_count=unread_count,
    )


@notifications_bp.route("/<int:notif_id>/read", methods=["POST"])
@login_required
def mark_read(notif_id):
    success = notification_service.mark_as_read(notif_id, current_user.id)
    if success:
        return jsonify({"success": True, "data": {"notification_id": notif_id}}), 200
    return jsonify({"success": False, "error": "Notification not found"}), 404


@notifications_bp.route("/read-all", methods=["POST"])
@login_required
def mark_all_read():
    success = notification_service.mark_all_read(current_user.id)
    if success:
        return (
            jsonify(
                {
                    "success": True,
                    "message": "All notifications marked as read",
                    "data": {"updated": True},
                }
            ),
            200,
        )
    return jsonify({"success": False, "error": "Unable to update notifications"}), 500


@notifications_bp.route("/<int:notif_id>/delete", methods=["POST"])
@login_required
def delete_notification(notif_id):
    try:
        query = Notification.query.filter_by(id=notif_id, user_id=current_user.id)
        if current_user.property_id is not None:
            query = query.filter_by(property_id=current_user.property_id)

        notification = query.first()
        if notification is None:
            return jsonify({"success": False, "error": "Notification not found"}), 404

        db.session.delete(notification)
        db.session.commit()
        return jsonify({"success": True, "data": {"notification_id": notif_id}}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "error": "Unable to delete notification"}), 500
