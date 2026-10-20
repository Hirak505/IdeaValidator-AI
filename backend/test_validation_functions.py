"""Unit tests for IdeaValidator-AI backend validation and consensus functions.

Tests the actual behavior, boundary conditions, defaults, and sanitization logic of:
- _sanitize_string_list
- _validate_finding
- _validate_roadmap_item
- _validate_judge_result
- calculate_consensus
- _validate_chief_result
"""

import sys
from pathlib import Path
import pytest

# Ensure backend directory is in sys.path for direct imports
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from judges import (
    _sanitize_string_list,
    _validate_finding,
    _validate_roadmap_item,
    _validate_judge_result,
    calculate_consensus,
    _validate_chief_result,
    _clamp_int,
    VALID_EVIDENCE_TYPES,
    VALID_PRIORITIES,
    VALID_IMPACT_EFFORT,
)


# ===========================================================================
# 1. String-List Sanitization (_sanitize_string_list)
# ===========================================================================

class TestStringListSanitization:
    """Tests for _sanitize_string_list."""

    def test_valid_list_of_strings(self):
        """Sanitizes and strips whitespace from a normal list of strings."""
        raw = ["  Clean Architecture  ", "Modular Design\n", "\tFastAPI Backend"]
        sanitized = _sanitize_string_list(raw)
        assert sanitized == ["Clean Architecture", "Modular Design", "FastAPI Backend"]

    def test_max_items_capping(self):
        """Respects max_items limit (default 5 or custom)."""
        items = [f"Item {i}" for i in range(10)]
        # Default max_items=5
        assert len(_sanitize_string_list(items)) == 5
        assert _sanitize_string_list(items) == ["Item 0", "Item 1", "Item 2", "Item 3", "Item 4"]

        # Custom max_items=2
        custom = _sanitize_string_list(items, max_items=2)
        assert len(custom) == 2
        assert custom == ["Item 0", "Item 1"]

    def test_long_strings_truncation(self):
        """Truncates long strings to max_length (default 300 or custom)."""
        long_str = "x" * 500
        # Default max_length=300
        result_default = _sanitize_string_list([long_str])
        assert len(result_default) == 1
        assert len(result_default[0]) == 300
        assert result_default[0] == "x" * 300

        # Custom max_length=40
        result_custom = _sanitize_string_list([long_str], max_length=40)
        assert len(result_custom[0]) == 40
        assert result_custom[0] == "x" * 40

    def test_empty_lists_and_empty_items(self):
        """Returns ['Not available'] when list is empty or items become empty after strip."""
        assert _sanitize_string_list([]) == ["Not available"]
        assert _sanitize_string_list(["", "   ", "\t\n  "]) == ["Not available"]

    def test_invalid_input_types(self):
        """Returns ['Not available'] for non-list inputs and filters out non-string elements."""
        # Non-list inputs
        assert _sanitize_string_list(None) == ["Not available"]
        assert _sanitize_string_list("string not a list") == ["Not available"]
        assert _sanitize_string_list(123) == ["Not available"]
        assert _sanitize_string_list({"key": "val"}) == ["Not available"]

        # List containing non-string items mixed with valid strings (within max_items=5)
        mixed = [None, 42, "Valid Entry", True, "Another Entry"]
        sanitized = _sanitize_string_list(mixed)
        assert sanitized == ["Valid Entry", "Another Entry"]

        # List with only non-string items
        assert _sanitize_string_list([None, 123, False]) == ["Not available"]


# ===========================================================================
# 2. Evidence Validation (_validate_finding)
# ===========================================================================

