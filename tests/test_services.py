import os
import unittest
from datetime import datetime, timedelta

from app import create_app
from app.extensions import db
from app.models.facility import Equipment, SensorReading
from app.models.inventory import FootTraffic, InventoryItem, SalesVelocity
from app.models.notification import Notification
from app.models.property import MallProperty
from app.models.tenant import Tenant
from app.models.user import User
from app.services.facility_service import compute_fps_for_equipment, get_fps_label
from app.services.inventory_service import compute_srs_for_sku, get_srs_label
from app.services.notification_service import create_notification, get_unread_count, mark_all_read, mark_as_read


def create_test_app():
    os.environ["FLASK_ENV"] = "testing"
    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    return app


class TestInventoryService(unittest.TestCase):
    def setUp(self):
        self.app = create_test_app()
        self.app_context = self.app.app_context()
        self.app_context.push()

        db.drop_all()
        db.create_all()

        self.property = MallProperty(
            name="Service Mall",
            city="Bengaluru",
            country="India",
            onboarding_complete=True,
            subscription_tier="professional",
        )
        db.session.add(self.property)
        db.session.flush()

        self.tenant = Tenant(
            property_id=self.property.id,
            name="Service Tenant",
            category="Sportswear",
            zone="B",
            floor=2,
            unit_number="B-201",
            is_active=True,
        )
        db.session.add(self.tenant)
        db.session.flush()

        self.base_item = InventoryItem(
            sku_id="SVC-SKU-001",
            tenant_id=self.tenant.id,
            property_id=self.property.id,
            product_name="Service Shoe",
            category="Sportswear",
            stock_level=30,
            reorder_threshold=12,
            unit_price=4500,
            cost_price=2100,
            supplier_lead_time_hours=24,
        )
        db.session.add(self.base_item)

        now = datetime.utcnow()
        for idx in range(8):
            db.session.add(
                FootTraffic(
                    property_id=self.property.id,
                    zone_id="B",
                    floor=2,
                    count=500 + (idx * 10),
                    timestamp=now - timedelta(minutes=(8 - idx) * 10),
                    data_source="simulator",
                )
            )

        db.session.add(
            SalesVelocity(
                sku_id="SVC-SKU-001",
                tenant_id=self.tenant.id,
                property_id=self.property.id,
                units_sold=6,
                sale_timestamp=now - timedelta(minutes=50),
                zone_id="B",
            )
        )
        db.session.add(
            SalesVelocity(
                sku_id="SVC-SKU-001",
                tenant_id=self.tenant.id,
                property_id=self.property.id,
                units_sold=5,
                sale_timestamp=now - timedelta(minutes=20),
                zone_id="B",
            )
        )

        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_compute_srs_clamped_between_0_and_1(self):
        result = compute_srs_for_sku("SVC-SKU-001", self.property.id, self.tenant.id)
        self.assertGreaterEqual(result["srs_score"], 0.0)
        self.assertLessEqual(result["srs_score"], 1.0)

    def test_compute_srs_returns_dict_with_required_keys(self):
        result = compute_srs_for_sku("SVC-SKU-001", self.property.id, self.tenant.id)
        required = {"sku_id", "srs_score", "ltr", "tpf", "hw"}
        self.assertTrue(required.issubset(set(result.keys())))

    def test_srs_low_stock_high_score(self):
        low_item = InventoryItem(
            sku_id="SVC-SKU-LOW",
            tenant_id=self.tenant.id,
            property_id=self.property.id,
            product_name="Low Stock Product",
            category="Sportswear",
            stock_level=2,
            reorder_threshold=20,
            unit_price=3500,
            cost_price=1400,
            supplier_lead_time_hours=24,
        )
        db.session.add(low_item)
        db.session.flush()

        now = datetime.utcnow()
        db.session.add(
            SalesVelocity(
                sku_id="SVC-SKU-LOW",
                tenant_id=self.tenant.id,
                property_id=self.property.id,
                units_sold=5,
                sale_timestamp=now - timedelta(minutes=30),
                zone_id="B",
            )
        )
        db.session.add(
            SalesVelocity(
                sku_id="SVC-SKU-LOW",
                tenant_id=self.tenant.id,
                property_id=self.property.id,
                units_sold=4,
                sale_timestamp=now - timedelta(minutes=80),
                zone_id="B",
            )
        )
        db.session.commit()

        result = compute_srs_for_sku("SVC-SKU-LOW", self.property.id, self.tenant.id)
        self.assertGreater(result["srs_score"], 0.5)

    def test_srs_high_stock_low_score(self):
        high_item = InventoryItem(
            sku_id="SVC-SKU-HIGH",
            tenant_id=self.tenant.id,
            property_id=self.property.id,
            product_name="High Stock Product",
            category="Sportswear",
            stock_level=200,
            reorder_threshold=10,
            unit_price=2500,
            cost_price=900,
            supplier_lead_time_hours=24,
        )
        db.session.add(high_item)
        db.session.commit()

        result = compute_srs_for_sku("SVC-SKU-HIGH", self.property.id, self.tenant.id)
        self.assertLess(result["srs_score"], 0.5)

    def test_get_srs_label(self):
        self.assertEqual(get_srs_label(0.9), ("Critical", "srs-critical"))
        self.assertEqual(get_srs_label(0.8), ("High Risk", "srs-high"))
        self.assertEqual(get_srs_label(0.6), ("Medium Risk", "srs-medium"))
        self.assertEqual(get_srs_label(0.3), ("Low Risk", "srs-low"))


