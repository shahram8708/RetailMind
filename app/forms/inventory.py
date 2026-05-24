from flask_wtf import FlaskForm
from wtforms import EmailField, IntegerField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional


class SKUConfigForm(FlaskForm):
    reorder_threshold = IntegerField(
        "Reorder Threshold (units)",
        validators=[DataRequired(), NumberRange(min=1, max=10000)],
    )
    supplier_lead_time_hours = IntegerField(
        "Supplier Lead Time (hours)",
        validators=[DataRequired(), NumberRange(min=1, max=720)],
        default=24,
    )
    supplier_name = StringField(
        "Supplier Name",
        validators=[Optional(), Length(max=100)],
    )
    supplier_email = EmailField(
        "Supplier Contact Email",
        validators=[Optional(), Email()],
    )
    sku_criticality = SelectField(
        "SKU Criticality",
        choices=[
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
            ("critical", "Critical"),
        ],
    )
    submit = SubmitField("Save Configuration")
