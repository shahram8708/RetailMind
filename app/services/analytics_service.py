import io
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import current_app
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.extensions import db
from app.models.agent import AgentAction
from app.models.campaign import Campaign
from app.models.facility import Equipment, WorkOrder
from app.models.inventory import FootTraffic, InventoryItem, SalesVelocity
from app.models.tenant import Tenant


def _safe_float(value):
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _coerce_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _build_date_axis(start_dt, end_dt):
    if end_dt < start_dt:
        start_dt, end_dt = end_dt, start_dt

    start_day = start_dt.date()
    end_day = end_dt.date()

    dates = []
    cursor = start_day
    while cursor <= end_day:
        dates.append(cursor)
        cursor += timedelta(days=1)

    return dates


def _trend_pct(current_value, previous_value):
    current_value = _safe_float(current_value)
    previous_value = _safe_float(previous_value)
    if previous_value > 0:
        return ((current_value - previous_value) / previous_value) * 100
    return 0.0


def _compute_roi_components(property_id, start_dt, end_dt):
    approved_inventory_actions = AgentAction.query.filter(
        AgentAction.property_id == property_id,
        AgentAction.mission_type == "inventory",
        AgentAction.status.in_(["approved", "auto_executed"]),
        AgentAction.resolved_at >= start_dt,
        AgentAction.resolved_at <= end_dt,
    ).all()

    stockout_prevention_revenue = 0.0
    for action in approved_inventory_actions:
        item = InventoryItem.query.filter_by(
            sku_id=action.entity_id,
            property_id=property_id,
        ).first()

        if item is None:
            stockout_prevention_revenue += 5000.0
            continue

        threshold_level = max(_safe_int(item.reorder_threshold), 10)
        stockout_prevention_revenue += _safe_float(item.unit_price) * threshold_level * 0.15

    campaigns = Campaign.query.filter(
        Campaign.property_id == property_id,
        Campaign.status.in_(["active", "completed"]),
        Campaign.activated_at >= start_dt,
        Campaign.activated_at <= end_dt,
    ).all()

    campaign_revenue = sum(_safe_float(campaign.revenue_attributed) for campaign in campaigns)

    completed_work_orders = WorkOrder.query.filter(
        WorkOrder.property_id == property_id,
        WorkOrder.status == "completed",
        WorkOrder.completed_at >= start_dt,
        WorkOrder.completed_at <= end_dt,
        WorkOrder.agent_action_id.isnot(None),
    ).all()

    maintenance_cost_saved = 0.0
    for work_order in completed_work_orders:
        preventive_cost = (
            _safe_float(work_order.actual_cost_inr)
            or _safe_float(work_order.estimated_cost_inr)
            or 5000.0
        )
        reactive_cost_estimate = preventive_cost * 4
        maintenance_cost_saved += reactive_cost_estimate - preventive_cost

    return {
        "stockout_prevention_revenue": stockout_prevention_revenue,
        "stockout_actions_count": len(approved_inventory_actions),
        "campaign_revenue": campaign_revenue,
        "campaigns_count": len(campaigns),
        "maintenance_cost_saved": maintenance_cost_saved,
        "work_orders_completed": len(completed_work_orders),
        "total_roi": stockout_prevention_revenue + campaign_revenue + maintenance_cost_saved,
    }


def get_date_range(range_str, start_str=None, end_str=None):
    now = datetime.utcnow()
    range_str = (range_str or "30d").strip().lower()

    if range_str == "7d":
        return now - timedelta(days=7), now

    if range_str == "30d":
        return now - timedelta(days=30), now

    if range_str == "quarter":
        return now - timedelta(days=90), now

    if range_str == "custom":
        try:
            start_day = datetime.strptime(start_str, "%Y-%m-%d") if start_str else now - timedelta(days=30)
            end_day = datetime.strptime(end_str, "%Y-%m-%d") if end_str else now
            start_dt = datetime.combine(start_day.date(), datetime.min.time())
            end_dt = datetime.combine(end_day.date(), datetime.max.time().replace(microsecond=0))
            return start_dt, end_dt
        except ValueError:
            return now - timedelta(days=30), now

    return now - timedelta(days=30), now


