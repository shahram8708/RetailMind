from datetime import datetime

from app.extensions import db


class Tenant(db.Model):
    __tablename__ = "tenants"

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("mall_properties.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100), nullable=True)
    zone = db.Column(db.String(50), nullable=True)
    floor = db.Column(db.Integer, default=1)
    unit_number = db.Column(db.String(20), nullable=True)
    manager_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    pos_system_type = db.Column(db.String(50), nullable=True)
    inventory_system_type = db.Column(db.String(50), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    contact_phone = db.Column(db.String(20), nullable=True)
    contact_email = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    manager = db.relationship("User", foreign_keys=[manager_user_id])
    inventory_items = db.relationship("InventoryItem", backref="tenant", lazy="dynamic")
