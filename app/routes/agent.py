import csv
from datetime import date, datetime, timedelta
import io

from flask import Blueprint, Response, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models.agent import AgentAction, AgentConfiguration
from app.models.property import MallProperty
from app.services import email_service
from app.services.notification_service import create_notification


agent_bp = Blueprint("agent", __name__)


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def _build_filtered_logs_query(property_id, args):
    mission_type = (args.get("mission_type", "all") or "all").strip().lower()
    status_filter = (args.get("status", "all") or "all").strip().lower()
    date_from = (args.get("date_from", "") or "").strip()
    date_to = (args.get("date_to", "") or "").strip()
    score_min = args.get("score_min", 0.0, type=float) or 0.0

    query = AgentAction.query.filter_by(property_id=property_id)

    if mission_type != "all":
        query = query.filter(AgentAction.mission_type == mission_type)

    if status_filter != "all":
        query = query.filter(AgentAction.status == status_filter)

    date_from_dt = _parse_date(date_from)
    if date_from_dt:
        query = query.filter(AgentAction.created_at >= date_from_dt)

    date_to_dt = _parse_date(date_to)
    if date_to_dt:
        query = query.filter(AgentAction.created_at <= date_to_dt + timedelta(days=1))

    if score_min > 0:
        query = query.filter(AgentAction.score >= score_min)

    return query.order_by(AgentAction.created_at.desc()), {
        "mission_type": mission_type,
        "status": status_filter,
        "date_from": date_from,
        "date_to": date_to,
        "score_min": score_min,
    }


def _summary_stats(property_id):
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_actions_month = AgentAction.query.filter(
        AgentAction.property_id == property_id,
        AgentAction.created_at >= month_start,
    ).count()

    resolved_actions = AgentAction.query.filter(
        AgentAction.property_id == property_id,
        AgentAction.created_at >= month_start,
        AgentAction.status.in_(["approved", "rejected", "auto_executed", "failed"]),
    ).all()

    approved_count = sum(
        1
        for action in resolved_actions
        if action.status in {"approved", "auto_executed"}
    )

    approval_rate = (approved_count / len(resolved_actions) * 100.0) if resolved_actions else 0.0

    resolution_durations = [
        (action.resolved_at - action.created_at).total_seconds() / 3600.0
        for action in resolved_actions
        if action.resolved_at and action.created_at
    ]

    avg_resolution_hours = (
        sum(resolution_durations) / len(resolution_durations)
        if resolution_durations
        else 0.0
    )

    auto_executed_count = AgentAction.query.filter(
        AgentAction.property_id == property_id,
        AgentAction.created_at >= month_start,
        AgentAction.status == "auto_executed",
    ).count()

    return {
        "total_actions_month": total_actions_month,
        "approval_rate": approval_rate,
        "avg_resolution_hours": avg_resolution_hours,
        "auto_executed_count": auto_executed_count,
    }


@agent_bp.route("/logs", methods=["GET"])
@login_required
def logs():
    property_id = current_user.property_id
    if not property_id:
        return redirect(url_for("dashboard.index"))

    query, filters = _build_filtered_logs_query(property_id, request.args)
    page = request.args.get("page", 1, type=int)
    pagination = query.paginate(page=page, per_page=25, error_out=False)

    stats = _summary_stats(property_id)

    return render_template(
        "agent/logs.html",
        pagination=pagination,
        filters=filters,
        total_actions_month=stats["total_actions_month"],
        approval_rate=stats["approval_rate"],
        avg_resolution_hours=stats["avg_resolution_hours"],
        auto_executed_count=stats["auto_executed_count"],
    )


