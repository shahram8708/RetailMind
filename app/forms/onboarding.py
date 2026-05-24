import json
from decimal import Decimal

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DecimalField,
    EmailField,
    HiddenField,
    IntegerField,
    RadioField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional, URL, ValidationError


INDIAN_CITY_CHOICES = [
    ("Mumbai", "Mumbai"),
    ("Delhi", "Delhi"),
    ("Bengaluru", "Bengaluru"),
    ("Hyderabad", "Hyderabad"),
    ("Chennai", "Chennai"),
    ("Kolkata", "Kolkata"),
    ("Pune", "Pune"),
    ("Ahmedabad", "Ahmedabad"),
    ("Jaipur", "Jaipur"),
    ("Surat", "Surat"),
    ("Lucknow", "Lucknow"),
    ("Kanpur", "Kanpur"),
    ("Nagpur", "Nagpur"),
    ("Indore", "Indore"),
    ("Thane", "Thane"),
    ("Bhopal", "Bhopal"),
    ("Visakhapatnam", "Visakhapatnam"),
    ("Pimpri-Chinchwad", "Pimpri-Chinchwad"),
    ("Patna", "Patna"),
    ("Vadodara", "Vadodara"),
    ("Ghaziabad", "Ghaziabad"),
    ("Ludhiana", "Ludhiana"),
    ("Agra", "Agra"),
    ("Nashik", "Nashik"),
    ("Faridabad", "Faridabad"),
    ("Meerut", "Meerut"),
    ("Rajkot", "Rajkot"),
    ("Kalyan-Dombivali", "Kalyan-Dombivali"),
    ("Vasai-Virar", "Vasai-Virar"),
    ("Srinagar", "Srinagar"),
    ("Aurangabad", "Aurangabad"),
    ("Dhanbad", "Dhanbad"),
    ("Amritsar", "Amritsar"),
    ("Navi Mumbai", "Navi Mumbai"),
    ("Allahabad", "Allahabad"),
    ("Ranchi", "Ranchi"),
    ("Howrah", "Howrah"),
    ("Coimbatore", "Coimbatore"),
    ("Jabalpur", "Jabalpur"),
    ("Gwalior", "Gwalior"),
    ("Vijayawada", "Vijayawada"),
    ("Jodhpur", "Jodhpur"),
    ("Madurai", "Madurai"),
    ("Raipur", "Raipur"),
    ("Kota", "Kota"),
    ("Guwahati", "Guwahati"),
    ("Chandigarh", "Chandigarh"),
    ("Solapur", "Solapur"),
    ("Hubli-Dharwad", "Hubli-Dharwad"),
    ("Tiruchirappalli", "Tiruchirappalli"),
    ("Bareilly", "Bareilly"),
    ("Aligarh", "Aligarh"),
    ("Mysuru", "Mysuru"),
    ("Tiruppur", "Tiruppur"),
    ("Gurgaon", "Gurgaon"),
    ("Noida", "Noida"),
    ("Kochi", "Kochi"),
    ("Other", "Other"),
]


DATA_CONNECTION_CHOICES = [
    ("none", "Not connected"),
    ("shopify", "Shopify POS"),
    ("lightspeed", "Lightspeed Retail"),
    ("marg", "Marg ERP"),
    ("tally", "Tally Prime"),
    ("petpooja", "Petpooja (F&B)"),
    ("gofrugal", "GoFrugal"),
    ("custom_api", "Custom API Integration"),
    ("csv_import", "Manual CSV Import"),
]


CRM_CHOICES = [
    ("none", "Not connected"),
    ("zoho", "Zoho CRM"),
    ("salesforce", "Salesforce"),
    ("hubspot", "HubSpot"),
    ("leadsquared", "LeadSquared"),
    ("custom_api", "Custom API"),
    ("csv_import", "Manual CSV"),
]


SENSOR_SOURCE_CHOICES = [
    ("simulator", "Use RetailMind Simulator (Recommended for Trial)"),
    ("iot_api", "Live IoT API"),
    ("csv_import", "Periodic CSV Upload"),
    ("none", "Not connected"),
]


class OnboardingStep1Form(FlaskForm):
    mall_name = StringField(
        "Mall / Property Name",
        validators=[DataRequired(), Length(min=3, max=200)],
    )
    full_address = TextAreaField(
        "Full Address",
        validators=[DataRequired(), Length(max=500)],
        render_kw={"rows": 3},
    )
    city = SelectField("City", choices=INDIAN_CITY_CHOICES, validators=[DataRequired()])
    country = StringField("Country", default="India")
    total_area_sqft = IntegerField(
        "Total Floor Area (sq ft)",
        validators=[Optional(), NumberRange(min=1000, max=10000000)],
    )
    num_floors = IntegerField(
        "Number of Floors",
        validators=[DataRequired(), NumberRange(min=1, max=20)],
        default=3,
    )
    num_tenants_approx = IntegerField(
        "Approximate Number of Tenant Stores",
        validators=[DataRequired(), NumberRange(min=1, max=2000)],
    )
    submit = SubmitField("Save & Continue ->")