class TestFacilityService(unittest.TestCase):
    def setUp(self):
        self.app = create_test_app()
        self.app_context = self.app.app_context()
        self.app_context.push()

        db.drop_all()
        db.create_all()

        self.property = MallProperty(
            name="Facility Mall",
            city="Hyderabad",
            country="India",
            onboarding_complete=True,
            subscription_tier="professional",
        )
        db.session.add(self.property)
        db.session.flush()

        self.equipment = Equipment(
            property_id=self.property.id,
            equipment_name="Escalator F-01",
            equipment_type="escalator",
            zone="A",
            floor=1,
            expected_lifetime_years=20,
            is_active=True,
        )
        db.session.add(self.equipment)
        db.session.flush()

        now = datetime.utcnow()
        for idx in range(60):
            db.session.add(
                SensorReading(
                    equipment_id=self.equipment.id,
                    property_id=self.property.id,
                    metric_name="vibration_hz",
                    metric_value=50.0 + ((idx % 5) * 0.6),
                    timestamp=now - timedelta(minutes=idx * 10),
                    anomaly_flag=False,
                )
            )

        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_compute_fps_returns_valid_score(self):
        result = compute_fps_for_equipment(self.equipment.id, self.property.id)
        self.assertGreaterEqual(result["fps_score"], 0.0)
        self.assertLessEqual(result["fps_score"], 1.0)

    def test_fps_insufficient_data(self):
        low_equipment = Equipment(
            property_id=self.property.id,
            equipment_name="HVAC F-02",
            equipment_type="hvac",
            zone="B",
            floor=2,
            expected_lifetime_years=15,
            is_active=True,
        )
        db.session.add(low_equipment)
        db.session.flush()

        now = datetime.utcnow()
        for idx in range(5):
            db.session.add(
                SensorReading(
                    equipment_id=low_equipment.id,
                    property_id=self.property.id,
                    metric_name="temperature_celsius",
                    metric_value=23.0 + idx,
                    timestamp=now - timedelta(minutes=idx * 5),
                )
            )
        db.session.commit()

        result = compute_fps_for_equipment(low_equipment.id, self.property.id)
        self.assertTrue(result.get("insufficient_data") is True or result["fps_score"] == 0.0)

    def test_get_fps_label(self):
        self.assertEqual(get_fps_label(0.9).get("label"), "Critical")
        self.assertEqual(get_fps_label(0.2).get("label"), "Healthy")


class TestNotificationService(unittest.TestCase):
    def setUp(self):
        self.app = create_test_app()
        self.app_context = self.app.app_context()
        self.app_context.push()

        db.drop_all()
        db.create_all()

        self.property = MallProperty(
            name="Notification Mall",
            city="Chennai",
            country="India",
            onboarding_complete=True,
            subscription_tier="starter",
        )
        db.session.add(self.property)
        db.session.flush()

        self.user = User(
            email="notify.user@retailmind.ai",
            full_name="Notify User",
            role="mall_admin",
            property_id=self.property.id,
            is_verified=True,
            is_active=True,
        )
        self.user.set_password("NotifyPass123!")

        self.user2 = User(
            email="notify.user2@retailmind.ai",
            full_name="Notify User Two",
            role="store_manager",
            property_id=self.property.id,
            is_verified=True,
            is_active=True,
        )
        self.user2.set_password("NotifyPass123!")

        db.session.add(self.user)
        db.session.add(self.user2)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_create_notification(self):
        result = create_notification(self.user.id, "Test Title", "Test message", "system", "info")
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.id)
        self.assertFalse(result.is_read)

    def test_get_unread_count(self):
        create_notification(self.user.id, "N1", "Msg", "system", "info")
        create_notification(self.user.id, "N2", "Msg", "system", "info")
        create_notification(self.user.id, "N3", "Msg", "system", "info")

        count = get_unread_count(self.user.id)
        self.assertEqual(count, 3)

    def test_mark_as_read(self):
        notif = create_notification(self.user.id, "Mark", "Read", "system", "info")
        result = mark_as_read(notif.id, self.user.id)

        self.assertTrue(result)
        self.assertEqual(get_unread_count(self.user.id), 0)

    def test_mark_all_read(self):
        for idx in range(5):
            create_notification(self.user.id, f"N{idx}", "Msg", "system", "info")

        mark_all_read(self.user.id)
        self.assertEqual(get_unread_count(self.user.id), 0)

    def test_cannot_mark_other_users_notification(self):
        notif = create_notification(self.user2.id, "Other", "User", "system", "info")
        result = mark_as_read(notif.id, self.user.id)

        self.assertFalse(result)
        notif_refreshed = Notification.query.get(notif.id)
        self.assertFalse(notif_refreshed.is_read)


if __name__ == "__main__":
    unittest.main()
