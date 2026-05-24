from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from app.extensions import db
from app.forms.inventory import SKUConfigForm
from app.models.agent import AgentAction, AgentConfiguration
from app.models.inventory import InventoryItem
from app.models.tenant import Tenant
from app.services import inventory_service
from app.services.notification_service import create_notification


inventory_bp = Blueprint("inventory", __name__)


def parse_inventory_filters(request_obj):
    return {
        "tenant_id": request_obj.args.get("tenant_id", type=int),
        "category": request_obj.args.get("category", ""),
        "risk_level": request_obj.args.get("risk_level", "all"),
        "sort_by": request_obj.args.get("sort_by", "srs_score_desc"),
        "search": request_obj.args.get("search", ""),
        "page": request_obj.args.get("page", 1, type=int),
    }


@inventory_bp.route("", methods=["GET"])
@inventory_bp.route("/", methods=["GET"])
@login_required
def index():
    property_id = current_user.property_id
    if not property_id:
        flash("Property not configured.", "warning")
        return redirect(url_for("dashboard.index"))

    filters = parse_inventory_filters(request)

    query = db.session.query(InventoryItem, Tenant).join(
        Tenant,
        InventoryItem.tenant_id == Tenant.id,
    ).filter(
        InventoryItem.property_id == property_id,
        Tenant.property_id == property_id,
    )

    if filters["tenant_id"]:
        query = query.filter(InventoryItem.tenant_id == filters["tenant_id"])

    if filters["category"]:
        query = query.filter(InventoryItem.category == filters["category"])

    if filters["risk_level"] == "critical":
        query = query.filter(InventoryItem.srs_score >= 0.85)
    elif filters["risk_level"] == "high":
        query = query.filter(InventoryItem.srs_score >= 0.70, InventoryItem.srs_score < 0.85)
    elif filters["risk_level"] == "medium":
        query = query.filter(InventoryItem.srs_score >= 0.50, InventoryItem.srs_score < 0.70)
    elif filters["risk_level"] == "low":
        query = query.filter(InventoryItem.srs_score < 0.50)

    if filters["search"]:
        search_term = f"%{filters['search']}%"
        query = query.filter(
            or_(
                InventoryItem.product_name.ilike(search_term),
                InventoryItem.sku_id.ilike(search_term),
                InventoryItem.brand.ilike(search_term),
            )
        )

    if filters["sort_by"] == "srs_score_asc":
        query = query.order_by(InventoryItem.srs_score.asc())
    elif filters["sort_by"] == "name":
        query = query.order_by(InventoryItem.product_name.asc())
    elif filters["sort_by"] == "stock_level":
        query = query.order_by(InventoryItem.stock_level.asc())
    else:
        query = query.order_by(InventoryItem.srs_score.desc())

    pagination = query.paginate(page=filters["page"], per_page=25, error_out=False)

    top_critical = (
        db.session.query(InventoryItem, Tenant)
        .join(Tenant, InventoryItem.tenant_id == Tenant.id)
        .filter(
            InventoryItem.property_id == property_id,
            Tenant.property_id == property_id,
            InventoryItem.srs_score > 0.70,
        )
        .order_by(InventoryItem.srs_score.desc())
        .limit(3)
        .all()
    )

    config = AgentConfiguration.query.filter_by(property_id=property_id).first()
    threshold = float(config.inventory_srs_threshold if config else 0.70)

    total_skus = InventoryItem.query.filter_by(property_id=property_id).count()
    above_threshold_today = InventoryItem.query.filter(
        InventoryItem.property_id == property_id,
        InventoryItem.srs_score > threshold,
    ).count()

    stockouts_prevented = AgentAction.query.filter(
        AgentAction.property_id == property_id,
        AgentAction.mission_type == "inventory",
        AgentAction.status.in_(["approved", "auto_executed"]),
    ).count()

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    auto_restocked_today = AgentAction.query.filter(
        AgentAction.property_id == property_id,
        AgentAction.mission_type == "inventory",
        AgentAction.status == "auto_executed",
        AgentAction.resolved_at >= today_start,
    ).count()

    tenants_list = Tenant.query.filter_by(property_id=property_id, is_active=True).order_by(Tenant.name.asc()).all()
    category_rows = (
        db.session.query(InventoryItem.category)
        .filter(InventoryItem.property_id == property_id, InventoryItem.category.isnot(None), InventoryItem.category != "")
        .distinct()
        .order_by(InventoryItem.category.asc())
        .all()
    )
    categories = [row[0] for row in category_rows]

    pending_actions = AgentAction.query.filter(
        AgentAction.property_id == property_id,
        AgentAction.mission_type == "inventory",
        AgentAction.status == "pending",
    ).all()
    pending_action_map = {row.entity_id: row for row in pending_actions}

    critical_srs_map = {}
    for item, _tenant in top_critical:
        critical_srs_map[item.sku_id] = inventory_service.compute_srs_for_sku(
            item.sku_id,
            property_id,
            item.tenant_id,
        )

    return render_template(
        "inventory/index.html",
        pagination=pagination,
        filters=filters,
        top_critical=top_critical,
        critical_srs_map=critical_srs_map,
        total_skus=total_skus,
        above_threshold_today=above_threshold_today,
        stockouts_prevented=stockouts_prevented,
        auto_restocked_today=auto_restocked_today,
        tenants_list=tenants_list,
        categories=categories,
        threshold=threshold,
        pending_action_map=pending_action_map,
        get_srs_label=inventory_service.get_srs_label,
    )


