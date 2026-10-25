"""
test_chief_judge_validation.py — Unit tests for Chief Judge response schema validation,
unambiguous field normalization, error handling, and diagnostics in IdeaValidator-AI.

Tests cover:
1. Valid Chief Judge canonical schema output
2. Chief Judge with unambiguous alternative field names (score, comments, strengths, weaknesses)
3. Chief Judge output wrapped in single wrapper dictionary (e.g. {"chief_judge": {...}})
4. Missing required fields (overall_score, final_verdict, top_strengths, top_improvements)
5. Incorrect field types (boolean/string score, non-string verdict, non-list strengths/improvements)
6. Malformed JSON response
7. Empty response
8. Truncated response (finish_reason=MAX_TOKENS)
9. Blocked response (block_reason=SAFETY)
10. run_chief_judge end-to-end integration with mock call_judge
"""

import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import gemini_service
from gemini_service import (
    ModelResponseError,
    validate_judge_schema,
    _unwrap_nested_dict,
    _normalize_alternative_fields,
)
from judges import run_chief_judge, _validate_chief_result


VALID_CHIEF_OUTPUT = {
    "overall_score": 7.8,
    "confidence": 88,
    "evidence_quality": 82,
    "final_verdict": "A well-structured platform with strong architecture and clear market potential.",
    "top_strengths": [
        "Modular backend architecture",
        "Clear competitive positioning",
        "Strong consensus across judges",
    ],
    "top_improvements": [
        "Add comprehensive automated integration tests",
        "Define concrete unit economics and pricing tiers",
        "Provide verifiable benchmark data",
    ],
    "improvement_roadmap": [
        "Implement end-to-end testing pipeline",
        "Run user validation interviews",
        "Refine market go-to-market plan",
    ],
    "judge_questions": [
        "How will you scale ingestion throughput under high load?",
        "What is your customer acquisition cost strategy?",
        "How do you prevent hallucinations in evaluation reports?",
        "What is the defensibility against established market players?",
        "What are your milestones for the next quarter?",
        "How do you plan to handle enterprise data governance?",
    ],
    "prioritized_roadmap": [
        {
            "priority": "P0",
            "title": "Establish automated test harness",
            "reason": "Crucial for reliable deployment and continuous delivery",
            "impact": "High",
            "effort": "Medium",
        }
    ],
    "differentiation": {
        "solution_category": "AI Evaluation Engine",
        "claimed_differentiators": ["Multi-judge adversarial consensus"],
        "differentiation_strengths": ["Comprehensive specialized perspectives"],
        "differentiation_gaps": ["Requires real-world validation data"],
        "unsupported_claims": [],
        "limitation_note": "Evaluated based on submitted documentation.",
    },
}


# ===========================================================================
# 1. Valid Chief Judge Schema Tests
# ===========================================================================

class TestValidChiefJudgeSchema(unittest.TestCase):
    """Test validation and normalization of valid Chief Judge responses."""

    def test_canonical_chief_judge_output_passes(self):
        """Standard valid Chief Judge response must validate successfully."""
        result = validate_judge_schema(dict(VALID_CHIEF_OUTPUT), "Chief Judge")
        self.assertEqual(result["overall_score"], 7.8)
        self.assertEqual(result["final_verdict"], VALID_CHIEF_OUTPUT["final_verdict"])
        self.assertEqual(len(result["top_strengths"]), 3)
        self.assertEqual(len(result["top_improvements"]), 3)

    def test_integer_overall_score_accepted(self):
        """Integer score (e.g. 8) should be accepted as valid number."""
        payload = dict(VALID_CHIEF_OUTPUT)
        payload["overall_score"] = 8
        result = validate_judge_schema(payload, "Chief Judge")
        self.assertEqual(result["overall_score"], 8)

    def test_numeric_string_overall_score_converted(self):
        """Numeric string score ('8.5') should be converted to float."""
        payload = dict(VALID_CHIEF_OUTPUT)
        payload["overall_score"] = "8.5"
        result = validate_judge_schema(payload, "Chief Judge")
        self.assertEqual(result["overall_score"], 8.5)

    def test_alternative_field_names_normalized(self):
        """Test unambiguous mapping: score -> overall_score, comments -> final_verdict, etc."""
        payload = {
            "score": 7.5,
            "comments": "Great work on this idea.",
            "strengths": ["Fast", "Modular"],
            "weaknesses": ["Needs more documentation"],
        }
        result = validate_judge_schema(payload, "Chief Judge")
        self.assertEqual(result["overall_score"], 7.5)
        self.assertEqual(result["final_verdict"], "Great work on this idea.")
        self.assertEqual(result["top_strengths"], ["Fast", "Modular"])
        self.assertEqual(result["top_improvements"], ["Needs more documentation"])

    def test_nested_under_chief_judge_wrapper(self):
        """Response nested under {'chief_judge': {...}} is automatically unwrapped."""
        payload = {"chief_judge": dict(VALID_CHIEF_OUTPUT)}
        result = validate_judge_schema(payload, "Chief Judge")
        self.assertEqual(result["overall_score"], 7.8)

    def test_nested_under_evaluation_wrapper(self):
        """Response nested under {'evaluation': {...}} is automatically unwrapped."""
        payload = {"evaluation": dict(VALID_CHIEF_OUTPUT)}
        result = validate_judge_schema(payload, "Chief Judge")
        self.assertEqual(result["overall_score"], 7.8)


