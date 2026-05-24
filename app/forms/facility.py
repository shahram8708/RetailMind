from flask_wtf import FlaskForm
from wtforms import DecimalField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class WorkOrderForm(FlaskForm):
    title = StringField(
        "Work Order Title",
        validators=[DataRequired(), Length(min=5, max=200)],
    )
    description = TextAreaField(
        "Issue Description / Maintenance Instructions",
        validators=[DataRequired(), Length(min=10, max=2000)],
        render_kw={"rows": 5},
    )
    priority = SelectField(
        "Priority",
        validators=[DataRequired()],
        choices=[
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
            ("critical", "Critical"),
        ],
    )
    assigned_to_user_id = SelectField(
        "Assign To",
        coerce=int,
        validators=[Optional()],
        choices=[(0, "Unassigned")],
    )
    estimated_cost_inr = DecimalField(
        "Estimated Cost (INR)",
        validators=[Optional(), NumberRange(min=0)],
        places=2,
    )
    submit = SubmitField("Create Work Order")


def parse_facility_filters(request_obj):
    return {
        "floor": request_obj.args.get("floor", type=int),
        "equipment_type": (request_obj.args.get("equipment_type", "") or "").strip().lower(),
        "status_filter": (request_obj.args.get("status", "all") or "all").strip().lower(),
    }
