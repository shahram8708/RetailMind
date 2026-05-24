import csv
import io
import os
import sys
from datetime import datetime, timedelta

import flask
from flask import Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from app.extensions import db
from app.models.agent import AgentAction, AgentConfiguration
from app.models.billing import DemoRequest, PaymentRecord, Subscription
from app.models.campaign import Campaign
from app.models.facility import Equipment, SensorReading, WorkOrder
from app.models.inventory import FootTraffic, InventoryItem, SalesVelocity
from app.models.notification import Notification
from app.models.property import MallProperty
from app.models.shopper import ShopperInteraction
from app.models.tenant import Tenant
from app.models.user import User


superadmin_bp = Blueprint("superadmin", __name__)

VALID_ROLES = {
    "superadmin",
    "mall_admin",
    "store_manager",
    "marketing_manager",
    "facility_manager",
    "shopper",
}
VALID_TIERS = {"starter", "professional", "enterprise"}
VALID_DEMO_STATUSES = {"new", "contacted", "qualified", "closed"}


@superadmin_bp.before_request
@login_required
def require_superadmin():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    if current_user.role != "superadmin":
        abort(403)


def _is_ajax_request():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def _format_uptime(delta):
    total_seconds = int(max(delta.total_seconds(), 0))
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    return f"{days} days, {hours} hours, {minutes} minutes"


def _change_property_tier_internal(property_id, new_tier):
    property_record = MallProperty.query.get_or_404(property_id)
    property_record.subscription_tier = new_tier

    subscription = Subscription.query.filter_by(property_id=property_id).first()
    if subscription:
        subscription.plan_name = new_tier

    db.session.commit()
    return property_record


def _build_agent_logs_query(args):
    mission_type = (args.get("mission_type", "all") or "all").strip().lower()
    status_filter = (args.get("status", "all") or "all").strip().lower()
    property_filter = args.get("property_id", 0, type=int)
    date_from = (args.get("date_from", "") or "").strip()
    date_to = (args.get("date_to", "") or "").strip()

    query = db.session.query(AgentAction, MallProperty).join(
        MallProperty,
        AgentAction.property_id == MallProperty.id,
    )

    if mission_type != "all":
        query = query.filter(AgentAction.mission_type == mission_type)

    if status_filter != "all":
        query = query.filter(AgentAction.status == status_filter)

    if property_filter > 0:
        query = query.filter(AgentAction.property_id == property_filter)

    date_from_dt = _parse_date(date_from)
    if date_from_dt:
        query = query.filter(AgentAction.created_at >= date_from_dt)

    date_to_dt = _parse_date(date_to)
    if date_to_dt:
        query = query.filter(AgentAction.created_at < (date_to_dt + timedelta(days=1)))

    query = query.order_by(AgentAction.created_at.desc())

    filters = {
        "mission_type": mission_type,
        "status": status_filter,
        "property_id": property_filter,
        "date_from": date_from,
        "date_to": date_to,
    }

    return query, filters


