import re

from flask_login import current_user
from flask_wtf import FlaskForm
from sqlalchemy import func
from wtforms import EmailField, PasswordField, SelectField, StringField, SubmitField
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


ROLE_CHOICES = [
    ("store_manager", "Store Manager"),
    ("marketing_manager", "Marketing Manager"),
    ("facility_manager", "Facility Manager"),
]


class InviteTeamMemberForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(min=2, max=100)])
    email = EmailField("Email Address", validators=[DataRequired(), Email()])
    role = SelectField("Role", validators=[DataRequired()], choices=ROLE_CHOICES)
    submit = SubmitField("Send Invitation")

    def validate_email(self, field):
        existing_user = User.query.filter(func.lower(User.email) == field.data.strip().lower()).first()
        if existing_user:
            raise ValidationError("A user with this email already exists.")


class ChangeRoleForm(FlaskForm):
    role = SelectField("Role", validators=[DataRequired()], choices=ROLE_CHOICES)
    submit = SubmitField("Change Role")


class ProfileEditForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(min=2, max=100)])
    phone = StringField("Phone", validators=[Optional(), Length(max=15)])
    submit = SubmitField("Save Profile")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current Password", validators=[DataRequired()])
    new_password = PasswordField("New Password", validators=[DataRequired(), Length(min=8)])
    confirm_new_password = PasswordField(
        "Confirm New Password",
        validators=[DataRequired(), EqualTo("new_password")],
    )
    submit = SubmitField("Change Password")

    def validate_current_password(self, field):
        if not current_user.is_authenticated or not current_user.check_password(field.data):
            raise ValidationError("Current password is incorrect.")

    def validate_new_password(self, field):
        _validate_password_strength(field.data)
