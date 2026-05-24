from collections import Counter
from datetime import date, datetime, timedelta
import statistics

from flask import current_app

from app.extensions import db
from app.models.facility import Equipment, SensorReading, WorkOrder
from app.models.user import User


def _clamp(value, low=0.0, high=1.0):
    return min(high, max(low, value))


def _primary_metric_for_equipment(equipment_type, readings):
    mapping = {
        "escalator": "vibration_hz",
        "elevator": "vibration_hz",
        "hvac": "temperature_celsius",
        "generator": "current_amps",
        "fire_alarm": "current_amps",
        "restroom_sensor": "occupancy_count",
        "parking_sensor": "occupancy_count",
        "food_court_exhaust": "temperature_celsius",
    }

    metric = mapping.get((equipment_type or "").strip().lower())
    if metric:
        return metric

    if not readings:
        return "vibration_hz"

    counts = Counter((reading.metric_name or "").strip() for reading in readings if reading.metric_name)
    if not counts:
        return "vibration_hz"

    return counts.most_common(1)[0][0]


def _trend_normalizer(equipment_type, slope):
    equipment_type = (equipment_type or "").strip().lower()
    if equipment_type in {"escalator", "elevator"}:
        return 5.0
    if equipment_type in {"hvac", "food_court_exhaust"}:
        return 3.0
    if equipment_type in {"generator", "fire_alarm"}:
        return 10.0
    if equipment_type in {"restroom_sensor", "parking_sensor", "restroom", "parking"}:
        return 50.0
    return max(abs(slope), 1.0)


def compute_fps_for_equipment(equipment_id, property_id):
    try:
        equipment = Equipment.query.filter_by(id=equipment_id, property_id=property_id).first()
        if equipment is None:
            return {
                "equipment_id": equipment_id,
                "fps_score": 0.0,
                "error": "Equipment not found",
            }

        readings = (
            SensorReading.query.filter_by(equipment_id=equipment_id)
            .order_by(SensorReading.timestamp.desc())
            .limit(500)
            .all()
        )

        if len(readings) < 50:
            return {
                "equipment_id": equipment_id,
                "fps_score": 0.0,
                "insufficient_data": True,
            }

        primary_metric = _primary_metric_for_equipment(equipment.equipment_type, readings)
        metric_readings = [reading for reading in readings if reading.metric_name == primary_metric]
        if len(metric_readings) < 20:
            metric_readings = readings

        values = [float(reading.metric_value or 0.0) for reading in metric_readings]
        if not values:
            return {
                "equipment_id": equipment_id,
                "fps_score": 0.0,
                "insufficient_data": True,
            }

        mu = statistics.mean(values)
        sigma = statistics.stdev(values) if len(values) >= 2 else 0.0
        if sigma == 0:
            sigma = 0.001

        cutoff_24h = datetime.utcnow() - timedelta(hours=24)

        anomaly_count = 0
        total_24h_count = 0
        readings_to_update = []

        for reading in metric_readings:
            if reading.timestamp and reading.timestamp >= cutoff_24h:
                total_24h_count += 1
                z_score = (float(reading.metric_value or 0.0) - mu) / sigma
                reading.z_score = round(z_score, 4)

                if abs(z_score) > 2.5:
                    reading.anomaly_flag = True
                    reading.anomaly_score = round(abs(z_score), 4)
                    anomaly_count += 1
                else:
                    reading.anomaly_flag = False
                    reading.anomaly_score = None

                readings_to_update.append(reading)

        if readings_to_update:
            db.session.commit()

        anomaly_rate = anomaly_count / total_24h_count if total_24h_count > 0 else 0.0
        anomaly_rate = _clamp(anomaly_rate)

        recent_50 = values[:50]
        n = len(recent_50)

        if n < 10:
            normalized_slope = 0.0
        else:
            x_values = list(range(n))
            y_values = recent_50

            sum_x = sum(x_values)
            sum_y = sum(y_values)
            sum_xy = sum(x_val * y_val for x_val, y_val in zip(x_values, y_values))
            sum_x2 = sum(x_val ** 2 for x_val in x_values)

            numerator = n * sum_xy - sum_x * sum_y
            denominator = n * sum_x2 - (sum_x ** 2)

            slope = numerator / denominator if denominator != 0 else 0.0
            normalizer = _trend_normalizer(equipment.equipment_type, slope)
            normalized_slope = _clamp(abs(slope) / normalizer)

        if equipment.installation_date:
            age_days = (date.today() - equipment.installation_date).days
            age_years = age_days / 365.25
            expected_lifetime = float(equipment.expected_lifetime_years or 1)
            if expected_lifetime <= 0:
                expected_lifetime = 1.0
            age_factor = min(1.0, age_years / expected_lifetime)
        else:
            age_factor = 0.3

        age_factor = _clamp(age_factor)

        fps = 0.40 * anomaly_rate + 0.35 * normalized_slope + 0.25 * age_factor
        fps = round(_clamp(fps), 4)

        equipment.fps_score = fps
        equipment.fps_last_computed = datetime.utcnow()
        db.session.commit()

        return {
            "equipment_id": equipment_id,
            "fps_score": fps,
            "anomaly_rate": anomaly_rate,
            "normalized_slope": normalized_slope,
            "age_factor": age_factor,
            "mu": round(mu, 4),
            "sigma": round(sigma, 4),
            "total_readings_analyzed": len(values),
            "readings_last_24h": total_24h_count,
            "anomalies_last_24h": anomaly_count,
            "primary_metric": primary_metric,
        }
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception(
            "Failed FPS computation for equipment_id=%s property_id=%s",
            equipment_id,
            property_id,
        )
        return {
            "equipment_id": equipment_id,
            "fps_score": 0.0,
            "error": str(exc),
        }