def compute_agent_roi(property_id, start_dt, end_dt):
    current_data = _compute_roi_components(property_id, start_dt, end_dt)

    period_delta = end_dt - start_dt
    previous_end = start_dt
    previous_start = start_dt - period_delta

    previous_data = _compute_roi_components(property_id, previous_start, previous_end)

    return {
        "stockout_prevention_revenue": float(current_data["stockout_prevention_revenue"]),
        "stockout_actions_count": int(current_data["stockout_actions_count"]),
        "stockout_trend_pct": float(
            _trend_pct(current_data["stockout_prevention_revenue"], previous_data["stockout_prevention_revenue"])
        ),
        "campaign_revenue": float(current_data["campaign_revenue"]),
        "campaigns_count": int(current_data["campaigns_count"]),
        "campaign_trend_pct": float(
            _trend_pct(current_data["campaign_revenue"], previous_data["campaign_revenue"])
        ),
        "maintenance_cost_saved": float(current_data["maintenance_cost_saved"]),
        "work_orders_completed": int(current_data["work_orders_completed"]),
        "maintenance_trend_pct": float(
            _trend_pct(current_data["maintenance_cost_saved"], previous_data["maintenance_cost_saved"])
        ),
        "total_roi": float(current_data["total_roi"]),
        "total_roi_trend_pct": float(_trend_pct(current_data["total_roi"], previous_data["total_roi"])),
        "period_start": start_dt.isoformat(),
        "period_end": end_dt.isoformat(),
    }


def get_daily_foot_traffic(property_id, start_dt, end_dt):
    rows = (
        db.session.query(
            db.func.date(FootTraffic.timestamp).label("traffic_date"),
            FootTraffic.zone_id,
            db.func.coalesce(db.func.sum(FootTraffic.count), 0).label("zone_total"),
        )
        .filter(
            FootTraffic.property_id == property_id,
            FootTraffic.timestamp >= start_dt,
            FootTraffic.timestamp <= end_dt,
        )
        .group_by(db.func.date(FootTraffic.timestamp), FootTraffic.zone_id)
        .order_by(db.func.date(FootTraffic.timestamp).asc())
        .all()
    )

    date_axis = _build_date_axis(start_dt, end_dt)
    zones = ["A", "B", "C", "D", "E"]

    matrix = {day: {zone: 0 for zone in zones} for day in date_axis}
    for row in rows:
        day = _coerce_date(row.traffic_date)
        zone = (row.zone_id or "").strip().upper()
        if day in matrix and zone in matrix[day]:
            matrix[day][zone] = _safe_int(row.zone_total)

    return {
        "dates": [day.strftime("%b %d") for day in date_axis],
        "zones": {
            zone: [matrix[day][zone] for day in date_axis]
            for zone in zones
        },
    }


def get_inventory_risk_trend(property_id, start_dt, end_dt):
    rows = (
        db.session.query(
            db.func.date(AgentAction.created_at).label("action_date"),
            db.func.count(AgentAction.id).label("action_count"),
        )
        .filter(
            AgentAction.property_id == property_id,
            AgentAction.mission_type == "inventory",
            AgentAction.created_at >= start_dt,
            AgentAction.created_at <= end_dt,
        )
        .group_by(db.func.date(AgentAction.created_at))
        .order_by(db.func.date(AgentAction.created_at).asc())
        .all()
    )

    date_axis = _build_date_axis(start_dt, end_dt)
    counts = {day: 0 for day in date_axis}

    for row in rows:
        day = _coerce_date(row.action_date)
        if day in counts:
            counts[day] = _safe_int(row.action_count)

    return {
        "dates": [day.strftime("%b %d") for day in date_axis],
        "alerts_per_day": [counts[day] for day in date_axis],
    }


