from datetime import date, datetime
import math
from urllib.parse import urlparse

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.forms.facility import WorkOrderForm, parse_facility_filters
from app.models.agent import AgentAction
from app.models.facility import Equipment, WorkOrder
from app.models.user import User
from app.services import analytics_service, facility_service
from app.services.notification_service import create_notification


facility_bp = Blueprint("facility", __name__)


def _is_ajax_request():
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
        or request.is_json
    )


def _status_match(equipment, status_filter):
    score = float(equipment.fps_score or 0.0)
    if status_filter == "critical":
        return score >= 0.85
    if status_filter == "risk":
        return 0.65 <= score < 0.85
    if status_filter == "monitor":
        return 0.40 <= score < 0.65
    if status_filter == "healthy":
        return score < 0.40
    return True


def _prepare_work_order_form(facility_managers):
    form = WorkOrderForm()
    form.assigned_to_user_id.choices = [(0, "Unassigned")] + [
        (manager.id, manager.full_name)
        for manager in facility_managers
    ]
    return form


def _resolve_work_order_equipment(property_id):
    equipment_id = request.form.get("equipment_id", type=int)
    if equipment_id:
        equipment = Equipment.query.filter_by(id=equipment_id, property_id=property_id).first()
        if equipment is not None:
            return equipment

    referrer = request.referrer or ""
    if referrer:
        parsed_referrer = urlparse(referrer)
        referrer_path = (parsed_referrer.path or "").rstrip("/")
        if referrer_path.startswith("/facility/"):
            referrer_equipment_id = referrer_path.rsplit("/", 1)[-1]
            if referrer_equipment_id.isdigit():
                equipment = Equipment.query.filter_by(
                    id=int(referrer_equipment_id),
                    property_id=property_id,
                ).first()
                if equipment is not None:
                    return equipment

    return Equipment.query.filter_by(property_id=property_id, is_active=True).order_by(Equipment.id.asc()).first()


@facility_bp.route("", methods=["GET"])
@facility_bp.route("/", methods=["GET"])
@login_required
def index():
    property_id = current_user.property_id
    if not property_id:
        flash("Property not configured.", "warning")
        return redirect(url_for("dashboard.index"))

    filters = parse_facility_filters(request)

    equipment_list = facility_service.get_equipment_for_property(property_id, floor_filter=filters["floor"])
    if filters["equipment_type"]:
        equipment_list = [
            equipment
            for equipment in equipment_list
            if (equipment.equipment_type or "").strip().lower() == filters["equipment_type"]
        ]

    if filters["status_filter"] != "all":
        equipment_list = [
            equipment
            for equipment in equipment_list
            if _status_match(equipment, filters["status_filter"])
        ]

    active_anomalies_all = facility_service.get_active_anomalies(property_id)
    active_anomalies = active_anomalies_all[:20]

    open_work_orders_all = facility_service.get_open_work_orders(property_id)
    wo_page = request.args.get("wo_page", 1, type=int)
    wo_per_page = 10
    wo_total = len(open_work_orders_all)
    wo_pages = max(1, int(math.ceil(wo_total / float(wo_per_page))))
    wo_page = max(1, min(wo_page, wo_pages))
    wo_start = (wo_page - 1) * wo_per_page
    wo_end = wo_start + wo_per_page
    open_work_orders = open_work_orders_all[wo_start:wo_end]

    anomaly_stats = {}
    for _reading, anomaly_equipment in active_anomalies:
        if anomaly_equipment.id not in anomaly_stats:
            anomaly_stats[anomaly_equipment.id] = facility_service.compute_fps_for_equipment(
                anomaly_equipment.id,
                property_id,
            )

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)

    total_equipment = Equipment.query.filter_by(property_id=property_id).count()

    critical_alerts_today = Equipment.query.filter(
        Equipment.property_id == property_id,
        Equipment.fps_score > 0.85,
        Equipment.fps_last_computed >= today_start,
    ).count()

    work_orders_completed_month = WorkOrder.query.filter(
        WorkOrder.property_id == property_id,
        WorkOrder.status == "completed",
        WorkOrder.completed_at >= month_start,
    ).count()

    roi_data_month = analytics_service.compute_agent_roi(property_id, month_start, now)
    maintenance_cost_saved_month = float(roi_data_month.get("maintenance_cost_saved", 0.0) or 0.0)

    available_floors = [
        row[0]
        for row in (
            db.session.query(Equipment.floor)
            .filter(Equipment.property_id == property_id)
            .distinct()
            .order_by(Equipment.floor.asc())
            .all()
        )
    ]

    available_equipment_types = [
        row[0]
        for row in (
            db.session.query(Equipment.equipment_type)
            .filter(Equipment.property_id == property_id)
            .distinct()
            .order_by(Equipment.equipment_type.asc())
            .all()
        )
    ]

    facility_managers = User.query.filter_by(
        property_id=property_id,
        role="facility_manager",
        is_active=True,
    ).all()

    work_order_form = _prepare_work_order_form(facility_managers)

    anomaly_equipment_ids = {equipment.id for _reading, equipment in active_anomalies_all}

    equipment_age_years = {}
    for equipment in equipment_list:
        if equipment.installation_date:
            equipment_age_years[equipment.id] = round(
                (date.today() - equipment.installation_date).days / 365.25,
                1,
            )
        else:
            equipment_age_years[equipment.id] = None

    return render_template(
        "facility/index.html",
        filters=filters,
        equipment_list=equipment_list,
        active_anomalies=active_anomalies,
        open_work_orders=open_work_orders,
        open_work_orders_total=wo_total,
        wo_page=wo_page,
        wo_pages=wo_pages,
        total_equipment=total_equipment,
        critical_alerts_today=critical_alerts_today,
        work_orders_completed_month=work_orders_completed_month,
        maintenance_cost_saved_month=maintenance_cost_saved_month,
        available_floors=available_floors,
        available_equipment_types=available_equipment_types,
        facility_managers=facility_managers,
        work_order_form=work_order_form,
        get_fps_label=facility_service.get_fps_label,
        anomaly_equipment_ids=anomaly_equipment_ids,
        anomaly_stats=anomaly_stats,
        equipment_age_years=equipment_age_years,
    )


