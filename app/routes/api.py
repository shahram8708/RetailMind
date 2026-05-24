import threading
from datetime import datetime, timedelta
import os
import uuid
from urllib.parse import urlparse

from flask import Blueprint, current_app, jsonify, request, session
from flask_login import current_user, login_required

from app.extensions import csrf, db
from app.models.agent import AgentAction, AgentConfiguration
from app.models.billing import PaymentRecord, Subscription
from app.models.campaign import Campaign
from app.models.facility import WorkOrder
from app.models.inventory import FootTraffic, InventoryItem
from app.models.property import MallProperty
from app.models.shopper import ShopperInteraction
from app.models.tenant import Tenant
from app.models.user import User
from app.services import analytics_service, email_service, facility_service, razorpay_service, shopper_service
from app.services.notification_service import create_notification, get_unread_count
from app.services.inventory_service import get_srs_label
from app.utils.decorators import role_required


api_bp = Blueprint("api", __name__)


def format_relative_time(dt):
    if dt is None:
        return "Never"

    now = datetime.utcnow()
    delta = now - dt
    total_seconds = int(delta.total_seconds())

    if total_seconds < 60:
        return "just now"

    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"

    hours = minutes // 60
    if hours < 24:
        label = "hour" if hours == 1 else "hours"
        return f"{hours} {label} ago"

    days = hours // 24
    label = "day" if days == 1 else "days"
    return f"{days} {label} ago"


def _mission_defaults(mission):
    defaults = {
        "inventory": "Checked 30 SKUs, 2 at risk",
        "campaign": "1 opportunity identified",
        "facility": "All equipment normal",
        "shopper": "3 queries resolved",
    }
    return defaults.get(mission, "No recent activity")


def _kpi_summary(property_id):
    if not property_id:
        return {
            "active_missions": 0,
            "inventory_alerts_today": 0,
            "campaigns_this_week": 0,
            "open_work_orders": 0,
        }

    now_local = datetime.now()
    today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())

    config = AgentConfiguration.query.filter_by(property_id=property_id).first()
    if config is None:
        active_missions = 0
    else:
        active_missions = sum(
            [
                int(bool(config.inventory_mission_enabled)),
                int(bool(config.campaign_mission_enabled)),
                int(bool(config.facility_mission_enabled)),
                int(bool(config.shopper_mission_enabled)),
            ]
        )

    inventory_alerts_today = AgentAction.query.filter(
        AgentAction.property_id == property_id,
        AgentAction.mission_type == "inventory",
        AgentAction.created_at >= today_start,
    ).count()

    campaigns_this_week = Campaign.query.filter(
        Campaign.property_id == property_id,
        Campaign.status == "active",
        Campaign.activated_at >= week_start,
    ).count()

    open_work_orders = WorkOrder.query.filter_by(property_id=property_id, status="open").count()

    return {
        "active_missions": active_missions,
        "inventory_alerts_today": inventory_alerts_today,
        "campaigns_this_week": campaigns_this_week,
        "open_work_orders": open_work_orders,
    }


def _current_foot_traffic(property_id):
    zones = ["A", "B", "C", "D", "E"]
    payload = {zone: 0 for zone in zones}

    if not property_id:
        return payload

    for zone in zones:
        latest = (
            FootTraffic.query.filter_by(property_id=property_id, zone_id=zone)
            .order_by(FootTraffic.timestamp.desc())
            .first()
        )
        payload[zone] = int(latest.count) if latest else 0

    return payload


def _resolve_billing_property_id(payload=None):
    payload = payload or {}

    if current_user.is_superadmin():
        requested_property_id = payload.get("property_id")
        try:
            requested_property_id = int(requested_property_id) if requested_property_id is not None else None
        except (TypeError, ValueError):
            requested_property_id = None

        if requested_property_id:
            property_record = MallProperty.query.get(requested_property_id)
            if property_record:
                return property_record.id

        if current_user.property_id:
            return current_user.property_id

        default_property = MallProperty.query.filter_by(onboarding_complete=True).first()
        return default_property.id if default_property else None

    return current_user.property_id


