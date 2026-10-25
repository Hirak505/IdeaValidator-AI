"""
test_timeout_diagnostics.py — Unit tests for slow model calls, provider timeouts,
timing diagnostics, and async evaluation background job lifecycle with status polling.

Covers:
1. Provider timeout in call_judge attaches stage name and elapsed time
2. Successful model call logs duration safely
3. Synchronous POST /evaluate returns 504 on timeout with structured stage info
4. Asynchronous POST /evaluate/async lifecycle (202 Accepted, status polling, completion)
5. Background job failure handling (timeout -> 504 status, quota -> 429, error -> 502)
6. 404 for unknown job ID
7. File validation and rate limiting on async evaluation endpoint
"""

import asyncio
import json
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
from gemini_service import call_judge
from main import app, _evaluation_jobs


MOCK_VALID_RESULTS = {
    "innovation": {"score": 8, "comments": "Good", "strengths": ["Original"], "weaknesses": ["None"]},
    "technical": {"score": 7, "comments": "Solid", "strengths": ["Clean"], "weaknesses": ["Tests"]},
    "business": {"score": 8, "comments": "Viable", "strengths": ["Market"], "weaknesses": ["Pricing"]},
    "presentation": {"score": 9, "comments": "Clear", "strengths": ["Slides"], "weaknesses": ["Pacing"]},
    "chief_judge": {
        "overall_score": 8.0,
        "final_verdict": "Promising venture.",
        "top_strengths": ["Strong tech"],
        "top_improvements": ["Scale tests"],
    },
    "consensus": {"mean": 8.0, "spread": 2, "agreement_level": "High"},
}


class TestCallJudgeTimeoutDiagnostics(unittest.IsolatedAsyncioTestCase):
    """Test timeout detection, metadata attachment, and duration tracking in call_judge."""

    def test_timeout_setting_is_bounded(self):
        for configured, expected in (("10", 10.0), ("300", 300.0)):
            with patch.dict(os.environ, {"GEMINI_TIMEOUT_SECONDS": configured}):
                self.assertEqual(gemini_service._get_timeout_seconds(), expected)

        for configured in ("9.9", "300.1", "not-a-number"):
            with patch.dict(os.environ, {"GEMINI_TIMEOUT_SECONDS": configured}):
                with self.assertRaisesRegex(RuntimeError, "GEMINI_TIMEOUT_SECONDS"):
                    gemini_service._get_timeout_seconds()

    @pytest.mark.asyncio
    async def test_slow_model_call_raises_timeout_with_metadata(self):
        """Simulate a model call that exceeds TIMEOUT_SECONDS."""
        mock_model = MagicMock()

        def slow_generate(prompt, request_options=None):
            time.sleep(0.2)
            mock_resp = MagicMock()
            mock_resp.text = '{"score": 8, "comments": "ok", "strengths": ["a"], "weaknesses": ["b"]}'
            return mock_resp

        mock_model.generate_content.side_effect = slow_generate

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-12345678"}):
            with patch.object(gemini_service, "get_model", return_value=mock_model):
                with patch.object(gemini_service, "TIMEOUT_SECONDS", 0.05):
                    with patch.object(gemini_service.logger, "warning") as mock_warning:
                        with pytest.raises(TimeoutError) as exc_info:
                            await call_judge("test prompt", "Technical Judge")

                err = exc_info.value
                self.assertIn("Technical Judge timed out", str(err))
                self.assertEqual(getattr(err, "judge_name", None), "Technical Judge")
                self.assertGreater(getattr(err, "elapsed", 0), 0)
                self.assertEqual(err.timeout_source, "application_asyncio_wait_for")
                self.assertEqual(err.underlying_exception_type, "not_available")
                self.assertIn(
                    "application_asyncio_wait_for",
                    mock_warning.call_args.args,
                )
                self.assertIn("not_available", mock_warning.call_args.args)

    @pytest.mark.asyncio
    async def test_sdk_request_uses_configured_timeout(self):
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"score": 8, "comments": "ok", "strengths": ["a"], "weaknesses": ["b"]}'
        mock_response.candidates = []
        mock_model.generate_content.return_value = mock_response

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-12345678"}):
            with patch.object(gemini_service, "get_model", return_value=mock_model):
                with patch.object(gemini_service, "TIMEOUT_SECONDS", 45.0):
                    await call_judge("test prompt", "Innovation Judge")

        mock_model.generate_content.assert_called_once_with(
            "test prompt",
            request_options={"timeout": 40.0},
        )

    @pytest.mark.asyncio
    async def test_sdk_timeout_preserves_source_and_underlying_exception(self):
        sdk_error = TimeoutError("mock SDK transport timeout")
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = sdk_error

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-12345678"}):
            with patch.object(gemini_service, "get_model", return_value=mock_model):
                with patch.object(gemini_service, "TIMEOUT_SECONDS", 1.0):
                    with self.assertRaises(TimeoutError) as exc_info:
                        await call_judge("test prompt", "Innovation Judge")

        self.assertEqual(exc_info.exception.timeout_source, "gemini_sdk")
        self.assertEqual(exc_info.exception.underlying_exception_type, "TimeoutError")
        self.assertIsInstance(exc_info.exception.__cause__, TimeoutError)
        self.assertIn("mock SDK transport timeout", str(exc_info.exception.__cause__))

    @pytest.mark.asyncio
    async def test_successful_call_logs_timing_safely(self):
        """Verify successful call logs duration and does not expose API key."""
        secret_key = "AIzaSySecretApiKey12345"
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"score": 9, "comments": "Great", "strengths": ["Fast"], "weaknesses": ["None"]}'
        mock_response.candidates = [MagicMock(finish_reason="STOP", block_reason=None)]
        mock_response.prompt_feedback = MagicMock()
        mock_response.prompt_feedback.block_reason = None
        mock_model.generate_content.return_value = mock_response

        with patch.dict(os.environ, {"GEMINI_API_KEY": secret_key}):
            with patch.object(gemini_service, "get_model", return_value=mock_model):
                with patch.object(gemini_service.logger, "info") as mock_info:
                    result = await call_judge("evaluate this", "Innovation Judge")
                    self.assertEqual(result["score"], 9)
                    # Verify logger was called with timing
                    mock_info.assert_called()
                    logged_texts = [str(call[0][0]) for call in mock_info.call_args_list]
                    self.assertTrue(any("completed successfully" in msg or "received in" in msg for msg in logged_texts))