@superadmin_bp.route("", methods=["GET"])
@superadmin_bp.route("/", methods=["GET"])
def dashboard():
    now = datetime.utcnow()
    first_day_of_current_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    total_properties = MallProperty.query.count()
    onboarded_properties = MallProperty.query.filter_by(onboarding_complete=True).count()

    total_users = User.query.count()
    role_breakdown = {
        role: count
        for role, count in db.session.query(User.role, db.func.count(User.id)).group_by(User.role).all()
    }

    total_tenants = Tenant.query.count()
    active_tenants = Tenant.query.filter_by(is_active=True).count()

    active_subscriptions = Subscription.query.filter_by(status="active").count()
    trial_subscriptions = Subscription.query.filter_by(status="trial").count()
    past_due_subscriptions = Subscription.query.filter_by(status="past_due").count()

    total_revenue_all_time = (
        db.session.query(db.func.sum(PaymentRecord.amount_inr))
        .filter(PaymentRecord.status == "captured")
        .scalar()
        or 0
    )

    total_revenue_this_month = (
        db.session.query(db.func.sum(PaymentRecord.amount_inr))
        .filter(
            PaymentRecord.status == "captured",
            PaymentRecord.created_at >= first_day_of_current_month,
        )
        .scalar()
        or 0
    )

    agent_actions_today = AgentAction.query.filter(AgentAction.created_at >= today_start).count()
    pending_agent_actions_all = AgentAction.query.filter_by(status="pending").count()

    total_inventory_items = InventoryItem.query.count()
    total_campaigns_active = Campaign.query.filter_by(status="active").count()
    total_open_work_orders = WorkOrder.query.filter_by(status="open").count()
    total_shopper_queries_today = ShopperInteraction.query.filter(ShopperInteraction.timestamp >= today_start).count()

    recent_agent_actions = AgentAction.query.order_by(AgentAction.created_at.desc()).limit(10).all()
    recent_properties = MallProperty.query.order_by(MallProperty.created_at.desc()).limit(5).all()
    recent_demo_requests = DemoRequest.query.order_by(DemoRequest.created_at.desc()).limit(5).all()

    scheduler = getattr(current_app, "scheduler", None)
    scheduler_running = scheduler.running if scheduler else False

    return render_template(
        "superadmin/dashboard.html",
        total_properties=total_properties,
        onboarded_properties=onboarded_properties,
        total_users=total_users,
        role_breakdown=role_breakdown,
        total_tenants=total_tenants,
        active_tenants=active_tenants,
        active_subscriptions=active_subscriptions,
        trial_subscriptions=trial_subscriptions,
        past_due_subscriptions=past_due_subscriptions,
        total_revenue_all_time=total_revenue_all_time,
        total_revenue_this_month=total_revenue_this_month,
        agent_actions_today=agent_actions_today,
        pending_agent_actions_all=pending_agent_actions_all,
        total_inventory_items=total_inventory_items,
        total_campaigns_active=total_campaigns_active,
        total_open_work_orders=total_open_work_orders,
        total_shopper_queries_today=total_shopper_queries_today,
        recent_agent_actions=recent_agent_actions,
        recent_properties=recent_properties,
        recent_demo_requests=recent_demo_requests,
        scheduler_running=scheduler_running,
    )


@superadmin_bp.route("/properties", methods=["GET"])
def properties():
    search = (request.args.get("search", "") or "").strip()
    tier_filter = (request.args.get("tier", "all") or "all").strip().lower()
    status_filter = (request.args.get("status", "all") or "all").strip().lower()
    page = request.args.get("page", 1, type=int)

    user_counts_subq = (
        db.session.query(
            User.property_id.label("property_id"),
            db.func.count(User.id).label("user_count"),
        )
        .group_by(User.property_id)
        .subquery()
    )
    tenant_counts_subq = (
        db.session.query(
            Tenant.property_id.label("property_id"),
            db.func.count(Tenant.id).label("tenant_count"),
        )
        .group_by(Tenant.property_id)
        .subquery()
    )

    query = (
        db.session.query(
            MallProperty,
            db.func.coalesce(user_counts_subq.c.user_count, 0).label("user_count"),
            db.func.coalesce(tenant_counts_subq.c.tenant_count, 0).label("tenant_count"),
        )
        .outerjoin(user_counts_subq, user_counts_subq.c.property_id == MallProperty.id)
        .outerjoin(tenant_counts_subq, tenant_counts_subq.c.property_id == MallProperty.id)
    )

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                MallProperty.name.ilike(search_term),
                MallProperty.city.ilike(search_term),
            )
        )

    if tier_filter != "all":
        query = query.filter(MallProperty.subscription_tier == tier_filter)

    if status_filter == "onboarded":
        query = query.filter(MallProperty.onboarding_complete.is_(True))
    elif status_filter == "pending":
        query = query.filter(MallProperty.onboarding_complete.is_(False))

    pagination = query.order_by(MallProperty.created_at.desc()).paginate(page=page, per_page=20, error_out=False)

    property_ids = [row[0].id for row in pagination.items]
    owner_ids = [row[0].owner_user_id for row in pagination.items if row[0].owner_user_id]

    owner_map = {}
    if owner_ids:
        owners = User.query.filter(User.id.in_(owner_ids)).all()
        owner_map = {user.id: user.full_name for user in owners}

    subscription_map = {}
    if property_ids:
        subscriptions = Subscription.query.filter(Subscription.property_id.in_(property_ids)).all()
        subscription_map = {sub.property_id: sub for sub in subscriptions}

    property_rows = []
    for property_record, user_count, tenant_count in pagination.items:
        subscription = subscription_map.get(property_record.id)
        property_rows.append(
            {
                "property": property_record,
                "owner_name": owner_map.get(property_record.owner_user_id, "Unassigned"),
                "tenant_count": int(tenant_count or 0),
                "user_count": int(user_count or 0),
                "subscription_status": subscription.status if subscription else "none",
            }
        )

    filters = {
        "search": search,
        "tier": tier_filter,
        "status": status_filter,
    }

    return render_template(
        "superadmin/properties.html",
        pagination=pagination,
        property_rows=property_rows,
        filters=filters,
    )