@api_bp.route("/agent/status", methods=["GET"])
@login_required
def agent_status():
    property_id = current_user.property_id
    config = AgentConfiguration.query.filter_by(property_id=property_id).first() if property_id else None

    mission_map = {
        "inventory": {
            "enabled": bool(config.inventory_mission_enabled) if config else False,
            "status": "running" if config and config.inventory_mission_enabled else ("paused" if config else "inactive"),
        },
        "campaign": {
            "enabled": bool(config.campaign_mission_enabled) if config else False,
            "status": "running" if config and config.campaign_mission_enabled else ("paused" if config else "inactive"),
        },
        "facility": {
            "enabled": bool(config.facility_mission_enabled) if config else False,
            "status": "running" if config and config.facility_mission_enabled else ("paused" if config else "inactive"),
        },
        "shopper": {
            "enabled": bool(config.shopper_mission_enabled) if config else False,
            "status": "running" if config and config.shopper_mission_enabled else ("paused" if config else "inactive"),
        },
    }

    data = {}
    for mission_type in ["inventory", "campaign", "facility", "shopper"]:
        latest_action = None
        if property_id:
            latest_action = (
                AgentAction.query.filter_by(property_id=property_id, mission_type=mission_type)
                .order_by(AgentAction.created_at.desc())
                .first()
            )

        data[mission_type] = {
            "enabled": mission_map[mission_type]["enabled"],
            "status": mission_map[mission_type]["status"],
            "last_action": format_relative_time(latest_action.created_at if latest_action else None),
            "last_action_description": (
                (latest_action.description or "")[:120]
                if latest_action and latest_action.description
                else _mission_defaults(mission_type)
            ),
        }

    return jsonify({"success": True, "data": data}), 200


@api_bp.route("/notifications/unread", methods=["GET"])
@login_required
def unread_notifications():
    count = get_unread_count(current_user.id)
    return jsonify({"success": True, "count": count, "data": {"count": count}}), 200


@api_bp.route("/actions/<int:action_id>/approve", methods=["POST"])
@login_required
def approve_action(action_id):
    property_id = current_user.property_id
    if not property_id:
        return jsonify({"success": False, "error": "Property not configured"}), 400

    action = AgentAction.query.filter_by(id=action_id, property_id=property_id).first()
    if action is None:
        return jsonify({"success": False, "error": "Action not found"}), 404

    try:
        action.status = "approved"
        action.approved_by_user_id = current_user.id
        action.resolved_at = datetime.utcnow()
        db.session.commit()

        create_notification(
            user_id=current_user.id,
            property_id=property_id,
            title="Agent action approved",
            message=f"Agent action approved: {(action.description or '')[:100]}",
            notification_type="agent_action",
            severity="info",
        )

        return jsonify(
            {
                "success": True,
                "message": "Action approved",
                "action_id": action_id,
                "data": {"action_id": action_id},
            }
        ), 200
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "error": "Unable to approve action"}), 500


@api_bp.route("/actions/<int:action_id>/reject", methods=["POST"])
@login_required
def reject_action(action_id):
    property_id = current_user.property_id
    if not property_id:
        return jsonify({"success": False, "error": "Property not configured"}), 400

    action = AgentAction.query.filter_by(id=action_id, property_id=property_id).first()
    if action is None:
        return jsonify({"success": False, "error": "Action not found"}), 404

    try:
        action.status = "rejected"
        action.approved_by_user_id = current_user.id
        action.resolved_at = datetime.utcnow()
        db.session.commit()

        create_notification(
            user_id=current_user.id,
            property_id=property_id,
            title="Agent action rejected",
            message=f"Agent action rejected: {(action.description or '')[:100]}",
            notification_type="agent_action",
            severity="warning",
        )

        return jsonify(
            {
                "success": True,
                "message": "Action rejected",
                "action_id": action_id,
                "data": {"action_id": action_id},
            }
        ), 200
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "error": "Unable to reject action"}), 500


