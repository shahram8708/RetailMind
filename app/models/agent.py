from datetime import datetime

from app.extensions import db


class AgentConfiguration(db.Model):
    __tablename__ = "agent_configurations"

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("mall_properties.id"), unique=True, nullable=False)
    inventory_srs_threshold = db.Column(db.Float, default=0.70)
    campaign_cos_threshold = db.Column(db.Float, default=0.75)
    facility_fps_threshold = db.Column(db.Float, default=0.65)
    auto_approve_restock = db.Column(db.Boolean, default=False)
    auto_approve_campaigns = db.Column(db.Boolean, default=False)
    auto_approve_maintenance = db.Column(db.Boolean, default=False)
    notification_email = db.Column(db.String(255), nullable=True)
    inventory_check_interval_minutes = db.Column(db.Integer, default=15)
    campaign_check_interval_minutes = db.Column(db.Integer, default=30)
    facility_check_interval_minutes = db.Column(db.Integer, default=10)
    inventory_mission_enabled = db.Column(db.Boolean, default=True)
    campaign_mission_enabled = db.Column(db.Boolean, default=True)
    facility_mission_enabled = db.Column(db.Boolean, default=True)
    shopper_mission_enabled = db.Column(db.Boolean, default=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    property = db.relationship("MallProperty", backref=db.backref("agent_config", uselist=False))


class AgentAction(db.Model):
    __tablename__ = "agent_actions"

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("mall_properties.id"), nullable=False)
    mission_type = db.Column(db.String(50), nullable=False)
    action_type = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    entity_id = db.Column(db.String(100), nullable=True)
    score = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(50), default="pending")
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    agent_reasoning = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

    property = db.relationship("MallProperty", backref="agent_actions")
    approved_by = db.relationship("User", foreign_keys=[approved_by_user_id])
