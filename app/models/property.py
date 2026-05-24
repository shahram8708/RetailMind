from datetime import datetime

from app.extensions import db


class MallProperty(db.Model):
    __tablename__ = "mall_properties"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    location = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(100), nullable=True)
    country = db.Column(db.String(100), default="India")
    total_area_sqft = db.Column(db.Integer, nullable=True)
    num_floors = db.Column(db.Integer, default=1)
    num_tenants = db.Column(db.Integer, default=0)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    elasticsearch_index_prefix = db.Column(db.String(100), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    subscription_tier = db.Column(db.String(50), default="starter")
    onboarding_complete = db.Column(db.Boolean, default=False)
    logo_url = db.Column(db.String(255), nullable=True)
    data_source_config = db.Column(db.Text, nullable=True)

    owner = db.relationship("User", foreign_keys=[owner_user_id], post_update=True)
    tenants = db.relationship("Tenant", backref="property", lazy="dynamic")