@inventory_bp.route("/<sku_id>", methods=["GET"])
@login_required
def detail(sku_id):
    property_id = current_user.property_id
    if not property_id:
        flash("Property not configured.", "warning")
        return redirect(url_for("dashboard.index"))

    record = (
        db.session.query(InventoryItem, Tenant)
        .join(Tenant, InventoryItem.tenant_id == Tenant.id)
        .filter(
            InventoryItem.sku_id == sku_id,
            InventoryItem.property_id == property_id,
            Tenant.property_id == property_id,
        )
        .first_or_404()
    )

    item, tenant = record

    srs_details = inventory_service.compute_srs_for_sku(
        sku_id,
        property_id,
        item.tenant_id,
    )
    velocity_data = inventory_service.get_sales_velocity_chart_data(sku_id, property_id)
    stock_history = inventory_service.get_stock_history_chart_data(sku_id, property_id)
    stockout_history = inventory_service.get_stockout_history(sku_id, property_id)

    pending_action = AgentAction.query.filter_by(
        entity_id=sku_id,
        mission_type="inventory",
        property_id=property_id,
        status="pending",
    ).first()

    risk_label, risk_css_class = inventory_service.get_srs_label(item.srs_score)

    return render_template(
        "inventory/detail.html",
        item=item,
        tenant=tenant,
        srs_details=srs_details,
        velocity_data=velocity_data,
        stock_history=stock_history,
        stockout_history=stockout_history,
        pending_action=pending_action,
        risk_label=risk_label,
        risk_css_class=risk_css_class,
    )


@inventory_bp.route("/configure/<sku_id>", methods=["GET", "POST"])
@login_required
def configure(sku_id):
    property_id = current_user.property_id
    if not property_id:
        flash("Property not configured.", "warning")
        return redirect(url_for("dashboard.index"))

    inventory_item = InventoryItem.query.filter_by(sku_id=sku_id, property_id=property_id).first_or_404()

    form = SKUConfigForm()

    if request.method == "GET":
        form.reorder_threshold.data = inventory_item.reorder_threshold
        form.supplier_lead_time_hours.data = inventory_item.supplier_lead_time_hours or 24
        form.supplier_name.data = inventory_item.supplier_name
        form.supplier_email.data = inventory_item.supplier_email
        form.sku_criticality.data = inventory_item.sku_criticality or "medium"

    if form.validate_on_submit():
        try:
            inventory_item.reorder_threshold = form.reorder_threshold.data
            inventory_item.supplier_lead_time_hours = form.supplier_lead_time_hours.data
            inventory_item.supplier_name = (form.supplier_name.data or "").strip() or None
            inventory_item.supplier_email = (form.supplier_email.data or "").strip() or None
            inventory_item.sku_criticality = form.sku_criticality.data
            inventory_item.updated_at = datetime.utcnow()

            db.session.commit()
            flash("Configuration saved.", "success")
            return redirect(url_for("inventory.detail", sku_id=sku_id))
        except Exception:
            db.session.rollback()
            flash("Unable to save configuration right now.", "danger")

    return render_template(
        "inventory/configure.html",
        form=form,
        item=inventory_item,
    )


@inventory_bp.route("/approve/<int:action_id>", methods=["POST"])
@login_required
def approve_action(action_id):
    property_id = current_user.property_id
    if not property_id:
        return jsonify({"success": False, "error": "Property not configured"}), 400

    action = AgentAction.query.filter_by(
        id=action_id,
        property_id=property_id,
        mission_type="inventory",
    ).first()

    if action is None:
        return jsonify({"success": False, "error": "Action not found"}), 404

    try:
        action.status = "approved"
        action.approved_by_user_id = current_user.id
        action.resolved_at = datetime.utcnow()
        db.session.commit()

        create_notification(
            user_id=current_user.id,
            title="Restock approved",
            message=f"Restock action {action.id} approved successfully.",
            notification_type="agent_action",
            severity="success",
            property_id=property_id,
        )

        return jsonify({"success": True, "message": "Restock approved."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "error": "Unable to approve action"}), 500


@inventory_bp.route("/reject/<int:action_id>", methods=["POST"])
@login_required
def reject_action(action_id):
    property_id = current_user.property_id
    if not property_id:
        return jsonify({"success": False, "error": "Property not configured"}), 400

    action = AgentAction.query.filter_by(
        id=action_id,
        property_id=property_id,
        mission_type="inventory",
    ).first()

    if action is None:
        return jsonify({"success": False, "error": "Action not found"}), 404

    try:
        action.status = "rejected"
        action.approved_by_user_id = current_user.id
        action.resolved_at = datetime.utcnow()
        db.session.commit()

        create_notification(
            user_id=current_user.id,
            title="Restock rejected",
            message=f"Restock action {action.id} was rejected.",
            notification_type="agent_action",
            severity="warning",
            property_id=property_id,
        )

        return jsonify({"success": True, "message": "Restock rejected."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "error": "Unable to reject action"}), 500