@superadmin_bp.route("/properties/<int:property_id>", methods=["GET"])
def property_detail(property_id):
    property_record = MallProperty.query.get_or_404(property_id)

    users = User.query.filter_by(property_id=property_id).order_by(User.created_at.desc()).all()
    tenants = Tenant.query.filter_by(property_id=property_id).order_by(Tenant.created_at.desc()).all()
    agent_config = AgentConfiguration.query.filter_by(property_id=property_id).first()
    subscription = Subscription.query.filter_by(property_id=property_id).first()

    recent_agent_actions = (
        AgentAction.query.filter_by(property_id=property_id)
        .order_by(AgentAction.created_at.desc())
        .limit(20)
        .all()
    )
    recent_campaigns = (
        Campaign.query.filter_by(property_id=property_id)
        .order_by(Campaign.created_at.desc())
        .limit(20)
        .all()
    )
    recent_work_orders = (
        WorkOrder.query.filter_by(property_id=property_id)
        .order_by(WorkOrder.created_at.desc())
        .limit(10)
        .all()
    )

    active_campaign_count = Campaign.query.filter_by(property_id=property_id, status="active").count()
    open_work_order_count = WorkOrder.query.filter_by(property_id=property_id, status="open").count()

    return render_template(
        "superadmin/property_detail.html",
        property=property_record,
        users=users,
        tenants=tenants,
        agent_config=agent_config,
        subscription=subscription,
        recent_agent_actions=recent_agent_actions,
        recent_campaigns=recent_campaigns,
        recent_work_orders=recent_work_orders,
        active_campaign_count=active_campaign_count,
        open_work_order_count=open_work_order_count,
    )


@superadmin_bp.route("/properties/<int:property_id>/change-tier", methods=["POST"])
def change_property_tier(property_id):
    payload = request.get_json(silent=True) or {}
    new_tier = (request.form.get("tier") or payload.get("tier") or "").strip().lower()

    if new_tier not in VALID_TIERS:
        return jsonify({"success": False, "message": "Invalid tier."}), 400

    try:
        _change_property_tier_internal(property_id, new_tier)
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "message": "Unable to change property tier."}), 500

    if _is_ajax_request():
        return jsonify({"success": True, "message": f"Property tier changed to {new_tier}."}), 200

    flash(f"Property tier changed to {new_tier}.", "success")
    return redirect(url_for("superadmin.property_detail", property_id=property_id))


@superadmin_bp.route("/properties/<int:property_id>/suspend", methods=["POST"])
def suspend_property(property_id):
    _property = MallProperty.query.get_or_404(property_id)

    try:
        User.query.filter(
            User.property_id == property_id,
            User.role != "superadmin",
        ).update({"is_active": False}, synchronize_session=False)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "message": "Unable to suspend property."}), 500

    return jsonify({"success": True, "message": "Property suspended. All users deactivated."}), 200


