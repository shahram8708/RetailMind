from datetime import date

from flask import Blueprint, Response, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.models.property import MallProperty
from app.services import analytics_service


analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("", methods=["GET"])
@analytics_bp.route("/", methods=["GET"])
@login_required
def index():
    property_id = current_user.property_id
    if not property_id:
        return redirect(url_for("dashboard.index"))

    range_str = request.args.get("range", "30d")
    start_str = request.args.get("start")
    end_str = request.args.get("end")

    start_dt, end_dt = analytics_service.get_date_range(range_str, start_str, end_str)

    property_record = MallProperty.query.filter_by(id=property_id).first_or_404()

    roi_data = analytics_service.compute_agent_roi(property_id, start_dt, end_dt)
    foot_traffic_data = analytics_service.get_daily_foot_traffic(property_id, start_dt, end_dt)
    inventory_trend = analytics_service.get_inventory_risk_trend(property_id, start_dt, end_dt)
    campaign_trend = analytics_service.get_campaign_performance_trend(property_id, start_dt, end_dt)
    facility_trend = analytics_service.get_facility_anomaly_trend(property_id, start_dt, end_dt)
    action_distribution = analytics_service.get_agent_action_distribution(property_id, start_dt, end_dt)
    tenant_performance = analytics_service.get_tenant_performance(property_id, start_dt, end_dt)
    summary_text = analytics_service.generate_analytics_summary_text(
        roi_data,
        property_record.name,
        start_dt,
        end_dt,
    )

    chart_data = {
        "foot_traffic": foot_traffic_data,
        "inventory_trend": inventory_trend,
        "campaign_trend": campaign_trend,
        "facility_trend": facility_trend,
        "action_distribution": action_distribution,
    }

    return render_template(
        "analytics/index.html",
        property=property_record,
        range_str=range_str,
        start_dt=start_dt,
        end_dt=end_dt,
        roi_data=roi_data,
        chart_data=chart_data,
        tenant_performance=tenant_performance,
        summary_text=summary_text,
    )


@analytics_bp.route("/export", methods=["GET"])
@login_required
def export_pdf():
    property_id = current_user.property_id
    if not property_id:
        return redirect(url_for("dashboard.index"))

    range_str = request.args.get("range", "30d")
    start_str = request.args.get("start")
    end_str = request.args.get("end")

    start_dt, end_dt = analytics_service.get_date_range(range_str, start_str, end_str)
    property_record = MallProperty.query.filter_by(id=property_id).first_or_404()

    roi_data = analytics_service.compute_agent_roi(property_id, start_dt, end_dt)
    tenant_performance = analytics_service.get_tenant_performance(property_id, start_dt, end_dt)

    period_label = f"{start_dt.strftime('%B %d')} to {end_dt.strftime('%B %d, %Y')}"
    pdf_bytes = analytics_service.generate_pdf_report(
        property_record,
        roi_data,
        tenant_performance,
        period_label,
    )

    filename = f"RetailMind_Report_{date.today().strftime('%Y%m%d')}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
