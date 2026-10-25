"""
test_json_extraction.py — Unit tests for the improved JSON extraction, schema
validation, diagnostic logging, and error handling in gemini_service.py.

Covers:
- Valid JSON (direct parse)
- JSON inside Markdown code fences (```json ... ```)
- Explanatory text surrounding JSON
- Deeply nested JSON objects (the Technical Judge root cause)
- Malformed / truncated JSON
- Empty responses
- Missing required fields
- ModelResponseError diagnostics
- call_judge empty / blocked response handling
- Diagnostic logging (_log_response_diagnostics)

All tests mock model responses — no live API calls are made.
"""

import asyncio
import json
import logging
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import gemini_service
from gemini_service import (
    ModelResponseError,
    _extract_outermost_json_object,
    _log_response_diagnostics,
    extract_json_from_response,
    validate_judge_schema,
)


# ---------------------------------------------------------------------------
# Sample payloads
# ---------------------------------------------------------------------------

VALID_TECHNICAL_JUDGE_JSON = {
    "score": 8,
    "confidence": 85,
    "evidence_quality": 75,
    "strengths": ["Clean modular code", "Well-designed API", "Good test coverage"],
    "weaknesses": ["Missing integration tests", "No CI/CD pipeline"],
    "comments": "Strong technical foundation with room for DevOps improvement.",
    "key_findings": [
        {
            "finding": "Uses FastAPI with async endpoints",
            "evidence": "backend/main.py imports FastAPI",
            "source": "Codebase",
            "evidence_type": "documented_fact",
            "confidence": 95,
        },
        {
            "finding": "No load testing results provided",
            "evidence": "Not directly verified",
            "source": "N/A",
            "evidence_type": "not_verified",
            "confidence": 40,
        },
    ],
}


class TestExtractOutermostJsonObject(unittest.TestCase):
    """Tests for the brace-balanced JSON object extractor."""

    def test_simple_object(self):
        result = _extract_outermost_json_object('{"a": 1}')
        self.assertEqual(result, '{"a": 1}')

    def test_nested_objects(self):
        text = '{"outer": {"inner": {"deep": 1}}}'
        result = _extract_outermost_json_object(text)
        self.assertEqual(result, text)

    def test_leading_text(self):
        text = 'Here is the result: {"score": 7}'
        result = _extract_outermost_json_object(text)
        self.assertEqual(result, '{"score": 7}')

    def test_trailing_text(self):
        text = '{"score": 7} Hope this helps!'
        result = _extract_outermost_json_object(text)
        self.assertEqual(result, '{"score": 7}')

    def test_braces_inside_strings(self):
        text = '{"msg": "use { and } carefully", "val": 1}'
        result = _extract_outermost_json_object(text)
        self.assertEqual(result, text)

    def test_escaped_quotes_in_strings(self):
        text = r'{"msg": "say \"hello\"", "val": 2}'
        result = _extract_outermost_json_object(text)
        self.assertEqual(result, text)

    def test_no_object(self):
        self.assertIsNone(_extract_outermost_json_object("no json here"))
        self.assertIsNone(_extract_outermost_json_object(""))

    def test_unbalanced_braces(self):
        self.assertIsNone(_extract_outermost_json_object('{"a": 1'))