@facility_bp.route("/<int:equipment_id>", methods=["GET"])
@login_required
def detail(equipment_id):
    property_id = current_user.property_id
    equipment = Equipment.query.filter_by(id=equipment_id, property_id=property_id).first_or_404()

    fps_result = facility_service.compute_fps_for_equipment(equipment.id, property_id)

    available_metrics = facility_service.get_available_metrics(equipment.id)
    selected_metric = request.args.get(
        "metric",
        fps_result.get("primary_metric", available_metrics[0] if available_metrics else "vibration_hz"),
    )

    if available_metrics and selected_metric not in available_metrics:
        selected_metric = available_metrics[0]

    telemetry_data = facility_service.get_sensor_telemetry_chart_data(equipment.id, selected_metric, limit=500)
    maintenance_history = facility_service.get_maintenance_history(equipment.id, property_id)

    pending_action = AgentAction.query.filter_by(
        entity_id=str(equipment.id),
        mission_type="facility",
        property_id=property_id,
        status="pending",
    ).first()

    facility_managers = User.query.filter_by(
        property_id=property_id,
        role="facility_manager",
        is_active=True,
    ).all()

    work_order_form = _prepare_work_order_form(facility_managers)

    age_years = None
    if equipment.installation_date:
        age_years = (date.today() - equipment.installation_date).days / 365.25

    return render_template(
        "facility/detail.html",
        equipment=equipment,
        fps_result=fps_result,
        available_metrics=available_metrics,
        selected_metric=selected_metric,
        telemetry_data=telemetry_data,
        maintenance_history=maintenance_history,
        pending_action=pending_action,
        facility_managers=facility_managers,
        work_order_form=work_order_form,
        get_fps_label=facility_service.get_fps_label,
        age_years=age_years,
    )