def get_campaign_performance_trend(property_id, start_dt, end_dt):
    rows = (
        db.session.query(
            Campaign.campaign_name,
            db.func.coalesce(db.func.sum(Campaign.impressions), 0).label("impressions_total"),
            db.func.coalesce(db.func.sum(Campaign.conversions), 0).label("conversions_total"),
        )
        .filter(
            Campaign.property_id == property_id,
            Campaign.activated_at >= start_dt,
            Campaign.activated_at <= end_dt,
        )
        .group_by(Campaign.campaign_name)
        .order_by(db.func.coalesce(db.func.sum(Campaign.impressions), 0).desc())
        .limit(5)
        .all()
    )

    return {
        "campaign_names": [row.campaign_name or "Untitled" for row in rows],
        "impressions": [_safe_int(row.impressions_total) for row in rows],
        "conversions": [_safe_int(row.conversions_total) for row in rows],
    }


def get_facility_anomaly_trend(property_id, start_dt, end_dt):
    rows = (
        db.session.query(
            db.func.date(AgentAction.created_at).label("action_date"),
            db.func.count(AgentAction.id).label("action_count"),
        )
        .filter(
            AgentAction.property_id == property_id,
            AgentAction.mission_type == "facility",
            AgentAction.created_at >= start_dt,
            AgentAction.created_at <= end_dt,
        )
        .group_by(db.func.date(AgentAction.created_at))
        .order_by(db.func.date(AgentAction.created_at).asc())
        .all()
    )

    date_axis = _build_date_axis(start_dt, end_dt)
    counts = {day: 0 for day in date_axis}

    for row in rows:
        day = _coerce_date(row.action_date)
        if day in counts:
            counts[day] = _safe_int(row.action_count)

    return {
        "dates": [day.strftime("%b %d") for day in date_axis],
        "anomaly_events": [counts[day] for day in date_axis],
    }


def get_agent_action_distribution(property_id, start_dt, end_dt):
    rows = (
        db.session.query(
            AgentAction.mission_type,
            db.func.count(AgentAction.id).label("mission_count"),
        )
        .filter(
            AgentAction.property_id == property_id,
            AgentAction.created_at >= start_dt,
            AgentAction.created_at <= end_dt,
        )
        .group_by(AgentAction.mission_type)
        .all()
    )

    count_map = defaultdict(int)
    for row in rows:
        count_map[(row.mission_type or "").strip().lower()] = _safe_int(row.mission_count)

    labels = ["Inventory", "Campaign", "Facility", "Shopper"]
    mission_keys = ["inventory", "campaign", "facility", "shopper"]

    return {
        "labels": labels,
        "counts": [count_map.get(key, 0) for key in mission_keys],
        "colors": ["#1A6FE8", "#0D9488", "#F97316", "#06B6D4"],
    }


def get_tenant_performance(property_id, start_dt, end_dt):
    tenants = Tenant.query.filter_by(property_id=property_id).all()
    if not tenants:
        return []

    items = InventoryItem.query.filter_by(property_id=property_id).all()
    sku_map = defaultdict(list)
    for item in items:
        sku_map[item.tenant_id].append(item)

    output = []
    for tenant in tenants:
        tenant_items = sku_map.get(tenant.id, [])
        sku_ids = [item.sku_id for item in tenant_items if item.sku_id]

        if sku_ids:
            inventory_alerts = AgentAction.query.filter(
                AgentAction.property_id == property_id,
                AgentAction.mission_type == "inventory",
                AgentAction.entity_id.in_(sku_ids),
                AgentAction.created_at >= start_dt,
                AgentAction.created_at <= end_dt,
            ).count()
        else:
            inventory_alerts = 0

        campaigns_activated = Campaign.query.filter(
            Campaign.property_id == property_id,
            Campaign.tenant_id == tenant.id,
            Campaign.activated_at >= start_dt,
            Campaign.activated_at <= end_dt,
        ).count()

        work_orders = (
            db.session.query(WorkOrder.id)
            .join(Equipment, WorkOrder.equipment_id == Equipment.id)
            .filter(
                WorkOrder.property_id == property_id,
                Equipment.property_id == property_id,
                Equipment.zone == tenant.zone,
                WorkOrder.created_at >= start_dt,
                WorkOrder.created_at <= end_dt,
            )
            .count()
        )

        avg_price = 0.0
        if tenant_items:
            avg_price = sum(_safe_float(item.unit_price) for item in tenant_items) / len(tenant_items)

        units_sold = (
            db.session.query(db.func.coalesce(db.func.sum(SalesVelocity.units_sold), 0))
            .filter(
                SalesVelocity.property_id == property_id,
                SalesVelocity.tenant_id == tenant.id,
                SalesVelocity.sale_timestamp >= start_dt,
                SalesVelocity.sale_timestamp <= end_dt,
            )
            .scalar()
            or 0
        )

        estimated_revenue = _safe_float(units_sold) * avg_price
        agent_actions_total = inventory_alerts + campaigns_activated

        output.append(
            {
                "tenant_name": tenant.name,
                "category": tenant.category,
                "zone": tenant.zone,
                "inventory_alerts": int(inventory_alerts),
                "campaigns_activated": int(campaigns_activated),
                "work_orders": int(work_orders),
                "estimated_revenue_inr": float(estimated_revenue),
                "agent_actions_total": int(agent_actions_total),
            }
        )

    output.sort(key=lambda row: row.get("estimated_revenue_inr", 0.0), reverse=True)
    return output


