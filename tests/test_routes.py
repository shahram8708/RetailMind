import json
import os
import unittest

from app import create_app
from app.extensions import db
from app.seed import seed_database_if_empty


def create_test_app():
    os.environ["FLASK_ENV"] = "testing"
    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    return app


class TestPublicRoutes(unittest.TestCase):
    def setUp(self):
        self.app = create_test_app()
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.app_context = self.app.app_context()
        self.app_context.push()

        db.drop_all()
        db.create_all()

        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_landing_page_returns_200(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_features_page_returns_200(self):
        response = self.client.get("/features")
        self.assertEqual(response.status_code, 200)

    def test_pricing_page_returns_200(self):
        response = self.client.get("/pricing")
        self.assertEqual(response.status_code, 200)

    def test_about_page_returns_200(self):
        response = self.client.get("/about")
        self.assertEqual(response.status_code, 200)

    def test_demo_get_returns_200(self):
        response = self.client.get("/demo")
        self.assertEqual(response.status_code, 200)

    def test_login_page_returns_200(self):
        response = self.client.get("/auth/login")
        self.assertEqual(response.status_code, 200)

    def test_register_page_returns_200(self):
        response = self.client.get("/auth/register")
        self.assertEqual(response.status_code, 200)


class TestAuthenticatedRoutes(unittest.TestCase):
    def setUp(self):
        self.app = create_test_app()
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.app_context = self.app.app_context()
        self.app_context.push()

        db.drop_all()
        db.create_all()
        seed_database_if_empty()

        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def login_as(self, email, password):
        return self.client.post(
            "/auth/login",
            data={"email": email, "password": password, "remember_me": False},
            follow_redirects=True,
        )

    def test_login_with_valid_credentials(self):
        response = self.login_as("rajan@phoenixmall.com", "MallAdmin@123")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(b"Dashboard" in response.data or b"Inventory" in response.data)

    def test_login_with_invalid_credentials(self):
        response = self.login_as("rajan@phoenixmall.com", "wrongpassword")
        self.assertIn(b"Invalid email or password", response.data)

    def test_dashboard_requires_login(self):
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)

    def test_dashboard_accessible_when_logged_in(self):
        self.login_as("rajan@phoenixmall.com", "MallAdmin@123")
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)

    def test_inventory_accessible_when_logged_in(self):
        self.login_as("rajan@phoenixmall.com", "MallAdmin@123")
        response = self.client.get("/inventory")
        self.assertEqual(response.status_code, 200)

    def test_campaigns_accessible_when_logged_in(self):
        self.login_as("rajan@phoenixmall.com", "MallAdmin@123")
        response = self.client.get("/campaigns")
        self.assertEqual(response.status_code, 200)

    def test_facility_accessible_when_logged_in(self):
        self.login_as("rajan@phoenixmall.com", "MallAdmin@123")
        response = self.client.get("/facility")
        self.assertEqual(response.status_code, 200)

    def test_analytics_accessible_when_logged_in(self):
        self.login_as("rajan@phoenixmall.com", "MallAdmin@123")
        response = self.client.get("/analytics")
        self.assertEqual(response.status_code, 200)

    def test_agent_logs_accessible_when_logged_in(self):
        self.login_as("rajan@phoenixmall.com", "MallAdmin@123")
        response = self.client.get("/agent/logs")
        self.assertEqual(response.status_code, 200)

    def test_notifications_accessible_when_logged_in(self):
        self.login_as("rajan@phoenixmall.com", "MallAdmin@123")
        response = self.client.get("/notifications")
        self.assertEqual(response.status_code, 200)

    def test_settings_accessible_when_logged_in(self):
        self.login_as("rajan@phoenixmall.com", "MallAdmin@123")
        response = self.client.get("/settings")
        self.assertEqual(response.status_code, 200)

    def test_shopper_accessible_without_login(self):
        response = self.client.get("/shopper")
        self.assertEqual(response.status_code, 200)

    def test_superadmin_requires_superadmin_role(self):
        self.login_as("rajan@phoenixmall.com", "MallAdmin@123")
        response = self.client.get("/superadmin")
        self.assertEqual(response.status_code, 403)

    def test_superadmin_accessible_with_superadmin_role(self):
        self.login_as("superadmin@retailmind.ai", "SuperAdmin@123")
        response = self.client.get("/superadmin")
        self.assertEqual(response.status_code, 200)

    def test_api_agent_status_returns_json(self):
        self.login_as("rajan@phoenixmall.com", "MallAdmin@123")
        response = self.client.get("/api/agent/status")
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertIn("data", data)

    def test_api_notifications_unread_returns_json(self):
        self.login_as("rajan@phoenixmall.com", "MallAdmin@123")
        response = self.client.get("/api/notifications/unread")

        data = json.loads(response.data)
        self.assertIn("count", data)

    def test_logout(self):
        self.login_as("rajan@phoenixmall.com", "MallAdmin@123")
        response = self.client.post("/auth/logout", follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        subsequent_response = self.client.get("/dashboard")
        self.assertEqual(subsequent_response.status_code, 302)

    def test_404_returns_custom_page(self):
        response = self.client.get("/this-route-does-not-exist-at-all")
        self.assertEqual(response.status_code, 404)
        self.assertTrue(b"404" in response.data or b"Not Found" in response.data)


if __name__ == "__main__":
    unittest.main()
