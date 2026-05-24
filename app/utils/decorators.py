from functools import wraps

from flask import abort, flash, redirect, url_for
from flask_login import current_user


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))

            if current_user.role == "superadmin":
                return view_func(*args, **kwargs)

            if current_user.role not in roles:
                abort(403)

            return view_func(*args, **kwargs)

        return wrapper

    return decorator


def property_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))

        if current_user.role == "superadmin":
            return view_func(*args, **kwargs)

        if current_user.property_id is None:
            flash("Please complete onboarding before accessing this section.", "warning")
            return redirect("/onboarding")

        return view_func(*args, **kwargs)

    return wrapper