@superadmin_bp.route("/users", methods=["GET"])
def users():
    search = (request.args.get("search", "") or "").strip()
    role_filter = (request.args.get("role", "all") or "all").strip().lower()
    property_filter = request.args.get("property_id", 0, type=int)
    active_filter = (request.args.get("active", "all") or "all").strip().lower()
    page = request.args.get("page", 1, type=int)

    query = db.session.query(User, MallProperty).outerjoin(
        MallProperty,
        User.property_id == MallProperty.id,
    )

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                User.full_name.ilike(search_term),
                User.email.ilike(search_term),
            )
        )

    if role_filter != "all":
        query = query.filter(User.role == role_filter)

    if property_filter > 0:
        query = query.filter(User.property_id == property_filter)

    if active_filter == "active":
        query = query.filter(User.is_active.is_(True))
    elif active_filter == "inactive":
        query = query.filter(User.is_active.is_(False))

    pagination = query.order_by(User.created_at.desc()).paginate(page=page, per_page=25, error_out=False)
    properties = MallProperty.query.order_by(MallProperty.name.asc()).all()

    filters = {
        "search": search,
        "role": role_filter,
        "property_id": property_filter,
        "active": active_filter,
    }

    return render_template(
        "superadmin/users.html",
        pagination=pagination,
        properties=properties,
        filters=filters,
    )


@superadmin_bp.route("/users/<int:user_id>/deactivate", methods=["POST"])
def deactivate_user(user_id):
    if user_id == current_user.id:
        return jsonify({"success": False, "message": "You cannot deactivate your own account."}), 400

    user = User.query.get_or_404(user_id)

    try:
        user.is_active = not bool(user.is_active)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "message": "Unable to update user status."}), 500

    message = "User activated." if user.is_active else "User deactivated."
    return jsonify({"success": True, "is_active": user.is_active, "message": message}), 200


@superadmin_bp.route("/users/<int:user_id>/change-role", methods=["POST"])
def change_user_role(user_id):
    if user_id == current_user.id:
        return jsonify({"success": False, "message": "You cannot change your own role."}), 400

    user = User.query.get_or_404(user_id)
    payload = request.get_json(silent=True) or {}
    new_role = (payload.get("role") or "").strip().lower()

    if new_role not in VALID_ROLES:
        return jsonify({"success": False, "message": "Invalid role."}), 400

    try:
        user.role = new_role
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "message": "Unable to change role."}), 500

    return jsonify({"success": True, "role": user.role}), 200


@superadmin_bp.route("/users/<int:user_id>/verify", methods=["POST"])
def verify_user(user_id):
    user = User.query.get_or_404(user_id)

    try:
        user.is_verified = True
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "message": "Unable to verify user."}), 500

    return jsonify({"success": True, "message": f"{user.full_name} verified."}), 200


@superadmin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
def delete_user(user_id):
    if user_id == current_user.id:
        return jsonify({"success": False, "message": "You cannot delete your own account."}), 400

    user = User.query.get_or_404(user_id)

    if user.role == "superadmin":
        return jsonify({"success": False, "message": "Superadmin users cannot be deleted here."}), 400

    owns_property = MallProperty.query.filter_by(owner_user_id=user.id).first() is not None
    if owns_property:
        try:
            user.is_active = False
            db.session.commit()
        except Exception:
            db.session.rollback()
            return jsonify({"success": False, "message": "Unable to deactivate owner user."}), 500

        return (
            jsonify(
                {
                    "success": True,
                    "message": "User deactivated instead of deleted (owns a property).",
                }
            ),
            200,
        )

    try:
        db.session.delete(user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "message": "Unable to delete user."}), 500

    return jsonify({"success": True}), 200


