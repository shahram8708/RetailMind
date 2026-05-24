import os
import unittest

from app import create_app
from app.extensions import db
from app.models.agent import AgentAction
from app.models.inventory import InventoryItem
from app.models.property import MallProperty
from app.models.tenant import Tenant
from app.models.user import User


def create_test_app():
    os.environ["FLASK_ENV"] = "testing"
    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    return app


class TestUserModel(unittest.TestCase):
    def setUp(self):
        self.app = create_test_app()
        self.app_context = self.app.app_context()
        self.app_context.push()

        db.drop_all()
        db.create_all()

        self.property = MallProperty(
            name="Test Mall",
            city="Mumbai",
            country="India",
            onboarding_complete=True,
            subscription_tier="starter",
        )
        db.session.add(self.property)
        db.session.commit()

        self.user = User(
            email="test.user@retailmind.ai",
            full_name="Test User",
            role="mall_admin",
            property_id=self.property.id,
            is_verified=True,
            is_active=True,
        )
        self.user.set_password("TestPass123!")
        db.session.add(self.user)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_password_hashing(self):
        self.assertTrue(self.user.check_password("TestPass123!"))
        self.assertFalse(self.user.check_password("wrong"))

    def test_password_hash_not_plaintext(self):
        self.assertNotEqual(self.user.password_hash, "TestPass123!")

    def test_get_dashboard_route(self):
        expected_routes = {
            "superadmin": "/superadmin",
            "mall_admin": "/dashboard",
            "store_manager": "/dashboard",
            "marketing_manager": "/dashboard",
            "facility_manager": "/dashboard",
            "shopper": "/shopper",
        }

        for role, expected in expected_routes.items():
            role_user = User(
                email=f"{role}.user@retailmind.ai",
                full_name=f"{role.title()} User",
                role=role,
                property_id=self.property.id,
                is_verified=True,
                is_active=True,
            )
            role_user.set_password("RolePass123!")
            db.session.add(role_user)
            db.session.flush()
            self.assertEqual(role_user.get_dashboard_route(), expected)

        db.session.rollback()

    def test_is_superadmin(self):
        superadmin_user = User(
            email="superadmin.model@retailmind.ai",
            full_name="Super Admin",
            role="superadmin",
            is_verified=True,
            is_active=True,
        )
        superadmin_user.set_password("SuperAdmin@123")

        mall_admin_user = User(
            email="malladmin.model@retailmind.ai",
            full_name="Mall Admin",
            role="mall_admin",
            property_id=self.property.id,
            is_verified=True,
            is_active=True,
        )
        mall_admin_user.set_password("MallAdmin@123")

        self.assertTrue(superadmin_user.is_superadmin())
        self.assertFalse(mall_admin_user.is_superadmin())


class TestInventoryItemModel(unittest.TestCase):
    def setUp(self):
        self.app = create_test_app()
        self.app_context = self.app.app_context()
        self.app_context.push()

        db.drop_all()
        db.create_all()

        self.property = MallProperty(
            name="Inventory Test Mall",
            city="Pune",
            country="India",
            onboarding_complete=True,
            subscription_tier="professional",
        )
        db.session.add(self.property)
        db.session.flush()

        self.tenant = Tenant(
            property_id=self.property.id,
            name="Inventory Tenant",
            category="Fashion",
            zone="A",
            floor=1,
            unit_number="A-101",
            is_active=True,
        )
        db.session.add(self.tenant)
        db.session.flush()

        self.inventory_item = InventoryItem(
            sku_id="TEST-SKU-001",
            tenant_id=self.tenant.id,
            property_id=self.property.id,
            product_name="Test Product",
            category="Fashion",
            stock_level=50,
            reorder_threshold=10,
            unit_price=999.0,
            cost_price=500.0,
        )
        db.session.add(self.inventory_item)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_srs_score_default(self):
        self.assertEqual(float(self.inventory_item.srs_score or 0.0), 0.0)

    def test_model_relationships(self):
        self.assertEqual(self.inventory_item.tenant.id, self.tenant.id)
        self.assertEqual(self.inventory_item.tenant.name, self.tenant.name)


class TestAgentActionModel(unittest.TestCase):
    def setUp(self):
        self.app = create_test_app()
        self.app_context = self.app.app_context()
        self.app_context.push()

        db.drop_all()
        db.create_all()

        self.property = MallProperty(
            name="Agent Action Mall",
            city="Delhi",
            country="India",
            onboarding_complete=True,
            subscription_tier="starter",
        )
        db.session.add(self.property)
        db.session.flush()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_status_default(self):
        action = AgentAction(
            property_id=self.property.id,
            mission_type="inventory",
            action_type="restock_request",
            description="Low stock alert",
            entity_id="TEST-SKU-100",
            score=0.8,
        )
        db.session.add(action)
        db.session.commit()

        self.assertEqual(action.status, "pending")

    def test_property_relationship(self):
        action = AgentAction(
            property_id=self.property.id,
            mission_type="campaign",
            action_type="campaign_opportunity",
            description="Campaign opportunity",
            entity_id="TENANT-10",
            score=0.6,
        )
        db.session.add(action)
        db.session.commit()

        self.assertEqual(action.property_id, self.property.id)


if __name__ == "__main__":
    unittest.main()
