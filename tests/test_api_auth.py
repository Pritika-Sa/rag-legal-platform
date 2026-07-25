"""Tests for api/routers/auth.py — the FastAPI adapter's session/auth
transport layer. Exercises the same behaviors verified manually during
Phase 1 (see the migration plan's regression report): every assertion here
checks a status code or message that database/auth.py already owned before
the adapter existed; nothing here tests new business logic, only that the
adapter wires the existing functions through HTTP correctly.

Run with:  python -m unittest discover -s tests
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from api.main import app
from database import auth
from database.connection import get_db


class TestAuthRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.email = f"pytest_{uuid.uuid4().hex[:12]}@example.com"
        self.password = "testpass123"

    def tearDown(self):
        get_db().users.delete_one({"email": self.email})

    def test_signup_then_me(self):
        resp = self.client.post(
            "/api/auth/signup",
            json={"name": "Pytest User", "email": self.email, "password": self.password},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["email"], self.email)
        self.assertIn("access_token", resp.cookies)

        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], self.email)

    def test_duplicate_signup_rejected(self):
        self.client.post(
            "/api/auth/signup",
            json={"name": "Pytest User", "email": self.email, "password": self.password},
        )
        resp = self.client.post(
            "/api/auth/signup",
            json={"name": "Someone Else", "email": self.email, "password": "otherpass123"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_login_wrong_password_rejected(self):
        self.client.post(
            "/api/auth/signup",
            json={"name": "Pytest User", "email": self.email, "password": self.password},
        )
        resp = self.client.post(
            "/api/auth/login", json={"email": self.email, "password": "wrongpassword"}
        )
        self.assertEqual(resp.status_code, 401)

    def test_me_without_session_rejected(self):
        anon_client = TestClient(app)
        resp = anon_client.get("/api/auth/me")
        self.assertEqual(resp.status_code, 401)

    def test_logout_clears_session(self):
        self.client.post(
            "/api/auth/signup",
            json={"name": "Pytest User", "email": self.email, "password": self.password},
        )
        logout_resp = self.client.post("/api/auth/logout")
        self.assertEqual(logout_resp.status_code, 204)

        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 401)

    def test_forgot_password_same_message_regardless_of_account_existence(self):
        self.client.post(
            "/api/auth/signup",
            json={"name": "Pytest User", "email": self.email, "password": self.password},
        )
        existing = self.client.post("/api/auth/forgot-password", json={"email": self.email})
        nonexistent = self.client.post(
            "/api/auth/forgot-password", json={"email": f"nobody_{uuid.uuid4().hex}@example.com"}
        )
        self.assertEqual(existing.status_code, 200)
        self.assertEqual(existing.json()["message"], nonexistent.json()["message"])

    def test_reset_password_full_cycle(self):
        self.client.post(
            "/api/auth/signup",
            json={"name": "Pytest User", "email": self.email, "password": self.password},
        )
        # Obtains the raw token directly from the (unmodified) backend
        # function, the same way the adapter's forgot-password route does —
        # bypasses actually sending an email for the test.
        token = auth.request_password_reset(self.email)
        self.assertIsNotNone(token)

        reset_resp = self.client.post(
            "/api/auth/reset-password", json={"token": token, "newPassword": "newpass456"}
        )
        self.assertEqual(reset_resp.status_code, 200)

        login_resp = self.client.post(
            "/api/auth/login", json={"email": self.email, "password": "newpass456"}
        )
        self.assertEqual(login_resp.status_code, 200)

        # Tokens are single-use — reusing it must fail.
        reuse_resp = self.client.post(
            "/api/auth/reset-password", json={"token": token, "newPassword": "anotherpass789"}
        )
        self.assertEqual(reuse_resp.status_code, 400)

    def test_reset_password_invalid_token_rejected(self):
        resp = self.client.post(
            "/api/auth/reset-password", json={"token": "not-a-real-token", "newPassword": "whatever123"}
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
