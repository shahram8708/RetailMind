from datetime import datetime

from app.extensions import db


class Equipment(db.Model):
    __tablename__ = "equipment"

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("mall_properties.id"), nullable=False)
    equipment_name = db.Column(db.String(200), nullable=False)
    equipment_type = db.Column(db.String(50), nullable=False)
    zone = db.Column(db.String(50), nullable=True)
    floor = db.Column(db.Integer, default=1)
    installation_date = db.Column(db.Date, nullable=True)
    expected_lifetime_years = db.Column(db.Integer, default=10)
    last_serviced = db.Column(db.DateTime, nullable=True)
    manufacturer = db.Column(db.String(100), nullable=True)
    model_number = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    fps_score = db.Column(db.Float, default=0.0)
    fps_last_computed = db.Column(db.DateTime, nullable=True)

    sensor_readings = db.relationship("SensorReading", backref="equipment", lazy="dynamic")


class SensorReading(db.Model):
    __tablename__ = "sensor_readings"

    id = db.Column(db.Integer, primary_key=True)
    equipment_id = db.Column(db.Integer, db.ForeignKey("equipment.id"), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey("mall_properties.id"), nullable=False)
    metric_name = db.Column(db.String(50), nullable=False)
    metric_value = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    anomaly_flag = db.Column(db.Boolean, default=False)
    anomaly_score = db.Column(db.Float, nullable=True)
    z_score = db.Column(db.Float, nullable=True)


class WorkOrder(db.Model):
    __tablename__ = "work_orders"

    id = db.Column(db.Integer, primary_key=True)
    equipment_id = db.Column(db.Integer, db.ForeignKey("equipment.id"), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey("mall_properties.id"), nullable=False)
    agent_action_id = db.Column(db.Integer, db.ForeignKey("agent_actions.id"), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    priority = db.Column(db.String(20), default="medium")
    assigned_to_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    status = db.Column(db.String(50), default="open")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    estimated_cost_inr = db.Column(db.Float, nullable=True)
    actual_cost_inr = db.Column(db.Float, nullable=True)

    equipment = db.relationship("Equipment", backref="work_orders")
    assigned_to = db.relationship("User", foreign_keys=[assigned_to_user_id])
    agent_action = db.relationship("AgentAction", backref="work_orders")