class TestEvidenceValidation:
    """Tests for _validate_finding."""

    @pytest.fixture
    def sample_context(self):
        return (
            "Project Name: FinGuard AI\n"
            "[Slide 1] Overview: FinGuard AI is a real-time fraud detection platform.\n"
            "[Slide 2] Architecture: Implemented with FastAPI backend and Redis streaming.\n"
            "[Slide 3] Performance: Sub-50ms latency across 100,000 transactions per second."
        )

    def test_finding_supported_by_context(self, sample_context):
        """A finding with documented_fact and evidence text found in context is preserved."""
        finding = {
            "finding": "Uses FastAPI backend and Redis streaming",
            "evidence": "FastAPI backend and Redis streaming",
            "source": "Slide 2",
            "evidence_type": "documented_fact",
            "confidence": 85,
        }
        validated = _validate_finding(finding, project_context=sample_context)
        assert validated is not None
        assert validated["finding"] == "Uses FastAPI backend and Redis streaming"
        assert validated["evidence_type"] == "documented_fact"
        assert validated["confidence"] == 85
        assert validated["source"] == "Slide 2"
        assert validated["evidence"] == "FastAPI backend and Redis streaming"

    def test_unsupported_claim_demotion_and_confidence_cap(self, sample_context):
        """A documented_fact absent from context is demoted to unsupported_claim with confidence <= 45."""
        hallucinated = {
            "finding": "Built using Solidity smart contracts on Ethereum",
            "evidence": "Deployed on Ethereum mainnet using Hardhat",
            "source": "Slide 2",
            "evidence_type": "documented_fact",
            "confidence": 90,
        }
        validated = _validate_finding(hallucinated, project_context=sample_context)
        assert validated is not None
        assert validated["evidence_type"] == "unsupported_claim"
        assert validated["confidence"] == 45  # Clamped to min(90, 45)

    def test_documented_fact_with_placeholder_evidence_demoted_to_not_verified(self, sample_context):
        """A documented_fact with placeholder evidence is demoted to not_verified (not unsupported_claim)."""
        finding = {
            "finding": "Claims high availability",
            "evidence": "Not directly verified",
            "source": "N/A",
            "evidence_type": "documented_fact",
            "confidence": 75,
        }
        validated = _validate_finding(finding, project_context=sample_context)
        assert validated is not None
        assert validated["evidence_type"] == "not_verified"
        assert validated["confidence"] == 45

    def test_supported_inference(self, sample_context):
        """A supported_inference whose terms root in the context is retained with original confidence."""
        inference = {
            "finding": "High throughput real-time streaming capability",
            "evidence": "100,000 transactions per second",
            "source": "Slide 3",
            "evidence_type": "supported_inference",
            "confidence": 80,
        }
        validated = _validate_finding(inference, project_context=sample_context)
        assert validated is not None
        assert validated["evidence_type"] == "supported_inference"
        assert validated["confidence"] == 80

    def test_unsupported_inference_demoted_to_not_verified(self, sample_context):
        """An inference with no grounding tokens in context is demoted to not_verified with confidence <= 40."""
        inference = {
            "finding": "Quantum cryptographic key distribution",
            "evidence": "Qubit entanglement communication channel",
            "source": "Slide 1",
            "evidence_type": "supported_inference",
            "confidence": 70,
        }
        validated = _validate_finding(inference, project_context=sample_context)
        assert validated is not None
        assert validated["evidence_type"] == "not_verified"
        assert validated["confidence"] == 40  # Clamped to min(70, 40)

    def test_fake_slide_attribution_invalidates_grounding(self, sample_context):
        """When slide markers exist in context but cited slide is absent, attribution is invalidated."""
        finding = {
            "finding": "Real-time fraud detection platform",
            "evidence": "real-time fraud detection platform",
            "source": "Slide 99",  # Slide 99 does not exist in context (only slides 1, 2, 3)
            "evidence_type": "documented_fact",
            "confidence": 85,
        }
        validated = _validate_finding(finding, project_context=sample_context)
        assert validated is not None
        assert validated["evidence_type"] == "unsupported_claim"
        assert validated["confidence"] == 45

    def test_invalid_finding_inputs(self):
        """Invalid finding inputs return None or fallback values."""
        # Non-dict returns None
        assert _validate_finding(None) is None
        assert _validate_finding("not a dict") is None
        assert _validate_finding([]) is None

        # Missing or empty finding string returns None
        assert _validate_finding({}) is None
        assert _validate_finding({"finding": ""}) is None
        assert _validate_finding({"finding": None}) is None
        assert _validate_finding({"finding": 12345}) is None

        # Invalid evidence_type falls back to not_verified
        finding = {"finding": "Valid finding text", "evidence_type": "invalid_type"}
        validated = _validate_finding(finding)
        assert validated["evidence_type"] == "not_verified"
        assert validated["evidence"] == "Not directly verified"
        assert validated["source"] == "N/A"
        assert validated["confidence"] == 50

        # Confidence clamping
        clamped_low = _validate_finding({"finding": "Text", "confidence": -10})
        assert clamped_low["confidence"] == 0
        clamped_high = _validate_finding({"finding": "Text", "confidence": 150})
        assert clamped_high["confidence"] == 100
        clamped_str = _validate_finding({"finding": "Text", "confidence": "high"})
        assert clamped_str["confidence"] == 50


