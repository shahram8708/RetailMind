import re
import threading
from datetime import datetime, timedelta

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.forms.campaigns import CampaignEditForm
from app.models.agent import AgentAction
from app.models.campaign import Campaign
from app.models.tenant import Tenant
from app.services import campaign_service
from app.services.agent_runner import run_campaign_mission
from app.services.notification_service import create_notification


campaigns_bp = Blueprint("campaigns", __name__)


def _parse_cos_factors(prompt_text):
    factors = {
        "tf": 0.0,
        "tp": 0.0,
        "wm": 0.0,
        "em": 0.0,
        "lp": 0.5,
        "rc": 0.0,
    }

    if not prompt_text:
        return factors

    pattern = re.compile(r"(TF|TP|WM|EM|LP)=([0-9]*\.?[0-9]+)", re.IGNORECASE)
    for key, value in pattern.findall(prompt_text):
        factors[key.lower()] = float(value)

    return factors


@campaigns_bp.route("", methods=["GET"])
@campaigns_bp.route("/", methods=["GET"])
@login_required
def index():
    property_id = current_user.property_id
    if not property_id:
        return render_template(
            "campaigns/index.html",
            active_campaigns=[],
            opportunity_campaigns=[],
            campaign_history=Campaign.query.filter_by(id=-1).paginate(page=1, per_page=20, error_out=False),
            total_active=0,
            total_impressions_this_week=0,
            total_revenue_attributed=0.0,
            avg_conversion_rate=0.0,
            edit_form=CampaignEditForm(),
        )

    page = request.args.get("page", 1, type=int)

    active_campaigns = campaign_service.get_active_campaigns(property_id)
    opportunity_campaigns = campaign_service.get_campaign_opportunities(property_id, limit=10)
    campaign_history = campaign_service.get_campaign_history(property_id, page=page)

    total_active = Campaign.query.filter_by(property_id=property_id, status="active").count()

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())

    total_impressions_this_week = (
        db.session.query(db.func.coalesce(db.func.sum(Campaign.impressions), 0))
        .filter(
            Campaign.property_id == property_id,
            Campaign.activated_at >= week_start,
        )
        .scalar()
        or 0
    )

    total_revenue_attributed = (
        db.session.query(db.func.coalesce(db.func.sum(Campaign.revenue_attributed), 0.0))
        .filter(Campaign.property_id == property_id)
        .scalar()
        or 0.0
    )

    campaigns_with_impressions = Campaign.query.filter(
        Campaign.property_id == property_id,
        Campaign.impressions > 0,
    ).all()

    if campaigns_with_impressions:
        rates = [
            (float(campaign.conversions or 0) / float(campaign.impressions)) * 100
            for campaign in campaigns_with_impressions
            if campaign.impressions > 0
        ]
        avg_conversion_rate = sum(rates) / len(rates) if rates else 0.0
    else:
        avg_conversion_rate = 0.0

    edit_form = CampaignEditForm()

    return render_template(
        "campaigns/index.html",
        active_campaigns=active_campaigns,
        opportunity_campaigns=opportunity_campaigns,
        campaign_history=campaign_history,
        total_active=total_active,
        total_impressions_this_week=int(total_impressions_this_week),
        total_revenue_attributed=float(total_revenue_attributed),
        avg_conversion_rate=float(avg_conversion_rate),
        edit_form=edit_form,
    )


@campaigns_bp.route("/<int:campaign_id>", methods=["GET"])
@login_required
def detail(campaign_id):
    property_id = current_user.property_id
    if not property_id:
        return redirect(url_for("campaigns.index"))

    record = (
        db.session.query(Campaign, Tenant)
        .outerjoin(Tenant, Campaign.tenant_id == Tenant.id)
        .filter(
            Campaign.id == campaign_id,
            Campaign.property_id == property_id,
        )
        .first_or_404()
    )

    campaign_record, tenant = record

    click_rate = (
        (float(campaign_record.clicks or 0) / float(campaign_record.impressions or 0)) * 100
        if (campaign_record.impressions or 0) > 0
        else 0
    )
    conversion_rate = (
        (float(campaign_record.conversions or 0) / float(campaign_record.clicks or 0)) * 100
        if (campaign_record.clicks or 0) > 0
        else 0
    )
    cost_per_conversion = None

    cos_factors = _parse_cos_factors(campaign_record.gemini_prompt_used)
    hourly_perf_data = campaign_service.get_campaign_hourly_performance(campaign_id)

    form = CampaignEditForm()
    form.campaign_name.data = campaign_record.campaign_name
    form.campaign_copy.data = campaign_record.campaign_copy
    form.target_audience_description.data = campaign_record.target_audience_description
    form.channel.data = campaign_record.channel
    form.expires_at.data = campaign_record.expires_at

    return render_template(
        "campaigns/detail.html",
        campaign=campaign_record,
        tenant=tenant,
        click_rate=click_rate,
        conversion_rate=conversion_rate,
        cost_per_conversion=cost_per_conversion,
        cos_factors=cos_factors,
        hourly_perf_data=hourly_perf_data,
        form=form,
    )


