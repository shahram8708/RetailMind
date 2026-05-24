import json
import unittest

from app import create_app
from app.extensions import db
from app.models.notification import PushSubscription
from app.models.user import User


class PwaTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update({
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()
            user = User(
                email="test@example.com",
                full_name="Test User",
                role="mall_admin",
                is_verified=True,
                is_active=True,
            )
            user.set_password("Password123!")
            db.session.add(user)
            db.session.commit()
            self.user_id = user.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def login(self):
        with self.client.session_transaction() as session:
            session["_user_id"] = str(self.user_id)
            session["_fresh"] = True

    def test_health_check(self):
        response = self.client.get("/api/health-check")
        self.assertEqual(response.status_code, 204)

    def test_manifest(self):
        response = self.client.get("/manifest.json")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data.decode("utf-8"))
        self.assertEqual(data.get("name"), "RetailMind")
        self.assertEqual(data.get("short_name"), "RetailMind")
        self.assertEqual(data.get("start_url"), "/dashboard?source=pwa")
        self.assertIn("icons", data)
        self.assertTrue(any(icon.get("sizes") == "192x192" for icon in data.get("icons", [])))

    def test_push_subscription_model(self):
        with self.app.app_context():
            subscription = PushSubscription(
                user_id=self.user_id,
                endpoint="https://example.com/endpoint",
                p256dh="p256dh",
                auth="auth",
                user_agent="test-agent",
                is_active=True,
            )
            db.session.add(subscription)
            db.session.commit()

            stored = PushSubscription.query.filter_by(user_id=self.user_id).first()
            self.assertIsNotNone(stored)
            self.assertEqual(stored.endpoint, "https://example.com/endpoint")

    def test_sync_queue_endpoint(self):
        self.login()
        response = self.client.post(
            "/api/sync/queue",
            json={"items": []},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload.get("success"))


if __name__ == "__main__":
    unittest.main()
