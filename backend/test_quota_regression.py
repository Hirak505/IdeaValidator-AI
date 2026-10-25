"""
test_quota_regression.py — Comprehensive regression tests for Gemini quota handling:
1. Parsing Google's retry_delay correctly without retrying early.
2. Failing gracefully when provider-requested retry delay exceeds configured maximum.
3. Treating confirmed daily quota exhaustion as terminal without retrying (fails fast).
4. Preventing undispatched judges from starting once a terminal error fails the evaluation.
5. Safe cancellation of outstanding async tasks without leaking thread capacity semaphores.
6. Preventing duplicate submissions while an evaluation is already running (HTTP 409).
7. Preserving distinctions between RPM rate limiting, daily quota, service unavailability, and timeouts.
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
    GeminiQuotaExceededError,
    GeminiServiceUnavailableError,
    GeminiPermissionError,
    extract_provider_retry_delay,
    extract_retry_delay,
    is_daily_quota_error,
    is_quota_error,
    call_judge,
    clear_daily_quota_exhaustion,
    mark_daily_quota_exhausted,
    is_daily_quota_exhausted,
    get_configured_model_name,
    get_daily_quota_info,
)
import judges
from judges import run_all_judges
import main
from main import app, _evaluation_jobs, _evaluation_jobs_lock


class TestRetryDelayHandling(unittest.IsolatedAsyncioTestCase):
    """Regression tests for parsing Google's retry delay and never retrying early."""

    def test_extract_provider_retry_delay_formats(self):
        # 1. Standard Google 51.4s message
        msg1 = (
            "429 Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, "
            "limit: 5, model: gemini-3.6-flash. Please retry in 51.415001046s. "
            "quota_id: 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier', retry_delay { seconds: 51 nanos: 415001046 }"
        )
        delay1 = extract_provider_retry_delay(Exception(msg1))
        self.assertIsNotNone(delay1)
        self.assertAlmostEqual(delay1, 51.415001046, places=4)

        # 2. Pure protobuf text block
        msg2 = "ResourceExhausted: [retry_delay {\n  seconds: 51\n  nanos: 500000000\n}]"
        delay2 = extract_provider_retry_delay(Exception(msg2))
        self.assertIsNotNone(delay2)
        self.assertAlmostEqual(delay2, 51.5, places=4)

        # 3. Seconds attribute / Duration
        mock_exc = MagicMock(spec=Exception)
        mock_duration = MagicMock()
        mock_duration.total_seconds.return_value = 51.2
        mock_exc.retry_delay = mock_duration
        delay3 = extract_provider_retry_delay(mock_exc)
        self.assertEqual(delay3, 51.2)

        # 4. None when no provider hint
        delay4 = extract_provider_retry_delay(Exception("Generic 429 without delay"))
        self.assertIsNone(delay4)

    def test_extract_retry_delay_never_returns_less_than_provider_requested(self):
        """extract_retry_delay must NEVER clamp down a provider-requested delay below provider value."""
        msg = "ResourceExhausted: 429 Please retry in 51.4s"
        exc = Exception(msg)

        # Even with max_delay=30.0, the returned delay must NOT be clamped to 30.0!
        delay = extract_retry_delay(exc, max_delay=30.0)
        self.assertGreaterEqual(delay, 51.4)

    @pytest.mark.asyncio
    async def test_requested_delay_exceeding_max_delay_fails_gracefully_without_retrying_early(self):
        """
        When Google asks for 51.4s, and max_delay is 30.0s:
        Backend must NOT retry early after 30s.
        It must fail gracefully immediately without sleeping or retrying.
        """
        mock_model = MagicMock()
        err_msg = (
            "429 Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, "
            "limit: 5, model: gemini-3.6-flash. Please retry in 51.4s."
        )
        mock_model.generate_content.side_effect = Exception(err_msg)

        with patch.object(gemini_service, "get_model", return_value=mock_model):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                with patch.dict(os.environ, {"GEMINI_MAX_RETRY_DELAY": "30.0", "GEMINI_MAX_RETRIES": "3"}):
                    with self.assertRaises(GeminiQuotaExceededError) as ctx:
                        await call_judge("Test Prompt", "Technical Judge")

                    # Must NOT have retried early!
                    self.assertEqual(mock_model.generate_content.call_count, 1)
                    # Must NOT have slept 30s to retry early
                    mock_sleep.assert_not_called()
                    # Error must convey the provider's requested delay
                    self.assertGreaterEqual(ctx.exception.retry_after, 51)
                    self.assertFalse(ctx.exception.is_daily)

    @pytest.mark.asyncio
    async def test_requested_delay_within_max_delay_sleeps_full_requested_delay(self):
        """When requested delay <= max_delay, it waits at least the requested delay and retries."""
        mock_model = MagicMock()
        err_msg = "ResourceExhausted: 429 Please retry in 5.0s"
        success_resp = MagicMock()
        success_resp.text = '{"score": 8, "comments": "Good", "strengths": ["Fast"], "weaknesses": ["None"]}'

        mock_model.generate_content.side_effect = [Exception(err_msg), success_resp]

        with patch.object(gemini_service, "get_model", return_value=mock_model):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                with patch.dict(os.environ, {"GEMINI_MAX_RETRY_DELAY": "30.0", "GEMINI_MAX_RETRIES": "3"}):
                    res = await call_judge("Test Prompt", "Innovation Judge")
                    self.assertEqual(res["score"], 8)
                    self.assertEqual(mock_model.generate_content.call_count, 2)
                    mock_sleep.assert_called_once()
                    slept = mock_sleep.call_args[0][0]
                    # Must never sleep less than the requested 5.0s
                    self.assertGreaterEqual(slept, 5.0)


