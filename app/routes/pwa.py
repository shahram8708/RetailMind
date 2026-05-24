from flask import Blueprint, current_app, make_response, render_template, send_from_directory


pwa_bp = Blueprint("pwa", __name__)


@pwa_bp.route("/manifest.json")
def manifest():
    response = make_response(
        send_from_directory(
            current_app.static_folder,
            "manifest.json",
            mimetype="application/manifest+json",
        )
    )
    response.headers["Cache-Control"] = "no-cache"
    return response


@pwa_bp.route("/sw.js")
def service_worker():
    response = make_response(
        send_from_directory(
            current_app.static_folder,
            "sw.js",
            mimetype="application/javascript",
        )
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@pwa_bp.route("/browserconfig.xml")
def browser_config():
    response = make_response(
        send_from_directory(
            current_app.static_folder,
            "browserconfig.xml",
            mimetype="application/xml",
        )
    )
    response.headers["Cache-Control"] = "no-cache"
    return response


@pwa_bp.route("/offline")
def offline():
    return render_template("offline.html")
