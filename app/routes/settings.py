import json
import os
import secrets
import string
from datetime import datetime
from io import BytesIO
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.request import Request
from urllib.request import urlopen

from flask import Blueprint
from flask import current_app
from flask import flash
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import send_file
from flask import url_for
from flask_login import current_user
from flask_login import login_required
from flask_login import logout_user
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.extensions import db
from app.forms.settings import ChangePasswordForm
from app.forms.settings import InviteTeamMemberForm
from app.forms.settings import ProfileEditForm
from app.models.billing import PaymentRecord
from app.models.billing import Subscription
from app.models.property import MallProperty
from app.models.user import User
from app.services import email_service
from app.utils.decorators import role_required


settings_bp = Blueprint("settings", __name__)


def _resolved_property_id():
    if current_user.is_superadmin():
        payload = request.get_json(silent=True) or {}
        requested = request.args.get("property_id", type=int) or payload.get("property_id")
        if requested:
            return int(requested)
        if current_user.property_id:
            return current_user.property_id
        default_property = MallProperty.query.filter_by(onboarding_complete=True).first()
        return default_property.id if default_property else None
    return current_user.property_id


def _load_property_config(property_record):
    if not property_record or not property_record.data_source_config:
        return {}
    try:
        return json.loads(property_record.data_source_config)
    except (TypeError, ValueError):
        return {}


def _integration_status_map(property_record):
    config = _load_property_config(property_record)

    def _status(value):
        if value in (None, "", "none"):
            return "not_connected"
        if value == "simulator":
            return "simulator"
        return "connected"

    pos_value = config.get("pos_system", "none")
    inventory_value = config.get("inventory_system", "none")
    crm_value = config.get("crm_system", "none")
    sensor_value = config.get("sensor_source", "none")

    status = {
        "pos": _status(pos_value),
        "inventory": _status(inventory_value),
        "crm": _status(crm_value),
        "sensor": _status(sensor_value),
        "weather": "connected" if current_app.config.get("GEMINI_ENABLED", False) else "not_connected",
        "elasticsearch": "connected" if current_app.config.get("ES_ENABLED", False) else "not_connected",
    }

    connected_integrations_count = sum(
        1
        for key in ["pos_system", "inventory_system", "crm_system", "sensor_source"]
        if config.get(key) not in (None, "", "none")
    )

    return config, status, connected_integrations_count


def _invite_context(property_id, invite_form=None):
    property_record = MallProperty.query.get(property_id) if property_id else None
    members = (
        User.query.filter_by(property_id=property_id, is_active=True)
        .order_by(User.created_at.asc())
        .all()
        if property_id
        else []
    )
    if invite_form is None:
        invite_form = InviteTeamMemberForm()
    return property_record, members, invite_form


@settings_bp.route("", methods=["GET"])
@settings_bp.route("/", methods=["GET"])
@login_required
def hub():
    property_id = _resolved_property_id()
    if not property_id:
        flash("Property not configured.", "warning")
        return redirect(url_for("dashboard.index"))

    property_record = MallProperty.query.get(property_id)
    subscription = Subscription.query.filter_by(property_id=property_id).first()
    team_count = User.query.filter_by(property_id=property_id, is_active=True).count()
    _config, _status, connected_count = _integration_status_map(property_record)

    return render_template(
        "settings/hub.html",
        property=property_record,
        subscription=subscription,
        team_count=team_count,
        connected_integrations_count=connected_count,
    )