@superadmin_bp.route("/tenants", methods=["GET"])
def tenants():
    search = (request.args.get("search", "") or "").strip()
    category_filter = (request.args.get("category", "all") or "all").strip()
    property_filter = request.args.get("property_id", 0, type=int)
    active_filter = (request.args.get("active", "all") or "all").strip().lower()
    page = request.args.get("page", 1, type=int)

    query = db.session.query(Tenant, MallProperty).join(
        MallProperty,
        Tenant.property_id == MallProperty.id,
    )

    if search:
        query = query.filter(Tenant.name.ilike(f"%{search}%"))

    if category_filter != "all":
        query = query.filter(Tenant.category == category_filter)

    if property_filter > 0:
        query = query.filter(Tenant.property_id == property_filter)

    if active_filter == "active":
        query = query.filter(Tenant.is_active.is_(True))
    elif active_filter == "inactive":
        query = query.filter(Tenant.is_active.is_(False))

    pagination = query.order_by(Tenant.created_at.desc()).paginate(page=page, per_page=25, error_out=False)

    category_rows = (
        db.session.query(Tenant.category)
        .filter(Tenant.category.isnot(None), Tenant.category != "")
        .distinct()
        .order_by(Tenant.category.asc())
        .all()
    )
    categories = [row[0] for row in category_rows]

    properties = MallProperty.query.order_by(MallProperty.name.asc()).all()

    top_categories_rows = (
        db.session.query(Tenant.category, db.func.count(Tenant.id).label("count"))
        .filter(Tenant.category.isnot(None), Tenant.category != "")
        .group_by(Tenant.category)
        .order_by(db.func.count(Tenant.id).desc())
        .limit(5)
        .all()
    )

    filters = {
        "search": search,
        "category": category_filter,
        "property_id": property_filter,
        "active": active_filter,
    }

    return render_template(
        "superadmin/tenants.html",
        pagination=pagination,
        categories=categories,
        properties=properties,
        top_categories=top_categories_rows,
        filters=filters,
    )


@superadmin_bp.route("/tenants/<int:tenant_id>/toggle-active", methods=["POST"])
def toggle_tenant_active(tenant_id):
    tenant = Tenant.query.get_or_404(tenant_id)

    try:
        tenant.is_active = not bool(tenant.is_active)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "message": "Unable to update tenant status."}), 500

    return jsonify(
        {
            "success": True,
            "is_active": tenant.is_active,
            "message": "Tenant activated." if tenant.is_active else "Tenant deactivated.",
        }
    ), 200


@superadmin_bp.route("/billing", methods=["GET"])
def billing():
    now = datetime.utcnow()
    first_day_of_current_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    subscriptions = (
        db.session.query(Subscription, MallProperty)
        .join(MallProperty, Subscription.property_id == MallProperty.id)
        .order_by(Subscription.created_at.desc())
        .all()
    )

    payments = (
        db.session.query(PaymentRecord, MallProperty)
        .join(MallProperty, PaymentRecord.property_id == MallProperty.id)
        .order_by(PaymentRecord.created_at.desc())
        .limit(50)
        .all()
    )

    revenue_by_month = []
    for offset in range(11, -1, -1):
        month_value = first_day_of_current_month.month - offset
        year_value = first_day_of_current_month.year
        while month_value <= 0:
            month_value += 12
            year_value -= 1

        month_start = datetime(year_value, month_value, 1)
        if month_value == 12:
            next_month = datetime(year_value + 1, 1, 1)
        else:
            next_month = datetime(year_value, month_value + 1, 1)

        month_total = (
            db.session.query(db.func.sum(PaymentRecord.amount_inr))
            .filter(
                PaymentRecord.status == "captured",
                PaymentRecord.created_at >= month_start,
                PaymentRecord.created_at < next_month,
            )
            .scalar()
            or 0
        )
        revenue_by_month.append({"month": month_start.strftime("%b %Y"), "total_inr": float(month_total)})

    revenue_by_tier_rows = (
        db.session.query(PaymentRecord.plan_name, db.func.sum(PaymentRecord.amount_inr))
        .filter(PaymentRecord.status == "captured")
        .group_by(PaymentRecord.plan_name)
        .all()
    )
    revenue_by_tier = [
        {"plan": (plan_name or "starter"), "total_inr": float(total or 0)}
        for plan_name, total in revenue_by_tier_rows
    ]

    outstanding_subscriptions = (
        db.session.query(Subscription, MallProperty)
        .join(MallProperty, Subscription.property_id == MallProperty.id)
        .filter(Subscription.status.in_(["past_due", "trial"]))
        .order_by(Subscription.created_at.desc())
        .all()
    )

    total_revenue_all_time = (
        db.session.query(db.func.sum(PaymentRecord.amount_inr))
        .filter(PaymentRecord.status == "captured")
        .scalar()
        or 0
    )
    total_revenue_this_month = (
        db.session.query(db.func.sum(PaymentRecord.amount_inr))
        .filter(
            PaymentRecord.status == "captured",
            PaymentRecord.created_at >= first_day_of_current_month,
        )
        .scalar()
        or 0
    )

    active_subscription_count = Subscription.query.filter_by(status="active").count()
    mrr_estimate = (
        db.session.query(db.func.sum(Subscription.price_inr))
        .filter(
            Subscription.status == "active",
            Subscription.billing_cycle == "monthly",
        )
        .scalar()
        or 0
    )

    return render_template(
        "superadmin/billing.html",
        subscriptions=subscriptions,
        payments=payments,
        revenue_by_month=revenue_by_month,
        revenue_by_tier=revenue_by_tier,
        past_due_subscriptions=outstanding_subscriptions,
        total_revenue_all_time=total_revenue_all_time,
        total_revenue_this_month=total_revenue_this_month,
        active_subscription_count=active_subscription_count,
        mrr_estimate=mrr_estimate,
    )


