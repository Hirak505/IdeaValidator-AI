"""
test_auth.py — Comprehensive unit and integration test suite for
Authentication, Password Security, JWT, Refresh Token Rotation,
Rate Limiting, and Session Management.
"""

import asyncio
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from starlette.testclient import TestClient

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import auth
import auth_routes
import database
from main import app


class TestAuthentication(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Create an isolated temporary SQLite database for each test run
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()

        # Point database module to our isolated test DB
        database._DB_PATH = self.temp_db_path
        await database.init_db()

        self.client = TestClient(app)

        # Clear rate limit state between tests
        auth_routes._auth_request_records.clear()

    async def asyncTearDown(self):
        auth_routes._auth_request_records.clear()
        if os.path.exists(self.temp_db_path):
            try:
                os.remove(self.temp_db_path)
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # 1. Registration
    # -------------------------------------------------------------------------
    def test_register_success(self):
        """Registering a new account returns 201, user profile, access token, and HttpOnly cookie."""
        res = self.client.post(
            "/auth/register",
            json={
                "email": "founder@startup.io",
                "password": "StrongPassword123!",
                "display_name": "Ada Lovelace",
            },
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertIn("user", data)
        self.assertIn("access_token", data)
        self.assertEqual(data["token_type"], "bearer")

        user = data["user"]
        self.assertEqual(user["email"], "founder@startup.io")
        self.assertEqual(user["display_name"], "Ada Lovelace")
        self.assertIn("id", user)
        self.assertIn("created_at", user)
        # Password hash must NEVER be returned in response
        self.assertNotIn("password_hash", user)
        self.assertNotIn("password", user)

        # Refresh token must be in HttpOnly cookie
        self.assertIn("iv_refresh_token", res.cookies)

    def test_register_duplicate_email_returns_409(self):
        """Registering with an already-registered email returns 409 Conflict."""
        # First registration
        self.client.post(
            "/auth/register",
            json={"email": "alice@venture.co", "password": "Password123!"},
        )
        # Second registration with same email (case-insensitive)
        res = self.client.post(
            "/auth/register",
            json={"email": "ALICE@venture.co", "password": "AnotherPassword456!"},
        )
        self.assertEqual(res.status_code, 409)
        self.assertIn("already exists", res.json()["detail"].lower())

    def test_register_invalid_email_returns_422(self):
        """Registering with an invalid email returns 422 Unprocessable Entity."""
        res = self.client.post(
            "/auth/register",
            json={"email": "not-an-email", "password": "ValidPassword123!"},
        )
        self.assertEqual(res.status_code, 422)

    def test_register_short_password_returns_422(self):
        """Passwords under 8 characters must be rejected with 422."""
        res = self.client.post(
            "/auth/register",
            json={"email": "short@startup.io", "password": "short"},
        )
        self.assertEqual(res.status_code, 422)

    # -------------------------------------------------------------------------
    # 2. Password Hashing Security
    # -------------------------------------------------------------------------
    async def test_password_hashing_security(self):
        """Passwords must be hashed with bcrypt (never plaintext, verifiable)."""
        raw_password = "SuperSecretPassword123!"
        hashed = auth.hash_password(raw_password)

        self.assertNotEqual(raw_password, hashed)
        self.assertTrue(hashed.startswith("$2b$") or hashed.startswith("$2a$"))
        self.assertTrue(auth.verify_password(raw_password, hashed))
        self.assertFalse(auth.verify_password("WrongPassword!", hashed))

    # -------------------------------------------------------------------------
    # 3. Login
    # -------------------------------------------------------------------------
    def test_login_success(self):
        """Login with valid credentials returns 200, access token, and sets refresh cookie."""
        # Setup user
        self.client.post(
            "/auth/register",
            json={"email": "bob@venture.co", "password": "CorrectPassword123!"},
        )

        # Login
        res = self.client.post(
            "/auth/login",
            json={"email": "bob@venture.co", "password": "CorrectPassword123!"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["user"]["email"], "bob@venture.co")
        self.assertIn("iv_refresh_token", res.cookies)

    def test_login_failure_wrong_password_returns_generic_401(self):
        """Wrong password returns 401 with generic error message."""
        self.client.post(
            "/auth/register",
            json={"email": "carol@venture.co", "password": "CorrectPassword123!"},
        )

        res = self.client.post(
            "/auth/login",
            json={"email": "carol@venture.co", "password": "WrongPassword999!"},
        )
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["detail"], "Invalid email or password.")

    def test_login_failure_nonexistent_email_returns_generic_401(self):
        """Non-existent email returns 401 with identical generic error message."""
        res = self.client.post(
            "/auth/login",
            json={"email": "ghost@doesnotexist.io", "password": "AnyPassword123!"},
        )
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["detail"], "Invalid email or password.")

    # -------------------------------------------------------------------------
    # 4. Protected Route: GET /auth/me
    # -------------------------------------------------------------------------
    def test_get_current_user_with_valid_token(self):
        """GET /auth/me returns current user info when valid bearer token is provided."""
        reg = self.client.post(
            "/auth/register",
            json={"email": "dan@startup.io", "password": "ValidPassword123!", "display_name": "Dan M"},
        )
        token = reg.json()["access_token"]

        res = self.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        user = res.json()
        self.assertEqual(user["email"], "dan@startup.io")
        self.assertEqual(user["display_name"], "Dan M")

    def test_get_current_user_unauthorized_cases(self):
        """GET /auth/me returns 401 for missing, garbage, or malformed tokens."""
        # Missing
        res_missing = self.client.get("/auth/me")
        self.assertEqual(res_missing.status_code, 401)

        # Garbage
        res_garbage = self.client.get("/auth/me", headers={"Authorization": "Bearer not.a.valid.jwt"})
        self.assertEqual(res_garbage.status_code, 401)

        # Malformed scheme
        res_malformed = self.client.get("/auth/me", headers={"Authorization": "Basic 12345"})
        self.assertEqual(res_malformed.status_code, 401)

    def test_expired_token_returns_401(self):
        """An expired access token returns 401."""
        # Manually create an already expired access token
        expired_token = auth.create_access_token(
            "test-user-id",
            "exp@test.io",
            expires_delta=auth.timedelta(seconds=-10),
        )
        res = self.client.get("/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        self.assertEqual(res.status_code, 401)

    # -------------------------------------------------------------------------
    # 5. Token Refresh & Rotation
    # -------------------------------------------------------------------------
    def test_refresh_token_rotation(self):
        """POST /auth/refresh with valid cookie returns a new access token and rotates cookie."""
        reg = self.client.post(
            "/auth/register",
            json={"email": "eve@security.io", "password": "EvePassword123!"},
        )
        initial_refresh_cookie = reg.cookies.get("iv_refresh_token")
        self.assertIsNotNone(initial_refresh_cookie)

        # Refresh tokens
        res_refresh = self.client.post(
            "/auth/refresh",
            cookies={"iv_refresh_token": initial_refresh_cookie},
        )
        self.assertEqual(res_refresh.status_code, 200)
        data = res_refresh.json()
        self.assertIn("access_token", data)

        # The response must issue a NEW rotated refresh token cookie
        new_refresh_cookie = res_refresh.cookies.get("iv_refresh_token")
        self.assertIsNotNone(new_refresh_cookie)
        self.assertNotEqual(initial_refresh_cookie, new_refresh_cookie)

        # Re-using the old refresh token must be rejected (revoked / rotated)
        res_reuse = self.client.post(
            "/auth/refresh",
            cookies={"iv_refresh_token": initial_refresh_cookie},
        )
        self.assertEqual(res_reuse.status_code, 401)

    def test_refresh_token_missing_cookie_returns_401(self):
        """POST /auth/refresh without cookie returns 401."""
        res = self.client.post("/auth/refresh")
        self.assertEqual(res.status_code, 401)

    # -------------------------------------------------------------------------
    # 6. Logout
    # -------------------------------------------------------------------------
    def test_logout_revokes_token_and_clears_cookie(self):
        """POST /auth/logout revokes refresh token and clears the cookie."""
        reg = self.client.post(
            "/auth/register",
            json={"email": "frank@logout.io", "password": "FrankPassword123!"},
        )
        cookie = reg.cookies.get("iv_refresh_token")

        res_logout = self.client.post("/auth/logout", cookies={"iv_refresh_token": cookie})
        self.assertEqual(res_logout.status_code, 200)
        self.assertEqual(res_logout.json()["status"], "logged_out")

        # Subsequent refresh with revoked cookie fails
        res_refresh = self.client.post("/auth/refresh", cookies={"iv_refresh_token": cookie})
        self.assertEqual(res_refresh.status_code, 401)

    # -------------------------------------------------------------------------
    # 7. Rate Limiting
    # -------------------------------------------------------------------------
    def test_auth_rate_limiting(self):
        """Exceeding auth rate limit (10 req/min) returns 429."""
        for _ in range(10):
            res = self.client.post(
                "/auth/login",
                json={"email": "ratelimit@test.io", "password": "WrongPassword1!"},
            )
            # Either 401 (failed auth)
            self.assertIn(res.status_code, [401, 429])

        # 11th request must trigger 429
        res_limit = self.client.post(
            "/auth/login",
            json={"email": "ratelimit@test.io", "password": "WrongPassword1!"},
        )
        self.assertEqual(res_limit.status_code, 429)

    # -------------------------------------------------------------------------
    # 8. Unauthenticated Public Pipeline Still Works
    # -------------------------------------------------------------------------
    def test_public_routes_remain_unauthenticated(self):
        """Public routes like /health and /evaluate remain accessible to visitors."""
        res_health = self.client.get("/health")
        self.assertEqual(res_health.status_code, 200)

        # POST /evaluate without credentials returns validation error (400 if no files), not 401!
        res_eval = self.client.post("/evaluate")
        self.assertNotEqual(res_eval.status_code, 401)
        self.assertEqual(res_eval.status_code, 400)


if __name__ == "__main__":
    unittest.main()