@api_bp.route("/kpi/summary", methods=["GET"])
@login_required
def kpi_summary():
    summary = _kpi_summary(current_user.property_id)
    return jsonify({"success": True, "data": summary}), 200


@api_bp.route("/health-check", methods=["GET", "HEAD"])
def health_check():
    cache_headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
    }

    if request.method == "HEAD":
        return ("", 200, cache_headers)

    return (
        jsonify(
            {
                "status": "ok",
                "service": "retailmind",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        ),
        200,
        cache_headers,
    )


@api_bp.route("/pwa/config", methods=["GET"])
def pwa_config():
    return (
        jsonify(
            {
                "push_vapid_public_key": current_app.config.get("VAPID_PUBLIC_KEY"),
                "cache_version": current_app.config.get("PWA_CACHE_VERSION"),
                "features": {
                    "push_notifications": bool(current_app.config.get("PUSH_NOTIFICATIONS_ENABLED")),
                    "background_sync": bool(current_app.config.get("BACKGROUND_SYNC_ENABLED")),
                },
                "pwa_dev_mode": bool(current_app.config.get("PWA_DEV_MODE")),
            }
        ),
        200,
    )


@api_bp.route("/sync/queue", methods=["POST"])
@login_required
@csrf.exempt
def sync_queue():
    payload = request.get_json(silent=True) or {}
    items = payload.get("items") or []
    if not isinstance(items, list):
        return jsonify({"success": False, "error": "Invalid queue payload"}), 400

    results = []
    cookie_header = request.headers.get("Cookie")

    with current_app.test_client() as client:
        for item in items:
            try:
                url = item.get("url") or ""
                method = str(item.get("method") or "POST").upper()
                headers = item.get("headers") or {}
                body = item.get("body")
                item_id = item.get("id")

                parsed = urlparse(url)
                path = parsed.path or url
                if parsed.query:
                    path = f"{path}?{parsed.query}"

                if cookie_header:
                    headers["Cookie"] = cookie_header

                response = client.open(
                    path,
                    method=method,
                    data=body,
                    headers=headers,
                )

                ok = 200 <= response.status_code < 300
                results.append(
                    {
                        "id": item_id,
                        "url": url,
                        "status": response.status_code,
                        "success": ok,
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "id": item.get("id"),
                        "url": item.get("url"),
                        "status": 500,
                        "success": False,
                        "error": str(exc),
                    }
                )

    return jsonify({"success": True, "results": results}), 200


@api_bp.route("/foot-traffic/current", methods=["GET"])
@login_required
def foot_traffic_current():
    traffic = _current_foot_traffic(current_user.property_id)
    response = {"success": True, "data": traffic}
    response.update(traffic)
    return jsonify(response), 200


@api_bp.route("/inventory/risk", methods=["GET"])
@login_required
def inventory_risk():
    property_id = current_user.property_id
    if not property_id:
        return jsonify({"success": False, "error": "Property not configured"}), 400

    rows = (
        db.session.query(InventoryItem, Tenant)
        .join(Tenant, InventoryItem.tenant_id == Tenant.id)
        .filter(
            InventoryItem.property_id == property_id,
            Tenant.property_id == property_id,
        )
        .order_by(InventoryItem.srs_score.desc())
        .limit(20)
        .all()
    )

    payload = []
    for item, tenant in rows:
        label, _css_class = get_srs_label(item.srs_score)
        payload.append(
            {
                "sku_id": item.sku_id,
                "product_name": item.product_name,
                "brand": item.brand,
                "tenant_name": tenant.name,
                "zone": tenant.zone,
                "stock_level": item.stock_level,
                "reorder_threshold": item.reorder_threshold,
                "srs_score": float(item.srs_score or 0.0),
                "srs_label": label,
                "unit_price": float(item.unit_price or 0.0),
            }
        )

    return jsonify({"success": True, "data": payload}), 200


@api_bp.route("/campaigns/opportunities", methods=["GET"])
@login_required
def campaign_opportunities():
    property_id = current_user.property_id
    if not property_id:
        return jsonify({"success": False, "error": "Property not configured"}), 400

    rows = (
        db.session.query(Campaign, Tenant)
        .outerjoin(Tenant, Campaign.tenant_id == Tenant.id)
        .filter(
            Campaign.property_id == property_id,
            Campaign.status.in_(["opportunity", "pending_activation"]),
        )
        .order_by(Campaign.opportunity_score.desc())
        .limit(10)
        .all()
    )

    data = []
    for campaign, tenant in rows:
        data.append(
            {
                "id": campaign.id,
                "campaign_name": campaign.campaign_name,
                "tenant_name": tenant.name if tenant else "Unknown Tenant",
                "zone": campaign.target_zone or (tenant.zone if tenant else None),
                "cos_score": float(campaign.opportunity_score or 0.0),
                "channel": campaign.channel,
                "campaign_copy_preview": (campaign.campaign_copy or "")[:100],
                "weather_context": campaign.weather_context,
                "event_context": campaign.event_context,
                "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
            }
        )

    return jsonify({"success": True, "data": data}), 200


@api_bp.route("/campaigns/<int:campaign_id>/activate", methods=["POST"])
@login_required
def activate_campaign_api(campaign_id):
    property_id = current_user.property_id
    if not property_id:
        return jsonify({"success": False, "error": "Property not configured"}), 400
    campaign = Campaign.query.filter_by(id=campaign_id, property_id=property_id).first()
    if campaign is None:
        return jsonify({"success": False, "error": "Campaign not found"}), 404

    try:
        campaign.status = "active"
        campaign.activated_at = datetime.utcnow()

        related_action = AgentAction.query.filter(
            AgentAction.entity_id == str(campaign.tenant_id),
            AgentAction.mission_type == "campaign",
            AgentAction.property_id == property_id,
            AgentAction.status == "pending",
        ).order_by(AgentAction.created_at.desc()).first()

        if related_action is not None:
            related_action.status = "approved"
            related_action.approved_by_user_id = current_user.id
            related_action.resolved_at = datetime.utcnow()

        db.session.commit()

        create_notification(
            user_id=current_user.id,
            property_id=property_id,
            title="Campaign activated",
            message=f"Campaign '{campaign.campaign_name}' is now active.",
            notification_type="campaign_opportunity",
            severity="success",
            action_url=f"/campaigns/{campaign.id}",
            push_payload={
                "title": "Campaign Activated",
                "body": f"{campaign.campaign_name} is now live for Zone {campaign.target_zone or '-' }.",
                "icon": "/static/img/offline-placeholder.svg",
                "badge": "/static/img/offline-placeholder.svg",
                "tag": f"campaign-activated-{campaign.id}",
                "data": {"url": f"/campaigns/{campaign.id}"},
                "vibrate": [120, 80, 120],
                "requireInteraction": False,
            },
        )

        return jsonify({"success": True, "campaign_id": campaign.id, "status": "active"}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "error": "Unable to activate campaign"}), 500