@superadmin_bp.route("/billing/extend-trial/<int:property_id>", methods=["POST"])
def extend_trial(property_id):
    subscription = Subscription.query.filter_by(property_id=property_id).first()
    if subscription is None:
        return jsonify({"success": False, "message": "Subscription not found."}), 404

    try:
        subscription.trial_ends_at = datetime.utcnow() + timedelta(days=14)
        if subscription.status == "cancelled":
            subscription.status = "trial"
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "message": "Unable to extend trial."}), 500

    return jsonify({"success": True, "message": "Trial extended by 14 days."}), 200


@superadmin_bp.route("/billing/change-tier/<int:property_id>", methods=["POST"])
def billing_change_tier(property_id):
    payload = request.get_json(silent=True) or {}
    new_tier = (request.form.get("tier") or payload.get("tier") or "").strip().lower()

    if new_tier not in VALID_TIERS:
        return jsonify({"success": False, "message": "Invalid tier."}), 400

    try:
        _change_property_tier_internal(property_id, new_tier)
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "message": "Unable to change tier."}), 500

    return jsonify({"success": True, "message": f"Property tier changed to {new_tier}."}), 200


@superadmin_bp.route("/agent-logs", methods=["GET"])
def agent_logs():
    page = request.args.get("page", 1, type=int)
    query, filters = _build_agent_logs_query(request.args)
    pagination = query.paginate(page=page, per_page=25, error_out=False)

    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    actions_this_month = AgentAction.query.filter(AgentAction.created_at >= month_start)
    total_actions_month = actions_this_month.count()

    resolved_total = actions_this_month.filter(
        AgentAction.status.in_(["approved", "rejected", "auto_executed", "failed"])
    ).count()
    approved_total = actions_this_month.filter(
        AgentAction.status.in_(["approved", "auto_executed"])
    ).count()
    approval_rate = (approved_total / resolved_total * 100.0) if resolved_total else 0.0

    auto_executed_count = actions_this_month.filter(AgentAction.status == "auto_executed").count()

    most_active_row = (
        db.session.query(MallProperty.name, db.func.count(AgentAction.id).label("action_count"))
        .join(AgentAction, AgentAction.property_id == MallProperty.id)
        .filter(AgentAction.created_at >= month_start)
        .group_by(MallProperty.id)
        .order_by(db.func.count(AgentAction.id).desc())
        .first()
    )
    most_active_property = most_active_row[0] if most_active_row else "N/A"

    properties = MallProperty.query.order_by(MallProperty.name.asc()).all()

    return render_template(
        "superadmin/agent_logs.html",
        pagination=pagination,
        filters=filters,
        properties=properties,
        total_actions_month=total_actions_month,
        approval_rate=approval_rate,
        auto_executed_count=auto_executed_count,
        most_active_property=most_active_property,
    )