@settings_bp.route("/team", methods=["GET", "POST"])
@login_required
@role_required("mall_admin", "superadmin")
def team():
    property_id = _resolved_property_id()
    if not property_id:
        flash("Property not configured.", "warning")
        return redirect(url_for("settings.hub"))

    if request.method == "GET":
        property_record, members, invite_form = _invite_context(property_id)
        return render_template(
            "settings/team.html",
            property=property_record,
            members=members,
            invite_form=invite_form,
        )

    invite_form = InviteTeamMemberForm(request.form)
    property_record, members, _ = _invite_context(property_id, invite_form=invite_form)

    if invite_form.validate_on_submit():
        try:
            alphabet = string.ascii_letters + string.digits + "!@#$%"
            temp_password = "".join(secrets.choice(alphabet) for _ in range(12))

            new_user = User(
                email=invite_form.email.data.strip().lower(),
                full_name=invite_form.full_name.data.strip(),
                role=invite_form.role.data,
                property_id=property_id,
                is_verified=True,
                is_active=True,
            )
            new_user.set_password(temp_password)

            db.session.add(new_user)
            db.session.commit()

            email_service.send_team_invite_email(
                new_user,
                current_user.full_name,
                property_record.name if property_record else "RetailMind Property",
                temp_password,
            )

            flash(
                f"Invitation sent to {new_user.email}. They can now log in.",
                "success",
            )
            return redirect(url_for("settings.team", property_id=property_id) if current_user.is_superadmin() else url_for("settings.team"))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Failed to invite team member")
            flash("Unable to invite team member right now.", "danger")

    if invite_form.errors:
        for field_errors in invite_form.errors.values():
            for err in field_errors:
                flash(err, "danger")

    return render_template(
        "settings/team.html",
        property=property_record,
        members=members,
        invite_form=invite_form,
    )


@settings_bp.route("/team/remove/<int:user_id>", methods=["POST"])
@login_required
@role_required("mall_admin", "superadmin")
def remove_member(user_id):
    if user_id == current_user.id:
        return jsonify({"success": False, "error": "You cannot remove yourself."}), 400

    target_user = User.query.get_or_404(user_id)
    if not current_user.is_superadmin() and target_user.property_id != current_user.property_id:
        return jsonify({"success": False, "error": "Access denied."}), 403

    try:
        target_user.is_active = False
        db.session.commit()
        return jsonify({"success": True, "message": f"{target_user.full_name} has been deactivated."}), 200
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to deactivate team member user_id=%s", user_id)
        return jsonify({"success": False, "error": "Unable to deactivate member."}), 500


@settings_bp.route("/team/change-role/<int:user_id>", methods=["POST"])
@login_required
@role_required("mall_admin", "superadmin")
def change_role(user_id):
    if user_id == current_user.id:
        return jsonify({"success": False, "error": "You cannot change your own role."}), 400

    target_user = User.query.get_or_404(user_id)
    if not current_user.is_superadmin() and target_user.property_id != current_user.property_id:
        return jsonify({"success": False, "error": "Access denied."}), 403

    payload = request.get_json(silent=True) or {}
    new_role = (payload.get("role") or "").strip()
    allowed_roles = {"store_manager", "marketing_manager", "facility_manager"}

    if new_role not in allowed_roles:
        return jsonify({"success": False, "error": "Invalid role selected."}), 400

    if new_role in {"superadmin", "mall_admin"}:
        return jsonify({"success": False, "error": "This role cannot be assigned here."}), 400

    try:
        target_user.role = new_role
        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to update role for user_id=%s", user_id)
        return jsonify({"success": False, "error": "Unable to change role."}), 500


@settings_bp.route("/billing", methods=["GET"])
@login_required
@role_required("mall_admin", "superadmin")
def billing():
    property_id = _resolved_property_id()
    if not property_id:
        flash("Property not configured.", "warning")
        return redirect(url_for("settings.hub"))

    property_record = MallProperty.query.get(property_id)
    subscription = Subscription.query.filter_by(property_id=property_id).first()
    payment_history = (
        PaymentRecord.query.filter_by(property_id=property_id)
        .order_by(PaymentRecord.created_at.desc())
        .all()
    )
    razorpay_key_id = os.getenv("RAZORPAY_KEY_ID", "")
    razorpay_enabled = current_app.config.get("RAZORPAY_ENABLED", False)

    return render_template(
        "settings/billing.html",
        property=property_record,
        subscription=subscription,
        payment_history=payment_history,
        razorpay_key_id=razorpay_key_id,
        razorpay_enabled=razorpay_enabled,
    )


