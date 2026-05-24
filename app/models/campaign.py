from datetime import datetime

from app.extensions import db


class Campaign(db.Model):
    __tablename__ = "campaigns"

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("mall_properties.id"), nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=True)
    campaign_name = db.Column(db.String(200), nullable=False)
    campaign_copy = db.Column(db.Text, nullable=True)
    target_zone = db.Column(db.String(50), nullable=True)
    target_audience_description = db.Column(db.Text, nullable=True)
    opportunity_score = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(50), default="opportunity")
    channel = db.Column(db.String(50), default="in_app")
    weather_context = db.Column(db.String(100), nullable=True)
    event_context = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    activated_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    impressions = db.Column(db.Integer, default=0)
    clicks = db.Column(db.Integer, default=0)
    conversions = db.Column(db.Integer, default=0)
    revenue_attributed = db.Column(db.Float, default=0.0)
    created_by_agent = db.Column(db.Boolean, default=True)
    gemini_prompt_used = db.Column(db.Text, nullable=True)

    property = db.relationship("MallProperty", backref="campaigns")
    tenant = db.relationship("Tenant", backref="campaigns")
