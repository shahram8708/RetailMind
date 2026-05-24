from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from app.extensions import db
from app.models.agent import AgentAction, AgentConfiguration
from app.models.campaign import Campaign
from app.models.facility import WorkOrder
from app.models.inventory import FootTraffic
from app.models.property import MallProperty
from app.services.notification_service import get_recent_notifications
from app.utils.decorators import role_required


dashboard_bp = Blueprint("dashboard", __name__)


def _default_agent_status():
    return {
        "inventory_enabled": False,
        "campaign_enabled": False,
        "facility_enabled": False,
        "shopper_enabled": False,
        "srs_threshold": 0.70,
        "cos_threshold": 0.75,
        "fps_threshold": 0.65,
    }


def _build_agent_status(property_id):
    if not property_id:
        return _default_agent_status()

    config = AgentConfiguration.query.filter_by(property_id=property_id).first()
    if config is None:
        return _default_agent_status()

    return {
        "inventory_enabled": bool(config.inventory_mission_enabled),
        "campaign_enabled": bool(config.campaign_mission_enabled),
        "facility_enabled": bool(config.facility_mission_enabled),
        "shopper_enabled": bool(config.shopper_mission_enabled),
        "srs_threshold": float(config.inventory_srs_threshold or 0.70),
        "cos_threshold": float(config.campaign_cos_threshold or 0.75),
        "fps_threshold": float(config.facility_fps_threshold or 0.65),
    }


def _build_kpi_data(property_id, agent_status, now_local):
    today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    yesterday_start = today_start - timedelta(days=1)
    week_start = today_start - timedelta(days=today_start.weekday())
    last_week_start = week_start - timedelta(days=7)

    if not property_id:
        return {
            "active_missions": 0,
            "inventory_alerts_today": 0,
            "campaigns_this_week": 0,
            "open_work_orders": 0,
            "inventory_alerts_yesterday": 0,
            "campaigns_last_week": 0,
            "work_orders_yesterday": 0,
            "today_start": today_start,
            "tomorrow_start": tomorrow_start,
        }

    inventory_alerts_today = AgentAction.query.filter(
        AgentAction.property_id == property_id,
        AgentAction.mission_type == "inventory",
        AgentAction.created_at >= today_start,
    ).count()

    inventory_alerts_yesterday = AgentAction.query.filter(
        AgentAction.property_id == property_id,
        AgentAction.mission_type == "inventory",
        AgentAction.created_at >= yesterday_start,
        AgentAction.created_at < today_start,
    ).count()

    campaigns_this_week = Campaign.query.filter(
        Campaign.property_id == property_id,
        Campaign.status == "active",
        Campaign.activated_at >= week_start,
    ).count()

    campaigns_last_week = Campaign.query.filter(
        Campaign.property_id == property_id,
        Campaign.status == "active",
        Campaign.activated_at >= last_week_start,
        Campaign.activated_at < week_start,
    ).count()

    open_work_orders = WorkOrder.query.filter_by(property_id=property_id, status="open").count()

    work_orders_yesterday = WorkOrder.query.filter(
        WorkOrder.property_id == property_id,
        WorkOrder.created_at >= yesterday_start,
        WorkOrder.created_at < today_start,
    ).count()

    active_missions = sum(
        [
            int(agent_status["inventory_enabled"]),
            int(agent_status["campaign_enabled"]),
            int(agent_status["facility_enabled"]),
            int(agent_status["shopper_enabled"]),
        ]
    )

    return {
        "active_missions": active_missions,
        "inventory_alerts_today": inventory_alerts_today,
        "campaigns_this_week": campaigns_this_week,
        "open_work_orders": open_work_orders,
        "inventory_alerts_yesterday": inventory_alerts_yesterday,
        "campaigns_last_week": campaigns_last_week,
        "work_orders_yesterday": work_orders_yesterday,
        "today_start": today_start,
        "tomorrow_start": tomorrow_start,
    }


def _pending_actions(property_id):
    if not property_id:
        return []

    return (
        AgentAction.query.filter_by(property_id=property_id, status="pending")
        .order_by(AgentAction.created_at.desc())
        .limit(10)
        .all()
    )


def _latest_foot_traffic_by_zone(property_id):
    zones = ["A", "B", "C", "D", "E"]
    traffic = {zone: 0 for zone in zones}

    if not property_id:
        return traffic, 1

    for zone in zones:
        latest_record = (
            FootTraffic.query.filter_by(property_id=property_id, zone_id=zone)
            .order_by(FootTraffic.timestamp.desc())
            .first()
        )
        traffic[zone] = int(latest_record.count) if latest_record else 0

    max_count = max(traffic.values()) if any(traffic.values()) else 1
    return traffic, max_count


