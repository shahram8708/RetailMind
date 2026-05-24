from datetime import datetime

from app.extensions import db


class InventoryItem(db.Model):
    __tablename__ = "inventory_items"

    id = db.Column(db.Integer, primary_key=True)
    sku_id = db.Column(db.String(50), nullable=False, index=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey("mall_properties.id"), nullable=False)
    product_name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100), nullable=True)
    brand = db.Column(db.String(100), nullable=True)
    color = db.Column(db.String(50), nullable=True)
    size = db.Column(db.String(20), nullable=True)
    stock_level = db.Column(db.Integer, default=0)
    reorder_threshold = db.Column(db.Integer, default=10)
    unit_price = db.Column(db.Float, default=0.0)
    cost_price = db.Column(db.Float, default=0.0)
    last_restocked = db.Column(db.DateTime, nullable=True)
    supplier_name = db.Column(db.String(100), nullable=True)
    supplier_email = db.Column(db.String(100), nullable=True)
    supplier_lead_time_hours = db.Column(db.Integer, default=24)
    sku_criticality = db.Column(db.String(20), default="medium")
    srs_score = db.Column(db.Float, default=0.0)
    srs_last_computed = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SalesVelocity(db.Model):
    __tablename__ = "sales_velocity"

    id = db.Column(db.Integer, primary_key=True)
    sku_id = db.Column(db.String(50), nullable=False, index=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey("mall_properties.id"), nullable=False)
    units_sold = db.Column(db.Integer, default=1)
    sale_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    zone_id = db.Column(db.String(50), nullable=True)
    transaction_id = db.Column(db.String(50), nullable=True)


class FootTraffic(db.Model):
    __tablename__ = "foot_traffic"

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("mall_properties.id"), nullable=False)
    zone_id = db.Column(db.String(50), nullable=False)
    floor = db.Column(db.Integer, default=1)
    count = db.Column(db.Integer, default=0)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    data_source = db.Column(db.String(50), default="simulator")
