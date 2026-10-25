"""
test_regression_evaluate_502.py — Regression tests for /evaluate 502 error,
safe backend logging, model configuration, and response parsing.
"""

import asyncio
import logging
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import gemini_service
from main import app


class TestRegressionEvaluate502(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.client = TestClient(app)
        import main
        main._request_records.clear()

    # -----------------------------------------------------------------------
    # 1. Safe Backend Logging & Secret Redaction
    # -----------------------------------------------------------------------
    def test_sanitize_log_message_scrubs_api_key(self):
        secret_key = "AIzaSyTestSecretKey123456789"
        with patch.dict(os.environ, {"GEMINI_API_KEY": secret_key}):
            raw_msg = f"Failed to connect using key={secret_key} to endpoint"
            sanitized = gemini_service._sanitize_log_message(raw_msg)
            self.assertNotIn(secret_key, sanitized)
            self.assertIn("[REDACTED_API_KEY]", sanitized)

    def test_sanitize_log_message_scrubs_query_params(self):
        raw_msg = "Error connecting to https://api.google.com/v1?key=AIzaSySecret123&token=my_secret_token"
        sanitized = gemini_service._sanitize_log_message(raw_msg)
        self.assertNotIn("AIzaSySecret123", sanitized)
        self.assertNotIn("my_secret_token", sanitized)
        self.assertIn("key=[REDACTED]", sanitized)
        self.assertIn("token=[REDACTED]", sanitized)

    @pytest.mark.asyncio
    async def test_call_judge_logs_safely_on_exception(self):
        """Verify call_judge logs the exception without exposing API keys and raises RuntimeError."""
        secret_key = "AIzaSyTopSecretKey987654321"
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = RuntimeError(f"Connection failed with key={secret_key}")

        with patch.dict(os.environ, {"GEMINI_API_KEY": secret_key}):
            with patch.object(gemini_service, "get_model", return_value=mock_model):
                with patch.object(gemini_service.logger, "error") as mock_logger_error:
                    with pytest.raises(RuntimeError) as exc_info:
                        await gemini_service.call_judge("dummy prompt", "Innovation Judge")

                    self.assertIn("Innovation Judge evaluation failed. Service temporarily unavailable.", str(exc_info.value))
                    mock_logger_error.assert_called_once()
                    log_args = mock_logger_error.call_args[0]
                    formatted_log = log_args[0] % log_args[1:]
                    self.assertNotIn(secret_key, formatted_log)
                    self.assertIn("[REDACTED_API_KEY]", formatted_log)

    # -----------------------------------------------------------------------
    # 2. Configurable Gemini Model Name
    # -----------------------------------------------------------------------
    def test_get_model_respects_gemini_model_env(self):
        with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-3.8-flash", "GEMINI_API_KEY": "dummy_key_123456"}):
            with patch.object(gemini_service.genai, "GenerativeModel") as mock_gen_model:
                with patch.object(gemini_service, "verify_environment"):
                    gemini_service._configured = True
                    gemini_service.get_model()
                    mock_gen_model.assert_called_once()
                    call_kwargs = mock_gen_model.call_args[1]
                    self.assertEqual(call_kwargs.get("model_name"), "gemini-3.8-flash")

    # -----------------------------------------------------------------------
    # 3. Robust JSON Extraction from Model Responses
    # -----------------------------------------------------------------------
    def test_extract_json_direct(self):
        text = '{"score": 8, "confidence": 85}'
        result = gemini_service.extract_json_from_response(text)
        self.assertEqual(result["score"], 8)
        self.assertEqual(result["confidence"], 85)

    def test_extract_json_in_markdown_code_fence(self):
        text = "```json\n{\"score\": 9, \"confidence\": 90}\n```"
        result = gemini_service.extract_json_from_response(text)
        self.assertEqual(result["score"], 9)
        self.assertEqual(result["confidence"], 90)

    def test_extract_json_with_surrounding_commentary(self):
        text = (
            "Here is my analysis of the hackathon project:\n\n"
            "```json\n"
            "{\n"
            '  "score": 7,\n'
            '  "strengths": ["Clear design"],\n'
            '  "weaknesses": ["Needs tests"]\n'
            "}\n"
            "```\n\n"
            "Overall, a solid submission."
        )
        result = gemini_service.extract_json_from_response(text)
        self.assertEqual(result["score"], 7)
        self.assertEqual(result["strengths"], ["Clear design"])

    def test_extract_json_invalid_raises_value_error(self):
        text = "I cannot evaluate this submission because no JSON is provided."
        with self.assertRaises(ValueError):
            gemini_service.extract_json_from_response(text)

    # -----------------------------------------------------------------------
    # 4. /evaluate Endpoint Exception Mapping & Error Payload Safety
    # -----------------------------------------------------------------------
    def test_evaluate_endpoint_maps_runtime_error_to_502(self):
        """Ensure RuntimeError in AI judges maps to 502 without leaking secrets or stack traces."""
        with patch("main.run_all_judges", new_callable=AsyncMock) as mock_judges:
            mock_judges.side_effect = RuntimeError("Innovation Judge evaluation failed. Service temporarily unavailable.")
            response = self.client.post(
                "/evaluate",
                data={"attack_mode": "false"},
                files={"readme": ("README.md", b"# Test Project\nIdea description", "text/plain")},
            )
            self.assertEqual(response.status_code, 502)
            data = response.json()
            self.assertEqual(data.get("detail"), "Evaluation service temporarily unavailable.")
            # Ensure no traceback or internal paths leaked to frontend
            self.assertNotIn("Traceback", response.text)
            self.assertNotIn("File \"", response.text)
            self.assertNotIn("API_KEY", response.text)

    def test_evaluate_endpoint_maps_timeout_error_to_504(self):
        with patch("main.run_all_judges", new_callable=AsyncMock) as mock_judges:
            mock_judges.side_effect = TimeoutError("Chief Judge timed out after 30.0 seconds.")
            response = self.client.post(
                "/evaluate",
                data={"attack_mode": "false"},
                files={"readme": ("README.md", b"# Test Project\nIdea description", "text/plain")},
            )
            self.assertEqual(response.status_code, 504)
            self.assertEqual(response.json().get("detail"), "AI evaluation timed out. Please try again.")

    def test_evaluate_endpoint_maps_environment_error_to_503(self):
        with patch("main.run_all_judges", new_callable=AsyncMock) as mock_judges:
            mock_judges.side_effect = EnvironmentError("Gemini service configuration missing.")
            response = self.client.post(
                "/evaluate",
                data={"attack_mode": "false"},
                files={"readme": ("README.md", b"# Test Project\nIdea description", "text/plain")},
            )
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json().get("detail"), "Service configuration unavailable.")

    # -----------------------------------------------------------------------
    # 5. Detection of Quota Errors & Provider Retry Delay Extraction
    # -----------------------------------------------------------------------
    def test_is_quota_error_detection(self):
        try:
            from google.api_core.exceptions import ResourceExhausted, TooManyRequests
            real_resource_exhausted = ResourceExhausted("429 Resource exhausted")
            real_too_many_requests = TooManyRequests("429 Rate limit")
            self.assertTrue(gemini_service.is_quota_error(real_resource_exhausted))
            self.assertTrue(gemini_service.is_quota_error(real_too_many_requests))
        except ImportError:
            pass

        class CustomResourceExhausted(Exception):
            code = 429

        class GenericErrorWith429(Exception):
            status_code = 429

        self.assertTrue(gemini_service.is_quota_error(CustomResourceExhausted("Rate exceeded")))
        self.assertTrue(gemini_service.is_quota_error(GenericErrorWith429("Too many requests")))
        self.assertTrue(gemini_service.is_quota_error(RuntimeError("429 You exceeded your current quota: retry in 5s")))
        self.assertTrue(gemini_service.is_quota_error(gemini_service.GeminiQuotaExceededError("Quota reached", retry_after=10)))

        # Non-quota errors should return False
        self.assertFalse(gemini_service.is_quota_error(RuntimeError("PermissionDenied with key=secret")))
        self.assertFalse(gemini_service.is_quota_error(ValueError("Could not parse JSON")))
        self.assertFalse(gemini_service.is_quota_error(None))

    def test_extract_retry_delay_from_provider_message(self):
        # 1. "Please retry in 11.415001046s"
        msg1 = "Quota exceeded... Please retry in 11.415001046s. [links {...}]"
        delay1 = gemini_service.extract_retry_delay(RuntimeError(msg1), max_delay=30.0)
        self.assertGreaterEqual(delay1, 11.4)
        self.assertLessEqual(delay1, 13.0)

        # 2. "retry_delay { seconds: 7 }"
        msg2 = "ResourceExhausted: [retry_delay {\n  seconds: 7\n  nanos: 500000000\n}]"
        delay2 = gemini_service.extract_retry_delay(RuntimeError(msg2), max_delay=30.0)
        self.assertGreaterEqual(delay2, 7.5)
        self.assertLessEqual(delay2, 9.0)

        # 3. Exception object with retry_delay attribute
        mock_exc = MagicMock(spec=Exception)
        mock_exc.retry_delay = 6.0
        delay3 = gemini_service.extract_retry_delay(mock_exc, max_delay=30.0)
        self.assertGreaterEqual(delay3, 6.0)
        self.assertLessEqual(delay3, 7.0)

        # 4. Fallback exponential backoff when no delay in message
        delay4 = gemini_service.extract_retry_delay(
            RuntimeError("429 Quota exceeded without hint"),
            attempt=1,
            initial_delay=2.0,
            backoff_factor=2.0,
            max_delay=30.0,
        )
        # Attempt 1: 2.0 * 2^1 = 4.0 + jitter
        self.assertGreaterEqual(delay4, 4.0)
        self.assertLessEqual(delay4, 5.0)

    # -----------------------------------------------------------------------
    # 6. Mocked Tests for Retry Success and Exponential Backoff
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_call_judge_retry_success(self):
        """Verify that call_judge detects 429 quota error, sleeps, retries, and succeeds."""
        mock_model = MagicMock()
        quota_err = RuntimeError("429 ResourceExhausted: Quota exceeded. Please retry in 1.2s.")
        success_resp = MagicMock()
        success_resp.text = '{"score": 9, "comments": "Excellent execution", "strengths": ["Fast"], "weaknesses": ["Minor style issues"]}'

        # Call 1 fails with 429; Call 2 succeeds
        mock_model.generate_content.side_effect = [quota_err, success_resp]

        with patch.object(gemini_service, "get_model", return_value=mock_model):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result = await gemini_service.call_judge("dummy prompt", "Technical Judge")

                self.assertEqual(result["score"], 9)
                self.assertEqual(result["comments"], "Excellent execution")
                self.assertEqual(mock_model.generate_content.call_count, 2)
                # Ensure asyncio.sleep was called with provider delay (>= 1.2s)
                mock_sleep.assert_called_once()
                slept_delay = mock_sleep.call_args[0][0]
                self.assertGreaterEqual(slept_delay, 1.2)

    # -----------------------------------------------------------------------
    # 7. Mocked Tests for Exhausted Retries and Non-Retryable Errors
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_call_judge_exhausted_retries_raises_gemini_quota_error(self):
        """Verify that call_judge stops after bounded retries and raises GeminiQuotaExceededError."""
        mock_model = MagicMock()
        quota_err = RuntimeError("ResourceExhausted: 429 Quota exceeded... retry_delay {\n  seconds: 5\n}")
        mock_model.generate_content.side_effect = quota_err

        # Configure max 2 retries (total 3 attempts)
        with patch.dict(os.environ, {"GEMINI_MAX_RETRIES": "2"}):
            with patch.object(gemini_service, "get_model", return_value=mock_model):
                with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                    with pytest.raises(gemini_service.GeminiQuotaExceededError) as exc_info:
                        await gemini_service.call_judge("dummy prompt", "Technical Judge")

                    # Total attempts = initial + 2 retries = 3
                    self.assertEqual(mock_model.generate_content.call_count, 3)
                    self.assertEqual(mock_sleep.call_count, 2)
                    self.assertGreaterEqual(exc_info.value.retry_after, 5)
                    self.assertIn("quota limits", str(exc_info.value))

    @pytest.mark.asyncio
    async def test_call_judge_non_retryable_error_does_not_retry(self):
        """Verify non-retryable errors (e.g. invalid arguments, internal errors) fail immediately without retrying."""
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = RuntimeError("InvalidArgument: prompt length exceeded 1000000")

        with patch.object(gemini_service, "get_model", return_value=mock_model):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                with pytest.raises(RuntimeError) as exc_info:
                    await gemini_service.call_judge("dummy prompt", "Business Judge")

                self.assertEqual(mock_model.generate_content.call_count, 1)
                mock_sleep.assert_not_called()
                self.assertIn("Business Judge evaluation failed", str(exc_info.value))

    # -----------------------------------------------------------------------
    # 8. HTTP 429 Status Mapping for Quota Exhaustion
    # -----------------------------------------------------------------------
    def test_evaluate_endpoint_maps_quota_exceeded_to_429(self):
        """Verify GeminiQuotaExceededError maps to HTTP 429 with Retry-After header and clean message."""
        with patch("main.run_all_judges", new_callable=AsyncMock) as mock_judges:
            mock_judges.side_effect = gemini_service.GeminiQuotaExceededError("API quota exceeded", retry_after=12)
            response = self.client.post(
                "/evaluate",
                data={"attack_mode": "false"},
                files={"readme": ("README.md", b"# Test Project\nIdea description", "text/plain")},
            )
            self.assertEqual(response.status_code, 429)
            data = response.json()
            self.assertIn("rate limit or quota exceeded", data.get("detail"))
            self.assertEqual(response.headers.get("retry-after"), "12")
            # Ensure no internal leaks
            self.assertNotIn("Traceback", response.text)
            self.assertNotIn("API_KEY", response.text)

    def test_evaluate_endpoint_maps_quota_runtime_error_to_429(self):
        """Verify a quota error wrapped in RuntimeError also maps to HTTP 429 instead of 502."""
        with patch("main.run_all_judges", new_callable=AsyncMock) as mock_judges:
            mock_judges.side_effect = RuntimeError("ResourceExhausted: 429 You exceeded your current quota. Please retry in 8s.")
            response = self.client.post(
                "/evaluate",
                data={"attack_mode": "false"},
                files={"readme": ("README.md", b"# Test Project\nIdea description", "text/plain")},
            )
            self.assertEqual(response.status_code, 429)
            self.assertIn("rate limit or quota exceeded", response.json().get("detail"))
            self.assertGreaterEqual(int(response.headers.get("retry-after", "0")), 8)

    # -----------------------------------------------------------------------
    # 9. Concurrent Judge Calls and Safe Sibling Cancellation under Rate Limiting
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_run_all_judges_controlled_concurrency(self):
        """Verify specialist judges obey configured JUDGE_CONCURRENCY to prevent quota bursting."""
        from judges import run_all_judges

        active_judges = 0
        max_active_judges = 0

        async def mock_judge_impl(prompt, name):
            nonlocal active_judges, max_active_judges
            active_judges += 1
            max_active_judges = max(max_active_judges, active_judges)
            await asyncio.sleep(0.05)
            active_judges -= 1
            if "Chief" in name:
                return {
                    "overall_score": 8.0,
                    "final_verdict": "Solid submission",
                    "top_strengths": ["Tech"],
                    "top_improvements": ["Scale"],
                    "improvement_roadmap": ["Iterate"],
                    "judge_questions": ["Question 1?"],
                }
            return {
                "score": 7,
                "strengths": ["Good concept"],
                "weaknesses": ["Needs testing"],
                "comments": f"{name} feedback",
            }

        with patch.dict(os.environ, {"JUDGE_CONCURRENCY": "2"}):
            with patch("judges.call_judge", side_effect=mock_judge_impl):
                results = await run_all_judges("Project sample context")

                # Specialist judges concurrency should not exceed 2
                self.assertLessEqual(max_active_judges, 2)
                self.assertIn("innovation", results)
                self.assertIn("technical", results)
                self.assertIn("business", results)
                self.assertIn("presentation", results)
                self.assertIn("chief_judge", results)
                self.assertIn("consensus", results)

    @pytest.mark.asyncio
    async def test_run_all_judges_cancels_siblings_on_quota_error(self):
        """Verify sibling judges are cancelled immediately if one judge hits exhausted quota."""
        from judges import run_all_judges

        async def fast_quota_fail(prompt, name):
            if "Technical" in name:
                await asyncio.sleep(0.01)
                raise gemini_service.GeminiQuotaExceededError("Quota exhausted", retry_after=15)
            # Other judges take long time
            await asyncio.sleep(5.0)
            return {"score": 7}

        with patch.dict(os.environ, {"JUDGE_CONCURRENCY": "2"}):
            with patch("judges.call_judge", side_effect=fast_quota_fail):
                start_time = asyncio.get_running_loop().time()
                with pytest.raises(gemini_service.GeminiQuotaExceededError) as exc_info:
                    await run_all_judges("Project context")

                elapsed = asyncio.get_running_loop().time() - start_time
                # Siblings must be cancelled promptly, not waiting 5 seconds
                self.assertLess(elapsed, 1.0)
                self.assertEqual(exc_info.value.retry_after, 15)


if __name__ == "__main__":
    unittest.main()