@superadmin_bp.route("/agent-logs/export", methods=["GET"])
def export_agent_logs():
    query, _filters = _build_agent_logs_query(request.args)
    rows = query.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Log ID",
            "Property",
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

    for action, property_record in rows:
        writer.writerow(
            [
                action.id,
                property_record.name if property_record else "",
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

    filename = f"RetailMind_PlatformAgentLogs_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@superadmin_bp.route("/demo-requests", methods=["GET"])
def demo_requests():
    status_filter = (request.args.get("status", "all") or "all").strip().lower()
    page = request.args.get("page", 1, type=int)

    query = DemoRequest.query
    if status_filter != "all":
        query = query.filter(DemoRequest.status == status_filter)

    pagination = query.order_by(DemoRequest.created_at.desc()).paginate(page=page, per_page=20, error_out=False)

    summary = {
        "new": DemoRequest.query.filter_by(status="new").count(),
        "contacted": DemoRequest.query.filter_by(status="contacted").count(),
        "qualified": DemoRequest.query.filter_by(status="qualified").count(),
        "closed": DemoRequest.query.filter_by(status="closed").count(),
    }

    return render_template(
        "superadmin/demo_requests.html",
        pagination=pagination,
        status_filter=status_filter,
        summary=summary,
    )


@superadmin_bp.route("/demo-requests/<int:req_id>/update", methods=["POST"])
def update_demo_request(req_id):
    demo_request = DemoRequest.query.get_or_404(req_id)

    payload = request.get_json(silent=True) or {}
    new_status = (payload.get("status") or "").strip().lower()

    if new_status not in VALID_DEMO_STATUSES:
        return jsonify({"success": False, "message": "Invalid status."}), 400

    try:
        demo_request.status = new_status
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "message": "Unable to update request."}), 500

    return jsonify({"success": True}), 200


