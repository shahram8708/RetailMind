from datetime import datetime

from app.extensions import db


class ShopperInteraction(db.Model):
    __tablename__ = "shopper_interactions"

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("mall_properties.id"), nullable=False)
    session_id = db.Column(db.String(100), nullable=True)
    shopper_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    query_text = db.Column(db.Text, nullable=False)
    results_returned = db.Column(db.Integer, default=0)
    result_clicked = db.Column(db.String(100), nullable=True)
    purchase_completed = db.Column(db.Boolean, default=False)
    mall_entry_zone = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    gemini_intent_extracted = db.Column(db.Text, nullable=True)
    response_time_ms = db.Column(db.Integer, nullable=True)