class TestExtractJsonFromResponse(unittest.TestCase):
    """Tests for extract_json_from_response with various model output formats."""

    def test_valid_json_direct(self):
        """Plain JSON text with no fences or prose."""
        text = json.dumps(VALID_TECHNICAL_JUDGE_JSON)
        result = extract_json_from_response(text)
        self.assertEqual(result["score"], 8)
        self.assertEqual(len(result["key_findings"]), 2)

    def test_json_in_code_fence(self):
        """JSON wrapped in ```json ... ``` fences."""
        text = "```json\n" + json.dumps(VALID_TECHNICAL_JUDGE_JSON) + "\n```"
        result = extract_json_from_response(text)
        self.assertEqual(result["score"], 8)

    def test_json_fence_label_is_case_insensitive(self):
        text = "```JSON\n" + json.dumps(VALID_TECHNICAL_JUDGE_JSON) + "\n```"
        result = extract_json_from_response(text)
        self.assertEqual(result["score"], 8)

    def test_json_in_plain_code_fence(self):
        """JSON wrapped in ``` ... ``` fences (no language tag)."""
        text = "```\n" + json.dumps(VALID_TECHNICAL_JUDGE_JSON, indent=2) + "\n```"
        result = extract_json_from_response(text)
        self.assertEqual(result["score"], 8)

    def test_json_with_leading_explanation(self):
        """Model returns explanation before the JSON."""
        text = (
            "Here is my evaluation of the technical aspects:\n\n"
            + json.dumps(VALID_TECHNICAL_JUDGE_JSON)
        )
        result = extract_json_from_response(text)
        self.assertEqual(result["score"], 8)
        self.assertIn("strengths", result)

    def test_json_with_trailing_explanation(self):
        """Model returns JSON followed by trailing comments."""
        text = json.dumps(VALID_TECHNICAL_JUDGE_JSON) + "\n\nI hope this evaluation helps!"
        result = extract_json_from_response(text)
        self.assertEqual(result["score"], 8)

    def test_json_surrounded_by_text(self):
        """Model wraps JSON in prose on both sides."""
        text = (
            "Based on my analysis:\n\n"
            + json.dumps(VALID_TECHNICAL_JUDGE_JSON)
            + "\n\nPlease let me know if you need more details."
        )
        result = extract_json_from_response(text)
        self.assertEqual(result["score"], 8)

    def test_fenced_json_with_explanation(self):
        """Model writes prose, then fenced JSON, then more prose."""
        text = (
            "Here's the technical evaluation:\n\n"
            "```json\n"
            + json.dumps(VALID_TECHNICAL_JUDGE_JSON, indent=2)
            + "\n```\n\n"
            "This concludes the evaluation."
        )
        result = extract_json_from_response(text)
        self.assertEqual(result["score"], 8)

    def test_deeply_nested_json_in_fence(self):
        """Reproduce the root cause: nested key_findings inside code fences.

        The old non-greedy regex ``{.*?}`` would truncate at the first ``}``,
        producing invalid JSON for the Technical Judge's deeply nested output.
        """
        text = "```json\n" + json.dumps(VALID_TECHNICAL_JUDGE_JSON, indent=2) + "\n```"
        result = extract_json_from_response(text)
        self.assertEqual(result["score"], 8)
        self.assertEqual(len(result["key_findings"]), 2)
        self.assertEqual(result["key_findings"][0]["evidence_type"], "documented_fact")

    def test_whitespace_around_json(self):
        text = "   \n\n  " + json.dumps({"score": 5, "strengths": [], "weaknesses": [], "comments": "ok"}) + "  \n  "
        result = extract_json_from_response(text)
        self.assertEqual(result["score"], 5)

    def test_empty_string_raises(self):
        with pytest.raises(ModelResponseError) as exc_info:
            extract_json_from_response("", "models/gemini-3.6-flash")
        self.assertEqual(exc_info.value.reason, "empty_response")

    def test_whitespace_only_raises(self):
        with pytest.raises(ModelResponseError) as exc_info:
            extract_json_from_response("   \n\t  ")
        self.assertEqual(exc_info.value.reason, "empty_response")

    def test_none_raises(self):
        with pytest.raises(ModelResponseError) as exc_info:
            extract_json_from_response(None)
        self.assertEqual(exc_info.value.reason, "empty_response")

    def test_malformed_json_raises(self):
        with pytest.raises(ModelResponseError) as exc_info:
            extract_json_from_response('{"score": 8, "strengths": [', "models/gemini-3.6-flash")
        self.assertEqual(exc_info.value.reason, "malformed_json")
        self.assertTrue(len(exc_info.value.preview) > 0)

    def test_plain_text_no_json_raises(self):
        with pytest.raises(ModelResponseError) as exc_info:
            extract_json_from_response("I cannot evaluate this project due to content restrictions.")
        self.assertEqual(exc_info.value.reason, "malformed_json")

    def test_json_array_does_not_recover_inner_object(self):
        """A judge result must be a JSON object, not an array containing one."""
        with pytest.raises(ModelResponseError) as exc_info:
            extract_json_from_response('[{"score": 5}]', "models/gemini-3.6-flash")
        self.assertEqual(exc_info.value.reason, "invalid_json_root")

    def test_plain_array_no_object_raises(self):
        """A JSON array with no inner object is not a valid judge result."""
        with pytest.raises(ModelResponseError) as exc_info:
            extract_json_from_response('[1, 2, 3]')
        self.assertEqual(exc_info.value.reason, "invalid_json_root")

    def test_multiple_json_objects_are_rejected(self):
        text = '{"score": 5} and also {"score": 9}'
        with pytest.raises(ModelResponseError) as exc_info:
            extract_json_from_response(text)
        self.assertEqual(exc_info.value.reason, "malformed_json")