@api_bp.route("/campaigns/<int:campaign_id>/pause", methods=["POST"])
@login_required
def pause_campaign_api(campaign_id):
    property_id = current_user.property_id
    if not property_id:
        return jsonify({"success": False, "error": "Property not configured"}), 400
    campaign = Campaign.query.filter_by(id=campaign_id, property_id=property_id).first()
    if campaign is None:
        return jsonify({"success": False, "error": "Campaign not found"}), 404

    try:
        campaign.status = "paused"
        db.session.commit()

        create_notification(
            user_id=current_user.id,
            property_id=property_id,
            title="Campaign paused",
            message=f"Campaign '{campaign.campaign_name}' has been paused.",
            notification_type="campaign_opportunity",
            severity="warning",
            action_url=f"/campaigns/{campaign.id}",
        )

        return jsonify({"success": True, "campaign_id": campaign.id, "status": "paused"}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "error": "Unable to pause campaign"}), 500


@api_bp.route("/facility/anomalies", methods=["GET"])
@login_required
def facility_anomalies():
    property_id = current_user.property_id
    if not property_id:
        return jsonify({"success": False, "error": "Property not configured"}), 400

    rows = facility_service.get_active_anomalies(property_id)
    payload = []

    for reading, equipment in rows:
        payload.append(
            {
                "equipment_name": equipment.equipment_name,
                "equipment_type": equipment.equipment_type,
                "zone": equipment.zone,
                "floor": equipment.floor,
                "metric_name": reading.metric_name,
                "metric_value": float(reading.metric_value or 0.0),
                "z_score": float(reading.z_score or 0.0),
                "anomaly_score": float(reading.anomaly_score or 0.0),
                "fps_score": float(equipment.fps_score or 0.0),
                "timestamp": reading.timestamp.isoformat() if reading.timestamp else None,
                "equipment_id": equipment.id,
            }
        )

    return jsonify({"success": True, "count": len(payload), "data": payload}), 200