class TestDailyQuotaFailFast(unittest.IsolatedAsyncioTestCase):
    """Regression tests for terminal daily quota exhaustion handling."""

    def test_daily_quota_detection_patterns(self):
        # 1. Real Google log pattern with limit: 20
        msg_daily = (
            "429 Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, "
            "limit: 20, model: gemini-3.6-flash. Please retry in 13h52m20s (seconds: 49940)"
        )
        self.assertTrue(is_daily_quota_error(Exception(msg_daily)))

        # 2. Daily limit 20 without hour string
        msg_daily_2 = (
            "ResourceExhausted: 429 Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, "
            "limit: 20, model: gemini-3.6-flash."
        )
        self.assertTrue(is_daily_quota_error(Exception(msg_daily_2)))

        # 3. Explicit GenerateRequestsPerDay
        msg_daily_3 = "ResourceExhausted: GenerateRequestsPerDayPerProjectPerModel-FreeTier limit: 20"
        self.assertTrue(is_daily_quota_error(Exception(msg_daily_3)))

        # 4. RPM 5 requests is NOT daily
        msg_rpm = (
            "429 Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, "
            "limit: 5, model: gemini-3.6-flash. Please retry in 51.4s. "
            "quota_id: 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier', retry_delay { seconds: 51 }"
        )
        self.assertFalse(is_daily_quota_error(Exception(msg_rpm)))

    @pytest.mark.asyncio
    async def test_daily_quota_exhaustion_is_terminal_fails_fast_without_retries(self):
        """Confirmed daily quota exhaustion must never be retried."""
        mock_model = MagicMock()
        daily_err = (
            "429 Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, "
            "limit: 20, model: gemini-3.6-flash. Please retry in 13h52m20s (seconds: 49940)"
        )
        mock_model.generate_content.side_effect = Exception(daily_err)

        with patch.object(gemini_service, "get_model", return_value=mock_model):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                with patch.dict(os.environ, {"GEMINI_MAX_RETRIES": "3"}):
                    with self.assertRaises(GeminiQuotaExceededError) as ctx:
                        await call_judge("Test Prompt", "Technical Judge")

                    self.assertTrue(ctx.exception.is_daily)
                    self.assertEqual(mock_model.generate_content.call_count, 1)
                    mock_sleep.assert_not_called()


