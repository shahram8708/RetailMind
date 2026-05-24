import importlib
import json
import os
import secrets
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, g, redirect, render_template, request, send_from_directory, url_for

from app.extensions import bcrypt, cache, csrf, db, limiter, login_manager, mail, migrate


def _print_env_warnings(app):
    warnings = []

    if not app.config.get("SECRET_KEY"):
        warnings.append("SECRET_KEY is missing. Session protection is weakened.")
    if not app.config.get("MAIL_USERNAME"):
        warnings.append("MAIL_USERNAME is missing. Outbound email features are disabled.")
    if not app.config.get("MAIL_PASSWORD"):
        warnings.append("MAIL_PASSWORD is missing. Outbound email features may fail.")
    if not app.config.get("GEMINI_ENABLED"):
        warnings.append("GEMINI_API_KEY is missing. Gemini powered features are disabled.")
    if not app.config.get("RAZORPAY_ENABLED"):
        warnings.append("Razorpay credentials are missing. Billing collection is disabled.")
    if not app.config.get("ES_ENABLED"):
        warnings.append("Elasticsearch credentials are missing. Search acceleration is disabled.")

    for warning in warnings:
        message = f"[RetailMind Warning] {warning}"
        print(message)
        app.logger.warning(message)


def _register_error_handlers(app):
    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(_error):
        db.session.rollback()
        return render_template("errors/500.html"), 500


def _load_asset_manifest(static_folder):
    manifest_path = os.path.join(static_folder, "asset-manifest.json")
    if not os.path.exists(manifest_path):
        return {}
    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
            return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def create_app():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_folder = os.path.join(project_root, "static")

    load_dotenv(os.path.join(project_root, ".env"))
    from app.config import config_map

    app = Flask(
        __name__,
        static_folder=static_folder,
        static_url_path="/static",
        template_folder="templates",
    )

    app.config["ASSET_MANIFEST"] = _load_asset_manifest(static_folder)

    env_name = os.getenv("FLASK_ENV", "development").strip().lower()
    config_class = config_map.get(env_name, config_map["development"])
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)
    bcrypt.init_app(app)
    cache.init_app(app)
    limiter.init_app(app)
    csrf.init_app(app)
    app.config["WTF_CSRF_ENABLED"] = True

    if app.config.get("FORCE_HTTPS_REDIRECT"):
        @app.before_request
        def enforce_https_redirect():
            forwarded_proto = request.headers.get("X-Forwarded-Proto", "")
            is_secure = request.is_secure or forwarded_proto == "https"
            if not is_secure and not app.debug:
                return redirect(request.url.replace("http://", "https://", 1), code=301)

    @app.before_request
    def set_csp_nonce():
        g.csp_nonce = secrets.token_urlsafe(16)

    from app.routes.auth import auth_bp
    from app.routes.agent import agent_bp
    from app.routes.analytics import analytics_bp
    from app.routes.api import api_bp, format_relative_time
    from app.routes.campaigns import campaigns_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.facility import facility_bp
    from app.routes.inventory import inventory_bp
    from app.routes.notifications import notifications_bp
    from app.routes.onboarding import onboarding_bp
    from app.routes.public import public_bp
    from app.routes.settings import settings_bp
    from app.routes.shopper import shopper_bp
    from app.routes.superadmin import superadmin_bp
    from app.routes.pwa import pwa_bp
    from app.routes.push import push_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(onboarding_bp, url_prefix="/onboarding")
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(notifications_bp, url_prefix="/notifications")
    app.register_blueprint(inventory_bp, url_prefix="/inventory")
    app.register_blueprint(campaigns_bp, url_prefix="/campaigns")
    app.register_blueprint(facility_bp, url_prefix="/facility")
    app.register_blueprint(analytics_bp, url_prefix="/analytics")
    app.register_blueprint(agent_bp, url_prefix="/agent")
    app.register_blueprint(shopper_bp, url_prefix="/shopper")
    app.register_blueprint(settings_bp, url_prefix="/settings")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(superadmin_bp, url_prefix="/superadmin")
    app.register_blueprint(pwa_bp)
    app.register_blueprint(push_bp, url_prefix="/push")

    from app.services.scheduler_service import init_scheduler

    init_scheduler(app)

    def format_inr(value):
        if value is None:
            return "0"

        value = int(value)
        sign = "-" if value < 0 else ""
        s = str(abs(value))

        if len(s) <= 3:
            return f"{sign}{s}"

        result = s[-3:]
        s = s[:-3]

        while len(s) > 2:
            result = s[-2:] + "," + result
            s = s[:-2]

        if s:
            result = s + "," + result

        return f"{sign}{result}"

    app.jinja_env.filters["format_inr"] = format_inr
    app.jinja_env.filters["relative_time"] = format_relative_time
    app.jinja_env.globals["format_relative_time"] = format_relative_time

    @app.context_processor
    def inject_pwa_config():
        def asset_url(asset_path):
            manifest = app.config.get("ASSET_MANIFEST") or {}
            if not app.config.get("PWA_DEV_MODE") and asset_path in manifest:
                return url_for("static", filename=manifest[asset_path])
            return url_for("static", filename=asset_path)

        return {
            "asset_url": asset_url,
            "pwa_dev_mode": bool(app.config.get("PWA_DEV_MODE")),
            "pwa_cache_version": app.config.get("PWA_CACHE_VERSION"),
            "csp_nonce": getattr(g, "csp_nonce", ""),
        }

    @app.after_request
    def add_security_and_cache_headers(response):
        path = request.path or ""

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")

        if app.config.get("FORCE_HTTPS_REDIRECT"):
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains; preload",
            )

        script_src = ["'self'", f"'nonce-{getattr(g, 'csp_nonce', '')}'", "https://cdn.jsdelivr.net", "https://checkout.razorpay.com"]
        style_src = ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"]
        img_src = ["'self'", "data:", "blob:"]
        font_src = ["'self'", "data:"]
        connect_src = [
            "'self'",
            "https://generativelanguage.googleapis.com",
            "https://api.razorpay.com",
            "https://checkout.razorpay.com",
            "https://cdn.jsdelivr.net",
        ]

        csp = (
            "default-src 'self'; "
            f"script-src {' '.join(script_src)}; "
            f"style-src {' '.join(style_src)}; "
            f"img-src {' '.join(img_src)}; "
            f"font-src {' '.join(font_src)}; "
            f"connect-src {' '.join(connect_src)}; "
            "frame-src 'self' https://checkout.razorpay.com; "
            "manifest-src 'self'; "
            "worker-src 'self';"
        )
        response.headers.setdefault("Content-Security-Policy", csp)

        if "Cache-Control" not in response.headers:
            if path.startswith("/api/"):
                response.headers["Cache-Control"] = "no-store"
            elif path.startswith("/static/"):
                if app.config.get("PWA_DEV_MODE"):
                    response.headers["Cache-Control"] = "no-cache"
                else:
                    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                response.headers["Cache-Control"] = "no-cache"

        return response

    _register_error_handlers(app)
    _print_env_warnings(app)

    with app.app_context():
        # Import models without rebinding the local `app` variable.
        importlib.import_module("app.models")

        db.create_all()

        from app.seed import seed_database_if_empty

        seed_database_if_empty()

    app.start_time = datetime.utcnow()

    return app