class TestValidateJudgeSchema(unittest.TestCase):
    """Tests for validate_judge_schema."""

    def test_valid_response(self):
        data = {
            "score": 7,
            "strengths": ["Good"],
            "weaknesses": ["Needs work"],
            "comments": "Solid effort.",
        }
        result = validate_judge_schema(data, "Technical Judge")
        self.assertEqual(result["score"], 7)

    def test_extra_fields_preserved(self):
        """Extra fields (key_findings, confidence, etc.) are not stripped."""
        data = {
            "score": 7,
            "strengths": ["a"],
            "weaknesses": ["b"],
            "comments": "c",
            "confidence": 80,
            "key_findings": [],
        }
        result = validate_judge_schema(data, "Technical Judge")
        self.assertEqual(result["confidence"], 80)

    def test_missing_score_raises(self):
        data = {"strengths": ["a"], "weaknesses": ["b"], "comments": "c"}
        with pytest.raises(ModelResponseError) as exc_info:
            validate_judge_schema(data, "Technical Judge")
        self.assertEqual(exc_info.value.reason, "missing_required_fields")
        self.assertIn("score", str(exc_info.value))

    def test_missing_multiple_fields_raises(self):
        data = {"score": 5}
        with pytest.raises(ModelResponseError) as exc_info:
            validate_judge_schema(data, "Technical Judge")
        self.assertEqual(exc_info.value.reason, "missing_required_fields")
        # Check that missing fields are listed
        msg = str(exc_info.value)
        self.assertIn("comments", msg)
        self.assertIn("strengths", msg)
        self.assertIn("weaknesses", msg)

    def test_empty_dict_raises(self):
        with pytest.raises(ModelResponseError) as exc_info:
            validate_judge_schema({}, "Innovation Judge")
        self.assertEqual(exc_info.value.reason, "missing_required_fields")

    def test_score_out_of_range_is_rejected(self):
        data = {
            "score": 11,
            "strengths": [],
            "weaknesses": [],
            "comments": "Out of range",
        }
        with pytest.raises(ModelResponseError) as exc_info:
            validate_judge_schema(data, "Innovation Judge")
        self.assertEqual(exc_info.value.reason, "invalid_field_values")

    def test_non_string_list_item_is_rejected(self):
        data = {
            "score": 7,
            "strengths": ["Original", 4],
            "weaknesses": [],
            "comments": "Good",
        }
        with pytest.raises(ModelResponseError) as exc_info:
            validate_judge_schema(data, "Innovation Judge")
        self.assertEqual(exc_info.value.reason, "invalid_field_types")