class TestJudgeSchedulingAndCancellation(unittest.IsolatedAsyncioTestCase):
    """Regression tests for judge scheduling, preventing extra dispatches, and cancellation."""

    @pytest.mark.asyncio
    async def test_undispatched_judges_prevented_from_starting_after_failure(self):
        """
        When Judge 1 fails with a terminal error, undispatched judges waiting in queue
        must NEVER be dispatched to the provider.
        """
        dispatched_judges = []

        async def mock_call_judge(prompt, name, abort_event=None):
            dispatched_judges.append(name)
            if "Innovation" in name:
                # Fails with daily quota
                raise GeminiQuotaExceededError("Daily quota limit reached", retry_after=86400, is_daily=True)
            # Other judges would succeed if dispatched
            await asyncio.sleep(0.5)
            return {"score": 8, "comments": "ok", "strengths": ["ok"], "weaknesses": ["ok"]}

        # Run with conservative concurrency=1 (sequential)
        with patch.dict(os.environ, {"JUDGE_CONCURRENCY": "1"}):
            with patch("judges.call_judge", side_effect=mock_call_judge):
                with self.assertRaises(GeminiQuotaExceededError):
                    await run_all_judges("Sample Project Context")

        # ONLY Innovation Judge was dispatched; undispatched judges were blocked!
        self.assertEqual(dispatched_judges, ["Innovation Judge"])

    @pytest.mark.asyncio
    async def test_cancelled_judge_terminates_immediately_and_cleans_up_capacity(self):
        """Verifies that an in-flight judge task when cancelled exits promptly without extra retries."""
        sem = gemini_service.get_concurrency_semaphore()
        initial_capacity = sem._value

        async def cancel_after_delay(task):
            await asyncio.sleep(0.05)
            task.cancel()

        mock_model = MagicMock()
        # Simulate blocking generation in worker thread
        def slow_generate(prompt, request_options=None):
            time.sleep(0.2)
            return MagicMock(text='{"score": 8, "comments": "ok", "strengths": ["ok"], "weaknesses": ["ok"]}')

        mock_model.generate_content.side_effect = slow_generate

        with patch.object(gemini_service, "get_model", return_value=mock_model):
            loop = asyncio.get_running_loop()
            task = loop.create_task(call_judge("Prompt", "Technical Judge"))
            loop.create_task(cancel_after_delay(task))

            with self.assertRaises(asyncio.CancelledError):
                await task

            # Wait for thread pool worker to finish and release capacity
            await asyncio.sleep(0.3)
            # Semaphore capacity must be fully restored (no resource leaks)
            self.assertEqual(sem._value, initial_capacity)


class TestDuplicateSubmissionPrevention(unittest.TestCase):
    """Regression tests for preventing duplicate evaluation submissions while one is running."""

    def setUp(self):
        self.client = TestClient(app)
        main._request_records.clear()
        with _evaluation_jobs_lock:
            _evaluation_jobs.clear()

    def tearDown(self):
        main._request_records.clear()
        with _evaluation_jobs_lock:
            _evaluation_jobs.clear()

    def test_duplicate_async_submission_rejected_with_409(self):
        """Submitting a second evaluation while one is running returns 409 Conflict."""
        with patch("main.asyncio.create_task") as mock_task:
            # 1. First submission succeeds (202)
            resp1 = self.client.post(
                "/evaluate/async",
                data={"attack_mode": "false"},
                files={"readme": ("README.md", b"# Idea\nContext text", "text/plain")},
            )
            self.assertEqual(resp1.status_code, 202)
            job_id = resp1.json()["job_id"]

            # 2. Second submission while first is still 'running' returns 409
            resp2 = self.client.post(
                "/evaluate/async",
                data={"attack_mode": "false"},
                files={"readme": ("README.md", b"# Duplicate Idea\nContext text", "text/plain")},
            )
            self.assertEqual(resp2.status_code, 409)
            data2 = resp2.json()
            self.assertIn("already running", data2["detail"])
            self.assertEqual(data2["job_id"], job_id)

    def test_new_submission_allowed_after_job_finishes(self):
        """Once the running job reaches completed or failed, new submissions are accepted."""
        with patch("main.asyncio.create_task") as mock_task:
            resp1 = self.client.post(
                "/evaluate/async",
                data={"attack_mode": "false"},
                files={"readme": ("README.md", b"# Idea\nContext text", "text/plain")},
            )
            self.assertEqual(resp1.status_code, 202)
            job_id = resp1.json()["job_id"]

            # Mark job completed
            with _evaluation_jobs_lock:
                _evaluation_jobs[job_id]["status"] = "completed"

            # Second submission is now accepted
            resp2 = self.client.post(
                "/evaluate/async",
                data={"attack_mode": "false"},
                files={"readme": ("README.md", b"# New Idea\nContext text", "text/plain")},
            )
            self.assertEqual(resp2.status_code, 202)