@facility_bp.route("/work-order/create", methods=["POST"])
@login_required
def create_work_order():
    property_id = current_user.property_id

    facility_managers = User.query.filter_by(
        property_id=property_id,
        role="facility_manager",
        is_active=True,
    ).all()

    form = WorkOrderForm(request.form)
    form.assigned_to_user_id.choices = [(0, "Unassigned")] + [
        (manager.id, manager.full_name)
        for manager in facility_managers
    ]

    if not form.validate():
        if _is_ajax_request():
            return jsonify({"success": False, "error": "Invalid work order data", "errors": form.errors}), 400
        flash("Unable to create work order. Please check required fields.", "danger")
        return redirect(request.referrer or url_for("facility.index"))

    equipment = _resolve_work_order_equipment(property_id)
    if equipment is None:
        if _is_ajax_request():
            return jsonify({"success": False, "error": "No equipment available for this property"}), 400
        flash("No equipment available for this property.", "warning")
        return redirect(url_for("facility.index"))

    assigned_to_user_id = int(form.assigned_to_user_id.data or 0)
    if assigned_to_user_id == 0:
        assigned_to_user_id = None

    work_order = WorkOrder(
        equipment_id=equipment.id,
        property_id=property_id,
        title=(form.title.data or "").strip(),
        description=(form.description.data or "").strip(),
        priority=form.priority.data,
        assigned_to_user_id=assigned_to_user_id,
        status="open",
        created_at=datetime.utcnow(),
        estimated_cost_inr=float(form.estimated_cost_inr.data) if form.estimated_cost_inr.data is not None else None,
    )

    try:
        db.session.add(work_order)
        db.session.commit()

        if assigned_to_user_id:
            create_notification(
                user_id=assigned_to_user_id,
                title=f"New Work Order Assigned #{work_order.id}",
                message=f"{work_order.title} has been assigned to you.",
                notification_type="facility_alert",
                severity="info",
                action_url=f"/facility/{equipment.id}",
                property_id=property_id,
            )

        if _is_ajax_request():
            return (
                jsonify(
                    {
                        "success": True,
                        "work_order_id": work_order.id,
                        "title": work_order.title,
                        "equipment_name": equipment.equipment_name,
                        "priority": work_order.priority,
                        "status": work_order.status,
                    }
                ),
                200,
            )

        flash("Work order created.", "success")
        return redirect(url_for("facility.index"))
    except Exception:
        db.session.rollback()
        if _is_ajax_request():
            return jsonify({"success": False, "error": "Unable to create work order"}), 500
        flash("Unable to create work order right now.", "danger")
        return redirect(url_for("facility.index"))


@facility_bp.route("/work-order/<int:wo_id>/complete", methods=["POST"])
@login_required
def complete_work_order(wo_id):
    property_id = current_user.property_id
    work_order = WorkOrder.query.filter_by(id=wo_id, property_id=property_id).first_or_404()

    payload = request.get_json(silent=True) or {}
    actual_cost = payload.get("actual_cost_inr")
    if actual_cost is None:
        actual_cost = request.form.get("actual_cost_inr")

    try:
        work_order.status = "completed"
        work_order.completed_at = datetime.utcnow()

        if actual_cost not in {None, ""}:
            work_order.actual_cost_inr = float(actual_cost)

        db.session.commit()
        return jsonify({"success": True, "message": "Work order completed."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "error": "Unable to complete work order"}), 500


@facility_bp.route("/work-order/<int:wo_id>/assign", methods=["POST"])
@login_required
def assign_work_order(wo_id):
    property_id = current_user.property_id
    work_order = WorkOrder.query.filter_by(id=wo_id, property_id=property_id).first_or_404()

    payload = request.get_json(silent=True) or {}
    user_id = payload.get("user_id")
    if user_id is None:
        user_id = request.form.get("user_id", type=int)

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid user"}), 400

    assignee = User.query.filter_by(id=user_id, property_id=property_id, is_active=True).first()
    if assignee is None:
        return jsonify({"success": False, "error": "User not found"}), 404

    try:
        work_order.assigned_to_user_id = assignee.id
        work_order.status = "in_progress"
        db.session.commit()

        create_notification(
            user_id=assignee.id,
            title=f"Work Order Assigned #{work_order.id}",
            message=f"You were assigned: {work_order.title}",
            notification_type="facility_alert",
            severity="info",
            action_url=f"/facility/{work_order.equipment_id}",
            property_id=property_id,
        )

        return jsonify({"success": True}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "error": "Unable to assign work order"}), 500
