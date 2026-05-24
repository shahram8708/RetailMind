import re

from flask_wtf import FlaskForm
from sqlalchemy import func
from wtforms import BooleanField, EmailField, PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, ValidationError

from app.models.user import User


SPECIAL_CHAR_PATTERN = re.compile(r"[^A-Za-z0-9]")


def _validate_password_strength(password):
    has_upper = any(char.isupper() for char in password)
    has_lower = any(char.islower() for char in password)
    has_digit = any(char.isdigit() for char in password)
    has_special = SPECIAL_CHAR_PATTERN.search(password) is not None

    if not has_upper:
        raise ValidationError("Password must include at least one uppercase letter.")
    if not has_lower:
        raise ValidationError("Password must include at least one lowercase letter.")
    if not has_digit:
        raise ValidationError("Password must include at least one number.")
    if not has_special:
        raise ValidationError("Password must include at least one special character.")


class LoginForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])
    remember_me = BooleanField("Remember me", default=False)
    submit = SubmitField("Sign In")


class RegisterForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(min=2, max=100)])
    email = EmailField("Email", validators=[DataRequired(), Email()])
    phone = StringField("Phone", validators=[Optional(), Length(max=15)])
    mall_name = StringField(
        "Mall / Property Name",
        validators=[DataRequired(), Length(min=3, max=200)],
    )
    city = StringField("City", validators=[DataRequired()])
    role = SelectField(
        "Role",
        choices=[
            ("mall_admin", "Mall Operations Manager"),
            ("marketing_manager", "Marketing Manager"),
            ("facility_manager", "Facility Manager"),
            ("store_manager", "Store Manager"),
        ],
        default="mall_admin",
    )
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match")],
    )
    agree_terms = BooleanField(
        "I agree to the Terms of Service",
        validators=[DataRequired(message="You must agree to the Terms of Service")],
    )
    submit = SubmitField("Create Account")

    def validate_email(self, field):
        existing_user = User.query.filter(func.lower(User.email) == field.data.lower()).first()
        if existing_user:
            raise ValidationError("An account with this email already exists.")

    def validate_password(self, field):
        _validate_password_strength(field.data)


class ForgotPasswordForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Send Reset Link")


class ResetPasswordForm(FlaskForm):
    password = PasswordField("New Password", validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[DataRequired(), EqualTo("password")],
    )
    submit = SubmitField("Reset Password")

    def validate_password(self, field):
        _validate_password_strength(field.data)