class TestErrorDistinction(unittest.TestCase):
    """Regression test preserving distinctions between RPM, daily quota, 503, and 504."""

    def setUp(self):
        self.client = TestClient(app)
        main._request_records.clear()
        with _evaluation_jobs_lock:
            _evaluation_jobs.clear()

    def test_distinction_rpm_daily_unavailable_timeout(self):
        # 1. Daily Quota: 429 with is_daily=True -> daily_quota_exceeded
        with _evaluation_jobs_lock:
            _evaluation_jobs["eval_daily"] = {
                "job_id": "eval_daily",
                "status": "failed",
                "category": "daily_quota_exceeded",
                "stage": "Specialist Judges",
                "error": "Gemini API daily request quota exceeded for this model.",
                "status_code": 429,
            }
        resp_daily = self.client.get("/evaluate/status/eval_daily").json()
        self.assertEqual(resp_daily["category"], "daily_quota_exceeded")
        self.assertEqual(resp_daily["error_code"], 429)

        # 2. Transient RPM: 429 with is_daily=False -> quota_exceeded
        with _evaluation_jobs_lock:
            _evaluation_jobs["eval_rpm"] = {
                "job_id": "eval_rpm",
                "status": "failed",
                "category": "quota_exceeded",
                "stage": "Specialist Judges",
                "error": "AI evaluation rate limit or quota exceeded.",
                "status_code": 429,
            }
        resp_rpm = self.client.get("/evaluate/status/eval_rpm").json()
        self.assertEqual(resp_rpm["category"], "quota_exceeded")
        self.assertEqual(resp_rpm["error_code"], 429)

        # 3. 503 Service Unavailable -> service_unavailable
        with _evaluation_jobs_lock:
            _evaluation_jobs["eval_503"] = {
                "job_id": "eval_503",
                "status": "failed",
                "category": "service_unavailable",
                "stage": "Specialist Judges",
                "error": "Gemini AI service is temporarily unavailable (503).",
                "status_code": 503,
            }
        resp_503 = self.client.get("/evaluate/status/eval_503").json()
        self.assertEqual(resp_503["category"], "service_unavailable")
        self.assertEqual(resp_503["error_code"], 503)

        # 4. 504 Timeout -> timeout
        with _evaluation_jobs_lock:
            _evaluation_jobs["eval_timeout"] = {
                "job_id": "eval_timeout",
                "status": "failed",
                "category": "timeout",
                "stage": "Chief Judge",
                "error": "AI evaluation timed out during stage 'Chief Judge'.",
                "status_code": 504,
            }
        resp_timeout = self.client.get("/evaluate/status/eval_timeout").json()
        self.assertEqual(resp_timeout["category"], "timeout")
        self.assertEqual(resp_timeout["error_code"], 504)


