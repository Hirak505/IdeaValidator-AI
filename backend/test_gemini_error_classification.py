"""
test_gemini_error_classification.py — Tests for distinguishing HTTP 429 (daily vs RPM),
HTTP 403 permission errors, HTTP 503 service unavailable, timeouts, and malformed model responses.
Verifies fast-failure, bounded retries, safe diagnostics, and job store category tracking.
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
from gemini_service import (
    GeminiPermissionError,
    GeminiQuotaExceededError,
    GeminiServiceUnavailableError,
    ModelResponseError,
    _sanitize_log_message,
    call_judge,
    extract_retry_delay,
    is_daily_quota_error,
    is_permission_error,
    is_quota_error,
    is_service_unavailable_error,
)
import main
from main import (
    app,
    _evaluation_jobs,
    _evaluation_jobs_lock,
    _run_background_evaluation,
)


# Mock exception classes mimicking google.api_core.exceptions
class MockPermissionDenied(Exception):
    def __init__(self, message="403 PERMISSION_DENIED: API key not valid"):
        super().__init__(message)
        self.code = 403


class MockResourceExhausted(Exception):
    def __init__(self, message="429 ResourceExhausted: Quota exceeded"):
        super().__init__(message)
        self.code = 429


class MockServiceUnavailable(Exception):
    def __init__(self, message="503 Service Unavailable"):
        super().__init__(message)
        self.code = 503


class TestErrorClassificationHelpers(unittest.TestCase):
    """Unit tests for exception classifier helpers in gemini_service."""

    def test_is_permission_error(self):
        self.assertTrue(is_permission_error(MockPermissionDenied()))
        self.assertTrue(is_permission_error(GeminiPermissionError()))
        self.assertTrue(is_permission_error(Exception("403 Forbidden: caller does not have permission")))
        self.assertTrue(is_permission_error(Exception("API key not valid. Please pass a valid API key.")))
        self.assertFalse(is_permission_error(MockResourceExhausted()))
        self.assertFalse(is_permission_error(Exception("500 Internal Server Error")))

    def test_is_daily_quota_error(self):
        # Daily quota patterns
        daily_err = MockResourceExhausted(
            "429 Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, "
            "limit: 20, model: gemini-3.8-flash. Please retry in 13h52m20s (seconds: 49940)"
        )
        self.assertTrue(is_daily_quota_error(daily_err))

        daily_err_2 = Exception("ResourceExhausted: GenerateRequestsPerDayPerProjectPerModel-FreeTier limit: 20")
        self.assertTrue(is_daily_quota_error(daily_err_2))

        # Explicit is_daily flag
        flagged = GeminiQuotaExceededError("Rate limit", is_daily=True)
        self.assertTrue(is_daily_quota_error(flagged))

        # Short-term RPM error with small delay is NOT daily
        short_err = MockResourceExhausted(
            "429 Quota exceeded for metric: requests_per_minute. Please retry in 11.4s"
        )
        self.assertFalse(is_daily_quota_error(short_err))

        # Real Google AI Studio free-tier per-minute error with free_tier_requests metric
        rpm_free_tier_err = MockResourceExhausted(
            "429 Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, "
            "limit: 5, model: gemini-3.6-flash. Please retry in 11.389334261s. "
            "quota_id: 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier', retry_delay { seconds: 11 }"
        )
        self.assertFalse(is_daily_quota_error(rpm_free_tier_err))

    def test_is_quota_error(self):
        self.assertTrue(is_quota_error(MockResourceExhausted()))
        self.assertTrue(is_quota_error(GeminiQuotaExceededError()))
        self.assertTrue(is_quota_error(Exception("429 Too Many Requests: quota exceeded")))
        self.assertFalse(is_quota_error(MockPermissionDenied()))
        self.assertFalse(is_quota_error(MockServiceUnavailable()))

    def test_is_service_unavailable_error(self):
        self.assertTrue(is_service_unavailable_error(MockServiceUnavailable()))
        self.assertTrue(is_service_unavailable_error(GeminiServiceUnavailableError()))
        self.assertTrue(is_service_unavailable_error(Exception("503 Service Unavailable: server overloaded")))
        self.assertFalse(is_service_unavailable_error(MockResourceExhausted()))

    def test_extract_retry_delay(self):
        # 1. From "retry in 11.4s"
        exc = Exception("ResourceExhausted: Please retry in 11.4s")
        delay = extract_retry_delay(exc, max_delay=30.0)
        self.assertGreaterEqual(delay, 11.4)
        self.assertLessEqual(delay, 12.0)

        # 2. From protobuf seconds: 7
        exc_pb = Exception("retry_delay {\n  seconds: 7\n  nanos: 0\n}")
        delay_pb = extract_retry_delay(exc_pb, max_delay=30.0)
        self.assertGreaterEqual(delay_pb, 7.0)
        self.assertLessEqual(delay_pb, 7.5)

        # 3. Fallback exponential backoff + jitter bounded
        exc_gen = Exception("Rate limit hit")
        delay_fallback = extract_retry_delay(exc_gen, attempt=2, initial_delay=2.0, max_delay=30.0)
        self.assertGreaterEqual(delay_fallback, 8.0)  # 2 * 2^2 = 8
        self.assertLessEqual(delay_fallback, 30.0)


class TestCallJudgeErrorHandling(unittest.IsolatedAsyncioTestCase):
    """Tests that call_judge handles errors properly: fast fails on 403 & daily 429, retries retryable errors."""

    @pytest.mark.asyncio
    async def test_permission_error_fails_immediately_no_retries(self):
        """HTTP 403 PermissionDenied must NOT be retried; fails fast on first attempt."""
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = MockPermissionDenied("403 Permission denied: API key invalid")

        with patch("gemini_service.get_model", return_value=mock_model):
            with patch.dict(os.environ, {"GEMINI_MAX_RETRIES": "3"}):
                with self.assertRaises(GeminiPermissionError):
                    await call_judge("Test Prompt", "Technical Judge")

        # Must have attempted exactly once (no retry!)
        self.assertEqual(mock_model.generate_content.call_count, 1)

    @pytest.mark.asyncio
    async def test_daily_quota_error_fails_immediately_no_retries(self):
        """Daily quota exhaustion (49940s retry) must NOT be retried; fails fast on first attempt."""
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = MockResourceExhausted(
            "429 Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, "
            "limit: 20. Please retry in 13h52m (seconds: 49940)"
        )

        with patch("gemini_service.get_model", return_value=mock_model):
            with patch.dict(os.environ, {"GEMINI_MAX_RETRIES": "3"}):
                with self.assertRaises(GeminiQuotaExceededError) as ctx:
                    await call_judge("Test Prompt", "Innovation Judge")

                self.assertTrue(ctx.exception.is_daily)

        # Must have attempted exactly once (no retry!)
        self.assertEqual(mock_model.generate_content.call_count, 1)

    @pytest.mark.asyncio
    async def test_short_term_rate_limit_retries_and_succeeds(self):
        """Short-term RPM 429 retries with backoff and succeeds on subsequent attempt."""
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"score": 8, "strengths": ["Innovation"], "weaknesses": ["Cost"], "comments": "Good"}'
        mock_response.candidates = [MagicMock(finish_reason="STOP")]

        # First call fails with transient 429, second call succeeds
        mock_model.generate_content.side_effect = [
            MockResourceExhausted("429 Too Many Requests. Please retry in 0.1s"),
            mock_response,
        ]

        with patch("gemini_service.get_model", return_value=mock_model):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                with patch.dict(os.environ, {"GEMINI_MAX_RETRIES": "3"}):
                    result = await call_judge("Test Prompt", "Business Judge")

        self.assertEqual(result["score"], 8)
        self.assertEqual(mock_model.generate_content.call_count, 2)
        mock_sleep.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_service_unavailable_retries_then_raises(self):
        """503 Service Unavailable retries up to max_retries then raises GeminiServiceUnavailableError."""
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = MockServiceUnavailable("503 Server overloaded")

        with patch("gemini_service.get_model", return_value=mock_model):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with patch.dict(os.environ, {"GEMINI_MAX_RETRIES": "2"}):
                    with self.assertRaises(GeminiServiceUnavailableError):
                        await call_judge("Test Prompt", "Presentation Judge")

        # Initial attempt + 2 retries = 3 attempts
        self.assertEqual(mock_model.generate_content.call_count, 3)

    @pytest.mark.asyncio
    async def test_malformed_response_raises_model_response_error_without_retrying_as_quota(self):
        """Malformed response is raised directly as ModelResponseError, not mistaken for quota."""
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "This is not JSON at all."
        mock_response.candidates = [MagicMock(finish_reason="STOP")]
        mock_model.generate_content.return_value = mock_response

        with patch("gemini_service.get_model", return_value=mock_model):
            with self.assertRaises(ModelResponseError):
                await call_judge("Test Prompt", "Chief Judge")


class TestAsyncJobFailureCategories(unittest.IsolatedAsyncioTestCase):
    """Tests that async background evaluation stores the precise failure category and safe diagnostics."""

    def setUp(self):
        self.client = TestClient(app)
        main._request_records.clear()
        with _evaluation_jobs_lock:
            _evaluation_jobs.clear()

    def tearDown(self):
        main._request_records.clear()
        with _evaluation_jobs_lock:
            _evaluation_jobs.clear()

    @pytest.mark.asyncio
    async def test_job_records_permission_denied_category_and_403(self):
        job_id = "eval_test_403"
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
            mock_judges.side_effect = GeminiPermissionError()
            await _run_background_evaluation(job_id, "Project context", False, None)

        response = self.client.get(f"/evaluate/status/{job_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["error_code"], 403)
        self.assertEqual(data["category"], "permission_denied")
        self.assertIn("authentication", data["detail"].lower())
        self.assertNotIn("quota", data["detail"].lower())

    @pytest.mark.asyncio
    async def test_job_records_daily_quota_exceeded_category(self):
        job_id = "eval_test_daily_429"
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
            mock_judges.side_effect = GeminiQuotaExceededError(
                "Daily quota exceeded for model gemini-3.8-flash", retry_after=49959, is_daily=True
            )
            await _run_background_evaluation(job_id, "Project context", False, None)

        response = self.client.get(f"/evaluate/status/{job_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["error_code"], 429)
        self.assertEqual(data["category"], "daily_quota_exceeded")
        self.assertIn("daily", data["detail"].lower())

    @pytest.mark.asyncio
    async def test_job_records_service_unavailable_category(self):
        job_id = "eval_test_503"
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
            mock_judges.side_effect = GeminiServiceUnavailableError()
            await _run_background_evaluation(job_id, "Project context", False, None)

        response = self.client.get(f"/evaluate/status/{job_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["error_code"], 503)
        self.assertEqual(data["category"], "service_unavailable")
        self.assertIn("service is temporarily unavailable", data["detail"].lower())

    @pytest.mark.asyncio
    async def test_job_records_malformed_response_category_and_502(self):
        job_id = "eval_test_malformed_502"
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
            mock_judges.side_effect = ModelResponseError("Malformed JSON output", reason="malformed_json")
            await _run_background_evaluation(job_id, "Project context", False, None)

        response = self.client.get(f"/evaluate/status/{job_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["error_code"], 502)
        self.assertEqual(data["category"], "malformed_response")
        self.assertIn("unparseable response format", data["detail"].lower())

    @pytest.mark.asyncio
    async def test_diagnostics_scrub_keys_and_prompts_in_status_response(self):
        job_id = "eval_test_safe_diag"
        secret_key = "AIzaSySecretApiKeyToScrub999"
        user_prompt = "MY_CONFIDENTIAL_PITCH_DECK_IDEA"

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
                    mock_judges.side_effect = RuntimeError(f"Error referencing key={secret_key}")
                    await _run_background_evaluation(job_id, user_prompt, False, None)

                # Server log must sanitize the secret key
                mock_logger_error.assert_called_once()
                log_args = mock_logger_error.call_args[0]
                formatted_log = log_args[0] % log_args[1:]
                self.assertNotIn(secret_key, formatted_log)
                self.assertIn("[REDACTED_API_KEY]", formatted_log)

        response = self.client.get(f"/evaluate/status/{job_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        raw_text = str(data)

        # Client response must NOT expose raw API key or prompt
        self.assertNotIn(secret_key, raw_text)
        self.assertNotIn(user_prompt, raw_text)


if __name__ == "__main__":
    unittest.main()