@campaigns_bp.route("/activate/<int:campaign_id>", methods=["POST"])
@login_required
def activate(campaign_id):
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
            title="Campaign activated",
            message=f"Campaign '{campaign.campaign_name}' is now active.",
            notification_type="campaign_opportunity",
            severity="success",
            action_url=f"/campaigns/{campaign.id}",
            property_id=property_id,
            push_payload={
                "title": "Campaign Activated",
                "body": f"{campaign.campaign_name} is now live for Zone {campaign.target_zone or '-'}.",
                "icon": "/static/img/offline-placeholder.svg",
                "badge": "/static/img/offline-placeholder.svg",
                "tag": f"campaign-activated-{campaign.id}",
                "data": {"url": f"/campaigns/{campaign.id}"},
                "vibrate": [120, 80, 120],
                "requireInteraction": False,
            },
        )

        return jsonify(
            {
                "success": True,
                "campaign_id": campaign_id,
                "status": "active",
                "message": "Campaign activated.",
            }
        ), 200
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "error": "Unable to activate campaign"}), 500


@campaigns_bp.route("/pause/<int:campaign_id>", methods=["POST"])
@login_required
def pause(campaign_id):
    property_id = current_user.property_id
    if not property_id:
        return jsonify({"success": False, "error": "Property not configured"}), 400
    campaign = Campaign.query.filter_by(id=campaign_id, property_id=property_id).first()

    if campaign is None:
        return jsonify({"success": False, "error": "Campaign not found"}), 404

    try:
        next_status = "rejected" if campaign.status in ["opportunity", "pending_activation"] else "paused"
        campaign.status = next_status
        db.session.commit()

        create_notification(
            user_id=current_user.id,
            title="Campaign updated",
            message=f"Campaign '{campaign.campaign_name}' has been {next_status}.",
            notification_type="campaign_opportunity",
            severity="warning",
            action_url=f"/campaigns/{campaign.id}",
            property_id=property_id,
        )

        return jsonify(
            {
                "success": True,
                "campaign_id": campaign_id,
                "status": next_status,
                "message": "Campaign dismissed." if next_status == "rejected" else "Campaign paused.",
            }
        ), 200
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "error": "Unable to pause campaign"}), 500


@campaigns_bp.route("/generate", methods=["POST"])
@login_required
def generate():
    try:
        if not current_user.property_id:
            return jsonify({"success": False, "error": "Property not configured"}), 400

        app_obj = current_app._get_current_object()
        worker = threading.Thread(
            target=run_campaign_mission,
            args=(app_obj, current_user.property_id),
            daemon=True,
        )
        worker.start()
        return jsonify(
            {
                "success": True,
                "message": "Campaign analysis complete. Check opportunities above.",
            }
        ), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@campaigns_bp.route("/<int:campaign_id>/edit", methods=["POST"])
@login_required
def edit(campaign_id):
    property_id = current_user.property_id
    if not property_id:
        return jsonify({"success": False, "error": "Property not configured"}), 400
    campaign = Campaign.query.filter_by(id=campaign_id, property_id=property_id).first()

    if campaign is None:
        return jsonify({"success": False, "error": "Campaign not found"}), 404

    form = CampaignEditForm()
    if not form.validate_on_submit():
        if request.headers.get("X-Requested-With") != "XMLHttpRequest":
            flash("Invalid campaign data. Please check the form values.", "danger")
            return redirect(url_for("campaigns.detail", campaign_id=campaign_id))
        return jsonify({"success": False, "error": "Invalid campaign data", "errors": form.errors}), 400

    try:
        campaign.campaign_name = form.campaign_name.data
        campaign.campaign_copy = form.campaign_copy.data
        campaign.target_audience_description = form.target_audience_description.data
        campaign.channel = form.channel.data
        campaign.expires_at = form.expires_at.data
        db.session.commit()

        if request.headers.get("X-Requested-With") != "XMLHttpRequest":
            flash("Campaign updated successfully.", "success")
            return redirect(url_for("campaigns.detail", campaign_id=campaign_id))

        return jsonify(
            {
                "success": True,
                "campaign_id": campaign.id,
                "campaign_name": campaign.campaign_name,
                "campaign_copy": campaign.campaign_copy,
                "channel": campaign.channel,
            }
        ), 200
    except Exception:
        db.session.rollback()
        if request.headers.get("X-Requested-With") != "XMLHttpRequest":
            flash("Unable to save campaign changes.", "danger")
            return redirect(url_for("campaigns.detail", campaign_id=campaign_id))
        return jsonify({"success": False, "error": "Unable to save campaign changes"}), 500
