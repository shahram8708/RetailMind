from datetime import datetime

from app.extensions import db


class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("mall_properties.id"), unique=True, nullable=False)
    plan_name = db.Column(db.String(50), nullable=False)
    price_inr = db.Column(db.Float, nullable=False)
    billing_cycle = db.Column(db.String(20), default="monthly")
    status = db.Column(db.String(50), default="trial")
    trial_ends_at = db.Column(db.DateTime, nullable=True)
    current_period_start = db.Column(db.DateTime, nullable=True)
    current_period_end = db.Column(db.DateTime, nullable=True)
    razorpay_subscription_id = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    property = db.relationship("MallProperty", backref=db.backref("subscription", uselist=False))


class PaymentRecord(db.Model):
    __tablename__ = "payment_records"

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("mall_properties.id"), nullable=False)
    razorpay_order_id = db.Column(db.String(100), nullable=True)
    razorpay_payment_id = db.Column(db.String(100), nullable=True)
    razorpay_signature = db.Column(db.String(200), nullable=True)
    amount_inr = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default="created")
    plan_name = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DemoRequest(db.Model):
    __tablename__ = "demo_requests"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    company_name = db.Column(db.String(200), nullable=True)
    email = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    num_stores = db.Column(db.String(50), nullable=True)
    role = db.Column(db.String(100), nullable=True)
    message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), default="new")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