@api_bp.route("/analytics/data", methods=["GET"])
@login_required
def analytics_data():
    property_id = current_user.property_id
    if not property_id:
        return jsonify({"success": False, "error": "Property not configured"}), 400

    range_str = request.args.get("range", "30d")
    start_str = request.args.get("start")
    end_str = request.args.get("end")

    start_dt, end_dt = analytics_service.get_date_range(range_str, start_str, end_str)

    foot_traffic = analytics_service.get_daily_foot_traffic(property_id, start_dt, end_dt)
    inventory_trend = analytics_service.get_inventory_risk_trend(property_id, start_dt, end_dt)
    campaign_trend = analytics_service.get_campaign_performance_trend(property_id, start_dt, end_dt)
    facility_trend = analytics_service.get_facility_anomaly_trend(property_id, start_dt, end_dt)
    action_distribution = analytics_service.get_agent_action_distribution(property_id, start_dt, end_dt)
    roi_data = analytics_service.compute_agent_roi(property_id, start_dt, end_dt)

    return (
        jsonify(
            {
                "success": True,
                "data": {
                    "range": range_str,
                    "period_start": start_dt.isoformat(),
                    "period_end": end_dt.isoformat(),
                    "foot_traffic": foot_traffic,
                    "inventory_trend": inventory_trend,
                    "campaign_trend": campaign_trend,
                    "facility_trend": facility_trend,
                    "action_distribution": action_distribution,
                    "roi_data": roi_data,
                },
            }
        ),
        200,
    )