class TestModelResponseError(unittest.TestCase):
    """Tests for the ModelResponseError exception class."""

    def test_is_value_error_subclass(self):
        err = ModelResponseError("test", reason="blocked")
        self.assertIsInstance(err, ValueError)

    def test_attributes(self):
        err = ModelResponseError("msg", reason="empty_response", preview="abc")
        self.assertEqual(err.reason, "empty_response")
        self.assertEqual(err.preview, "abc")
        self.assertEqual(str(err), "msg")

    def test_default_attributes(self):
        err = ModelResponseError("msg")
        self.assertEqual(err.reason, "unknown")
        self.assertEqual(err.preview, "")


class TestLogResponseDiagnostics(unittest.TestCase):
    """Tests for _log_response_diagnostics."""

    def test_logs_finish_reason(self):
        response = MagicMock()
        candidate = MagicMock()
        candidate.finish_reason = "STOP"
        candidate.block_reason = None
        response.candidates = [candidate]
        response.prompt_feedback = MagicMock()
        response.prompt_feedback.block_reason = None
        response.text = '{"score": 5}'

        with patch.object(gemini_service.logger, "info") as mock_info:
            _log_response_diagnostics(response, "Technical Judge", "models/gemini-3.6-flash")
            self.assertIn("response_length", mock_info.call_args[0][0])
            self.assertIn("model=%s", mock_info.call_args[0][0])
            self.assertIn("models/gemini-3.6-flash", mock_info.call_args[0])
            self.assertIn("preview=%", mock_info.call_args[0][0])

    def test_warns_on_max_tokens(self):
        response = MagicMock()
        candidate = MagicMock()
        candidate.finish_reason = "MAX_TOKENS"
        candidate.block_reason = None
        response.candidates = [candidate]
        response.prompt_feedback = MagicMock()
        response.prompt_feedback.block_reason = None
        response.text = '{"score": 5}'

        with patch.object(gemini_service.logger, "warning") as mock_warn:
            _log_response_diagnostics(response, "Technical Judge")
            mock_warn.assert_called()
            self.assertIn("truncated", mock_warn.call_args[0][0])

    def test_warns_on_safety_block(self):
        response = MagicMock()
        candidate = MagicMock()
        candidate.finish_reason = "SAFETY"
        candidate.block_reason = "HARM_CATEGORY_DANGEROUS"
        response.candidates = [candidate]
        response.prompt_feedback = MagicMock()
        response.prompt_feedback.block_reason = None
        response.text = ""

        with patch.object(gemini_service.logger, "warning") as mock_warn:
            _log_response_diagnostics(response, "Technical Judge")
            mock_warn.assert_called()
            self.assertIn("blocked", mock_warn.call_args[0][0])

    def test_no_crash_on_broken_response(self):
        """Diagnostic logging must never crash even with a weird response object."""
        response = object()  # Has no attributes at all
        # Should not raise
        _log_response_diagnostics(response, "Technical Judge")


