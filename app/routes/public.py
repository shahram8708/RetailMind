from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_wtf import FlaskForm
from wtforms import EmailField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional

from app.extensions import db
from app.models.billing import DemoRequest
from app.services.email_service import send_admin_demo_notification, send_demo_request_confirmation


public_bp = Blueprint("public", __name__)


class DemoRequestForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(max=100)])
    company_name = StringField("Company / Mall Name", validators=[Optional(), Length(max=200)])
    email = EmailField("Email Address", validators=[DataRequired(), Email()])
    phone = StringField("Phone Number", validators=[Optional(), Length(max=20)])
    city = StringField("City", validators=[Optional(), Length(max=100)])
    num_stores = SelectField(
        "Number of Tenant Stores",
        choices=[
            ("Less than 50", "Less than 50"),
            ("50-100", "50-100"),
            ("100-200", "100-200"),
            ("200+", "200+"),
        ],
        validators=[DataRequired()],
    )
    role = SelectField(
        "Your Role",
        choices=[
            ("Mall Operations Manager", "Mall Operations Manager"),
            ("Store Manager", "Store Manager"),
            ("Marketing Manager", "Marketing Manager"),
            ("Facility Manager", "Facility Manager"),
            ("IT Manager", "IT Manager"),
            ("C-Suite Executive", "C-Suite Executive"),
            ("Other", "Other"),
        ],
        validators=[DataRequired()],
    )
    message = TextAreaField("Message / Specific Requirements", validators=[Optional(), Length(max=2000)])
    submit = SubmitField("Request My Demo ->")


@public_bp.route("/")
def index():
    return render_template("public/index.html")


@public_bp.route("/features")
def features():
    return render_template("public/features.html")


@public_bp.route("/pricing")
def pricing():
    return render_template("public/pricing.html")


@public_bp.route("/about")
def about():
    return render_template("public/about.html")


@public_bp.route("/demo", methods=["GET", "POST"])
def demo():
    form = DemoRequestForm()

    if form.validate_on_submit():
        try:
            demo_request = DemoRequest(
                full_name=form.full_name.data.strip(),
                company_name=(form.company_name.data or "").strip() or None,
                email=form.email.data.strip().lower(),
                phone=(form.phone.data or "").strip() or None,
                city=(form.city.data or "").strip() or None,
                num_stores=form.num_stores.data,
                role=form.role.data,
                message=(form.message.data or "").strip() or None,
            )
            db.session.add(demo_request)
            db.session.commit()

            send_demo_request_confirmation(
                demo_request.full_name,
                demo_request.email,
                demo_request.company_name,
            )
            send_admin_demo_notification(demo_request)

            flash(
                (
                    f"Thank you, {demo_request.full_name}! We've received your demo request "
                    f"and will contact you at {demo_request.email} within 24 business hours."
                ),
                "success",
            )
            return redirect(url_for("public.demo"))
        except Exception:
            db.session.rollback()
            flash("Unable to submit your request right now. Please try again shortly.", "danger")

    return render_template("public/demo.html", form=form)
