from flask_wtf import FlaskForm
from wtforms import DateTimeLocalField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional


class CampaignEditForm(FlaskForm):
    campaign_name = StringField(
        "Campaign Name",
        validators=[DataRequired(), Length(max=200)],
    )
    campaign_copy = TextAreaField(
        "Campaign Copy",
        validators=[DataRequired(), Length(max=2000)],
        render_kw={"rows": 5},
    )
    target_audience_description = TextAreaField(
        "Target Audience",
        validators=[Optional(), Length(max=500)],
        render_kw={"rows": 3},
    )
    channel = SelectField(
        "Channel",
        choices=[
            ("in_app", "In-App Notification"),
            ("push_notification", "Push Notification"),
            ("digital_signage", "Digital Signage"),
            ("sms", "SMS"),
            ("email", "Email"),
        ],
    )
    expires_at = DateTimeLocalField(
        "Campaign Expiry",
        validators=[Optional()],
        format="%Y-%m-%dT%H:%M",
    )
    submit = SubmitField("Save Changes")