# ===========================================================================
# 2. Missing Fields Validation Tests
# ===========================================================================

class TestMissingFieldsChiefJudge(unittest.TestCase):
    """Ensure missing mandatory fields raise ModelResponseError without fabricating values."""

    def test_missing_overall_score_raises(self):
        payload = {
            "final_verdict": "Solid submission.",
            "top_strengths": ["Strength 1"],
            "top_improvements": ["Improvement 1"],
        }
        with pytest.raises(ModelResponseError) as exc_info:
            validate_judge_schema(payload, "Chief Judge")
        self.assertEqual(exc_info.value.reason, "missing_required_fields")
        self.assertIn("overall_score", str(exc_info.value))

    def test_missing_final_verdict_raises(self):
        payload = {
            "overall_score": 7.0,
            "top_strengths": ["Strength 1"],
            "top_improvements": ["Improvement 1"],
        }
        with pytest.raises(ModelResponseError) as exc_info:
            validate_judge_schema(payload, "Chief Judge")
        self.assertEqual(exc_info.value.reason, "missing_required_fields")
        self.assertIn("final_verdict", str(exc_info.value))

    def test_missing_top_strengths_raises(self):
        payload = {
            "overall_score": 7.0,
            "final_verdict": "Solid submission.",
            "top_improvements": ["Improvement 1"],
        }
        with pytest.raises(ModelResponseError) as exc_info:
            validate_judge_schema(payload, "Chief Judge")
        self.assertEqual(exc_info.value.reason, "missing_required_fields")
        self.assertIn("top_strengths", str(exc_info.value))

    def test_missing_top_improvements_raises(self):
        payload = {
            "overall_score": 7.0,
            "final_verdict": "Solid submission.",
            "top_strengths": ["Strength 1"],
        }
        with pytest.raises(ModelResponseError) as exc_info:
            validate_judge_schema(payload, "Chief Judge")
        self.assertEqual(exc_info.value.reason, "missing_required_fields")
        self.assertIn("top_improvements", str(exc_info.value))

    def test_empty_dict_raises(self):
        with pytest.raises(ModelResponseError) as exc_info:
            validate_judge_schema({}, "Chief Judge")
        self.assertEqual(exc_info.value.reason, "missing_required_fields")

    def test_non_dict_raises(self):
        with pytest.raises(ModelResponseError) as exc_info:
            validate_judge_schema("invalid json", "Chief Judge")
        self.assertEqual(exc_info.value.reason, "invalid_field_types")


# ===========================================================================
# 3. Incorrect Field Types Tests
# ===========================================================================

class TestIncorrectFieldTypesChiefJudge(unittest.TestCase):
    """Ensure invalid field types raise ModelResponseError."""

    def test_invalid_score_string_type_raises(self):
        payload = dict(VALID_CHIEF_OUTPUT)
        payload["overall_score"] = "not_a_number"
        with pytest.raises(ModelResponseError) as exc_info:
            validate_judge_schema(payload, "Chief Judge")
        self.assertEqual(exc_info.value.reason, "invalid_field_types")

    def test_boolean_score_type_raises(self):
        payload = dict(VALID_CHIEF_OUTPUT)
        payload["overall_score"] = True
        with pytest.raises(ModelResponseError) as exc_info:
            validate_judge_schema(payload, "Chief Judge")
        self.assertEqual(exc_info.value.reason, "invalid_field_types")

    def test_list_score_type_raises(self):
        payload = dict(VALID_CHIEF_OUTPUT)
        payload["overall_score"] = [8.0]
        with pytest.raises(ModelResponseError) as exc_info:
            validate_judge_schema(payload, "Chief Judge")
        self.assertEqual(exc_info.value.reason, "invalid_field_types")

    def test_non_string_final_verdict_raises(self):
        payload = dict(VALID_CHIEF_OUTPUT)
        payload["final_verdict"] = ["Not", "a", "string"]
        with pytest.raises(ModelResponseError) as exc_info:
            validate_judge_schema(payload, "Chief Judge")
        self.assertEqual(exc_info.value.reason, "invalid_field_types")

    def test_non_list_top_strengths_raises(self):
        payload = dict(VALID_CHIEF_OUTPUT)
        payload["top_strengths"] = "Single strength string"
        with pytest.raises(ModelResponseError) as exc_info:
            validate_judge_schema(payload, "Chief Judge")
        self.assertEqual(exc_info.value.reason, "invalid_field_types")

    def test_non_list_top_improvements_raises(self):
        payload = dict(VALID_CHIEF_OUTPUT)
        payload["top_improvements"] = 12345
        with pytest.raises(ModelResponseError) as exc_info:
            validate_judge_schema(payload, "Chief Judge")
        self.assertEqual(exc_info.value.reason, "invalid_field_types")


