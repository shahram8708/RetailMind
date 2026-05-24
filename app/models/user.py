from datetime import datetime

from flask_login import UserMixin

from app.extensions import bcrypt, db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False, default="mall_admin")
    phone = db.Column(db.String(20), nullable=True)
    is_verified = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    property_id = db.Column(db.Integer, db.ForeignKey("mall_properties.id"), nullable=True)
    notification_preferences = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    property = db.relationship(
        "MallProperty",
        foreign_keys=[property_id],
        backref=db.backref("users", lazy="dynamic"),
    )

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def is_superadmin(self):
        return self.role == "superadmin"

    def get_dashboard_route(self):
        if self.role != "shopper" and self.property_id and self.property and not self.property.onboarding_complete:
            return "/onboarding/step/1"

        role_routes = {
            "superadmin": "/superadmin",
            "mall_admin": "/dashboard",
            "store_manager": "/dashboard",
            "marketing_manager": "/dashboard",
            "facility_manager": "/dashboard",
            "shopper": "/shopper",
        }
        return role_routes.get(self.role, "/dashboard")

    def get_initials(self):
        name = (self.full_name or "").strip()
        if not name:
            return "U"
        return name[0].upper()


class EmailVerificationToken(db.Model):
    __tablename__ = "email_verification_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    token = db.Column(db.String(255), unique=True, index=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="verification_tokens")


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    token = db.Column(db.String(255), unique=True, index=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="reset_tokens")
