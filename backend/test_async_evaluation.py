"""
test_async_evaluation.py — Tests for asynchronous evaluation lifecycle,
background job execution, safe diagnostic logging, and consistent status polling.
"""

import asyncio
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import gemini_service
from judges import run_all_judges
import main
from main import (
    app,
    _evaluation_jobs,
    _evaluation_jobs_lock,
    _prune_evaluation_jobs,
    _run_background_evaluation,
)


class TestAsyncEvaluation(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.client = TestClient(app)
        main._request_records.clear()
        # Clear evaluation jobs between tests
        with _evaluation_jobs_lock:
            _evaluation_jobs.clear()

    def tearDown(self):
        main._request_records.clear()
        with _evaluation_jobs_lock:
            _evaluation_jobs.clear()

    # -----------------------------------------------------------------------
    # 1. Job Creation
    # -----------------------------------------------------------------------
    def test_create_async_evaluation_returns_202_and_job_id(self):
        """Verify POST /evaluate/async starts a job and returns 202 with job_id."""
        with patch("main.asyncio.create_task") as mock_task:
            response = self.client.post(
                "/evaluate/async",
                data={"attack_mode": "false"},
                files={"readme": ("README.md", b"# Test Idea\nA revolutionary project", "text/plain")},
            )
            self.assertEqual(response.status_code, 202)
            data = response.json()
            self.assertIn("job_id", data)
            self.assertTrue(data["job_id"].startswith("eval_"))
            self.assertEqual(data["status"], "running")
            self.assertEqual(data["stage"], "Specialist Judges")
            mock_task.assert_called_once()

    def test_create_async_evaluation_alias_route(self):
        """Verify POST /evaluate/request also returns 202."""
        with patch("main.asyncio.create_task") as mock_task:
            response = self.client.post(
                "/evaluate/request",
                data={"attack_mode": "false"},
                files={"readme": ("README.md", b"# Test Idea\nIdea text", "text/plain")},
            )
            self.assertEqual(response.status_code, 202)
            self.assertIn("job_id", response.json())
            mock_task.assert_called_once()

    def test_create_async_evaluation_no_files_returns_400(self):
        response = self.client.post("/evaluate/async", data={"attack_mode": "false"})
        self.assertEqual(response.status_code, 400)

    # -----------------------------------------------------------------------
    # 2. Status Polling - Running, Completed, Unknown
    # -----------------------------------------------------------------------
    def test_status_polling_running_job(self):
        job_id = "eval_test_running_123"
        with _evaluation_jobs_lock:
            _evaluation_jobs[job_id] = {
                "job_id": job_id,
                "status": "running",
                "stage": "Specialist Judges",
                "created_at": time.time(),
                "results": None,
                "error": None,
                "status_code": None,
                "duration": None,
            }

        response = self.client.get(f"/evaluate/status/{job_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["job_id"], job_id)
        self.assertEqual(data["status"], "running")
        self.assertEqual(data["stage"], "Specialist Judges")
        self.assertIn("elapsed_seconds", data)

    def test_status_polling_completed_job(self):
        job_id = "eval_test_completed_456"
        mock_results = {
            "innovation": {"score": 9},
            "technical": {"score": 8},
            "business": {"score": 8},
            "presentation": {"score": 9},
            "chief_judge": {"overall_score": 8.5},
            "consensus": {"mean": 8.5},
        }
        with _evaluation_jobs_lock:
            _evaluation_jobs[job_id] = {
                "job_id": job_id,
                "status": "completed",
                "stage": "Completed",
                "created_at": time.time() - 15.0,
                "results": mock_results,
                "error": None,
                "status_code": None,
                "duration": 14.8,
            }

        response = self.client.get(f"/evaluate/status/{job_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["job_id"], job_id)
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["stage"], "Completed")
        self.assertEqual(data["results"], mock_results)
        self.assertEqual(data["duration_seconds"], 14.8)

    def test_status_polling_unknown_id_returns_404_not_502(self):
        """Unknown job IDs must return 404, never 502."""
        response = self.client.get("/evaluate/status/eval_nonexistent_999")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn("not found or expired", data.get("detail", ""))

    # -----------------------------------------------------------------------
    # 3. Background Execution Exceptions Captured as Failed Results (HTTP 200)
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_background_runtime_error_stored_as_failed_job_and_returns_200(self):
        """
        Regression: When background execution hits a generic RuntimeError,
        status check endpoint must return HTTP 200 with status='failed' and detail,
        NOT HTTP 502 Bad Gateway.
        """
        job_id = "eval_597d350ca160"
        with _evaluation_jobs_lock:
            _evaluation_jobs[job_id] = {
                "job_id": job_id,
                "status": "running",
                "stage": "Specialist Judges",
                "created_at": time.time(),
                "results": None,
                "error": None,
                "status_code": None,
                "duration": None,
            }

        with patch("main.run_all_judges", new_callable=AsyncMock) as mock_judges:
            mock_judges.side_effect = RuntimeError("Innovation Judge evaluation failed. Service temporarily unavailable.")
            await _run_background_evaluation(job_id, "Project context", False, None)

        with _evaluation_jobs_lock:
            job = _evaluation_jobs[job_id]
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error"], "Evaluation service temporarily unavailable.")
        self.assertEqual(job["status_code"], 502)

        # Poll status endpoint: MUST be HTTP 200 with failure details, NOT HTTP 502
        response = self.client.get(f"/evaluate/status/{job_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["job_id"], job_id)
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["detail"], "Evaluation service temporarily unavailable.")
        self.assertEqual(data["error"], "Evaluation service temporarily unavailable.")
        self.assertEqual(data["error_code"], 502)
        self.assertIn("elapsed_seconds", data)

    @pytest.mark.asyncio
    async def test_background_quota_exceeded_stored_as_failed_job(self):
        job_id = "eval_quota_test"
        with _evaluation_jobs_lock:
            _evaluation_jobs[job_id] = {
                "job_id": job_id,
                "status": "running",
                "stage": "Specialist Judges",
                "created_at": time.time(),
                "results": None,
                "error": None,
                "status_code": None,
                "duration": None,
            }

        with patch("main.run_all_judges", new_callable=AsyncMock) as mock_judges:
            mock_judges.side_effect = gemini_service.GeminiQuotaExceededError("ResourceExhausted 429", retry_after=12)
            await _run_background_evaluation(job_id, "Project context", False, None)

        response = self.client.get(f"/evaluate/status/{job_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "failed")
        self.assertIn("rate limit or quota exceeded", data["detail"])
        self.assertEqual(data["error_code"], 429)

    @pytest.mark.asyncio
    async def test_background_timeout_error_stored_as_failed_job(self):
        job_id = "eval_timeout_test"
        with _evaluation_jobs_lock:
            _evaluation_jobs[job_id] = {
                "job_id": job_id,
                "status": "running",
                "stage": "Specialist Judges",
                "created_at": time.time(),
                "results": None,
                "error": None,
                "status_code": None,
                "duration": None,
            }

        timeout_err = TimeoutError("Chief Judge timed out.")
        timeout_err.judge_name = "Chief Judge"

        with patch("main.run_all_judges", new_callable=AsyncMock) as mock_judges:
            mock_judges.side_effect = timeout_err
            await _run_background_evaluation(job_id, "Project context", False, None)

        response = self.client.get(f"/evaluate/status/{job_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["stage"], "Chief Judge")
        self.assertIn("timed out", data["detail"])
        self.assertEqual(data["error_code"], 504)

    @pytest.mark.asyncio
    async def test_background_environment_error_stored_as_failed_job(self):
        job_id = "eval_env_test"
        with _evaluation_jobs_lock:
            _evaluation_jobs[job_id] = {
                "job_id": job_id,
                "status": "running",
                "stage": "Specialist Judges",
                "created_at": time.time(),
                "results": None,
                "error": None,
                "status_code": None,
                "duration": None,
            }

        with patch("main.run_all_judges", new_callable=AsyncMock) as mock_judges:
            mock_judges.side_effect = EnvironmentError("Missing API key")
            await _run_background_evaluation(job_id, "Project context", False, None)

        response = self.client.get(f"/evaluate/status/{job_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["detail"], "Service configuration unavailable.")
        self.assertEqual(data["error_code"], 503)

    # -----------------------------------------------------------------------
    # 4. Safe Diagnostic Logging (Never Log API Keys or Prompts)
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_background_logging_sanitizes_secrets_and_does_not_log_prompts(self):
        job_id = "eval_log_test_789"
        secret_key = "AIzaSySecretApiKeyToSanitize999"
        user_prompt = "MY_HIGHLY_SECRET_USER_PROMPT_IDEA"

        with _evaluation_jobs_lock:
            _evaluation_jobs[job_id] = {
                "job_id": job_id,
                "status": "running",
                "stage": "Specialist Judges",
                "created_at": time.time(),
                "results": None,
                "error": None,
                "status_code": None,
                "duration": None,
            }

        with patch.dict(os.environ, {"GEMINI_API_KEY": secret_key}):
            with patch("main.logger.error") as mock_logger_error:
                with patch("main.run_all_judges", new_callable=AsyncMock) as mock_judges:
                    mock_judges.side_effect = RuntimeError(f"Connection error to key={secret_key}")
                    await _run_background_evaluation(job_id, user_prompt, False, None)

                mock_logger_error.assert_called_once()
                log_args = mock_logger_error.call_args[0]
                formatted_log = log_args[0] % log_args[1:]

                # Diagnostic log must contain job ID, state, exc_type
                self.assertIn(job_id, formatted_log)
                self.assertIn("state=failed", formatted_log)
                self.assertIn("exc_type=RuntimeError", formatted_log)

                # Must NOT contain raw secret API key or user prompt
                self.assertNotIn(secret_key, formatted_log)
                self.assertNotIn(user_prompt, formatted_log)
                self.assertIn("[REDACTED_API_KEY]", formatted_log)

    # -----------------------------------------------------------------------
    # 5. In-Memory Job Store TTL Pruning
    # -----------------------------------------------------------------------
    def test_pruning_evicts_stale_completed_jobs_but_preserves_running(self):
        now = time.time()
        with _evaluation_jobs_lock:
            # Stale completed job (> 3600s old) -> should be pruned
            _evaluation_jobs["eval_stale_done"] = {
                "status": "completed",
                "created_at": now - 4000,
            }
            # Stale running job (> 3600s old) -> should NOT be pruned while running
            _evaluation_jobs["eval_stale_running"] = {
                "status": "running",
                "created_at": now - 4000,
            }
            # Fresh completed job -> should NOT be pruned
            _evaluation_jobs["eval_fresh_done"] = {
                "status": "completed",
                "created_at": now - 100,
            }

        _prune_evaluation_jobs()

        with _evaluation_jobs_lock:
            self.assertNotIn("eval_stale_done", _evaluation_jobs)
            self.assertIn("eval_stale_running", _evaluation_jobs)
            self.assertIn("eval_fresh_done", _evaluation_jobs)

    # -----------------------------------------------------------------------
    # 6. Stage Callback Updates Stage During run_all_judges
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_run_all_judges_invokes_stage_callback(self):
        stages_visited = []

        def callback(stage_name):
            stages_visited.append(stage_name)

        async def mock_judge(prompt, name):
            if "Chief" in name:
                return {
                    "overall_score": 8.0,
                    "final_verdict": "Verdict",
                    "top_strengths": ["A"],
                    "top_improvements": ["B"],
                    "improvement_roadmap": ["C"],
                    "judge_questions": ["Q1"],
                }
            return {"score": 7, "strengths": ["S"], "weaknesses": ["W"], "comments": "C"}

        with patch("judges.call_judge", side_effect=mock_judge):
            results = await run_all_judges("Test project", stage_callback=callback)
            self.assertIn("Specialist Judges", stages_visited)
            self.assertIn("Chief Judge", stages_visited)
            self.assertIn("Completed", stages_visited)
            self.assertIn("chief_judge", results)


if __name__ == "__main__":
    unittest.main()