@api_bp.route("/agent/run-now/<mission_type>", methods=["POST"])
@login_required
def run_mission_now(mission_type):
    mission_type = (mission_type or "").strip().lower()
    if mission_type not in {"inventory", "campaign", "facility", "shopper"}:
        return jsonify({"success": False, "error": "Invalid mission type"}), 400

    if mission_type in {"shopper"}:
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Shopper mission runs on demand via user queries. No scheduled run needed.",
                }
            ),
            200,
        )

    from app.services.agent_runner import run_campaign_mission, run_facility_mission, run_inventory_mission

    app_obj = current_app._get_current_object()
    property_id = current_user.property_id

    if not property_id:
        return jsonify({"success": False, "error": "Property not configured"}), 400

    try:
        if mission_type == "inventory":
            worker = threading.Thread(
                target=run_inventory_mission,
                args=(app_obj, property_id),
                daemon=True,
            )
            worker.start()
        elif mission_type == "campaign":
            worker = threading.Thread(
                target=run_campaign_mission,
                args=(app_obj, property_id),
                daemon=True,
            )
            worker.start()
        elif mission_type == "facility":
            worker = threading.Thread(
                target=run_facility_mission,
                args=(app_obj, property_id),
                daemon=True,
            )
            worker.start()

        return (
            jsonify(
                {
                    "success": True,
                    "message": "Mission triggered. Results will appear in 30-60 seconds.",
                }
            ),
            200,
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/admin/platform-stats", methods=["GET"])
@login_required
@role_required("superadmin")
def admin_platform_stats():
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    payload = {
        "total_properties": MallProperty.query.count(),
        "total_users": User.query.count(),
        "agent_actions_today": AgentAction.query.filter(AgentAction.created_at >= today_start).count(),
        "pending_all": AgentAction.query.filter_by(status="pending").count(),
        "total_active_campaigns": Campaign.query.filter_by(status="active").count(),
        "shopper_queries_today": ShopperInteraction.query.filter(ShopperInteraction.timestamp >= today_start).count(),
    }

    return jsonify({"success": True, "data": payload, **payload}), 200


@api_bp.route("/shopper/search", methods=["POST"])
@csrf.exempt
def shopper_search():
    payload = request.get_json(silent=True) or {}
    query_text = (payload.get("query") or "").strip()
    property_id = payload.get("property_id")

    try:
        property_id = int(property_id) if property_id is not None else None
    except (TypeError, ValueError):
        property_id = None

    if not query_text:
        return jsonify({"success": False, "error": "Query cannot be empty"}), 400

    if not property_id:
        default_property = MallProperty.query.filter_by(onboarding_complete=True).first()
        if default_property:
            property_id = default_property.id

    if not property_id:
        return jsonify({"success": False, "error": "No mall configured yet."}), 404

    session_id = session.get("shopper_session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        session["shopper_session_id"] = session_id

    recent = session.get("shopper_recent_searches", [])
    if query_text not in recent:
        recent.insert(0, query_text)
        session["shopper_recent_searches"] = recent[:5]
    session.modified = True

    result = shopper_service.process_query(
        query_text,
        property_id,
        session_id=session_id,
    )

    if result.get("error"):
        return jsonify({"success": False, "error": result.get("error")}), 500

    return jsonify(
        {
            "success": True,
            "query_id": result.get("query_id"),
            "results_count": result.get("results_count", 0),
            "results": result.get("results", []),
            "intent": result.get("intent", {}),
            "response_time_ms": result.get("response_time_ms", 0),
            "redirect_url": f"/shopper/result/{result.get('query_id')}",
        }
    ), 200


@api_bp.route("/payment/create-order", methods=["POST"])
@login_required
@role_required("mall_admin", "superadmin")
def payment_create_order():
    try:
        payload = request.get_json(silent=True) or {}
        plan_name = (payload.get("plan_name") or "").strip().lower()
        billing_cycle = (payload.get("billing_cycle") or "monthly").strip().lower()
        property_id = _resolve_billing_property_id(payload)

        if property_id is None:
            return jsonify({"success": False, "error": "Property not configured."}), 400

        if plan_name not in ["starter", "professional", "enterprise"]:
            return jsonify({"success": False, "error": "Invalid plan selected."}), 400

        if billing_cycle not in ["monthly", "annual"]:
            return jsonify({"success": False, "error": "Invalid billing cycle."}), 400

        if plan_name == "enterprise":
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Enterprise pricing is custom. Contact sales@retailmind.ai",
                    }
                ),
                400,
            )

        amount_inr = razorpay_service.PLAN_PRICES_INR[plan_name][billing_cycle]
        if not current_app.config.get("RAZORPAY_ENABLED"):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Payment gateway not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env",
                    }
                ),
                503,
            )

        order = razorpay_service.create_order(amount_inr, plan_name, property_id, billing_cycle)
        razorpay_order_id = order.get("id")

        return jsonify(
            {
                "success": True,
                "order_id": razorpay_order_id,
                "amount": amount_inr,
                "amount_paise": int(float(amount_inr) * 100),
                "currency": "INR",
                "plan_name": plan_name,
                "plan_display_name": razorpay_service.PLAN_DISPLAY_NAMES[plan_name],
                "billing_cycle": billing_cycle,
                "property_id": property_id,
                "key_id": os.getenv("RAZORPAY_KEY_ID"),
            }
        ), 200
    except Exception as exc:
        current_app.logger.exception("Failed to create payment order")
        return jsonify({"success": False, "error": str(exc)}), 500