class OnboardingStep2Form(FlaskForm):
    pos_system = SelectField("POS System", choices=DATA_CONNECTION_CHOICES, default="none")
    pos_api_endpoint = StringField(
        "API Endpoint URL (if Custom API)",
        validators=[Optional(), URL(require_tld=False)],
    )
    pos_api_key = StringField("API Key (if applicable)", validators=[Optional(), Length(max=255)])

    inventory_system = SelectField(
        "Inventory Management System",
        choices=DATA_CONNECTION_CHOICES,
        default="none",
    )
    inventory_api_endpoint = StringField(
        "Inventory API Endpoint URL",
        validators=[Optional(), URL(require_tld=False)],
    )
    inventory_api_key = StringField("Inventory API Key", validators=[Optional(), Length(max=255)])

    crm_system = SelectField("CRM System", choices=CRM_CHOICES, default="none")
    sensor_source = SelectField("Sensor / IoT Data Source", choices=SENSOR_SOURCE_CHOICES, default="simulator")
    sensor_api_endpoint = StringField(
        "IoT API Endpoint URL",
        validators=[Optional(), URL(require_tld=False)],
    )
    weather_api_key = StringField(
        "OpenWeatherMap API Key (for campaign weather intelligence)",
        validators=[Optional(), Length(max=255)],
    )

    submit = SubmitField("Save & Continue ->")


class OnboardingStep3Form(FlaskForm):
    tenants_json = HiddenField()
    skip_for_now = BooleanField(
        "I'll add tenants later (you can add them in Settings)",
        default=False,
    )
    submit = SubmitField("Save & Continue ->")

    def validate_tenants_json(self, field):
        if self.skip_for_now.data:
            return

        raw_value = (field.data or "").strip()
        if not raw_value:
            return

        try:
            tenant_rows = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ValidationError("Tenant data format is invalid.") from exc

        if not isinstance(tenant_rows, list):
            raise ValidationError("Tenant data must be a list.")


class OnboardingStep4Form(FlaskForm):
    inventory_srs_threshold = DecimalField(
        "Stockout Risk Score Threshold",
        validators=[DataRequired(), NumberRange(min=Decimal("0.50"), max=Decimal("0.95"))],
        default=Decimal("0.70"),
        places=2,
    )
    campaign_cos_threshold = DecimalField(
        "Campaign Opportunity Score Threshold",
        validators=[DataRequired(), NumberRange(min=Decimal("0.50"), max=Decimal("0.95"))],
        default=Decimal("0.75"),
        places=2,
    )
    facility_fps_threshold = DecimalField(
        "Facility Failure Probability Threshold",
        validators=[DataRequired(), NumberRange(min=Decimal("0.50"), max=Decimal("0.95"))],
        default=Decimal("0.65"),
        places=2,
    )

    auto_approve_restock = BooleanField(
        "Auto-Approve Restock Orders (Agent acts without human approval)",
        default=False,
    )
    auto_approve_campaigns = BooleanField("Auto-Approve Campaign Activation", default=False)
    auto_approve_maintenance = BooleanField("Auto-Approve Maintenance Work Orders", default=False)

    notification_email = EmailField(
        "Alert Notification Email",
        validators=[Optional(), Email()],
    )

    inventory_check_interval_minutes = IntegerField(
        "Inventory Check Interval (minutes)",
        validators=[DataRequired(), NumberRange(min=5, max=60)],
        default=15,
    )
    campaign_check_interval_minutes = IntegerField(
        "Campaign Check Interval (minutes)",
        validators=[DataRequired(), NumberRange(min=15, max=120)],
        default=30,
    )
    facility_check_interval_minutes = IntegerField(
        "Facility Check Interval (minutes)",
        validators=[DataRequired(), NumberRange(min=5, max=30)],
        default=10,
    )

    submit = SubmitField("Save & Continue ->")


class OnboardingStep5Form(FlaskForm):
    email_alerts_enabled = BooleanField("Email Alerts", default=True)
    inapp_alerts_enabled = BooleanField("In-App Notifications", default=True)
    sms_alerts_enabled = BooleanField("SMS Alerts (requires phone number)", default=False)

    notify_inventory = BooleanField("Inventory Stockout Alerts", default=True)
    notify_campaigns = BooleanField("Campaign Opportunities", default=True)
    notify_facility = BooleanField("Facility & Equipment Alerts", default=True)
    notify_agent_actions = BooleanField("Agent Action Completions", default=True)
    notify_weekly_summary = BooleanField("Weekly Performance Summary Email", default=True)

    notification_frequency = RadioField(
        "Notification Frequency",
        choices=[
            ("immediate", "Immediate"),
            ("hourly", "Batched Hourly"),
            ("daily", "Daily Digest"),
        ],
        default="immediate",
        validators=[DataRequired()],
    )

    submit = SubmitField("Complete Setup & Go to Dashboard ->")