def generate_analytics_summary_text(roi_data, property_name, start_dt, end_dt):
    total_roi = _safe_float(roi_data.get("total_roi", 0) or 0)
    stockout_count = _safe_int(roi_data.get("stockout_actions_count", 0) or 0)
    stockout_revenue = _safe_float(roi_data.get("stockout_prevention_revenue", 0) or 0)
    campaign_revenue = _safe_float(roi_data.get("campaign_revenue", 0) or 0)
    campaigns_count = _safe_int(roi_data.get("campaigns_count", 0) or 0)
    maintenance_saved = _safe_float(roi_data.get("maintenance_cost_saved", 0) or 0)

    fallback = (
        f"From {start_dt.strftime('%B %d')} to {end_dt.strftime('%B %d, %Y')}, RetailMind generated an estimated "
        f"ROI of INR {total_roi:,.0f} for {property_name}. Inventory interventions prevented {stockout_count} stockout "
        f"events and protected around INR {stockout_revenue:,.0f}. Campaigns contributed INR {campaign_revenue:,.0f} "
        f"across {campaigns_count} activations, while predictive maintenance saved approximately INR {maintenance_saved:,.0f}."
    )

    if not current_app.config.get("GEMINI_ENABLED", False):
        return fallback

    prompt = (
        "You are a retail analytics AI. Write a concise 3-4 sentence business summary of these results for the mall "
        f"operations manager of {property_name}:\n\n"
        f"Period: {start_dt.strftime('%B %d')} to {end_dt.strftime('%B %d, %Y')}\n"
        f"Agent ROI: INR {total_roi:,.0f} total value generated\n"
        f"Stockouts prevented: {stockout_count} events, saving INR {stockout_revenue:,.0f}\n"
        f"Campaigns revenue: INR {campaign_revenue:,.0f} from {campaigns_count} campaigns\n"
        f"Maintenance savings: INR {maintenance_saved:,.0f}\n\n"
        "Write a professional summary highlighting the most significant achievement, any concerns, and one "
        "recommendation for improvement. Use Indian business context. Keep it under 100 words."
    )

    try:
        from google import genai

        client = genai.Client()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        result_text = response.text
        if result_text and result_text.strip():
            return result_text.strip()
    except Exception:
        current_app.logger.exception("Gemini analytics summary generation failed for property=%s", property_name)

    return fallback


def _format_inr(value):
    return f"INR {_safe_float(value):,.0f}"


def _format_trend_cell(value):
    value = _safe_float(value)
    sign = "+" if value >= 0 else ""
    arrow = "\u2191" if value >= 0 else "\u2193"
    return f"{sign}{value:.1f}%", arrow