class TestDailyQuotaExhaustionAndModelConfig(unittest.IsolatedAsyncioTestCase):
    """
    Mocked tests verifying:
    1. Daily quota errors trigger zero additional retries.
    2. Daily quota errors prevent further judge dispatch.
    3. Pre-dispatch check detects daily quota exhaustion before making API calls.
    4. Switching models via GEMINI_MODEL allows evaluations to proceed without code changes.
    5. Clean diagnostic messages distinguish daily quota from RPM, malformed JSON, and provider errors.
    """

    def setUp(self):
        clear_daily_quota_exhaustion()
        self.client = TestClient(app)
        main._request_records.clear()
        with _evaluation_jobs_lock:
            _evaluation_jobs.clear()

    def tearDown(self):
        clear_daily_quota_exhaustion()
        main._request_records.clear()
        with _evaluation_jobs_lock:
            _evaluation_jobs.clear()

    @pytest.mark.asyncio
    async def test_daily_quota_error_triggers_zero_additional_retries(self):
        """When a daily quota error occurs, it must fail immediately on attempt 1 with zero retries."""
        mock_model = MagicMock()
        mock_model.model_name = "gemini-3.8-flash"
        daily_err = (
            "429 Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, "
            "limit: 20, model: gemini-3.8-flash. Please retry in 13h52m20s (seconds: 49940)"
        )
        mock_model.generate_content.side_effect = Exception(daily_err)

        with patch.object(gemini_service, "get_model", return_value=mock_model):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                with patch.dict(os.environ, {"GEMINI_MAX_RETRIES": "5", "GEMINI_MODEL": "gemini-3.8-flash"}):
                    with self.assertRaises(GeminiQuotaExceededError) as ctx:
                        await call_judge("Test Prompt", "Technical Judge")

                    # Crucial: Exactly 1 call, zero additional retries!
                    self.assertEqual(mock_model.generate_content.call_count, 1)
                    mock_sleep.assert_not_called()

                    # Exception must capture daily flag, model, and actionable retry guidance
                    self.assertTrue(ctx.exception.is_daily)
                    self.assertEqual(ctx.exception.model, "gemini-3.8-flash")
                    self.assertGreaterEqual(ctx.exception.retry_after, 49900)
                    self.assertIn("gemini-3.8-flash", str(ctx.exception))
                    self.assertIn("GEMINI_MODEL", ctx.exception.retry_guidance or "")

                    # State tracking must now mark the model daily quota as exhausted
                    self.assertTrue(is_daily_quota_exhausted("gemini-3.8-flash"))

    @pytest.mark.asyncio
    async def test_pre_dispatch_daily_quota_exhaustion_blocks_judge_without_calling_model(self):
        """If daily quota exhaustion was previously detected, call_judge must abort with zero model calls."""
        mark_daily_quota_exhausted("gemini-3.8-flash", retry_after=49940)
        self.assertTrue(is_daily_quota_exhausted("gemini-3.8-flash"))

        mock_model = MagicMock()
        mock_model.model_name = "gemini-3.8-flash"

        with patch.object(gemini_service, "get_model", return_value=mock_model):
            with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-3.8-flash"}):
                with self.assertRaises(GeminiQuotaExceededError) as ctx:
                    await call_judge("Test Prompt", "Innovation Judge")

                # The provider model must NEVER have been called!
                self.assertEqual(mock_model.generate_content.call_count, 0)
                self.assertTrue(ctx.exception.is_daily)
                self.assertEqual(ctx.exception.model, "gemini-3.8-flash")
                self.assertIn("prevented", str(ctx.exception).lower())

    @pytest.mark.asyncio
    async def test_daily_quota_prevents_further_judge_dispatch_in_pipeline(self):
        """When an in-flight judge encounters daily quota exhaustion, remaining queued judges and Chief Judge must not be dispatched."""
        dispatched_judges = []

        async def mock_call_judge(prompt, name, abort_event=None):
            dispatched_judges.append(name)
            if "Innovation" in name:
                mark_daily_quota_exhausted("gemini-3.8-flash", retry_after=86400)
                if abort_event:
                    abort_event.set()
                raise GeminiQuotaExceededError(
                    "Daily quota exceeded for model gemini-3.8-flash",
                    retry_after=86400,
                    is_daily=True,
                    model="gemini-3.8-flash",
                )
            await asyncio.sleep(0.2)
            return {"score": 8, "comments": "ok", "strengths": ["ok"], "weaknesses": ["ok"]}

        with patch.dict(os.environ, {"JUDGE_CONCURRENCY": "1", "GEMINI_MODEL": "gemini-3.8-flash"}):
            with patch("judges.call_judge", side_effect=mock_call_judge):
                with self.assertRaises(GeminiQuotaExceededError):
                    await run_all_judges("Project Pitch Context")

        # ONLY Innovation Judge was dispatched; Technical, Business, Presentation, and Chief were prevented!
        self.assertEqual(dispatched_judges, ["Innovation Judge"])

    @pytest.mark.asyncio
    async def test_pipeline_aborts_immediately_when_daily_quota_already_exhausted(self):
        """run_all_judges must abort before scheduling any specialist tasks if model daily quota is already exhausted."""
        mark_daily_quota_exhausted("gemini-3.8-flash", retry_after=3600)
        dispatched_judges = []

        async def mock_call_judge(prompt, name, abort_event=None):
            dispatched_judges.append(name)
            return {"score": 9, "comments": "ok", "strengths": ["ok"], "weaknesses": ["ok"]}

        with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-3.8-flash"}):
            with patch("judges.call_judge", side_effect=mock_call_judge):
                with self.assertRaises(GeminiQuotaExceededError) as ctx:
                    await run_all_judges("Project Pitch Context")

                self.assertTrue(ctx.exception.is_daily)
                self.assertEqual(ctx.exception.model, "gemini-3.8-flash")
                self.assertEqual(len(dispatched_judges), 0)

    @pytest.mark.asyncio
    async def test_switching_model_via_env_var_allows_evaluation_to_proceed(self):
        """Switching GEMINI_MODEL allows evaluating with the new model even if another model's daily quota was exhausted."""
        # Exhaust gemini-3.8-flash
        mark_daily_quota_exhausted("gemini-3.8-flash", retry_after=50000)
        self.assertTrue(is_daily_quota_exhausted("gemini-3.8-flash"))

        # Switch to gemini-1.5-flash via environment variable
        with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-1.5-flash"}):
            self.assertEqual(get_configured_model_name(), "gemini-1.5-flash")
            self.assertFalse(is_daily_quota_exhausted("gemini-1.5-flash"))

            mock_model = MagicMock()
            mock_model.model_name = "gemini-1.5-flash"
            mock_resp = MagicMock()
            mock_resp.text = '{"score": 8, "comments": "Good", "strengths": ["Clear"], "weaknesses": ["None"]}'
            mock_resp.candidates = [MagicMock(finish_reason="STOP")]
            mock_model.generate_content.return_value = mock_resp

            with patch.object(gemini_service, "get_model", return_value=mock_model):
                result = await call_judge("Evaluate idea", "Business Judge")

            self.assertEqual(result["score"], 8)
            self.assertEqual(mock_model.generate_content.call_count, 1)

    def test_clear_message_distinguishes_daily_quota_from_rpm_malformed_and_provider_errors(self):
        """Verify API status response clearly distinguishes daily quota from RPM, malformed JSON, and 503."""
        secret_key = "AIzaSySecretApiKeyMustNotLeak"

        # 1. Daily Quota: HTTP 429, daily_quota_exceeded, mentions model, reset, and GEMINI_MODEL guidance
        with _evaluation_jobs_lock:
            _evaluation_jobs["job_daily"] = {
                "job_id": "job_daily",
                "status": "failed",
                "category": "daily_quota_exceeded",
                "stage": "Specialist Judges",
                "error": "Gemini API daily request quota exceeded for model 'gemini-3.8-flash'. Please wait for the daily quota reset or configure a billing-enabled API key or alternate model.",
                "model": "gemini-3.8-flash",
                "retry_after": 49940,
                "retry_guidance": "Daily request quota is exhausted for model 'gemini-3.8-flash'. Quota will reset in ~13h 52m. To resume immediately, switch to another supported model by setting GEMINI_MODEL in backend/.env.",
                "status_code": 429,
            }

        resp_daily = self.client.get("/evaluate/status/job_daily").json()
        self.assertEqual(resp_daily["category"], "daily_quota_exceeded")
        self.assertEqual(resp_daily["error_code"], 429)
        self.assertEqual(resp_daily["model"], "gemini-3.8-flash")
        self.assertIn("daily", resp_daily["detail"].lower())
        self.assertIn("gemini-3.8-flash", resp_daily["detail"])
        self.assertIn("gemini_model", resp_daily["retry_guidance"].lower())
        self.assertNotIn("per-minute", resp_daily["detail"].lower())

        # 2. Transient RPM Limit: HTTP 429, quota_exceeded, mentions per-minute delay
        with _evaluation_jobs_lock:
            _evaluation_jobs["job_rpm"] = {
                "job_id": "job_rpm",
                "status": "failed",
                "category": "quota_exceeded",
                "stage": "Specialist Judges",
                "error": "AI evaluation temporary rate limit exceeded for model 'gemini-3.8-flash'.",
                "model": "gemini-3.8-flash",
                "retry_after": 15,
                "retry_guidance": "Per-minute rate limit (RPM) temporarily reached for model 'gemini-3.8-flash'. Please wait 15s before retrying.",
                "status_code": 429,
            }

        resp_rpm = self.client.get("/evaluate/status/job_rpm").json()
        self.assertEqual(resp_rpm["category"], "quota_exceeded")
        self.assertEqual(resp_rpm["error_code"], 429)
        self.assertIn("temporary", resp_rpm["detail"].lower())
        self.assertNotIn("daily", resp_rpm["detail"].lower())

        # 3. Malformed JSON: HTTP 502, malformed_response
        with _evaluation_jobs_lock:
            _evaluation_jobs["job_malformed"] = {
                "job_id": "job_malformed",
                "status": "failed",
                "category": "malformed_response",
                "stage": "Specialist Judges",
                "error": "AI judge returned an unparseable response format. Please try again.",
                "status_code": 502,
                "diagnostic": "ModelResponseError (502): reason=malformed_json",
            }

        resp_malformed = self.client.get("/evaluate/status/job_malformed").json()
        self.assertEqual(resp_malformed["category"], "malformed_response")
        self.assertEqual(resp_malformed["error_code"], 502)
        self.assertIn("unparseable response format", resp_malformed["detail"].lower())
        self.assertNotIn("quota", resp_malformed["detail"].lower())

        # 4. Service Unavailable: HTTP 503, service_unavailable
        with _evaluation_jobs_lock:
            _evaluation_jobs["job_503"] = {
                "job_id": "job_503",
                "status": "failed",
                "category": "service_unavailable",
                "stage": "Specialist Judges",
                "error": "Gemini AI service is temporarily unavailable (503 Service Unavailable). Please try again in a few moments.",
                "status_code": 503,
            }

        resp_503 = self.client.get("/evaluate/status/job_503").json()
        self.assertEqual(resp_503["category"], "service_unavailable")
        self.assertEqual(resp_503["error_code"], 503)
        self.assertIn("temporarily unavailable", resp_503["detail"].lower())
        self.assertNotIn("quota", resp_503["detail"].lower())

        # 5. Verify no sensitive secrets leak in any response
        for resp in [resp_daily, resp_rpm, resp_malformed, resp_503]:
            raw_str = str(resp)
            self.assertNotIn(secret_key, raw_str)


if __name__ == "__main__":
    unittest.main()
