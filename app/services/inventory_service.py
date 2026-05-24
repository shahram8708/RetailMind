from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import current_app

from app.extensions import db
from app.models.agent import AgentAction
from app.models.inventory import FootTraffic, InventoryItem, SalesVelocity
from app.models.tenant import Tenant


def _clamp(value, low=0.0, high=1.0):
    return min(high, max(low, value))


def _hour_label(hour_dt):
    return hour_dt.strftime("%a %I%p").replace(" 0", " ")


def _parse_sql_date(value):
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


def compute_srs_for_sku(sku_id, property_id, tenant_id):
    try:
        now = datetime.utcnow()
        inventory_item = InventoryItem.query.filter_by(
            sku_id=sku_id,
            property_id=property_id,
        ).first()

        if inventory_item is None:
            return {"sku_id": sku_id, "srs_score": 0.0, "error": "SKU not found"}

        S = int(inventory_item.stock_level or 0)
        T = int(inventory_item.reorder_threshold or 0)

        two_hours_ago = now - timedelta(hours=2)
        V = (
            db.session.query(db.func.coalesce(db.func.sum(SalesVelocity.units_sold), 0))
            .filter(
                SalesVelocity.sku_id == sku_id,
                SalesVelocity.property_id == property_id,
                SalesVelocity.sale_timestamp >= two_hours_ago,
            )
            .scalar()
            or 0
        )
        V = int(V)

        tenant = Tenant.query.filter_by(id=tenant_id, property_id=property_id).first()
        zone_id = tenant.zone if tenant and tenant.zone else None

        F_current = 1.0
        traffic_counts = []

        if zone_id:
            latest_traffic_record = (
                FootTraffic.query.filter_by(property_id=property_id, zone_id=zone_id)
                .order_by(FootTraffic.timestamp.desc())
                .first()
            )
            if latest_traffic_record is not None:
                F_current = float(latest_traffic_record.count or 1.0)

            recent_traffic_records = (
                FootTraffic.query.filter_by(property_id=property_id, zone_id=zone_id)
                .order_by(FootTraffic.timestamp.desc())
                .limit(50)
                .all()
            )
            traffic_counts = [float(row.count or 0.0) for row in recent_traffic_records]

        if len(traffic_counts) < 5:
            F = 1.0
        else:
            F_average = sum(traffic_counts) / len(traffic_counts)
            if F_average > 0:
                F = F_current / F_average
            else:
                F = 1.0
            F = _clamp(F, 0.1, 3.0)

        thirty_days_ago = now - timedelta(days=30)
        has_sales_history = (
            SalesVelocity.query.filter(
                SalesVelocity.sku_id == sku_id,
                SalesVelocity.property_id == property_id,
            )
            .limit(1)
            .first()
            is not None
        )

        if not has_sales_history:
            H = 0.1
        else:
            zero_sales_days = (
                db.session.query(db.func.date(SalesVelocity.sale_timestamp))
                .filter(
                    SalesVelocity.sku_id == sku_id,
                    SalesVelocity.property_id == property_id,
                    SalesVelocity.sale_timestamp >= thirty_days_ago,
                    SalesVelocity.units_sold == 0,
                )
                .distinct()
                .count()
            )
            H = zero_sales_days / 30.0

        H = _clamp(H)

        L = int(inventory_item.supplier_lead_time_hours or 24)
        DR = float(V) * float(F)

        if DR > 0:
            TTS = float(S) / DR
        else:
            TTS = float("inf")

        if TTS < L:
            LTR = 1.0
        elif TTS == float("inf"):
            LTR = 0.0
        else:
            LTR = max(0.0, 1.0 - (TTS - L) / max(L, 1))

        LTR = _clamp(LTR)

        TPF = max(0.0, min(1.0, 1.0 - (S - T) / max(T, 1)))
        HW = _clamp(H)

        SRS = 0.40 * LTR + 0.35 * TPF + 0.25 * HW
        SRS = _clamp(SRS)

        inventory_item.srs_score = round(SRS, 4)
        inventory_item.srs_last_computed = now
        db.session.commit()

        return {
            "sku_id": sku_id,
            "srs_score": float(SRS),
            "ltr": float(LTR),
            "tpf": float(TPF),
            "hw": float(HW),
            "dr": float(DR),
            "tts_hours": TTS if TTS != float("inf") else None,
            "stock_level": S,
            "reorder_threshold": T,
            "sales_velocity_2h": V,
            "foot_traffic_multiplier": float(F),
            "supplier_lead_time_hours": L,
        }
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to compute SRS for sku_id=%s property_id=%s", sku_id, property_id)
        return {"sku_id": sku_id, "srs_score": 0.0, "error": str(e)}