class TestCallJudgeErrorHandling(unittest.IsolatedAsyncioTestCase):
    """Tests for call_judge's handling of empty, blocked, and malformed responses."""

    @pytest.mark.asyncio
    async def test_empty_response_raises_model_response_error(self):
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = ""
        mock_response.candidates = []
        mock_response.prompt_feedback = MagicMock()
        mock_response.prompt_feedback.block_reason = None
        mock_model.generate_content.return_value = mock_response

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-12345678"}):
            with patch.object(gemini_service, "get_model", return_value=mock_model):
                with pytest.raises(ModelResponseError) as exc_info:
                    await gemini_service.call_judge("prompt", "Technical Judge")
                self.assertEqual(exc_info.value.reason, "empty_response")

    @pytest.mark.asyncio
    async def test_blocked_response_raises_model_response_error(self):
        mock_model = MagicMock()
        mock_response = MagicMock()
        # .text raises when response is blocked in some SDK versions
        type(mock_response).text = property(lambda self: (_ for _ in ()).throw(ValueError("blocked")))
        mock_response.candidates = []
        pf = MagicMock()
        pf.block_reason = "HARM_CATEGORY_DANGEROUS"
        mock_response.prompt_feedback = pf
        mock_model.generate_content.return_value = mock_response

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-12345678"}):
            with patch.object(gemini_service, "get_model", return_value=mock_model):
                with pytest.raises((ModelResponseError, ValueError)) as exc_info:
                    await gemini_service.call_judge("prompt", "Technical Judge")
                exc = exc_info.value
                if isinstance(exc, ModelResponseError):
                    self.assertIn(exc.reason, ("blocked", "empty_response"))

    @pytest.mark.asyncio
    async def test_malformed_json_logs_model_and_bounded_preview(self):
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "This is not JSON at all, just plain text."
        mock_response.candidates = [MagicMock(finish_reason="STOP", block_reason=None)]
        mock_response.prompt_feedback = MagicMock()
        mock_response.prompt_feedback.block_reason = None
        mock_model.generate_content.return_value = mock_response
        mock_model.model_name = "models/gemini-3.6-flash"

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-12345678"}):
            with patch.object(gemini_service, "get_model", return_value=mock_model):
                with patch.object(gemini_service.logger, "warning") as mock_warning:
                    with pytest.raises(ModelResponseError) as exc_info:
                        await gemini_service.call_judge("prompt", "Innovation Judge")
                    self.assertEqual(exc_info.value.reason, "malformed_json")
                    warning_text = " ".join(str(call.args) for call in mock_warning.call_args_list)
                    self.assertIn("response parsing failed", warning_text)
                    self.assertIn("models/gemini-3.6-flash", warning_text)
                    self.assertIn("not JSON", warning_text)

    @pytest.mark.asyncio
    async def test_truncated_response_is_rejected_even_if_json_is_complete(self):
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "score": 8,
            "strengths": ["Good"],
            "weaknesses": ["Needs work"],
            "comments": "Partial model completion",
        })
        mock_response.candidates = [MagicMock(finish_reason="MAX_TOKENS", block_reason=None)]
        mock_response.prompt_feedback = MagicMock(block_reason=None)
        mock_model.generate_content.return_value = mock_response

        with patch.object(gemini_service, "get_model", return_value=mock_model):
            with pytest.raises(ModelResponseError) as exc_info:
                await gemini_service.call_judge("prompt", "Innovation Judge")
        self.assertEqual(exc_info.value.reason, "truncated")
        self.assertEqual(mock_model.generate_content.call_count, 1)

    @pytest.mark.asyncio
    async def test_nonempty_safety_block_is_not_parsed_as_evaluation(self):
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "score": 8,
            "strengths": [],
            "weaknesses": [],
            "comments": "Partial blocked response",
        })
        mock_response.candidates = [MagicMock(finish_reason="SAFETY", block_reason=None)]
        mock_response.prompt_feedback = MagicMock(block_reason=None)
        mock_model.generate_content.return_value = mock_response

        with patch.object(gemini_service, "get_model", return_value=mock_model):
            with pytest.raises(ModelResponseError) as exc_info:
                await gemini_service.call_judge("prompt", "Innovation Judge")
        self.assertEqual(exc_info.value.reason, "blocked")

    @pytest.mark.asyncio
    async def test_missing_fields_raises_value_error(self):
        """Response is valid JSON but missing required 'score' field."""
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({"strengths": ["a"], "weaknesses": ["b"], "comments": "c"})
        mock_response.candidates = [MagicMock(finish_reason="STOP", block_reason=None)]
        mock_response.prompt_feedback = MagicMock()
        mock_response.prompt_feedback.block_reason = None
        mock_model.generate_content.return_value = mock_response

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-12345678"}):
            with patch.object(gemini_service, "get_model", return_value=mock_model):
                with patch.object(gemini_service.logger, "warning") as mock_warning:
                    with pytest.raises(ModelResponseError) as exc_info:
                        await gemini_service.call_judge("prompt", "Technical Judge")
                    self.assertIn("score", str(exc_info.value))
                    self.assertIn("schema validation failed", str(mock_warning.call_args))

    @pytest.mark.asyncio
    async def test_valid_fenced_response_succeeds(self):
        """A well-formed fenced JSON response should parse successfully."""
        valid_data = {
            "score": 7,
            "strengths": ["Good architecture"],
            "weaknesses": ["No tests"],
            "comments": "Decent technical work.",
            "confidence": 70,
            "evidence_quality": 65,
            "key_findings": [],
        }
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "```json\n" + json.dumps(valid_data, indent=2) + "\n```"
        mock_response.candidates = [MagicMock(finish_reason="STOP", block_reason=None)]
        mock_response.prompt_feedback = MagicMock()
        mock_response.prompt_feedback.block_reason = None
        mock_model.generate_content.return_value = mock_response

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-12345678"}):
            with patch.object(gemini_service, "get_model", return_value=mock_model):
                result = await gemini_service.call_judge("prompt", "Technical Judge")
                self.assertEqual(result["score"], 7)
                self.assertIn("strengths", result)

    @pytest.mark.asyncio
    async def test_call_judge_fenced_multiline_and_trailing_comma_succeeds(self):
        """call_judge succeeds when fenced JSON has unescaped newlines and trailing commas."""
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = (
            "```json\n"
            "{\n"
            '  "score": 9,\n'
            '  "strengths": ["s1",],\n'
            '  "weaknesses": ["w1"],\n'
            '  "comments": "Paragraph 1\nParagraph 2",\n'
            "}\n"
            "```"
        )
        mock_response.candidates = [MagicMock(finish_reason="STOP", block_reason=None)]
        mock_response.prompt_feedback = MagicMock(block_reason=None)
        mock_model.generate_content.return_value = mock_response

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-12345678"}):
            with patch.object(gemini_service, "get_model", return_value=mock_model):
                result = await gemini_service.call_judge("prompt", "Business Judge")
                self.assertEqual(result["score"], 9)
                self.assertIn("Paragraph 1\nParagraph 2", result["comments"])

    @pytest.mark.asyncio
    async def test_call_judge_logs_parsing_exception_and_300_char_preview(self):
        """call_judge logs exact failure diagnostics: judge/model, length, finish_reason, 300 preview, parsing exception."""
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"score": 8, "strengths": [' + "x" * 400
        mock_response.candidates = [MagicMock(finish_reason="STOP", block_reason=None)]
        mock_response.prompt_feedback = MagicMock(block_reason=None)
        mock_model.generate_content.return_value = mock_response
        mock_model.model_name = "models/gemini-3.6-flash"

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-12345678"}):
            with patch.object(gemini_service, "get_model", return_value=mock_model):
                with patch.object(gemini_service.logger, "warning") as mock_warning:
                    with pytest.raises(ModelResponseError) as exc_info:
                        await gemini_service.call_judge("prompt", "Technical Judge")
                    self.assertEqual(exc_info.value.reason, "malformed_json")
                    calls = " ".join(str(c.args) for c in mock_warning.call_args_list)
                    self.assertIn("response parsing failed", calls)
                    self.assertIn("models/gemini-3.6-flash", calls)
                    self.assertIn("parsing_exception", calls)
                    self.assertIn("JSONDecodeError", calls)
                    self.assertIn("preview=", calls)

    @pytest.mark.asyncio
    async def test_integer_finish_reason_max_tokens_detected_as_truncated(self):
        """Verify that integer finish_reason=2 from Google SDK candidate is classified as truncated."""
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"score": 8, "strengths": ["Incomplete'
        # Google SDK sets finish_reason as integer 2 (MAX_TOKENS)
        mock_response.candidates = [MagicMock(finish_reason=2, block_reason=None)]
        mock_response.prompt_feedback = MagicMock(block_reason=None)
        mock_model.generate_content.return_value = mock_response

        with patch.object(gemini_service, "get_model", return_value=mock_model):
            with pytest.raises(ModelResponseError) as exc_info:
                await gemini_service.call_judge("prompt", "Technical Judge")
        self.assertEqual(exc_info.value.reason, "truncated")

    @pytest.mark.asyncio
    async def test_integer_finish_reason_safety_detected_as_blocked(self):
        """Verify that integer finish_reason=3 from Google SDK candidate is classified as blocked."""
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"score": 1}'
        mock_response.candidates = [MagicMock(finish_reason=3, block_reason=None)]
        mock_response.prompt_feedback = MagicMock(block_reason=None)
        mock_model.generate_content.return_value = mock_response

        with patch.object(gemini_service, "get_model", return_value=mock_model):
            with pytest.raises(ModelResponseError) as exc_info:
                await gemini_service.call_judge("prompt", "Innovation Judge")
        self.assertEqual(exc_info.value.reason, "blocked")


class TestJsonExtractionRegression(unittest.TestCase):
    """Regression tests for previously persistent ModelResponseError causes."""

    def test_multiline_unescaped_newline_in_fenced_json(self):
        text = (
            "```json\n"
            "{\n"
            '  "score": 8,\n'
            '  "strengths": ["a"],\n'
            '  "weaknesses": ["b"],\n'
            '  "comments": "First line.\nSecond line."\n'
            "}\n"
            "```"
        )
        result = extract_json_from_response(text)
        self.assertEqual(result["score"], 8)
        self.assertEqual(result["comments"], "First line.\nSecond line.")

    def test_trailing_comma_in_fenced_json(self):
        text = (
            "```json\n"
            "{\n"
            '  "score": 8,\n'
            '  "strengths": ["a",],\n'
            '  "weaknesses": ["b"],\n'
            '  "comments": "Good",\n'
            "}\n"
            "```"
        )
        result = extract_json_from_response(text)
        self.assertEqual(result["score"], 8)

    def test_fenced_json_with_trailing_code_block(self):
        text = (
            "```json\n"
            '{"score": 8, "strengths": ["a"], "weaknesses": ["b"], "comments": "good"}\n'
            "```\n\n"
            "```python\n"
            "print('example')\n"
            "```"
        )
        result = extract_json_from_response(text)
        self.assertEqual(result["score"], 8)

    def test_parsing_exception_recorded_on_malformed_json(self):
        with pytest.raises(ModelResponseError) as exc_info:
            extract_json_from_response('{"score": 8, "broken": [')
        self.assertEqual(exc_info.value.reason, "malformed_json")
        self.assertIsNotNone(exc_info.value.parse_exception)
        self.assertIsInstance(exc_info.value.parse_exception, json.JSONDecodeError)

    def test_normalize_finish_reason(self):
        from gemini_service import _normalize_finish_reason
        self.assertEqual(_normalize_finish_reason(None), "")
        self.assertEqual(_normalize_finish_reason("STOP"), "STOP")
        self.assertEqual(_normalize_finish_reason("max_tokens"), "MAX_TOKENS")
        self.assertEqual(_normalize_finish_reason(1), "STOP")
        self.assertEqual(_normalize_finish_reason(2), "MAX_TOKENS")
        self.assertEqual(_normalize_finish_reason(3), "SAFETY")
        self.assertEqual(_normalize_finish_reason(4), "RECITATION")

        class MockEnum:
            def __init__(self, name, val):
                self.name = name
                self.val = val
            def __int__(self):
                return self.val

        self.assertEqual(_normalize_finish_reason(MockEnum("MAX_TOKENS", 2)), "MAX_TOKENS")


if __name__ == "__main__":
    unittest.main()