def _today_hourly_traffic(property_id, today_start, tomorrow_start):
    hours = list(range(24))
    counts = [0] * 24

    if not property_id:
        return {"hours": hours, "counts": counts}

    hour_rows = (
        db.session.query(
            func.extract("hour", FootTraffic.timestamp).label("hour_value"),
            func.sum(FootTraffic.count).label("total_count"),
        )
        .filter(
            FootTraffic.property_id == property_id,
            FootTraffic.timestamp >= today_start,
            FootTraffic.timestamp < tomorrow_start,
        )
        .group_by(func.extract("hour", FootTraffic.timestamp))
        .all()
    )

    for row in hour_rows:
        hour = int(row.hour_value)
        if 0 <= hour <= 23:
            counts[hour] = int(row.total_count or 0)

    return {"hours": hours, "counts": counts}


def _today_stats(property_id, today_start):
    if not property_id:
        return {
            "revenue_attributed_today": 0,
            "agent_actions_today": 0,
            "alerts_resolved_today": 0,
        }

    revenue_attributed_today = (
        db.session.query(func.coalesce(func.sum(Campaign.revenue_attributed), 0.0))
        .filter(
            Campaign.property_id == property_id,
            Campaign.activated_at >= today_start,
        )
        .scalar()
        or 0.0
    )

    agent_actions_today = AgentAction.query.filter(
        AgentAction.property_id == property_id,
        AgentAction.created_at >= today_start,
    ).count()

    alerts_resolved_today = AgentAction.query.filter(
        AgentAction.property_id == property_id,
        AgentAction.status.in_(["approved", "rejected", "auto_executed"]),
        AgentAction.resolved_at >= today_start,
    ).count()

    return {
        "revenue_attributed_today": float(revenue_attributed_today),
        "agent_actions_today": agent_actions_today,
        "alerts_resolved_today": alerts_resolved_today,
    }


@dashboard_bp.route("/dashboard")
@login_required
@role_required("superadmin", "mall_admin", "store_manager", "marketing_manager", "facility_manager")
def index():
    view_property_id = request.args.get("view_property_id", type=int)
    if view_property_id and current_user.is_superadmin():
        target_property_id = view_property_id
    else:
        target_property_id = current_user.property_id

    property_record = MallProperty.query.get(target_property_id) if target_property_id else None

    if property_record and not property_record.onboarding_complete and not current_user.is_superadmin():
        flash("Please complete onboarding to access the dashboard.", "warning")
        return redirect(url_for("onboarding.complete"))

    if not target_property_id and current_user.role != "superadmin":
        flash("Please complete onboarding to access the dashboard.", "warning")
        return redirect(url_for("onboarding.step1"))

    now_local = datetime.now()
    agent_status = _build_agent_status(target_property_id)
    kpi_data = _build_kpi_data(target_property_id, agent_status, now_local)
    pending_actions = _pending_actions(target_property_id)
    recent_notifications = get_recent_notifications(current_user.id, limit=10)
    foot_traffic_data, heatmap_max_count = _latest_foot_traffic_by_zone(target_property_id)
    today_hourly_traffic = _today_hourly_traffic(
        target_property_id,
        kpi_data["today_start"],
        kpi_data["tomorrow_start"],
    )
    today_stats = _today_stats(target_property_id, kpi_data["today_start"])

    hourly_counts = today_hourly_traffic["counts"]
    peak_hour = hourly_counts.index(max(hourly_counts)) if any(hourly_counts) else None
    peak_hour_label = "No data"
    if peak_hour is not None:
        suffix = "AM" if peak_hour < 12 else "PM"
        display_hour = peak_hour % 12
        display_hour = 12 if display_hour == 0 else display_hour
        peak_hour_label = f"{display_hour}{suffix}"

    total_visitors = sum(hourly_counts)
    busiest_zone = max(foot_traffic_data, key=foot_traffic_data.get) if any(foot_traffic_data.values()) else "N/A"

    return render_template(
        "dashboard/index.html",
        agent_status=agent_status,
        kpi_data=kpi_data,
        pending_actions=pending_actions,
        recent_notifications=recent_notifications,
        foot_traffic_data=foot_traffic_data,
        heatmap_max_count=heatmap_max_count,
        today_hourly_traffic=today_hourly_traffic,
        today_stats=today_stats,
        peak_hour_label=peak_hour_label,
        total_visitors=total_visitors,
        busiest_zone=busiest_zone,
        target_property=property_record,
        target_property_id=target_property_id,
        current_time=now_local,
    )