def generate_pdf_report(property, roi_data, tenant_performance, period_label):
    summary_text = generate_analytics_summary_text(
        roi_data,
        property.name,
        datetime.fromisoformat(roi_data["period_start"]),
        datetime.fromisoformat(roi_data["period_end"]),
    )

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=36,
        leftMargin=28,
        rightMargin=28,
        bottomMargin=42,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        textColor=colors.HexColor("#0A1628"),
        fontSize=20,
        leading=24,
        spaceAfter=8,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubTitle",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#0A1628"),
        fontSize=13,
        leading=16,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["BodyText"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#111827"),
    )

    story = []
    story.append(Paragraph("RetailMind", ParagraphStyle("LogoText", parent=styles["Heading2"], textColor=colors.HexColor("#0A1628"), fontSize=16)))
    story.append(Paragraph("RetailMind Analytics Report", title_style))
    story.append(Paragraph(property.name or "Mall Property", subtitle_style))
    story.append(Paragraph(f"Generated: {datetime.utcnow().strftime('%d %b %Y %H:%M UTC')}", body_style))
    story.append(Paragraph(f"Report Period: {period_label}", body_style))
    story.append(Spacer(1, 14))

    stockout_trend_text, stockout_arrow = _format_trend_cell(roi_data.get("stockout_trend_pct", 0))
    campaign_trend_text, campaign_arrow = _format_trend_cell(roi_data.get("campaign_trend_pct", 0))
    maintenance_trend_text, maintenance_arrow = _format_trend_cell(roi_data.get("maintenance_trend_pct", 0))
    total_trend_text, total_arrow = _format_trend_cell(roi_data.get("total_roi_trend_pct", 0))

    roi_table_data = [
        ["Metric", "Value", "vs Previous Period", "Trend"],
        ["Stockout Prevention Revenue", _format_inr(roi_data.get("stockout_prevention_revenue", 0)), stockout_trend_text, stockout_arrow],
        ["Campaign Revenue", _format_inr(roi_data.get("campaign_revenue", 0)), campaign_trend_text, campaign_arrow],
        ["Maintenance Cost Saved", _format_inr(roi_data.get("maintenance_cost_saved", 0)), maintenance_trend_text, maintenance_arrow],
        ["Total Agent ROI", _format_inr(roi_data.get("total_roi", 0)), total_trend_text, total_arrow],
    ]

    roi_table = Table(roi_table_data, colWidths=[180, 110, 120, 70])
    roi_table_style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0A1628")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 1), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F4F6")]),
            ("FONTNAME", (0, 4), (1, 4), "Helvetica-Bold"),
        ]
    )
    roi_table.setStyle(roi_table_style)

    story.append(roi_table)
    story.append(Spacer(1, 14))

    story.append(Paragraph("Performance Summary", styles["Heading3"]))
    story.append(Paragraph(summary_text or "Summary unavailable.", body_style))
    story.append(Spacer(1, 14))

    tenant_rows = tenant_performance[:10]
    if len(tenant_rows) > 6:
        story.append(PageBreak())

    story.append(Paragraph("Tenant Performance", styles["Heading3"]))
    tenant_table_data = [
        ["Tenant", "Category", "Zone", "Est. Revenue INR", "Inventory Alerts", "Campaigns", "Agent Actions"]
    ]

    for row in tenant_rows:
        tenant_table_data.append(
            [
                str(row.get("tenant_name") or "-"),
                str(row.get("category") or "-"),
                str(row.get("zone") or "-"),
                f"{_safe_float(row.get('estimated_revenue_inr')):,.0f}",
                str(_safe_int(row.get("inventory_alerts"))),
                str(_safe_int(row.get("campaigns_activated"))),
                str(_safe_int(row.get("agent_actions_total"))),
            ]
        )

    tenant_table = Table(tenant_table_data, colWidths=[110, 85, 40, 85, 60, 55, 65])
    tenant_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0A1628")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
            ]
        )
    )
    story.append(tenant_table)

    report_date = datetime.utcnow().strftime("%d %b %Y")

    def _draw_footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#6B7280"))
        footer_text = f"Generated by RetailMind AI | {property.name} | {report_date}"
        canvas.drawCentredString(A4[0] / 2, 18, footer_text)
        canvas.drawRightString(A4[0] - 28, 18, f"Page {_doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return buffer.getvalue()
