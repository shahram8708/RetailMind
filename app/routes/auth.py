from datetime import datetime
from urllib.parse import urljoin, urlparse

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from markupsafe import Markup
from sqlalchemy import func

from app.extensions import db, limiter
from app.forms.auth import ForgotPasswordForm, LoginForm, RegisterForm, ResetPasswordForm
from app.models.property import MallProperty
from app.models.user import PasswordResetToken, User
from app.services.auth_service import (
    generate_password_reset_token,
    generate_verification_token,
    verify_email_token,
    verify_password_reset_token,
)
from app.services.email_service import send_password_reset_email, send_verification_email


auth_bp = Blueprint("auth", __name__)


def _slugify_prefix(mall_name, city, fallback):
    raw = f"{mall_name}-{city}".strip().lower()
    slug = "".join(char if char.isalnum() else "_" for char in raw)
    slug = "_".join(filter(None, slug.split("_")))
    return slug[:80] if slug else fallback


def _is_safe_next_url(target):
    if not target:
        return False
    host_url = urlparse(request.host_url)
    redirect_url = urlparse(urljoin(request.host_url, target))
    return redirect_url.scheme in {"http", "https"} and host_url.netloc == redirect_url.netloc


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(current_user.get_dashboard_route())

    form = RegisterForm()
    plan = request.args.get("plan", "starter").strip().lower()
    if plan not in {"starter", "professional", "enterprise"}:
        plan = "starter"

    if form.validate_on_submit():
        try:
            user = User(
                email=form.email.data.strip().lower(),
                full_name=form.full_name.data.strip(),
                role=form.role.data,
                phone=(form.phone.data or "").strip() or None,
                is_verified=False,
                is_active=True,
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.flush()

            property_prefix = _slugify_prefix(form.mall_name.data, form.city.data, f"property_{user.id}")
            property_record = MallProperty(
                name=form.mall_name.data.strip(),
                city=form.city.data.strip(),
                country="India",
                owner_user_id=user.id,
                subscription_tier=plan,
                onboarding_complete=False,
                elasticsearch_index_prefix=f"{property_prefix}_{user.id}",
            )
            db.session.add(property_record)
            db.session.flush()

            user.property_id = property_record.id
            db.session.commit()

            token = generate_verification_token(user.id)
            send_verification_email(user, token)

            flash("Account created! Please check your email to verify your account.", "success")
            return redirect(url_for("auth.login"))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Registration failed")
            flash("We could not create your account right now. Please try again.", "danger")

    return render_template("auth/register.html", form=form, plan=plan)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(current_user.get_dashboard_route())

    form = LoginForm()

    if form.validate_on_submit():
        try:
            email = form.email.data.strip().lower()
            user = User.query.filter(func.lower(User.email) == email).first()

            if user is None or not user.check_password(form.password.data):
                flash("Invalid email or password.", "danger")
                return render_template("auth/login.html", form=form)

            if not user.is_verified:
                resend_url = url_for("auth.resend_verification", email=email)
                flash(
                    Markup(
                        "Please verify your email address first. "
                        f"<a href=\"{resend_url}\">Resend verification email</a>"
                    ),
                    "warning",
                )
                return render_template("auth/login.html", form=form)

            if not user.is_active:
                flash("Your account has been deactivated. Contact support.", "danger")
                return render_template("auth/login.html", form=form)

            login_user(user, remember=form.remember_me.data)

            session.permanent = True
            if form.remember_me.data:
                current_app.permanent_session_lifetime = current_app.config.get("REMEMBER_COOKIE_DURATION")
            else:
                current_app.permanent_session_lifetime = current_app.config.get("PERMANENT_SESSION_LIFETIME")

            user.last_login = datetime.utcnow()
            db.session.commit()

            next_page = request.args.get("next")
            if next_page and _is_safe_next_url(next_page):
                return redirect(next_page)

            return redirect(current_user.get_dashboard_route())
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Login failed")
            flash("Unable to process login right now. Please try again.", "danger")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("public.index"))


@auth_bp.route("/verify-email/<token>")
def verify_email(token):
    try:
        user, error = verify_email_token(token)
        if error:
            resend_url = url_for("auth.resend_verification")
            flash(Markup(f"{error}. <a href=\"{resend_url}\">Resend verification email</a>"), "danger")
            return redirect(url_for("auth.login"))

        flash("Email verified! You can now log in.", "success")
        return redirect(url_for("auth.login"))
    except Exception:
        current_app.logger.exception("Email verification failed")
        flash("Unable to verify email at the moment. Please try again.", "danger")
        return redirect(url_for("auth.login"))


@auth_bp.route("/resend-verification")
def resend_verification():
    email = (request.args.get("email") or "").strip().lower()

    if email:
        user = User.query.filter(func.lower(User.email) == email).first()
        if user and not user.is_verified:
            try:
                token = generate_verification_token(user.id)
                send_verification_email(user, token)
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Failed to resend verification")

    flash("If that account exists and is unverified, a new verification email has been sent.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    form = ForgotPasswordForm()

    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter(func.lower(User.email) == email).first()

        if user:
            try:
                token = generate_password_reset_token(user.id)
                send_password_reset_email(user, token)
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Failed to generate password reset token")

        flash(
            "If that email address is registered, you will receive a password reset link shortly.",
            "info",
        )
        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html", form=form)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user, error = verify_password_reset_token(token)

    if error:
        flash(error, "danger")
        return redirect(url_for("auth.forgot_password"))

    form = ResetPasswordForm()

    if form.validate_on_submit():
        try:
            user.set_password(form.password.data)
            reset_token = PasswordResetToken.query.filter_by(token=token, used=False).first()
            if reset_token:
                reset_token.used = True
            db.session.commit()

            flash("Password reset successfully. Please sign in.", "success")
            return redirect(url_for("auth.login"))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Password reset failed")
            flash("Unable to reset password right now. Please try again.", "danger")

    return render_template("auth/reset_password.html", form=form)
