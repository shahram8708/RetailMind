import os
import sys

# Ensure the local package is imported before any installed "app" package.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# If another package named "app" was loaded earlier, drop it so local imports win.
existing_app = sys.modules.get("app")
if existing_app is not None:
    existing_path = getattr(existing_app, "__file__", "") or ""
    if not existing_path.startswith(PROJECT_ROOT):
        del sys.modules["app"]

from app import create_app


app = create_app()

# For local direct execution only. Production WSGI servers handle process management.
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, port=5000)
