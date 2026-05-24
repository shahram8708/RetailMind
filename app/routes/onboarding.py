import json
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.forms.onboarding import (
    OnboardingStep1Form,
    OnboardingStep2Form,
    OnboardingStep3Form,
    OnboardingStep4Form,
    OnboardingStep5Form,
)
from app.models.agent import AgentConfiguration
from app.models.property import MallProperty
from app.models.tenant import Tenant
from app.services.notification_service import create_notification


onboarding_bp = Blueprint("onboarding", __name__)


STEP_DETAILS = {
    1: {
        "title": "Property Details",
        "description": "Basic info about your mall",
    },
    2: {
        "title": "Data Connections",
        "description": "Link your existing systems",
    },
    3: {
        "title": "Tenant Setup",
        "description": "Add your tenant stores",
    },
    4: {
        "title": "Agent Configuration",
        "description": "Configure AI thresholds",
    },
    5: {
        "title": "Preferences",
        "description": "Notifications and alerts",
    },
}


def _json_loads_safe(value, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _get_property_for_user(user):
    if user.property_id is None:
        return None
    return MallProperty.query.get(user.property_id)


def get_current_onboarding_step(user):
    property_record = _get_property_for_user(user)

    if property_record is None:
        return 1

    if not property_record.location or not property_record.city:
        return 1

    has_data_source_config = bool(
        property_record.data_source_config
        and property_record.data_source_config.strip()
        and property_record.data_source_config.strip() not in {"{}", "null"}
    )
    if not has_data_source_config:
        return 2

    has_tenant_records = Tenant.query.filter_by(property_id=property_record.id).count() > 0
    skipped_tenant_setup = bool(session.get("tenant_setup_skipped", False))
    if not has_tenant_records and not skipped_tenant_setup:
        return 3

    agent_config = AgentConfiguration.query.filter_by(property_id=property_record.id).first()
    if agent_config is None:
        return 4

    if not property_record.onboarding_complete:
        return 5

    return 0


@onboarding_bp.before_request
def enforce_onboarding_progress():
    if not current_user.is_authenticated:
        return None

    endpoint = request.endpoint or ""
    if endpoint == "onboarding.static":
        return None

    allowed_step = get_current_onboarding_step(current_user)
    session_step = session.get("onboarding_step")
    if isinstance(session_step, int) and session_step > 0 and allowed_step > 0:
        allowed_step = min(allowed_step, session_step)

    if allowed_step == 0 and endpoint != "onboarding.complete":
        return redirect(url_for("dashboard.index"))

    if endpoint.startswith("onboarding.step"):
        try:
            requested_step = int(endpoint.replace("onboarding.step", ""))
        except ValueError:
            return None

        if requested_step > allowed_step > 0:
            return redirect(url_for(f"onboarding.step{allowed_step}"))

    return None


def _render_step(template_name, form, step_number, **context):
    details = STEP_DETAILS[step_number]
    previous_step_url = url_for(f"onboarding.step{step_number - 1}") if step_number > 1 else None

    return render_template(
        template_name,
        form=form,
        current_step=step_number,
        step_title=details["title"],
        step_description=details["description"],
        previous_step_url=previous_step_url,
        **context,
    )


@onboarding_bp.route("/")
@login_required
def root():
    return redirect(url_for("onboarding.complete"))


@onboarding_bp.route("/step/1", methods=["GET", "POST"])
@login_required
def step1():
    form = OnboardingStep1Form()
    property_record = _get_property_for_user(current_user)

    if request.method == "GET" and property_record is not None:
        form.mall_name.data = property_record.name
        form.full_address.data = property_record.location
        if property_record.city:
            form.city.data = property_record.city
        form.country.data = property_record.country or "India"
        form.total_area_sqft.data = property_record.total_area_sqft
        form.num_floors.data = property_record.num_floors
        form.num_tenants_approx.data = property_record.num_tenants

    if form.validate_on_submit():
        try:
            property_record = _get_property_for_user(current_user)

            if property_record is None:
                property_record = MallProperty(
                    owner_user_id=current_user.id,
                    country="India",
                    onboarding_complete=False,
                )
                db.session.add(property_record)
                db.session.flush()
                current_user.property_id = property_record.id

            property_record.name = (form.mall_name.data or "").strip()
            property_record.location = (form.full_address.data or "").strip()
            property_record.city = form.city.data
            property_record.country = "India"
            property_record.total_area_sqft = form.total_area_sqft.data
            property_record.num_floors = form.num_floors.data
            property_record.num_tenants = form.num_tenants_approx.data

            db.session.commit()
            session["onboarding_step"] = 2
            return redirect(url_for("onboarding.step2"))
        except Exception:
            db.session.rollback()
            flash("Unable to save property details right now. Please try again.", "danger")

    return _render_step("onboarding/step1.html", form, 1)


@onboarding_bp.route("/step/2", methods=["GET", "POST"])
@login_required
def step2():
    property_record = _get_property_for_user(current_user)
    if property_record is None:
        return redirect(url_for("onboarding.step1"))

    form = OnboardingStep2Form()

    if request.method == "GET":
        existing_config = _json_loads_safe(property_record.data_source_config, {})
        form.pos_system.data = existing_config.get("pos_system", form.pos_system.data)
        form.pos_api_endpoint.data = existing_config.get("pos_api_endpoint")
        form.pos_api_key.data = existing_config.get("pos_api_key")
        form.inventory_system.data = existing_config.get("inventory_system", form.inventory_system.data)
        form.inventory_api_endpoint.data = existing_config.get("inventory_api_endpoint")
        form.inventory_api_key.data = existing_config.get("inventory_api_key")
        form.crm_system.data = existing_config.get("crm_system", form.crm_system.data)
        form.sensor_source.data = existing_config.get("sensor_source", form.sensor_source.data)
        form.sensor_api_endpoint.data = existing_config.get("sensor_api_endpoint")
        form.weather_api_key.data = existing_config.get("weather_api_key")

    if form.validate_on_submit():
        config_payload = {
            "pos_system": form.pos_system.data,
            "pos_api_endpoint": (form.pos_api_endpoint.data or "").strip() or None,
            "pos_api_key": (form.pos_api_key.data or "").strip() or None,
            "inventory_system": form.inventory_system.data,
            "inventory_api_endpoint": (form.inventory_api_endpoint.data or "").strip() or None,
            "inventory_api_key": (form.inventory_api_key.data or "").strip() or None,
            "crm_system": form.crm_system.data,
            "sensor_source": form.sensor_source.data,
            "sensor_api_endpoint": (form.sensor_api_endpoint.data or "").strip() or None,
            "weather_api_key": (form.weather_api_key.data or "").strip() or None,
        }

        try:
            property_record.data_source_config = json.dumps(config_payload)
            db.session.commit()
            session["onboarding_step"] = 3
            return redirect(url_for("onboarding.step3"))
        except Exception:
            db.session.rollback()
            flash("Unable to save data connections right now. Please try again.", "danger")

    return _render_step("onboarding/step2.html", form, 2)


@onboarding_bp.route("/step/3", methods=["GET", "POST"])
@login_required
def step3():
    property_record = _get_property_for_user(current_user)
    if property_record is None:
        return redirect(url_for("onboarding.step1"))

    form = OnboardingStep3Form()
    existing_tenants = Tenant.query.filter_by(property_id=property_record.id).order_by(Tenant.id.asc()).all()
    existing_tenants_json = [
        {
            "name": tenant.name,
            "category": tenant.category or "",
            "zone": tenant.zone or "",
            "floor": tenant.floor,
            "unit_number": tenant.unit_number or "",
            "contact_email": tenant.contact_email or "",
        }
        for tenant in existing_tenants
    ]

    if form.validate_on_submit():
        try:
            if form.skip_for_now.data:
                session["tenant_setup_skipped"] = True
                session["onboarding_step"] = 4
                return redirect(url_for("onboarding.step4"))

            submitted_rows = _json_loads_safe(form.tenants_json.data, [])
            existing_by_unit = {
                (tenant.unit_number or "").strip().lower(): tenant
                for tenant in existing_tenants
                if (tenant.unit_number or "").strip()
            }

            submitted_units = set()
            for row in submitted_rows:
                if not isinstance(row, dict):
                    continue

                name = (row.get("name") or "").strip()
                category = (row.get("category") or "").strip()
                zone = (row.get("zone") or "").strip()
                floor = row.get("floor")
                unit_number = (row.get("unit_number") or "").strip()
                contact_email = (row.get("contact_email") or "").strip() or None

                if not all([name, category, zone, unit_number]) or floor in (None, ""):
                    continue

                try:
                    floor_value = int(floor)
                except (TypeError, ValueError):
                    continue

                unit_key = unit_number.lower()
                submitted_units.add(unit_key)

                tenant = existing_by_unit.get(unit_key)
                if tenant is None:
                    tenant = Tenant(property_id=property_record.id, unit_number=unit_number)
                    db.session.add(tenant)

                tenant.name = name
                tenant.category = category
                tenant.zone = zone
                tenant.floor = floor_value
                tenant.unit_number = unit_number
                tenant.contact_email = contact_email
                tenant.is_active = True

            for tenant in existing_tenants:
                existing_key = (tenant.unit_number or "").strip().lower()
                if not existing_key or existing_key not in submitted_units:
                    db.session.delete(tenant)

            db.session.flush()
            property_record.num_tenants = Tenant.query.filter_by(property_id=property_record.id).count()

            session["tenant_setup_skipped"] = False
            session["onboarding_step"] = 4
            db.session.commit()
            return redirect(url_for("onboarding.step4"))
        except Exception:
            db.session.rollback()
            flash("Unable to save tenant setup right now. Please try again.", "danger")

    return _render_step(
        "onboarding/step3.html",
        form,
        3,
        existing_tenants=existing_tenants_json,
    )


@onboarding_bp.route("/step/4", methods=["GET", "POST"])
@login_required
def step4():
    property_record = _get_property_for_user(current_user)
    if property_record is None:
        return redirect(url_for("onboarding.step1"))

    form = OnboardingStep4Form()
    config = AgentConfiguration.query.filter_by(property_id=property_record.id).first()

    if request.method == "GET" and config is not None:
        form.inventory_srs_threshold.data = config.inventory_srs_threshold
        form.campaign_cos_threshold.data = config.campaign_cos_threshold
        form.facility_fps_threshold.data = config.facility_fps_threshold
        form.auto_approve_restock.data = config.auto_approve_restock
        form.auto_approve_campaigns.data = config.auto_approve_campaigns
        form.auto_approve_maintenance.data = config.auto_approve_maintenance
        form.notification_email.data = config.notification_email
        form.inventory_check_interval_minutes.data = config.inventory_check_interval_minutes
        form.campaign_check_interval_minutes.data = config.campaign_check_interval_minutes
        form.facility_check_interval_minutes.data = config.facility_check_interval_minutes

    if form.validate_on_submit():
        try:
            config = AgentConfiguration.query.filter_by(property_id=property_record.id).first()
            if config is None:
                config = AgentConfiguration(property_id=property_record.id)
                db.session.add(config)

            config.inventory_srs_threshold = float(form.inventory_srs_threshold.data)
            config.campaign_cos_threshold = float(form.campaign_cos_threshold.data)
            config.facility_fps_threshold = float(form.facility_fps_threshold.data)
            config.auto_approve_restock = bool(form.auto_approve_restock.data)
            config.auto_approve_campaigns = bool(form.auto_approve_campaigns.data)
            config.auto_approve_maintenance = bool(form.auto_approve_maintenance.data)
            config.notification_email = (form.notification_email.data or "").strip() or None
            config.inventory_check_interval_minutes = form.inventory_check_interval_minutes.data
            config.campaign_check_interval_minutes = form.campaign_check_interval_minutes.data
            config.facility_check_interval_minutes = form.facility_check_interval_minutes.data
            config.updated_at = datetime.utcnow()

            db.session.commit()
            session["onboarding_step"] = 5
            return redirect(url_for("onboarding.step5"))
        except Exception:
            db.session.rollback()
            flash("Unable to save agent configuration right now. Please try again.", "danger")

    return _render_step("onboarding/step4.html", form, 4)


@onboarding_bp.route("/step/5", methods=["GET", "POST"])
@login_required
def step5():
    property_record = _get_property_for_user(current_user)
    if property_record is None:
        return redirect(url_for("onboarding.step1"))

    form = OnboardingStep5Form()
    config = AgentConfiguration.query.filter_by(property_id=property_record.id).first()
    data_source_config = _json_loads_safe(property_record.data_source_config, {})

    integration_fields = [
        data_source_config.get("pos_system"),
        data_source_config.get("inventory_system"),
        data_source_config.get("crm_system"),
        data_source_config.get("sensor_source"),
    ]
    integrations_count = sum(
        1
        for value in integration_fields
        if value and value not in {"none", "simulator", "csv_import"}
    )

    if request.method == "GET":
        saved_preferences = _json_loads_safe(current_user.notification_preferences, {})
        categories = saved_preferences.get("categories", [])

        if saved_preferences:
            form.email_alerts_enabled.data = bool(saved_preferences.get("email", True))
            form.inapp_alerts_enabled.data = bool(saved_preferences.get("inapp", True))
            form.sms_alerts_enabled.data = bool(saved_preferences.get("sms", False))
            form.notify_inventory.data = "inventory" in categories
            form.notify_campaigns.data = "campaigns" in categories
            form.notify_facility.data = "facility" in categories
            form.notify_agent_actions.data = "agent_actions" in categories
            form.notify_weekly_summary.data = "weekly_summary" in categories
            form.notification_frequency.data = saved_preferences.get("frequency", "immediate")

    if form.validate_on_submit():
        try:
            categories = []
            if form.notify_inventory.data:
                categories.append("inventory")
            if form.notify_campaigns.data:
                categories.append("campaigns")
            if form.notify_facility.data:
                categories.append("facility")
            if form.notify_agent_actions.data:
                categories.append("agent_actions")
            if form.notify_weekly_summary.data:
                categories.append("weekly_summary")

            current_user.notification_preferences = json.dumps(
                {
                    "email": bool(form.email_alerts_enabled.data),
                    "inapp": bool(form.inapp_alerts_enabled.data),
                    "sms": bool(form.sms_alerts_enabled.data),
                    "categories": categories,
                    "frequency": form.notification_frequency.data,
                }
            )

            property_record.onboarding_complete = True
            db.session.commit()

            session.pop("onboarding_step", None)
            session.pop("tenant_setup_skipped", None)

            create_notification(
                user_id=current_user.id,
                property_id=property_record.id,
                title="Welcome to RetailMind! \U0001F389",
                message="Your RetailMind setup is complete. Your AI agents are now active and monitoring your mall.",
                notification_type="system",
                severity="info",
            )

            flash("Setup complete! Your AI agents are now active.", "success")
            return redirect(url_for("dashboard.index"))
        except Exception:
            db.session.rollback()
            flash("Unable to complete setup right now. Please try again.", "danger")

    tenants_count = Tenant.query.filter_by(property_id=property_record.id).count()

    return _render_step(
        "onboarding/step5.html",
        form,
        5,
        property=property_record,
        integrations_count=integrations_count,
        tenants_count=tenants_count,
        agent_config=config,
    )


@onboarding_bp.route("/complete")
@login_required
def complete():
    property_record = _get_property_for_user(current_user)
    if property_record and property_record.onboarding_complete:
        return redirect(url_for("dashboard.index"))

    current_step = get_current_onboarding_step(current_user)
    return redirect(url_for(f"onboarding.step{current_step}"))