@api_bp.route("/payment/verify", methods=["POST"])
@login_required
def payment_verify():
    try:
        payload = request.get_json(silent=True) or {}
        razorpay_order_id = (payload.get("razorpay_order_id") or "").strip()
        razorpay_payment_id = (payload.get("razorpay_payment_id") or "").strip()
        razorpay_signature = (payload.get("razorpay_signature") or "").strip()
        plan_name = (payload.get("plan_name") or "").strip().lower()
        billing_cycle = (payload.get("billing_cycle") or "monthly").strip().lower()
        property_id = _resolve_billing_property_id(payload)

        if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
            return jsonify({"success": False, "error": "Missing required payment fields."}), 400

        if plan_name not in razorpay_service.PLAN_PRICES_INR:
            return jsonify({"success": False, "error": "Invalid plan name."}), 400

        if billing_cycle not in ["monthly", "annual"]:
            return jsonify({"success": False, "error": "Invalid billing cycle."}), 400

        if property_id is None:
            return jsonify({"success": False, "error": "Property not configured."}), 400

        existing_payment = PaymentRecord.query.filter_by(razorpay_payment_id=razorpay_payment_id).first()
        if existing_payment:
            if existing_payment.property_id != property_id:
                return jsonify({"success": False, "error": "Payment does not belong to this property."}), 403
            return (
                jsonify(
                    {
                        "success": True,
                        "message": f"Payment successful! Your {existing_payment.plan_name.title()} plan is now active.",
                        "plan": existing_payment.plan_name,
                    }
                ),
                200,
            )

        signature_valid = razorpay_service.verify_payment_signature(
            razorpay_order_id,
            razorpay_payment_id,
            razorpay_signature,
        )

        if not signature_valid:
            current_app.logger.warning(
                "Payment signature verification failed for order=%s payment=%s user=%s",
                razorpay_order_id,
                razorpay_payment_id,
                current_user.id,
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Payment verification failed. Invalid signature.",
                    }
                ),
                400,
            )

        payment = razorpay_service.get_payment_details(razorpay_payment_id)
        if not payment:
            return jsonify({"success": False, "error": "Unable to verify payment details."}), 400

        if payment.get("status") != "captured":
            return jsonify({"success": False, "error": "Payment is not captured."}), 400

        amount_inr = razorpay_service.PLAN_PRICES_INR[plan_name][billing_cycle]

        payment_record = PaymentRecord(
            property_id=property_id,
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature,
            amount_inr=amount_inr,
            status="captured",
            plan_name=plan_name,
            created_at=datetime.utcnow(),
        )
        db.session.add(payment_record)

        subscription = Subscription.query.filter_by(property_id=property_id).first()
        period_start = datetime.utcnow()
        period_end = period_start + timedelta(days=30 if billing_cycle == "monthly" else 365)

        if subscription:
            subscription.plan_name = plan_name
            subscription.price_inr = amount_inr
            subscription.billing_cycle = billing_cycle
            subscription.status = "active"
            subscription.razorpay_subscription_id = razorpay_payment_id
            subscription.current_period_start = period_start
            subscription.current_period_end = period_end
        else:
            subscription = Subscription(
                property_id=property_id,
                plan_name=plan_name,
                price_inr=amount_inr,
                billing_cycle=billing_cycle,
                status="active",
                razorpay_subscription_id=razorpay_payment_id,
                current_period_start=period_start,
                current_period_end=period_end,
                created_at=datetime.utcnow(),
            )
            db.session.add(subscription)

        property_record = MallProperty.query.get(property_id)
        if property_record:
            property_record.subscription_tier = plan_name

        db.session.commit()

        email_service.send_payment_receipt_email(
            current_user,
            amount_inr,
            plan_name,
            razorpay_payment_id,
        )

        create_notification(
            user_id=current_user.id,
            property_id=property_id,
            title="Payment successful",
            message=f"Payment successful! Your {plan_name} plan is now active.",
            notification_type="system",
            severity="success",
            action_url="/settings/billing",
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": f"Payment successful! Your {plan_name.title()} plan is now active.",
                    "plan": plan_name,
                }
            ),
            200,
        )
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Payment verification failed")
        return jsonify({"success": False, "error": str(exc)}), 500