@agent_bp.route("/logs/export", methods=["GET"])
@login_required
def export_logs():
    property_id = current_user.property_id
    if not property_id:
        return redirect(url_for("dashboard.index"))

    query, _filters = _build_filtered_logs_query(property_id, request.args)
    actions = query.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Log ID",
            "Timestamp",
            "Mission Type",
            "Action Type",
            "Description",
            "Entity ID",
            "Score",
            "Status",
            "Approved By",
            "Agent Reasoning",
            "Created At",
            "Resolved At",
        ]
    )

    for action in actions:
        writer.writerow(
            [
                action.id,
                action.created_at.isoformat() if action.created_at else "",
                action.mission_type,
                action.action_type,
                action.description,
                action.entity_id,
                action.score,
                action.status,
                action.approved_by.full_name if action.approved_by else "",
                action.agent_reasoning,
                action.created_at.isoformat() if action.created_at else "",
                action.resolved_at.isoformat() if action.resolved_at else "",
            ]
        )

    filename = f"RetailMind_AgentLogs_{date.today().strftime('%Y%m%d')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@agent_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    property_id = current_user.property_id
    if not property_id:
        return redirect(url_for("dashboard.index"))

    property_record = MallProperty.query.filter_by(id=property_id).first()

    agent_config = AgentConfiguration.query.filter_by(property_id=property_id).first()
    if agent_config is None:
        agent_config = AgentConfiguration(property_id=property_id)
        db.session.add(agent_config)
        db.session.commit()

    if request.method == "POST":
        inventory_mission_enabled = "inventory_mission_enabled" in request.form
        campaign_mission_enabled = "campaign_mission_enabled" in request.form
        facility_mission_enabled = "facility_mission_enabled" in request.form
        shopper_mission_enabled = "shopper_mission_enabled" in request.form

        inventory_srs_threshold = request.form.get("inventory_srs_threshold", 0.70, type=float)
        campaign_cos_threshold = request.form.get("campaign_cos_threshold", 0.75, type=float)
        facility_fps_threshold = request.form.get("facility_fps_threshold", 0.65, type=float)

        if not (0.50 <= inventory_srs_threshold <= 0.95):
            flash("Inventory threshold must be between 0.50 and 0.95", "danger")
            return redirect(url_for("agent.settings"))
        if not (0.50 <= campaign_cos_threshold <= 0.95):
            flash("Campaign threshold must be between 0.50 and 0.95", "danger")
            return redirect(url_for("agent.settings"))
        if not (0.50 <= facility_fps_threshold <= 0.95):
            flash("Facility threshold must be between 0.50 and 0.95", "danger")
            return redirect(url_for("agent.settings"))

        try:
            agent_config.inventory_mission_enabled = inventory_mission_enabled
            agent_config.campaign_mission_enabled = campaign_mission_enabled
            agent_config.facility_mission_enabled = facility_mission_enabled
            agent_config.shopper_mission_enabled = shopper_mission_enabled
            agent_config.inventory_srs_threshold = inventory_srs_threshold
            agent_config.campaign_cos_threshold = campaign_cos_threshold
            agent_config.facility_fps_threshold = facility_fps_threshold
            agent_config.auto_approve_restock = "auto_approve_restock" in request.form
            agent_config.auto_approve_campaigns = "auto_approve_campaigns" in request.form
            agent_config.auto_approve_maintenance = "auto_approve_maintenance" in request.form
            agent_config.notification_email = (request.form.get("notification_email", "") or "").strip() or None
            agent_config.inventory_check_interval_minutes = request.form.get(
                "inventory_check_interval_minutes",
                15,
                type=int,
            )
            agent_config.campaign_check_interval_minutes = request.form.get(
                "campaign_check_interval_minutes",
                30,
                type=int,
            )
            agent_config.facility_check_interval_minutes = request.form.get(
                "facility_check_interval_minutes",
                10,
                type=int,
            )
            agent_config.updated_at = datetime.utcnow()

            db.session.add(
                AgentAction(
                    property_id=property_id,
                    mission_type="system",
                    action_type="settings_updated",
                    description=f"Agent configuration updated by {current_user.full_name}",
                    entity_id=str(agent_config.id),
                    status="approved",
                    approved_by_user_id=current_user.id,
                    resolved_at=datetime.utcnow(),
                    created_at=datetime.utcnow(),
                )
            )

            db.session.commit()
            flash("Agent configuration saved.", "success")
            return redirect(url_for("agent.settings"))
        except Exception:
            db.session.rollback()
            flash("Unable to save settings right now.", "danger")
            return redirect(url_for("agent.settings"))

    return render_template(
        "agent/settings.html",
        agent_config=agent_config,
        property=property_record,
    )


@agent_bp.route("/settings/test-alert", methods=["POST"])
@login_required
def test_alert():
    property_id = current_user.property_id
    if not property_id:
        return jsonify({"success": False, "error": "Property not configured"}), 400

    try:
        create_notification(
            user_id=current_user.id,
            title="Test Alert from RetailMind",
            message="This is a test notification from your Agent Configuration page.",
            notification_type="system",
            severity="info",
            action_url="/notifications",
            property_id=property_id,
        )

        agent_config = AgentConfiguration.query.filter_by(property_id=property_id).first()
        if agent_config and agent_config.notification_email:
            email_service.send_morning_briefing_email(
                current_user,
                {
                    "inventory_alerts": 1,
                    "campaign_opportunities": 1,
                    "open_work_orders": 1,
                    "overnight_agent_actions": 1,
                },
            )

        return jsonify({"success": True, "message": "Test alert sent."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "error": "Unable to send test alert"}), 500


@agent_bp.route("/settings/reset", methods=["POST"])
@login_required
def reset_settings():
    property_id = current_user.property_id
    if not property_id:
        return jsonify({"success": False, "error": "Property not configured"}), 400

    agent_config = AgentConfiguration.query.filter_by(property_id=property_id).first()
    if agent_config is None:
        agent_config = AgentConfiguration(property_id=property_id)
        db.session.add(agent_config)

    try:
        agent_config.inventory_srs_threshold = 0.70
        agent_config.campaign_cos_threshold = 0.75
        agent_config.facility_fps_threshold = 0.65
        agent_config.auto_approve_restock = False
        agent_config.auto_approve_campaigns = False
        agent_config.auto_approve_maintenance = False
        agent_config.notification_email = None
        agent_config.inventory_check_interval_minutes = 15
        agent_config.campaign_check_interval_minutes = 30
        agent_config.facility_check_interval_minutes = 10
        agent_config.inventory_mission_enabled = True
        agent_config.campaign_mission_enabled = True
        agent_config.facility_mission_enabled = True
        agent_config.shopper_mission_enabled = True
        agent_config.updated_at = datetime.utcnow()

        db.session.commit()

        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({"success": True}), 200

        flash("Settings reset to defaults.", "success")
        return redirect(url_for("agent.settings"))
    except Exception:
        db.session.rollback()
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({"success": False, "error": "Unable to reset settings"}), 500
        flash("Unable to reset settings right now.", "danger")
        return redirect(url_for("agent.settings"))