@superadmin_bp.route("/system-health", methods=["GET"])
def system_health():
    now = datetime.utcnow()
    start_time = getattr(current_app, "start_time", now)
    uptime_delta = now - start_time
    uptime_formatted = _format_uptime(uptime_delta)

    db_uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    db_path = db_uri.replace("sqlite:///", "") if db_uri.startswith("sqlite:///") else ""
    if db_path and not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(current_app.root_path), db_path)

    if not db_path or ":memory:" in db_path or not os.path.exists(db_path):
        size_mb = 0
    else:
        size_mb = os.path.getsize(db_path) / (1024 * 1024)

    try:
        table_names = db.inspect(db.engine).get_table_names()
    except Exception:
        try:
            with db.engine.connect() as connection:
                table_names = db.engine.dialect.get_table_names(connection)
        except Exception:
            table_names = []

    record_counts = {
        "Users": User.query.count(),
        "Properties": MallProperty.query.count(),
        "Tenants": Tenant.query.count(),
        "Agent Actions": AgentAction.query.count(),
        "Inventory Items": InventoryItem.query.count(),
        "Sales Velocity Records": SalesVelocity.query.count(),
        "Foot Traffic Records": FootTraffic.query.count(),
        "Campaigns": Campaign.query.count(),
        "Equipment": Equipment.query.count(),
        "Sensor Readings": SensorReading.query.count(),
        "Work Orders": WorkOrder.query.count(),
        "Shopper Interactions": ShopperInteraction.query.count(),
        "Notifications": Notification.query.count(),
        "Subscriptions": Subscription.query.count(),
        "Payment Records": PaymentRecord.query.count(),
        "Demo Requests": DemoRequest.query.count(),
    }

    scheduler = getattr(current_app, "scheduler", None)
    scheduler_running = scheduler.running if scheduler else False
    scheduler_jobs = []
    if scheduler:
        for job in scheduler.get_jobs():
            scheduler_jobs.append(
                {
                    "id": job.id,
                    "name": job.name or job.id,
                    "next_run": job.next_run_time.strftime("%Y-%m-%d %H:%M UTC") if job.next_run_time else "Not scheduled",
                    "trigger": str(job.trigger),
                }
            )

    gemini_status = {"enabled": False, "latency_ms": None, "response": None, "error": None}
    if current_app.config.get("GEMINI_ENABLED"):
        try:
            import time
            from google import genai

            t0 = time.time()
            client = genai.Client()
            response = client.models.generate_content(model="gemini-2.5-flash", contents="test")
            latency = int((time.time() - t0) * 1000)
            gemini_status = {
                "enabled": True,
                "latency_ms": latency,
                "response": (response.text or "").strip() if response else None,
                "error": None,
            }
        except Exception as exc:
            gemini_status = {"enabled": True, "latency_ms": None, "response": None, "error": str(exc)}

    razorpay_status = {"enabled": False, "error": None, "key_id_prefix": None}
    if current_app.config.get("RAZORPAY_ENABLED"):
        try:
            from app.services.razorpay_service import get_razorpay_client

            client = get_razorpay_client()
            if hasattr(client, "order"):
                client.order.all({"count": 1})

            key_id = current_app.config.get("RAZORPAY_KEY_ID") or os.getenv("RAZORPAY_KEY_ID") or ""
            razorpay_status = {
                "enabled": True,
                "error": None,
                "key_id_prefix": f"{key_id[:8]}..." if key_id else None,
            }
        except Exception as exc:
            key_id = current_app.config.get("RAZORPAY_KEY_ID") or os.getenv("RAZORPAY_KEY_ID") or ""
            razorpay_status = {
                "enabled": True,
                "error": str(exc),
                "key_id_prefix": f"{key_id[:8]}..." if key_id else None,
            }

    es_status = {"enabled": False, "connected": False, "cluster_status": None, "error": None}
    if current_app.config.get("ES_ENABLED"):
        try:
            from elasticsearch import Elasticsearch

            es = Elasticsearch(cloud_id=os.getenv("ES_CLOUD_ID"), api_key=os.getenv("ES_API_KEY"))
            ping_result = es.ping()

            cluster_status = None
            if ping_result:
                try:
                    health = es.cluster.health()
                    cluster_status = health.get("status")
                except Exception:
                    cluster_status = None

            es_status = {
                "enabled": True,
                "connected": bool(ping_result),
                "cluster_status": cluster_status,
                "error": None,
            }
        except Exception as exc:
            es_status = {
                "enabled": True,
                "connected": False,
                "cluster_status": None,
                "error": str(exc),
            }

    python_version = sys.version.split()[0]
    flask_version = flask.__version__

    seed_superadmin = User.query.filter_by(role="superadmin").order_by(User.created_at.asc()).first()
    last_seed_run = seed_superadmin.created_at if seed_superadmin else None

    flask_env = current_app.config.get("ENV", "development")

    issue_count = 0
    if not scheduler_running:
        issue_count += 1
    if gemini_status.get("enabled") and gemini_status.get("error"):
        issue_count += 1
    if razorpay_status.get("enabled") and razorpay_status.get("error"):
        issue_count += 1
    if es_status.get("enabled") and not es_status.get("connected"):
        issue_count += 1

    return render_template(
        "superadmin/system_health.html",
        uptime_formatted=uptime_formatted,
        issue_count=issue_count,
        start_time=start_time,
        db_path=db_path or "In-memory / unknown",
        size_mb=size_mb,
        total_tables=len(table_names),
        record_counts=record_counts,
        scheduler_running=scheduler_running,
        scheduler_jobs=scheduler_jobs,
        gemini_status=gemini_status,
        razorpay_status=razorpay_status,
        es_status=es_status,
        python_version=python_version,
        flask_version=flask_version,
        last_seed_run=last_seed_run,
        flask_env=flask_env,
    )