@settings_bp.route("/billing/invoice/<int:payment_id>", methods=["GET"])
@login_required
@role_required("mall_admin", "superadmin")
def billing_invoice(payment_id):
    property_id = _resolved_property_id()
    payment = PaymentRecord.query.get_or_404(payment_id)

    if not current_user.is_superadmin() and payment.property_id != current_user.property_id:
        flash("Access denied.", "danger")
        return redirect(url_for("settings.billing"))

    if current_user.is_superadmin() and property_id and payment.property_id != property_id:
        flash("Invoice not found for selected property.", "danger")
        return redirect(url_for("settings.billing", property_id=property_id))

    property_record = MallProperty.query.get(payment.property_id)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 60
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(50, y, "RetailMind Payment Receipt")

    y -= 30
    pdf.setFont("Helvetica", 11)
    pdf.drawString(50, y, f"Date: {payment.created_at.strftime('%d %b %Y %I:%M %p') if payment.created_at else 'N/A'}")
    y -= 20
    pdf.drawString(50, y, f"Property: {property_record.name if property_record else 'N/A'}")
    y -= 20
    pdf.drawString(50, y, f"Plan: {(payment.plan_name or 'N/A').title()}")
    y -= 20
    pdf.drawString(50, y, f"Amount: \u20b9{int(payment.amount_inr or 0):,}")
    y -= 20
    pdf.drawString(50, y, f"Status: {(payment.status or 'N/A').title()}")
    y -= 20
    pdf.drawString(50, y, f"Razorpay Order ID: {payment.razorpay_order_id or 'N/A'}")
    y -= 20
    pdf.drawString(50, y, f"Razorpay Payment ID: {payment.razorpay_payment_id or 'N/A'}")
    y -= 35
    pdf.setFont("Helvetica-Oblique", 10)
    pdf.drawString(50, y, "This is a computer generated receipt.")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    file_name = f"retailmind_invoice_{payment.id}.pdf"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=file_name,
        mimetype="application/pdf",
    )


@settings_bp.route("/integrations", methods=["GET"])
@login_required
def integrations():
    property_id = _resolved_property_id()
    if not property_id:
        flash("Property not configured.", "warning")
        return redirect(url_for("settings.hub"))

    property_record = MallProperty.query.get(property_id)
    config, statuses, _connected_count = _integration_status_map(property_record)

    es_enabled = current_app.config.get("ES_ENABLED", False)
    es_cloud_id = current_app.config.get("ES_CLOUD_ID")
    gemini_enabled = current_app.config.get("GEMINI_ENABLED", False)

    return render_template(
        "settings/integrations.html",
        property=property_record,
        config=config,
        statuses=statuses,
        es_enabled=es_enabled,
        es_cloud_id=es_cloud_id,
        gemini_enabled=gemini_enabled,
    )