# ===========================================================================
# 3. Roadmap Item Validation (_validate_roadmap_item)
# ===========================================================================

class TestRoadmapItemValidation:
    """Tests for _validate_roadmap_item."""

    def test_valid_roadmap_item(self):
        """Preserves a fully compliant roadmap item."""
        item = {
            "priority": "P0",
            "title": "Migrate database to PostgreSQL",
            "reason": "SQLite will not scale horizontally",
            "impact": "High",
            "effort": "Medium",
        }
        validated = _validate_roadmap_item(item)
        assert validated == item

    def test_invalid_priority_fallback(self):
        """Invalid priority like 'P9' or 'Critical' falls back to 'P1'."""
        assert _validate_roadmap_item({"title": "Task", "priority": "P9"})["priority"] == "P1"
        assert _validate_roadmap_item({"title": "Task", "priority": "High"})["priority"] == "P1"
        assert _validate_roadmap_item({"title": "Task", "priority": None})["priority"] == "P1"

        # Valid priorities {"P0", "P1", "P2"} are kept
        for p in VALID_PRIORITIES:
            assert _validate_roadmap_item({"title": "Task", "priority": p})["priority"] == p

    def test_invalid_impact_fallback(self):
        """Invalid impact like 'Extreme' falls back to 'Medium'."""
        assert _validate_roadmap_item({"title": "Task", "impact": "Extreme"})["impact"] == "Medium"
        assert _validate_roadmap_item({"title": "Task", "impact": "Low-Medium"})["impact"] == "Medium"
        assert _validate_roadmap_item({"title": "Task", "impact": None})["impact"] == "Medium"

        # Valid impacts {"High", "Medium", "Low"} are kept
        for imp in VALID_IMPACT_EFFORT:
            assert _validate_roadmap_item({"title": "Task", "impact": imp})["impact"] == imp

    def test_valid_and_invalid_effort_values(self):
        """Valid effort values ('High', 'Medium', 'Low') are preserved; invalid fall back to 'Medium'."""
        for eff in VALID_IMPACT_EFFORT:
            assert _validate_roadmap_item({"title": "Task", "effort": eff})["effort"] == eff

        assert _validate_roadmap_item({"title": "Task", "effort": "Minimal"})["effort"] == "Medium"
        assert _validate_roadmap_item({"title": "Task", "effort": 5})["effort"] == "Medium"

    def test_title_and_reason_normalization(self):
        """Title is required and stripped/truncated to 200 chars; reason defaults and truncates to 300."""
        # Missing or empty title returns None
        assert _validate_roadmap_item({}) is None
        assert _validate_roadmap_item({"title": ""}) is None
        assert _validate_roadmap_item({"title": "   "}) is None
        assert _validate_roadmap_item(None) is None

        # Truncation
        long_title = "T" * 300
        long_reason = "R" * 500
        validated = _validate_roadmap_item({"title": long_title, "reason": long_reason})
        assert len(validated["title"]) == 200
        assert len(validated["reason"]) == 300

        # Default reason
        no_reason = _validate_roadmap_item({"title": "Clean Code"})
        assert no_reason["reason"] == "Based on evaluation feedback"


# ===========================================================================
# 4. Judge Result Defaults (_validate_judge_result)
# ===========================================================================

