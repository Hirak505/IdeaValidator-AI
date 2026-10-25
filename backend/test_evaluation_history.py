"""
test_evaluation_history.py — Tests for Saved Evaluations, History,
Ownership Isolation, and Per-User Limits.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from starlette.testclient import TestClient

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import auth
import auth_routes
import database
import evaluation_routes
from main import app


class TestEvaluationHistory(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Create an isolated temporary SQLite database for each test
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()

        database._DB_PATH = self.temp_db_path
        await database.init_db()

        self.client = TestClient(app)
        auth_routes._auth_request_records.clear()

        # Register User A
        res_a = self.client.post(
            "/auth/register",
            json={"email": "usera@venture.co", "password": "UserAPassword123!", "display_name": "User A"},
        )
        self.user_a_token = res_a.json()["access_token"]
        self.user_a_id = res_a.json()["user"]["id"]

        # Register User B
        res_b = self.client.post(
            "/auth/register",
            json={"email": "userb@venture.co", "password": "UserBPassword123!", "display_name": "User B"},
        )
        self.user_b_token = res_b.json()["access_token"]
        self.user_b_id = res_b.json()["user"]["id"]

        # Sample evaluation result payload
        self.sample_results = {
            "chief_judge": {
                "overall_score": 8.5,
                "confidence": 92,
                "evidence_quality": 88,
                "final_verdict": "Promising venture thesis.",
                "top_strengths": ["High technical defensibility"],
                "top_improvements": ["Go-to-market execution risks"],
            },
            "innovation": {"score": 8.0, "comments": "Novel architecture."},
            "technical": {"score": 9.0, "comments": "Scalable design."},
            "business": {"score": 7.5, "comments": "Large TAM."},
            "presentation": {"score": 8.5, "comments": "Concise pitch."},
        }

    async def asyncTearDown(self):
        auth_routes._auth_request_records.clear()
        if os.path.exists(self.temp_db_path):
            try:
                os.remove(self.temp_db_path)
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # 1. Save Evaluation
    # -------------------------------------------------------------------------
    def test_save_evaluation_authenticated_success(self):
        """User A can save an evaluation result and receive 201 with record id."""
        res = self.client.post(
            "/evaluations/save",
            headers={"Authorization": f"Bearer {self.user_a_token}"},
            json={
                "title": "Quantum Compute Seed Pitch",
                "attack_mode": False,
                "results": self.sample_results,
            },
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertIn("id", data)
        self.assertEqual(data["title"], "Quantum Compute Seed Pitch")
        self.assertFalse(data["attack_mode"])
        self.assertIn("created_at", data)

    def test_save_evaluation_unauthenticated_returns_401(self):
        """Saving an evaluation without authentication returns 401."""
        res = self.client.post(
            "/evaluations/save",
            json={
                "title": "Unauthenticated Save",
                "attack_mode": False,
                "results": self.sample_results,
            },
        )
        self.assertEqual(res.status_code, 401)

    def test_save_evaluation_empty_results_returns_422(self):
        """Saving an evaluation with empty results dictionary returns 422."""
        res = self.client.post(
            "/evaluations/save",
            headers={"Authorization": f"Bearer {self.user_a_token}"},
            json={
                "title": "Empty Results",
                "results": {},
            },
        )
        self.assertEqual(res.status_code, 422)

    # -------------------------------------------------------------------------
    # 2. List Evaluations
    # -------------------------------------------------------------------------
    def test_list_evaluations_returns_only_owners_records(self):
        """Listing evaluations returns only records belonging to the authenticated user."""
        # User A saves 2 evaluations
        self.client.post(
            "/evaluations/save",
            headers={"Authorization": f"Bearer {self.user_a_token}"},
            json={"title": "Eval A1", "results": self.sample_results},
        )
        self.client.post(
            "/evaluations/save",
            headers={"Authorization": f"Bearer {self.user_a_token}"},
            json={"title": "Eval A2", "results": self.sample_results},
        )

        # User B saves 1 evaluation
        self.client.post(
            "/evaluations/save",
            headers={"Authorization": f"Bearer {self.user_b_token}"},
            json={"title": "Eval B1", "results": self.sample_results},
        )

        # User A lists evaluations -> exactly 2
        res_a = self.client.get(
            "/evaluations",
            headers={"Authorization": f"Bearer {self.user_a_token}"},
        )
        self.assertEqual(res_a.status_code, 200)
        data_a = res_a.json()
        self.assertEqual(data_a["total"], 2)
        titles_a = [e["title"] for e in data_a["evaluations"]]
        self.assertIn("Eval A1", titles_a)
        self.assertIn("Eval A2", titles_a)
        self.assertNotIn("Eval B1", titles_a)

        # User B lists evaluations -> exactly 1
        res_b = self.client.get(
            "/evaluations",
            headers={"Authorization": f"Bearer {self.user_b_token}"},
        )
        self.assertEqual(res_b.status_code, 200)
        data_b = res_b.json()
        self.assertEqual(data_b["total"], 1)
        self.assertEqual(data_b["evaluations"][0]["title"], "Eval B1")

    # -------------------------------------------------------------------------
    # 3. Ownership Isolation: Detail View (GET /evaluations/{id})
    # -------------------------------------------------------------------------
    def test_get_evaluation_detail_owner_success(self):
        """Owner can view full evaluation results."""
        save_res = self.client.post(
            "/evaluations/save",
            headers={"Authorization": f"Bearer {self.user_a_token}"},
            json={"title": "Confidential A", "results": self.sample_results},
        )
        eval_id = save_res.json()["id"]

        detail_res = self.client.get(
            f"/evaluations/{eval_id}",
            headers={"Authorization": f"Bearer {self.user_a_token}"},
        )
        self.assertEqual(detail_res.status_code, 200)
        data = detail_res.json()
        self.assertEqual(data["title"], "Confidential A")
        self.assertEqual(data["results"]["chief_judge"]["overall_score"], 8.5)

    def test_get_evaluation_cross_user_isolation_returns_404(self):
        """User B attempting to view User A's evaluation receives 404 (no info leakage)."""
        save_res = self.client.post(
            "/evaluations/save",
            headers={"Authorization": f"Bearer {self.user_a_token}"},
            json={"title": "User A Proprietary Deck", "results": self.sample_results},
        )
        eval_id = save_res.json()["id"]

        # User B tries to view User A's evaluation
        res = self.client.get(
            f"/evaluations/{eval_id}",
            headers={"Authorization": f"Bearer {self.user_b_token}"},
        )
        # Must return 404 NOT 403, preventing resource enumeration
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["detail"], "Evaluation not found.")

    # -------------------------------------------------------------------------
    # 4. Ownership Isolation: Deletion (DELETE /evaluations/{id})
    # -------------------------------------------------------------------------
    def test_delete_evaluation_owner_success(self):
        """Owner can delete their own evaluation."""
        save_res = self.client.post(
            "/evaluations/save",
            headers={"Authorization": f"Bearer {self.user_a_token}"},
            json={"title": "To Delete", "results": self.sample_results},
        )
        eval_id = save_res.json()["id"]

        del_res = self.client.delete(
            f"/evaluations/{eval_id}",
            headers={"Authorization": f"Bearer {self.user_a_token}"},
        )
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json()["status"], "deleted")

        # Subsequent fetch returns 404
        get_res = self.client.get(
            f"/evaluations/{eval_id}",
            headers={"Authorization": f"Bearer {self.user_a_token}"},
        )
        self.assertEqual(get_res.status_code, 404)

    def test_delete_evaluation_cross_user_isolation_returns_404(self):
        """User B cannot delete User A's evaluation (returns 404, record remains intact)."""
        save_res = self.client.post(
            "/evaluations/save",
            headers={"Authorization": f"Bearer {self.user_a_token}"},
            json={"title": "Undeletable by B", "results": self.sample_results},
        )
        eval_id = save_res.json()["id"]

        # User B attempts to delete User A's evaluation
        del_res = self.client.delete(
            f"/evaluations/{eval_id}",
            headers={"Authorization": f"Bearer {self.user_b_token}"},
        )
        self.assertEqual(del_res.status_code, 404)

        # Record must STILL exist for User A
        verify_res = self.client.get(
            f"/evaluations/{eval_id}",
            headers={"Authorization": f"Bearer {self.user_a_token}"},
        )
        self.assertEqual(verify_res.status_code, 200)
        self.assertEqual(verify_res.json()["title"], "Undeletable by B")

    # -------------------------------------------------------------------------
    # 5. Per-User Storage Limit Enforcement
    # -------------------------------------------------------------------------
    async def test_per_user_storage_limit_enforcement(self):
        """Saving evaluations beyond MAX_SAVED_EVALUATIONS returns 409 Conflict."""
        # Temporarily lower limit to 3 for fast testing
        original_limit = evaluation_routes.MAX_SAVED_EVALUATIONS
        evaluation_routes.MAX_SAVED_EVALUATIONS = 3
        try:
            for i in range(3):
                res = self.client.post(
                    "/evaluations/save",
                    headers={"Authorization": f"Bearer {self.user_a_token}"},
                    json={"title": f"Eval {i}", "results": self.sample_results},
                )
                self.assertEqual(res.status_code, 201)

            # 4th evaluation must be rejected with 409
            res_limit = self.client.post(
                "/evaluations/save",
                headers={"Authorization": f"Bearer {self.user_a_token}"},
                json={"title": "Eval 4", "results": self.sample_results},
            )
            self.assertEqual(res_limit.status_code, 409)
            self.assertIn("Maximum saved evaluations", res_limit.json()["detail"])
        finally:
            evaluation_routes.MAX_SAVED_EVALUATIONS = original_limit


if __name__ == "__main__":
    unittest.main()