@settings_bp.route("/integrations/test/<integration_type>", methods=["POST"])
@login_required
def test_integration(integration_type):
    integration_type = (integration_type or "").strip().lower()
    property_id = _resolved_property_id()
    property_record = MallProperty.query.get(property_id) if property_id else None
    config = _load_property_config(property_record)

    if integration_type in {"pos", "inventory", "crm"}:
        return jsonify(
            {
                "success": True,
                "message": "Simulated connection successful. Real integration coming in Enterprise plan.",
            }
        ), 200

    if integration_type == "sensor":
        sensor_source = config.get("sensor_source", "simulator")
        if sensor_source == "simulator":
            return jsonify(
                {
                    "success": True,
                    "message": "Simulator active. Generating data every 5 minutes.",
                }
            ), 200

        if sensor_source == "iot_api":
            endpoint = (config.get("sensor_api_endpoint") or "").strip()
            if not endpoint:
                return jsonify({"success": False, "message": "IoT API endpoint is not configured."}), 400

            try:
                req = Request(endpoint, method="GET")
                with urlopen(req, timeout=5) as response:
                    if 200 <= response.status < 300:
                        return jsonify({"success": True, "message": "IoT endpoint is reachable."}), 200
                    return jsonify({"success": False, "message": f"IoT endpoint returned status {response.status}."}), 502
            except HTTPError as exc:
                return jsonify({"success": False, "message": f"IoT endpoint error: HTTP {exc.code}."}), 502
            except URLError as exc:
                return jsonify({"success": False, "message": f"IoT endpoint unreachable: {exc.reason}."}), 502
            except Exception as exc:
                return jsonify({"success": False, "message": f"Sensor test failed: {exc}"}), 500

        return jsonify({"success": False, "message": "Sensor source is not configured."}), 400

    if integration_type == "weather":
        if not current_app.config.get("GEMINI_ENABLED", False):
            return jsonify({"success": False, "message": "GEMINI_API_KEY not configured."}), 400

        city = property_record.city if property_record and property_record.city else "Mumbai"
        try:
            from google import genai

            client = genai.Client()
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"Provide current weather summary for {city}, India in one line.",
            )
            _text = (response.text or "").strip()
            return jsonify(
                {
                    "success": True,
                    "message": f"Weather API active. Current conditions retrieved for {city}.",
                }
            ), 200
        except Exception:
            current_app.logger.exception("Weather integration test failed")
            return jsonify({"success": False, "message": "Unable to fetch weather right now."}), 500

    if integration_type == "elasticsearch":
        if not current_app.config.get("ES_ENABLED", False):
            return jsonify(
                {
                    "success": False,
                    "message": "Elasticsearch not configured. Set ES_CLOUD_ID and ES_API_KEY in .env",
                }
            ), 400

        try:
            from elasticsearch import Elasticsearch

            es = Elasticsearch(
                cloud_id=current_app.config.get("ES_CLOUD_ID"),
                api_key=current_app.config.get("ES_API_KEY"),
            )
            ping_ok = bool(es.ping())
            if ping_ok:
                return jsonify({"success": True, "message": "Elasticsearch connection successful."}), 200
            return jsonify({"success": False, "message": "Elasticsearch ping failed."}), 502
        except Exception as exc:
            current_app.logger.exception("Elasticsearch integration test failed")
            return jsonify({"success": False, "message": f"Elasticsearch error: {exc}"}), 500

    return jsonify({"success": False, "message": "Unsupported integration type."}), 400


@settings_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    profile_form = ProfileEditForm(obj=current_user)
    password_form = ChangePasswordForm()

    if request.method == "POST":
        form_name = (request.form.get("form_name") or "").strip().lower()

        if form_name == "profile":
            profile_form = ProfileEditForm(request.form)
            password_form = ChangePasswordForm()
            if profile_form.validate_on_submit():
                try:
                    current_user.full_name = profile_form.full_name.data.strip()
                    current_user.phone = (profile_form.phone.data or "").strip() or None
                    db.session.commit()
                    flash("Profile updated successfully.", "success")
                    return redirect(url_for("settings.profile"))
                except Exception:
                    db.session.rollback()
                    current_app.logger.exception("Failed to update profile")
                    flash("Unable to update profile right now.", "danger")
            else:
                for field_errors in profile_form.errors.values():
                    for err in field_errors:
                        flash(err, "danger")

        elif form_name == "password":
            profile_form = ProfileEditForm(obj=current_user)
            password_form = ChangePasswordForm(request.form)
            if password_form.validate_on_submit():
                try:
                    current_user.set_password(password_form.new_password.data)
                    db.session.commit()
                    flash("Password changed successfully.", "success")
                    logout_user()
                    return redirect(url_for("auth.login"))
                except Exception:
                    db.session.rollback()
                    current_app.logger.exception("Failed to change password")
                    flash("Unable to change password right now.", "danger")
            else:
                for field_errors in password_form.errors.values():
                    for err in field_errors:
                        flash(err, "danger")

    property_id = _resolved_property_id()
    subscription = Subscription.query.filter_by(property_id=property_id).first() if property_id else None

    return render_template(
        "settings/profile.html",
        profile_form=profile_form,
        password_form=password_form,
        subscription=subscription,
    )