class TestJudgeResultDefaults:
    """Tests for _validate_judge_result."""

    def test_empty_or_incomplete_judge_result(self):
        """Empty or incomplete input returns default score, confidence, evidence quality, and key findings."""
        validated = _validate_judge_result({}, "technical")

        assert validated["score"] == 5
        assert validated["strengths"] == ["Clear project submission"]
        assert validated["weaknesses"] == ["Further details needed"]
        assert validated["comments"] == "The technical evaluation was completed with default parameters."
        assert validated["confidence"] == 50
        assert validated["evidence_quality"] == 50
        assert len(validated["key_findings"]) == 1
        default_finding = validated["key_findings"][0]
        assert default_finding["finding"] == "General technical evaluation completed"
        assert default_finding["evidence"] == "Not directly verified"
        assert default_finding["source"] == "N/A"
        assert default_finding["evidence_type"] == "not_verified"
        assert default_finding["confidence"] == 50

    def test_non_dict_judge_result_handled_gracefully(self):
        """Passing None or non-dict produces the standard fallback structure."""
        validated = _validate_judge_result(None, "innovation")
        assert validated["score"] == 5
        assert validated["comments"] == "The innovation evaluation was completed with default parameters."

    def test_score_bounds_and_clamping(self):
        """Scores are clamped to integers between 0 and 10."""
        assert _validate_judge_result({"score": 15}, "business")["score"] == 10
        assert _validate_judge_result({"score": -3}, "business")["score"] == 0
        assert _validate_judge_result({"score": "nine"}, "business")["score"] == 5
        assert _validate_judge_result({"score": 8.7}, "business")["score"] == 8

    def test_confidence_and_evidence_quality_bounds(self):
        """Confidence and evidence_quality are clamped between 0 and 100 with default 50."""
        res = {
            "confidence": -25,
            "evidence_quality": 200,
        }
        validated = _validate_judge_result(res, "presentation")
        assert validated["confidence"] == 0
        assert validated["evidence_quality"] == 100

    def test_key_findings_sanitization(self):
        """Valid findings are preserved up to 5; invalid items are filtered out."""
        findings = [
            {"finding": f"Finding {i}", "evidence": "Doc", "evidence_type": "documented_fact", "confidence": 80}
            for i in range(7)
        ]
        # Include an invalid finding that returns None
        findings.insert(2, {"invalid": "missing finding key"})

        validated = _validate_judge_result({"key_findings": findings}, "technical")
        # Slices raw findings to 5, one was invalid, so 4 remain
        assert len(validated["key_findings"]) == 4
        for f in validated["key_findings"]:
            assert f["evidence_type"] == "documented_fact"


# ===========================================================================
# 5. Consensus Calculation (calculate_consensus)
# ===========================================================================

class TestConsensusCalculation:
    """Tests for calculate_consensus."""

    def test_consensus_metrics_calculation(self):
        """Verifies mean, min, max, spread, and scores dictionary."""
        inv = {"score": 8, "confidence": 80, "evidence_quality": 70}
        tech = {"score": 6, "confidence": 90, "evidence_quality": 85}
        biz = {"score": 7, "confidence": 75, "evidence_quality": 65}
        pres = {"score": 9, "confidence": 85, "evidence_quality": 80}

        consensus = calculate_consensus(inv, tech, biz, pres)

        assert consensus["scores"] == {"innovation": 8, "technical": 6, "business": 7, "presentation": 9}
        assert consensus["mean"] == 7.5
        assert consensus["min"] == 6
        assert consensus["max"] == 9
        assert consensus["spread"] == 3

    def test_consensus_agreement_levels(self):
        """Tests agreement level thresholds: spread <= 2 strong, spread <= 4 moderate, > 4 weak."""
        # Strong: spread <= 2
        strong = calculate_consensus({"score": 7}, {"score": 8}, {"score": 7}, {"score": 8})
        assert strong["spread"] == 1
        assert strong["agreement_level"] == "strong"

        exact_two = calculate_consensus({"score": 6}, {"score": 8}, {"score": 7}, {"score": 7})
        assert exact_two["spread"] == 2
        assert exact_two["agreement_level"] == "strong"

        # Moderate: 2 < spread <= 4
        moderate = calculate_consensus({"score": 5}, {"score": 7}, {"score": 8}, {"score": 7})
        assert moderate["spread"] == 3
        assert moderate["agreement_level"] == "moderate"

        exact_four = calculate_consensus({"score": 5}, {"score": 9}, {"score": 7}, {"score": 7})
        assert exact_four["spread"] == 4
        assert exact_four["agreement_level"] == "moderate"

        # Weak: spread > 4
        weak = calculate_consensus({"score": 2}, {"score": 9}, {"score": 4}, {"score": 8})
        assert weak["spread"] == 7
        assert weak["agreement_level"] == "weak"

    def test_consensus_judge_alignment_and_disagreement(self):
        """Verifies most_aligned (closest to mean) and largest_disagreement (farthest from mean)."""
        # Scores: inv=8, tech=8, biz=8, pres=2 -> mean = 6.5
        # Distances: inv=1.5, tech=1.5, biz=1.5, pres=4.5
        inv = {"score": 8}
        tech = {"score": 8}
        biz = {"score": 8}
        pres = {"score": 2}

        consensus = calculate_consensus(inv, tech, biz, pres)
        assert consensus["mean"] == 6.5
        assert consensus["most_aligned"] == "innovation"  # First with min distance
        assert consensus["largest_disagreement"] == "presentation"  # Distance 4.5

    def test_consensus_average_confidence_and_evidence_quality(self):
        """Computes rounded averages of confidence and evidence_quality across all 4 judges."""
        inv = {"score": 7, "confidence": 85, "evidence_quality": 90}
        tech = {"score": 7, "confidence": 75, "evidence_quality": 80}
        biz = {"score": 7, "confidence": 65, "evidence_quality": 70}
        pres = {"score": 7, "confidence": 95, "evidence_quality": 60}

        consensus = calculate_consensus(inv, tech, biz, pres)
        # avg_confidence = round((85 + 75 + 65 + 95) / 4) = round(320 / 4) = 80
        # avg_evidence_quality = round((90 + 80 + 70 + 60) / 4) = round(300 / 4) = 75
        assert consensus["avg_confidence"] == 80
        assert consensus["avg_evidence_quality"] == 75

        # Defaults when confidence / evidence_quality missing
        empty_consensus = calculate_consensus({}, {}, {}, {})
        assert empty_consensus["avg_confidence"] == 50
        assert empty_consensus["avg_evidence_quality"] == 50