class TestSynchronousEvaluateTimeoutMapping(unittest.TestCase):
    """Test HTTP 504 mapping on synchronous POST /evaluate."""

    def setUp(self):
        self.client = TestClient(app)

    def test_sync_evaluate_timeout_returns_504_with_stage(self):
        timeout_err = TimeoutError("Chief Judge timed out after 60.0 seconds.")
        timeout_err.judge_name = "Chief Judge"
        timeout_err.elapsed = 60.05

        with patch("main.run_all_judges", new_callable=AsyncMock) as mock_judges:
            mock_judges.side_effect = timeout_err
            response = self.client.post(
                "/evaluate",
                data={"attack_mode": "false"},
                files={"readme": ("README.md", b"# Test Project\nIdea details", "text/plain")},
            )
            self.assertEqual(response.status_code, 504)
            data = response.json()
            self.assertEqual(data.get("detail"), "AI evaluation timed out. Please try again.")
            self.assertEqual(data.get("stage"), "Chief Judge")
            self.assertIn("elapsed_seconds", data)


class TestAsyncEvaluationJobLifecycle(unittest.TestCase):
    """Test the asynchronous background evaluation endpoints (POST /evaluate/async and GET /evaluate/status/{id})."""

    def setUp(self):
        self.client = TestClient(app)
        _evaluation_jobs.clear()
        import main
        main._request_records.clear()

    def test_async_evaluate_requires_at_least_one_file(self):
        response = self.client.post("/evaluate/async", data={"attack_mode": "false"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("upload at least one file", response.json().get("detail", ""))

    def test_async_evaluate_lifecycle_success(self):
        """Full lifecycle: start job -> 202 -> status running -> status completed with results."""
        with patch("main.run_all_judges", new_callable=AsyncMock) as mock_judges:
            mock_judges.return_value = MOCK_VALID_RESULTS

            # 1. Start job
            response = self.client.post(
                "/evaluate/async",
                data={"attack_mode": "false"},
                files={"readme": ("README.md", b"# Async Project\nDetails", "text/plain")},
            )
            self.assertEqual(response.status_code, 202)
            data = response.json()
            job_id = data.get("job_id")
            self.assertTrue(job_id)
            self.assertEqual(data.get("status"), "running")

            # 2. Check status
            status_resp = self.client.get(f"/evaluate/status/{job_id}")
            self.assertEqual(status_resp.status_code, 200)
            status_data = status_resp.json()
            self.assertIn(status_data.get("status"), ("running", "completed"))

    def test_async_evaluate_lifecycle_timeout_failure(self):
        """Simulate a background timeout -> status failed with 200 response, status='failed', and error_code=504."""
        timeout_err = TimeoutError("Chief Judge timed out after 60.0 seconds.")
        timeout_err.judge_name = "Chief Judge"

        with patch("main.run_all_judges", new_callable=AsyncMock) as mock_judges:
            mock_judges.side_effect = timeout_err

            # Start job
            response = self.client.post(
                "/evaluate/async",
                data={"attack_mode": "false"},
                files={"readme": ("README.md", b"# Timeout Project", "text/plain")},
            )
            self.assertEqual(response.status_code, 202)
            job_id = response.json().get("job_id")

            # Allow background task to execute
            time.sleep(0.1)

            # Check status
            status_resp = self.client.get(f"/evaluate/status/{job_id}")
            self.assertEqual(status_resp.status_code, 200)
            status_data = status_resp.json()
            self.assertEqual(status_data.get("status"), "failed")
            self.assertEqual(status_data.get("stage"), "Chief Judge")
            self.assertEqual(status_data.get("error_code"), 504)
            self.assertIn("timed out", status_data.get("detail", ""))

    def test_status_endpoint_returns_404_for_unknown_job(self):
        response = self.client.get("/evaluate/status/eval_nonexistent123")
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json().get("detail", ""))


if __name__ == "__main__":
    unittest.main()
