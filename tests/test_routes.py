import json
import os
import unittest

from app import create_app
from app.extensions import db
from app.models.facility import Equipment, WorkOrder
from app.models.property import MallProperty
from app.models.tenant import Tenant
from app.models.user import User
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

    def test_facility_work_order_create_handles_missing_equipment_id(self):
        self.login_as("rajan@phoenixmall.com", "MallAdmin@123")

        user = User.query.filter_by(email="rajan@phoenixmall.com").first()
        self.assertIsNotNone(user)

        equipment = Equipment.query.filter_by(property_id=user.property_id).order_by(Equipment.id.asc()).first()
        self.assertIsNotNone(equipment)

        before_count = WorkOrder.query.count()

        response = self.client.post(
            "/facility/work-order/create",
            data={
                "title": "Test fallback work order",
                "description": "Test fallback work order description for missing equipment id.",
                "priority": "medium",
                "assigned_to_user_id": 0,
                "estimated_cost_inr": "0",
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        self.assertEqual(response.status_code, 200)

        payload = json.loads(response.data)
        self.assertTrue(payload["success"])
        self.assertEqual(WorkOrder.query.count(), before_count + 1)

        created = WorkOrder.query.order_by(WorkOrder.id.desc()).first()
        self.assertIsNotNone(created)
        self.assertEqual(created.equipment_id, equipment.id)

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


class TestOnboardingStep3(unittest.TestCase):
    def setUp(self):
        self.app = create_test_app()
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.app_context = self.app.app_context()
        self.app_context.push()

        db.drop_all()
        db.create_all()

        self.user = User(
            email="tenantflow@example.com",
            full_name="Tenant Flow Admin",
            role="mall_admin",
            is_verified=True,
            is_active=True,
        )
        self.user.set_password("TenantFlow123!")
        db.session.add(self.user)
        db.session.flush()

        self.property = MallProperty(
            owner_user_id=self.user.id,
            name="Tenant Flow Mall",
            location="123 Retail Avenue",
            city="Mumbai",
            country="India",
            total_area_sqft=250000,
            num_floors=4,
            num_tenants=0,
            onboarding_complete=False,
            data_source_config=json.dumps(
                {
                    "pos_system": "shopify",
                    "inventory_system": "none",
                    "crm_system": "none",
                    "sensor_source": "simulator",
                }
            ),
        )
        db.session.add(self.property)
        db.session.flush()

        self.user.property_id = self.property.id
        db.session.commit()

        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def login(self):
        response = self.client.post(
            "/auth/login",
            data={
                "email": self.user.email,
                "password": "TenantFlow123!",
                "remember_me": False,
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)

    def test_step3_allows_empty_tenant_submission_and_moves_forward(self):
        self.login()

        response = self.client.post(
            "/onboarding/step/3",
            data={"tenants_json": "[]"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request.path, "/onboarding/step/4")
        self.assertEqual(Tenant.query.filter_by(property_id=self.property.id).count(), 0)

        with self.client.session_transaction() as session_data:
            self.assertTrue(session_data.get("tenant_setup_skipped"))

    def test_step3_saves_complete_tenants_and_ignores_partial_rows(self):
        self.login()

        response = self.client.post(
            "/onboarding/step/3",
            data={
                "tenants_json": json.dumps(
                    [
                        {
                            "name": "Zara Fashion",
                            "category": "Fashion",
                            "zone": "A",
                            "floor": "1",
                            "unit_number": "A-101",
                            "contact_email": "store@example.com",
                        },
                        {
                            "name": "Incomplete Store",
                            "category": "",
                            "zone": "B",
                            "floor": "",
                            "unit_number": "B-202",
                            "contact_email": "bad@example.com",
                        },
                    ]
                )
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request.path, "/onboarding/step/4")

        tenants = Tenant.query.filter_by(property_id=self.property.id).all()
        self.assertEqual(len(tenants), 1)
        self.assertEqual(tenants[0].name, "Zara Fashion")
        self.assertEqual(tenants[0].unit_number, "A-101")
        self.assertEqual(self.property.num_tenants, 1)

        with self.client.session_transaction() as session_data:
            self.assertFalse(session_data.get("tenant_setup_skipped"))


if __name__ == "__main__":
    unittest.main()