# ===========================================================================
# 6. Chief Judge Result Validation (_validate_chief_result)
# ===========================================================================

class TestChiefJudgeResultValidation:
    """Tests for _validate_chief_result."""

    def test_overall_score_bounds(self):
        """Overall score is bounded between 0.0 and 10.0 and rounded to 1 decimal place."""
        assert _validate_chief_result({"overall_score": 12.5})["overall_score"] == 10.0
        assert _validate_chief_result({"overall_score": -4.2})["overall_score"] == 0.0
        assert _validate_chief_result({"overall_score": "bad_score"})["overall_score"] == 5.0
        assert _validate_chief_result({"overall_score": 7.84})["overall_score"] == 7.8
        assert _validate_chief_result({})["overall_score"] == 5.0

    def test_differentiation_fields_preservation_and_sanitization(self):
        """Preserves and sanitizes differentiation fields including solution_category and unsupported_claims."""
        raw = {
            "overall_score": 8.2,
            "differentiation": {
                "solution_category": "Autonomous Cloud Security Agent",
                "claimed_differentiators": ["Zero-knowledge proof verification", "Real-time kernel tracing"],
                "differentiation_strengths": ["Strong theoretical foundation"],
                "differentiation_gaps": ["No production performance benchmarks"],
                "unsupported_claims": ["100% exploit prevention guarantee", "Zero latency overhead"],
                "limitation_note": "Evaluated against architectural description only.",
            },
        }
        validated = _validate_chief_result(raw)
        diff = validated["differentiation"]

        assert diff["solution_category"] == "Autonomous Cloud Security Agent"
        assert len(diff["claimed_differentiators"]) == 2
        assert len(diff["differentiation_strengths"]) == 1
        assert len(diff["differentiation_gaps"]) == 1
        assert diff["unsupported_claims"] == ["100% exploit prevention guarantee", "Zero latency overhead"]
        assert diff["limitation_note"] == "Evaluated against architectural description only."

    def test_differentiation_unsupported_claims_empty_list_preserved(self):
        """An empty unsupported_claims list is preserved as valid empty list (clean submission)."""
        raw = {
            "differentiation": {
                "solution_category": "FinTech",
                "unsupported_claims": [],
            }
        }
        validated = _validate_chief_result(raw)
        assert validated["differentiation"]["unsupported_claims"] == []

    def test_differentiation_defaults_on_missing_input(self):
        """When differentiation is omitted or invalid, correct defaults are populated."""
        validated = _validate_chief_result({})
        diff = validated["differentiation"]

        assert diff["solution_category"] == "Not determined"
        assert diff["claimed_differentiators"] == ["Not identified"]
        assert diff["differentiation_strengths"] == ["Not determined"]
        assert diff["differentiation_gaps"] == ["Not determined"]
        assert diff["unsupported_claims"] == []
        assert "submitted materials" in diff["limitation_note"]

    def test_judge_questions_enforcement(self):
        """Enforces max 6 judge questions with truncation to 250 chars and default questions on missing input."""
        # Defaults to 6 questions
        validated_default = _validate_chief_result({})
        assert len(validated_default["judge_questions"]) == 6
        assert "value proposition" in validated_default["judge_questions"][0]

        # Providing 10 questions capped to 6
        questions = [f"Question {i}?" for i in range(10)]
        validated_custom = _validate_chief_result({"judge_questions": questions})
        assert len(validated_custom["judge_questions"]) == 6
        assert validated_custom["judge_questions"] == [f"Question {i}?" for i in range(6)]

        # Truncation of long question
        long_q = "Q" * 400
        validated_trunc = _validate_chief_result({"judge_questions": [long_q]})
        assert len(validated_trunc["judge_questions"][0]) == 250