# ===========================================================================
# 4. Mocked Call Judge Error Handling Tests for Chief Judge
# ===========================================================================

class TestCallChiefJudgeErrorHandling(unittest.IsolatedAsyncioTestCase):
    """Test call_judge handling of empty, blocked, malformed, and truncated Chief Judge responses."""

    @pytest.mark.asyncio
    async def test_call_chief_judge_empty_response(self):
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
                    await gemini_service.call_judge("dummy prompt", "Chief Judge")
                self.assertEqual(exc_info.value.reason, "empty_response")

    @pytest.mark.asyncio
    async def test_call_chief_judge_malformed_json(self):
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"overall_score": 8, "final_verdict": "Incomplete...'
        mock_response.candidates = [MagicMock(finish_reason="STOP", block_reason=None)]
        mock_response.prompt_feedback = MagicMock()
        mock_response.prompt_feedback.block_reason = None
        mock_model.generate_content.return_value = mock_response

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-12345678"}):
            with patch.object(gemini_service, "get_model", return_value=mock_model):
                with pytest.raises(ModelResponseError) as exc_info:
                    await gemini_service.call_judge("dummy prompt", "Chief Judge")
                self.assertEqual(exc_info.value.reason, "malformed_json")

    @pytest.mark.asyncio
    async def test_call_chief_judge_truncated_response(self):
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"overall_score": 8, "final_verdict": "Truncated assessment'
        cand = MagicMock()
        cand.finish_reason = "MAX_TOKENS"
        cand.block_reason = None
        mock_response.candidates = [cand]
        mock_response.prompt_feedback = MagicMock()
        mock_response.prompt_feedback.block_reason = None
        mock_model.generate_content.return_value = mock_response

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-12345678"}):
            with patch.object(gemini_service, "get_model", return_value=mock_model):
                with pytest.raises(ModelResponseError) as exc_info:
                    await gemini_service.call_judge("dummy prompt", "Chief Judge")
                self.assertEqual(exc_info.value.reason, "truncated")

    @pytest.mark.asyncio
    async def test_call_chief_judge_blocked_response(self):
        mock_model = MagicMock()
        mock_response = MagicMock()
        type(mock_response).text = property(lambda self: (_ for _ in ()).throw(ValueError("blocked")))
        mock_response.candidates = []
        pf = MagicMock()
        pf.block_reason = "HARM_CATEGORY_DANGEROUS"
        mock_response.prompt_feedback = pf
        mock_model.generate_content.return_value = mock_response

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-12345678"}):
            with patch.object(gemini_service, "get_model", return_value=mock_model):
                with pytest.raises(ModelResponseError) as exc_info:
                    await gemini_service.call_judge("dummy prompt", "Chief Judge")
                self.assertIn(exc_info.value.reason, ("blocked", "empty_response"))

    @pytest.mark.asyncio
    async def test_run_chief_judge_success(self):
        """Verify run_chief_judge succeeds when call_judge returns valid payload."""
        with patch("judges.call_judge", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = dict(VALID_CHIEF_OUTPUT)
            chief_res = await run_chief_judge(
                project_context="Test project context",
                innovation={"score": 8},
                technical={"score": 7},
                business={"score": 8},
                presentation={"score": 8},
                attack_mode=False,
            )
            self.assertEqual(chief_res["overall_score"], 7.8)
            self.assertEqual(chief_res["final_verdict"], VALID_CHIEF_OUTPUT["final_verdict"])
            self.assertEqual(len(chief_res["top_strengths"]), 3)
            self.assertEqual(len(chief_res["top_improvements"]), 3)


if __name__ == "__main__":
    unittest.main()
