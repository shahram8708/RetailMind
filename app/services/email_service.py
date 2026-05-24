import os
from datetime import datetime

from flask_mail import Message


def _build_email_html(title, body_html, cta_text=None, cta_url=None):
    cta_html = f'<a href="{cta_url}" class="cta-button">{cta_text}</a>' if cta_text and cta_url else ""
    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #F3F4F6; margin: 0; padding: 0; }}
    .email-container {{ max-width: 600px; margin: 32px auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
    .email-header {{ background: #0A1628; padding: 24px 32px; text-align: center; }}
    .email-header h1 {{ color: white; font-size: 22px; margin: 0; font-weight: 700; letter-spacing: -0.5px; }}
    .email-header .brand-dot {{ display: inline-block; width: 8px; height: 8px; background: #1A6FE8; border-radius: 50%; margin-left: 3px; vertical-align: middle; }}
    .email-body {{ padding: 32px; color: #111827; line-height: 1.6; }}
    .email-body h2 {{ color: #0A1628; font-size: 18px; margin-top: 0; }}
    .email-body p {{ color: #374151; font-size: 15px; }}
    .email-body .highlight-box {{ background: #F0F6FF; border-left: 4px solid #1A6FE8; padding: 16px 20px; border-radius: 0 8px 8px 0; margin: 20px 0; }}
    .email-body .cta-button {{ display: inline-block; background: #1A6FE8; color: white; padding: 12px 28px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 15px; margin: 16px 0; }}
    .email-body .cta-button:hover {{ background: #1558C0; }}
    .email-footer {{ background: #F9FAFB; padding: 20px 32px; text-align: center; border-top: 1px solid #E5E7EB; color: #6B7280; font-size: 13px; }}
    .email-footer a {{ color: #1A6FE8; text-decoration: none; }}
    .info-row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #F3F4F6; }}
    .info-label {{ color: #6B7280; font-size: 13px; }}
    .info-value {{ color: #111827; font-weight: 500; font-size: 13px; }}
    .stats-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 14px 0; }}
    .stat-card {{ background: #F8FAFC; border: 1px solid #E5E7EB; border-radius: 8px; padding: 12px; }}
    .stat-label {{ color: #6B7280; font-size: 12px; margin-bottom: 4px; }}
    .stat-value {{ color: #0A1628; font-size: 18px; font-weight: 700; }}
  </style>
</head>
<body>
  <div class="email-container">
    <div class="email-header">
      <h1>RetailMind<span class="brand-dot"></span></h1>
    </div>
    <div class="email-body">
      {body_html}
      {cta_html}
    </div>
    <div class="email-footer">
    <p>(c) 2026 RetailMind - AI-Powered Mall Operations - <a href="mailto:support@retailmind.ai">support@retailmind.ai</a></p>
      <p>This email was sent by RetailMind. If you did not request this, you can safely ignore it.</p>
    </div>
  </div>
</body>
</html>
"""


def _send_email(subject, recipient_email, plain_body, html_body, function_name):
    try:
        mail_username = os.getenv("MAIL_USERNAME")
        if not mail_username:
            print(f"[Email Service] MAIL_USERNAME not configured. Skipping {function_name} email.")
            return False

        from app.extensions import mail

        msg = Message(
            subject=subject,
            recipients=[recipient_email],
            body=plain_body,
            html=html_body,
        )
        mail.send(msg)
        return True
    except Exception as e:
        print(f"[Email Service] Failed to send email: {e}")
        return False


def send_verification_email(user, token):
    base_url = os.getenv("BASE_URL", "http://localhost:5000")
    cta_url = f"{base_url}/auth/verify-email/{token}"
    subject = "Verify Your RetailMind Account - Action Required"

    body_html = (
        f"<h2>Hello {user.full_name},</h2>"
        "<p>Welcome to RetailMind. Please verify your email address to activate your account.</p>"
        "<p>Please complete verification within 24 hours.</p>"
        "<div class=\"highlight-box\">This verification link will expire in 24 hours. If it expires, request a new verification email from the login page.</div>"
    )
    html_body = _build_email_html("Verify Account", body_html, "Verify Email", cta_url)

    plain_body = (
        f"Hello {user.full_name},\n\n"
        "Welcome to RetailMind. Please verify your email address using the link below:\n"
        f"{cta_url}\n\n"
        "This link expires in 24 hours."
    )

    return _send_email(subject, user.email, plain_body, html_body, "send_verification_email")


def send_password_reset_email(user, token):
    base_url = os.getenv("BASE_URL", "http://localhost:5000")
    cta_url = f"{base_url}/auth/reset-password/{token}"
    subject = "Reset Your RetailMind Password"

    body_html = (
        f"<h2>Hello {user.full_name},</h2>"
        "<p>A password reset was requested for your RetailMind account.</p>"
        "<p>Use the secure button below to set a new password.</p>"
        "<div class=\"highlight-box\">This reset link will expire in 1 hour for security reasons.</div>"
        "<p>If you did not request this reset, no action is needed.</p>"
    )
    html_body = _build_email_html("Reset Password", body_html, "Reset Password", cta_url)

    plain_body = (
        f"Hello {user.full_name},\n\n"
        "A password reset was requested for your account.\n"
        f"Reset link: {cta_url}\n\n"
        "This link expires in 1 hour. If you did not request this, ignore this email."
    )

    return _send_email(subject, user.email, plain_body, html_body, "send_password_reset_email")


def send_team_invite_email(invited_user, inviter_name, property_name, temp_password):
    base_url = os.getenv("BASE_URL", "http://localhost:5000")
    cta_url = f"{base_url}/auth/login"
    subject = f"You've been invited to join {property_name} on RetailMind"

    role_descriptions = {
        "store_manager": "You can monitor inventory risk and take stock actions.",
        "marketing_manager": "You can manage campaigns and analytics workflows.",
        "facility_manager": "You can monitor equipment and work orders.",
        "mall_admin": "You have full administrative control for this property.",
    }

    role_label = invited_user.role.replace("_", " ").title()
    role_note = role_descriptions.get(invited_user.role, "Your role permissions are now active.")

    body_html = (
        f"<h2>Hello {invited_user.full_name},</h2>"
        f"<p>{inviter_name} has added you to {property_name}'s RetailMind account as <strong>{role_label}</strong>.</p>"
        f"<div class=\"highlight-box\">"
        f"<div><strong>Email:</strong> {invited_user.email}</div>"
        f"<div><strong>Temporary Password:</strong> {temp_password}</div>"
        f"<div>Please change your password after first login.</div>"
        f"</div>"
        f"<p>{role_note}</p>"
    )
    html_body = _build_email_html("Team Invitation", body_html, "Go to Login", cta_url)

    plain_body = (
        f"Hello {invited_user.full_name},\n\n"
        f"{inviter_name} invited you to join {property_name} on RetailMind as {role_label}.\n"
        f"Email: {invited_user.email}\n"
        f"Temporary Password: {temp_password}\n"
        "Please change your password after first login.\n"
        f"Login: {cta_url}"
    )

    return _send_email(subject, invited_user.email, plain_body, html_body, "send_team_invite_email")


def send_demo_request_confirmation(name, email, company_name):
    subject = "Demo Request Received - RetailMind"

    body_html = (
        f"<h2>Thank you {name}!</h2>"
        f"<p>We received your demo request for <strong>{company_name or 'your company'}</strong>.</p>"
        f"<p>Our team will contact you at <strong>{email}</strong> within 24 business hours.</p>"
        "<p>What to expect: 45 minute product walkthrough, Q and A session, and a custom ROI estimate for your property.</p>"
    )
    html_body = _build_email_html("Demo Request Received", body_html)

    plain_body = (
        f"Thank you {name}!\n\n"
        f"We received your demo request for {company_name or 'your company'}.\n"
        f"Our team will contact you at {email} within 24 business hours.\n"
        "What to expect: 45 minute walkthrough, Q and A, custom ROI estimate."
    )

    return _send_email(subject, email, plain_body, html_body, "send_demo_request_confirmation")


def send_admin_demo_notification(demo_request):
    mail_username = os.getenv("MAIL_USERNAME")
    if not mail_username:
        print("[Email Service] MAIL_USERNAME not configured. Skipping send_admin_demo_notification email.")
        return False

    company = demo_request.company_name or "Unknown Company"
    subject = f"New Demo Request: {company}"
    submitted_at = demo_request.created_at.strftime("%d %b %Y %I:%M %p") if demo_request.created_at else "N/A"

    body_html = (
        "<h2>New Demo Request Submitted</h2>"
        "<p>A new demo request was submitted.</p>"
        "<div class=\"highlight-box\">"
        f"<div><strong>Name:</strong> {demo_request.full_name}</div>"
        f"<div><strong>Email:</strong> {demo_request.email}</div>"
        f"<div><strong>Phone:</strong> {demo_request.phone or 'N/A'}</div>"
        f"<div><strong>Company:</strong> {company}</div>"
        f"<div><strong>City:</strong> {demo_request.city or 'N/A'}</div>"
        f"<div><strong>Number of Stores:</strong> {demo_request.num_stores or 'N/A'}</div>"
        f"<div><strong>Role:</strong> {demo_request.role or 'N/A'}</div>"
        f"<div><strong>Message:</strong> {demo_request.message or 'N/A'}</div>"
        f"<div><strong>Submitted At:</strong> {submitted_at}</div>"
        "</div>"
    )
    html_body = _build_email_html("New Demo Request", body_html)

    plain_body = (
        "New demo request submitted.\n\n"
        f"Name: {demo_request.full_name}\n"
        f"Email: {demo_request.email}\n"
        f"Phone: {demo_request.phone or 'N/A'}\n"
        f"Company: {company}\n"
        f"City: {demo_request.city or 'N/A'}\n"
        f"Num Stores: {demo_request.num_stores or 'N/A'}\n"
        f"Role: {demo_request.role or 'N/A'}\n"
        f"Message: {demo_request.message or 'N/A'}\n"
        f"Submitted At: {submitted_at}"
    )

    return _send_email(subject, mail_username, plain_body, html_body, "send_admin_demo_notification")


def send_restock_alert_email(user, inventory_item, srs_score, action_id):
    base_url = os.getenv("BASE_URL", "http://localhost:5000")
    cta_url = f"{base_url}/inventory/{inventory_item.sku_id}"
    subject = f"Restock Alert: {inventory_item.product_name} - SRS {srs_score:.0%}"

    if srs_score >= 0.9:
        stockout_eta = "within a few hours"
    elif srs_score >= 0.8:
        stockout_eta = "within 24 hours"
    elif srs_score >= 0.7:
        stockout_eta = "in 2 to 3 days"
    else:
        stockout_eta = "soon"

    score_color = "#DC2626" if srs_score > 0.85 else "#F97316"

    body_html = (
        "<h2>Inventory Restock Alert</h2>"
        "<p>The following product requires immediate restocking action:</p>"
        "<div class=\"info-row\"><span class=\"info-label\">Product Name</span><span class=\"info-value\">"
        f"{inventory_item.product_name}</span></div>"
        "<div class=\"info-row\"><span class=\"info-label\">SKU ID</span><span class=\"info-value\">"
        f"{inventory_item.sku_id}</span></div>"
        "<div class=\"info-row\"><span class=\"info-label\">Current Stock</span><span class=\"info-value\">"
        f"{inventory_item.stock_level}</span></div>"
        "<div class=\"info-row\"><span class=\"info-label\">Reorder Threshold</span><span class=\"info-value\">"
        f"{inventory_item.reorder_threshold}</span></div>"
        "<div class=\"info-row\"><span class=\"info-label\">SRS Score</span><span class=\"info-value\" style=\"color:"
        f"{score_color};\">{srs_score:.2f}</span></div>"
        "<div class=\"info-row\"><span class=\"info-label\">Supplier</span><span class=\"info-value\">"
        f"{inventory_item.supplier_name or 'N/A'}</span></div>"
        "<div class=\"info-row\"><span class=\"info-label\">Lead Time</span><span class=\"info-value\">"
        f"{inventory_item.supplier_lead_time_hours or 'N/A'} hours</span></div>"
        f"<div class=\"highlight-box\">SRS Score {srs_score:.2f} - Estimated stockout {stockout_eta}.</div>"
        f"<p><strong>Action ID:</strong> {action_id}</p>"
    )
    html_body = _build_email_html("Restock Alert", body_html, "Approve Restock Now", cta_url)

    plain_body = (
        f"Restock Alert: {inventory_item.product_name}\n\n"
        f"SKU: {inventory_item.sku_id}\n"
        f"Current Stock: {inventory_item.stock_level}\n"
        f"Reorder Threshold: {inventory_item.reorder_threshold}\n"
        f"SRS Score: {srs_score:.2f}\n"
        f"Supplier: {inventory_item.supplier_name or 'N/A'}\n"
        f"Lead Time: {inventory_item.supplier_lead_time_hours or 'N/A'} hours\n"
        f"Estimated stockout: {stockout_eta}\n"
        f"Review: {cta_url}"
    )

    return _send_email(subject, user.email, plain_body, html_body, "send_restock_alert_email")


def send_facility_alert_email(user, equipment, fps_score, work_order_id):
    base_url = os.getenv("BASE_URL", "http://localhost:5000")
    cta_url = f"{base_url}/facility/{equipment.id}"
    severity = "CRITICAL" if fps_score > 0.85 else "Warning"
    priority = "Critical" if fps_score > 0.85 else "High" if fps_score > 0.70 else "Medium"
    subject = f"{severity}: {equipment.equipment_name} - FPS {fps_score:.0%}"

    body_html = (
        "<h2>Facility Alert</h2>"
        "<p>A facility equipment alert requires your attention:</p>"
        "<div class=\"info-row\"><span class=\"info-label\">Equipment Name</span><span class=\"info-value\">"
        f"{equipment.equipment_name}</span></div>"
        "<div class=\"info-row\"><span class=\"info-label\">Type</span><span class=\"info-value\">"
        f"{equipment.equipment_type}</span></div>"
        "<div class=\"info-row\"><span class=\"info-label\">Location</span><span class=\"info-value\">"
        f"Zone {equipment.zone} - Floor {equipment.floor}</span></div>"
        "<div class=\"info-row\"><span class=\"info-label\">FPS Score</span><span class=\"info-value\">"
        f"{fps_score:.2f}</span></div>"
        "<div class=\"info-row\"><span class=\"info-label\">Work Order ID</span><span class=\"info-value\">"
        f"{work_order_id}</span></div>"
        "<div class=\"info-row\"><span class=\"info-label\">Priority</span><span class=\"info-value\">"
        f"{priority}</span></div>"
    )
    html_body = _build_email_html("Facility Alert", body_html, "View Equipment Details", cta_url)

    plain_body = (
        f"Facility Alert: {equipment.equipment_name}\n\n"
        f"Type: {equipment.equipment_type}\n"
        f"Location: Zone {equipment.zone}, Floor {equipment.floor}\n"
        f"FPS Score: {fps_score:.2f}\n"
        f"Work Order ID: {work_order_id}\n"
        f"Priority: {priority}\n"
        f"View details: {cta_url}"
    )

    return _send_email(subject, user.email, plain_body, html_body, "send_facility_alert_email")


def send_payment_receipt_email(user, amount_inr, plan_name, payment_id):
    today = datetime.utcnow().strftime("%d %b %Y")
    amount_text = f"\u20b9{amount_inr:,.0f}"
    subject = f"Payment Confirmed - RetailMind {plan_name.title()} Plan"

    body_html = (
        "<h2>Payment Confirmed</h2>"
        f"<p>Payment received successfully. Your {plan_name.title()} subscription is now active.</p>"
        "<div class=\"highlight-box\">"
        f"<div><strong>Amount Paid:</strong> {amount_text}</div>"
        f"<div><strong>Plan:</strong> {plan_name.title()}</div>"
        f"<div><strong>Payment ID:</strong> {payment_id}</div>"
        f"<div><strong>Date:</strong> {today}</div>"
        "</div>"
        "<p>Your account has been upgraded and all features are now available.</p>"
        "<p class=\"small\">Retain this email as your payment receipt. GST invoice available on request.</p>"
    )
    html_body = _build_email_html("Payment Receipt", body_html)

    plain_body = (
        "Payment received successfully.\n\n"
        f"Amount Paid: {amount_text}\n"
        f"Plan: {plan_name.title()}\n"
        f"Payment ID: {payment_id}\n"
        f"Date: {today}\n\n"
        "Your account has been upgraded. Keep this email as your receipt."
    )

    return _send_email(subject, user.email, plain_body, html_body, "send_payment_receipt_email")


def send_morning_briefing_email(user, brief_data):
    base_url = os.getenv("BASE_URL", "http://localhost:5000")
    cta_url = f"{base_url}/dashboard"
    first_name = (user.full_name or "User").split()[0]
    subject = f"Good Morning {first_name} - RetailMind Daily Briefing"

    inventory_alerts = int(brief_data.get("inventory_alerts", 0))
    campaign_opportunities = int(brief_data.get("campaign_opportunities", 0))
    open_work_orders = int(brief_data.get("open_work_orders", 0))
    overnight_actions = int(brief_data.get("overnight_agent_actions", 0))

    body_html = (
        "<h2>Daily Operations Briefing</h2>"
        "<p>Here's your RetailMind operations summary for today:</p>"
        "<div class=\"stats-grid\">"
        f"<div class=\"stat-card\"><div class=\"stat-label\">Inventory Alerts</div><div class=\"stat-value\">{inventory_alerts}</div></div>"
        f"<div class=\"stat-card\"><div class=\"stat-label\">Campaign Opportunities</div><div class=\"stat-value\">{campaign_opportunities}</div></div>"
        f"<div class=\"stat-card\"><div class=\"stat-label\">Open Work Orders</div><div class=\"stat-value\">{open_work_orders}</div></div>"
        f"<div class=\"stat-card\"><div class=\"stat-label\">Agent Actions Overnight</div><div class=\"stat-value\">{overnight_actions}</div></div>"
        "</div>"
        "<p class=\"small\">This briefing is sent daily at 8:00 AM.</p>"
    )
    html_body = _build_email_html("Daily Briefing", body_html, "Go to Dashboard", cta_url)

    plain_body = (
        f"Good morning {first_name}.\n\n"
        f"Inventory Alerts: {inventory_alerts}\n"
        f"Campaign Opportunities: {campaign_opportunities}\n"
        f"Open Work Orders: {open_work_orders}\n"
        f"Agent Actions Overnight: {overnight_actions}\n\n"
        f"Dashboard: {cta_url}\n"
        "This briefing is sent daily at 8:00 AM."
    )

    return _send_email(subject, user.email, plain_body, html_body, "send_morning_briefing_email")