# ===========================================================================
# 7. Fallback Roadmap Conversion
# ===========================================================================

class TestFallbackRoadmapConversion:
    """Tests for chief judge result fallback roadmap conversion."""

    def test_fallback_roadmap_from_improvement_roadmap_strings(self):
        """When prioritized_roadmap is omitted, converts string improvement_roadmap to structured items."""
        raw = {
            "overall_score": 7.0,
            "improvement_roadmap": [
                "Implement end-to-end encryption",
                "Add multi-region database failover",
                "Write comprehensive API documentation",
            ],
        }
        validated = _validate_chief_result(raw)
        roadmap = validated["prioritized_roadmap"]

        assert len(roadmap) == 3
        # Verify normalization and fallback values
        assert roadmap[0]["priority"] == "P1"
        assert roadmap[0]["title"] == "Implement end-to-end encryption"
        assert roadmap[0]["reason"] == "Based on evaluation feedback"
        assert roadmap[0]["impact"] == "Medium"
        assert roadmap[0]["effort"] == "Medium"

        assert roadmap[1]["priority"] == "P1"
        assert roadmap[1]["title"] == "Add multi-region database failover"

        # Verify differentiation solution_category default
        assert validated["differentiation"]["solution_category"] == "Not determined"

    def test_fallback_roadmap_default_when_all_roadmaps_omitted(self):
        """When neither prioritized_roadmap nor improvement_roadmap is provided, creates fallback item from default."""
        validated = _validate_chief_result({})
        roadmap = validated["prioritized_roadmap"]

        assert len(roadmap) == 1
        assert roadmap[0]["priority"] == "P1"
        assert roadmap[0]["title"] == "Review feedback and iterate on core architecture."
        assert roadmap[0]["reason"] == "Based on evaluation feedback"
        assert roadmap[0]["impact"] == "Medium"
        assert roadmap[0]["effort"] == "Medium"

    def test_explicit_prioritized_roadmap_preserved_over_fallback(self):
        """When prioritized_roadmap is explicitly provided with valid items, fallback conversion is not used."""
        raw = {
            "overall_score": 8.0,
            "improvement_roadmap": ["Unused fallback step 1", "Unused fallback step 2"],
            "prioritized_roadmap": [
                {
                    "priority": "P0",
                    "title": "Fix critical SQL injection vulnerability",
                    "reason": "Prevents unauthorized database extraction",
                    "impact": "High",
                    "effort": "Low",
                },
                {
                    "priority": "P2",
                    "title": "Add dark mode toggle to frontend",
                    "reason": "Improves developer UX in low light",
                    "impact": "Low",
                    "effort": "Low",
                },
            ],
        }
        validated = _validate_chief_result(raw)
        roadmap = validated["prioritized_roadmap"]

        assert len(roadmap) == 2
        assert roadmap[0]["priority"] == "P0"
        assert roadmap[0]["title"] == "Fix critical SQL injection vulnerability"
        assert roadmap[0]["impact"] == "High"
        assert roadmap[1]["priority"] == "P2"
        assert roadmap[1]["title"] == "Add dark mode toggle to frontend"