def get_srs_label(srs_score):
    score = float(srs_score or 0.0)
    if score >= 0.85:
        return "Critical", "srs-critical"
    if score >= 0.70:
        return "High Risk", "srs-high"
    if score >= 0.50:
        return "Medium Risk", "srs-medium"
    return "Low Risk", "srs-low"


def get_top_at_risk_skus(property_id, limit=20):
    return (
        db.session.query(InventoryItem, Tenant)
        .join(Tenant, InventoryItem.tenant_id == Tenant.id)
        .filter(InventoryItem.property_id == property_id)
        .order_by(InventoryItem.srs_score.desc())
        .limit(limit)
        .all()
    )


def get_sales_velocity_chart_data(sku_id, property_id, hours=48):
    hours = max(1, int(hours or 48))
    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    start_time = now - timedelta(hours=hours - 1)

    sales_rows = (
        SalesVelocity.query.filter(
            SalesVelocity.sku_id == sku_id,
            SalesVelocity.property_id == property_id,
            SalesVelocity.sale_timestamp >= start_time,
            SalesVelocity.sale_timestamp <= now + timedelta(hours=1),
        )
        .order_by(SalesVelocity.sale_timestamp.asc())
        .all()
    )

    grouped = defaultdict(int)
    for row in sales_rows:
        hour_bucket = row.sale_timestamp.replace(minute=0, second=0, microsecond=0)
        grouped[hour_bucket] += int(row.units_sold or 0)

    timestamps = []
    units_sold = []
    for idx in range(hours):
        bucket = start_time + timedelta(hours=idx)
        timestamps.append(_hour_label(bucket))
        units_sold.append(int(grouped.get(bucket, 0)))

    return {"timestamps": timestamps, "units_sold": units_sold}


def get_stock_history_chart_data(sku_id, property_id, days=30):
    days = max(1, int(days or 30))
    inventory_item = InventoryItem.query.filter_by(
        sku_id=sku_id,
        property_id=property_id,
    ).first()

    if inventory_item is None:
        return {"dates": [], "stock_levels": [], "reorder_threshold": 0}

    current_stock = int(inventory_item.stock_level or 0)
    today = datetime.utcnow().date()
    start_date = today - timedelta(days=days - 1)

    sales_by_day_rows = (
        db.session.query(
            db.func.date(SalesVelocity.sale_timestamp).label("sale_day"),
            db.func.coalesce(db.func.sum(SalesVelocity.units_sold), 0).label("units"),
        )
        .filter(
            SalesVelocity.sku_id == sku_id,
            SalesVelocity.property_id == property_id,
            SalesVelocity.sale_timestamp >= datetime.combine(start_date, datetime.min.time()),
        )
        .group_by(db.func.date(SalesVelocity.sale_timestamp))
        .all()
    )

    daily_sales = {}
    for row in sales_by_day_rows:
        row_day = _parse_sql_date(row.sale_day)
        if row_day is not None:
            daily_sales[row_day] = int(row.units or 0)

    reverse_dates = []
    reverse_levels = []
    cumulative_sales = 0

    for offset in range(days):
        day = today - timedelta(days=offset)
        cumulative_sales += int(daily_sales.get(day, 0))
        estimated_stock = max(0, int(current_stock + cumulative_sales))
        reverse_dates.append(day)
        reverse_levels.append(estimated_stock)

    reverse_dates.reverse()
    reverse_levels.reverse()

    return {
        "dates": [day.strftime("%b %d").replace(" 0", " ") for day in reverse_dates],
        "stock_levels": reverse_levels,
        "reorder_threshold": int(inventory_item.reorder_threshold or 0),
    }


def get_stockout_history(sku_id, property_id):
    inventory_item = InventoryItem.query.filter_by(
        sku_id=sku_id,
        property_id=property_id,
    ).first()

    revenue_risk = 0.0
    if inventory_item is not None:
        revenue_risk = float(inventory_item.unit_price or 0.0) * (float(inventory_item.reorder_threshold or 0) / 2.0)

    rows = (
        AgentAction.query.filter(
            AgentAction.entity_id == sku_id,
            AgentAction.mission_type == "inventory",
            AgentAction.property_id == property_id,
        )
        .order_by(AgentAction.created_at.desc())
        .limit(10)
        .all()
    )

    history = []
    for row in rows:
        history.append(
            {
                "date": row.created_at,
                "description": row.description,
                "srs_score": float(row.score or 0.0),
                "status": row.status,
                "resolved_at": row.resolved_at,
                "estimated_revenue_loss": round(revenue_risk, 2),
            }
        )

    return history