def get_fps_label(fps_score):
    score = float(fps_score or 0.0)
    if score < 0.40:
        return {"label": "Healthy", "class": "fps-healthy", "color": "green"}
    if score < 0.65:
        return {"label": "Monitor", "class": "fps-monitor", "color": "orange"}
    if score < 0.85:
        return {"label": "At Risk", "class": "fps-risk", "color": "orange"}
    return {"label": "Critical", "class": "fps-critical", "color": "red"}


def get_sensor_telemetry_chart_data(equipment_id, metric_name, limit=500):
    limit = max(10, int(limit or 500))

    readings_desc = (
        SensorReading.query.filter_by(equipment_id=equipment_id, metric_name=metric_name)
        .order_by(SensorReading.timestamp.desc())
        .limit(limit)
        .all()
    )
    readings = list(reversed(readings_desc))

    if not readings:
        return {
            "timestamps": [],
            "values": [],
            "mean_line": [],
            "upper_threshold": [],
            "lower_threshold": [],
            "anomaly_indices": [],
            "anomaly_values": [],
            "metric_name": metric_name,
            "mu": 0.0,
            "sigma": 0.0,
        }

    values = [float(reading.metric_value or 0.0) for reading in readings]
    mu = statistics.mean(values)
    sigma = statistics.stdev(values) if len(values) >= 2 else 0.0
    if sigma == 0:
        sigma = 0.001

    upper = mu + 2.5 * sigma
    lower = mu - 2.5 * sigma

    anomaly_indices = []
    anomaly_values = []
    for idx, reading in enumerate(readings):
        if bool(reading.anomaly_flag):
            anomaly_indices.append(idx)
            anomaly_values.append(float(reading.metric_value or 0.0))

    return {
        "timestamps": [reading.timestamp.strftime("%b %d %H:%M") for reading in readings],
        "values": values,
        "mean_line": [mu for _ in values],
        "upper_threshold": [upper for _ in values],
        "lower_threshold": [lower for _ in values],
        "anomaly_indices": anomaly_indices,
        "anomaly_values": anomaly_values,
        "metric_name": metric_name,
        "mu": mu,
        "sigma": sigma,
    }


def get_available_metrics(equipment_id):
    rows = (
        db.session.query(SensorReading.metric_name)
        .filter(SensorReading.equipment_id == equipment_id)
        .distinct()
        .order_by(SensorReading.metric_name.asc())
        .all()
    )
    return [row[0] for row in rows if row and row[0]]


def get_maintenance_history(equipment_id, property_id):
    return (
        db.session.query(WorkOrder, User)
        .outerjoin(User, WorkOrder.assigned_to_user_id == User.id)
        .filter(
            WorkOrder.equipment_id == equipment_id,
            WorkOrder.property_id == property_id,
        )
        .order_by(WorkOrder.created_at.desc())
        .all()
    )


def get_equipment_for_property(property_id, floor_filter=None):
    query = Equipment.query.filter_by(property_id=property_id)
    if floor_filter is not None:
        query = query.filter(Equipment.floor == floor_filter)
    return query.order_by(Equipment.fps_score.desc(), Equipment.equipment_name.asc()).all()


def get_active_anomalies(property_id):
    cutoff = datetime.utcnow() - timedelta(hours=24)
    return (
        db.session.query(SensorReading, Equipment)
        .join(Equipment, SensorReading.equipment_id == Equipment.id)
        .filter(
            Equipment.property_id == property_id,
            SensorReading.property_id == property_id,
            SensorReading.anomaly_flag.is_(True),
            SensorReading.timestamp >= cutoff,
        )
        .order_by(db.func.abs(SensorReading.z_score).desc(), SensorReading.timestamp.desc())
        .all()
    )


def get_open_work_orders(property_id):
    priority_order = db.case(
        {
            "critical": 1,
            "high": 2,
            "medium": 3,
            "low": 4,
        },
        value=WorkOrder.priority,
        else_=5,
    )

    return (
        db.session.query(WorkOrder, Equipment, User)
        .join(Equipment, WorkOrder.equipment_id == Equipment.id)
        .outerjoin(User, WorkOrder.assigned_to_user_id == User.id)
        .filter(
            WorkOrder.property_id == property_id,
            WorkOrder.status.in_(["open", "in_progress"]),
        )
        .order_by(priority_order.asc(), WorkOrder.created_at.desc())
        .all()
    )
