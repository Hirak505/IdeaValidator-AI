import unittest
from judges import (
    _validate_judge_result,
    _validate_chief_result,
    calculate_consensus,
    _validate_finding,
    _validate_roadmap_item,
    _clamp_int,
    _sanitize_string_list,
)


class TestEvalPipeline(unittest.TestCase):

    def test_clamp_int(self):
        self.assertEqual(_clamp_int(5, 0, 10, 5), 5)
        self.assertEqual(_clamp_int(-10, 0, 10, 5), 0)
        self.assertEqual(_clamp_int(15, 0, 10, 5), 10)
        self.assertEqual(_clamp_int("invalid", 0, 10, 5), 5)
        self.assertEqual(_clamp_int(None, 0, 10, 5), 5)

    def test_sanitize_string_list(self):
        items = ["  Valid item  ", "a" * 500, "", None, 123]
        sanitized = _sanitize_string_list(items, max_items=3, max_length=50)
        self.assertEqual(len(sanitized), 2)
        self.assertEqual(sanitized[0], "Valid item")
        self.assertEqual(len(sanitized[1]), 50)

        # Fallback when empty
        self.assertEqual(_sanitize_string_list([], max_items=3), ["Not available"])
        self.assertEqual(_sanitize_string_list("not a list", max_items=3), ["Not available"])

    def test_validate_finding(self):
        valid = {
            "finding": "Uses WebSockets for real-time messaging",
            "evidence": "Mentioned in Architecture section of README",
            "source": "README.md",
            "evidence_type": "project",
            "confidence": 85,
        }
        res = _validate_finding(valid)
        self.assertIsNotNone(res)
        self.assertEqual(res["finding"], "Uses WebSockets for real-time messaging")
        self.assertEqual(res["evidence_type"], "project")
        self.assertEqual(res["confidence"], 85)

        # Invalid type falls back to not_verified
        invalid_type = valid.copy()
        invalid_type["evidence_type"] = "unsupported_type"
        res2 = _validate_finding(invalid_type)
        self.assertEqual(res2["evidence_type"], "not_verified")

        # Missing finding returns None
        self.assertIsNone(_validate_finding({"evidence": "foo"}))

    def test_validate_judge_result(self):
        raw = {
            "score": 8,
            "strengths": ["Clean modular code"],
            "weaknesses": ["Needs integration tests"],
            "comments": "Strong technical foundation.",
            "confidence": 90,
            "evidence_quality": 80,
            "key_findings": [
                {
                    "finding": "Implemented with FastAPI and Vite",
                    "evidence": "package.json and backend/main.py verified",
                    "source": "Codebase",
                    "evidence_type": "project",
                    "confidence": 95,
                }
            ],
        }
        validated = _validate_judge_result(raw, "technical")
        self.assertEqual(validated["score"], 8)
        self.assertEqual(validated["confidence"], 90)
        self.assertEqual(validated["evidence_quality"], 80)
        self.assertEqual(len(validated["key_findings"]), 1)
        self.assertEqual(validated["key_findings"][0]["evidence_type"], "project")

        # Fallback defaults for missing/corrupted data
        corrupted = _validate_judge_result({}, "technical")
        self.assertEqual(corrupted["score"], 5)
        self.assertEqual(corrupted["confidence"], 50)
        self.assertEqual(corrupted["evidence_quality"], 50)
        self.assertEqual(len(corrupted["key_findings"]), 1)
        self.assertEqual(corrupted["key_findings"][0]["evidence_type"], "not_verified")

    def test_calculate_consensus_strong(self):
        # All scores close: 7, 8, 8, 7 -> spread 1 (strong)
        inv = {"score": 8, "confidence": 80, "evidence_quality": 70}
        tech = {"score": 7, "confidence": 85, "evidence_quality": 75}
        biz = {"score": 8, "confidence": 90, "evidence_quality": 80}
        pres = {"score": 7, "confidence": 75, "evidence_quality": 65}

        consensus = calculate_consensus(inv, tech, biz, pres)
        self.assertEqual(consensus["agreement_level"], "strong")
        self.assertEqual(consensus["spread"], 1)
        self.assertEqual(consensus["mean"], 7.5)
        self.assertEqual(consensus["avg_confidence"], 82)
        self.assertEqual(consensus["avg_evidence_quality"], 72)

    def test_calculate_consensus_weak(self):
        # High spread: 3, 9, 8, 4 -> spread 6 (weak)
        inv = {"score": 9, "confidence": 90, "evidence_quality": 80}
        tech = {"score": 3, "confidence": 60, "evidence_quality": 50}
        biz = {"score": 8, "confidence": 85, "evidence_quality": 70}
        pres = {"score": 4, "confidence": 55, "evidence_quality": 45}

        consensus = calculate_consensus(inv, tech, biz, pres)
        self.assertEqual(consensus["agreement_level"], "weak")
        self.assertEqual(consensus["spread"], 6)
        self.assertEqual(consensus["min"], 3)
        self.assertEqual(consensus["max"], 9)

    def test_validate_chief_result(self):
        raw = {
            "overall_score": 7.8,
            "final_verdict": "Promising hackathon submission with strong innovation.",
            "top_strengths": ["Clear UI", "Working backend"],
            "top_improvements": ["Add automated tests", "Clarify monetization"],
            "improvement_roadmap": ["Add tests", "Deploy to cloud"],
            "judge_questions": ["What is your CAC?", "How do you scale?"],
            "confidence": 85,
            "evidence_quality": 80,
            "prioritized_roadmap": [
                {
                    "priority": "P0",
                    "title": "Fix critical security headers",
                    "reason": "Prevents clickjacking",
                    "impact": "High",
                    "effort": "Low",
                },
                {
                    "priority": "P1",
                    "title": "Add integration test suite",
                    "reason": "Ensure stability across releases",
                    "impact": "High",
                    "effort": "Medium",
                },
            ],
            "differentiation": {
                "solution_category": "AI Evaluation Platform",
                "claimed_differentiators": ["Multi-judge consensus", "Defense in depth"],
                "differentiation_strengths": ["Evidence verification mechanism"],
                "differentiation_gaps": ["No live multi-tenant benchmarker"],
                "unsupported_claims": [],
                "limitation_note": "Based solely on provided materials",
            },
        }

        validated = _validate_chief_result(raw)
        self.assertEqual(validated["overall_score"], 7.8)
        self.assertEqual(validated["confidence"], 85)
        self.assertEqual(validated["evidence_quality"], 80)
        self.assertEqual(len(validated["prioritized_roadmap"]), 2)
        self.assertEqual(validated["prioritized_roadmap"][0]["priority"], "P0")
        self.assertEqual(validated["differentiation"]["solution_category"], "AI Evaluation Platform")
        self.assertEqual(len(validated["differentiation"]["claimed_differentiators"]), 2)

    def test_validate_chief_result_fallback_roadmap(self):
        # When prioritized_roadmap is omitted, converts string improvement_roadmap to structured items
        raw = {
            "overall_score": 6.0,
            "improvement_roadmap": ["Setup CI/CD pipeline", "Refactor judges to async"],
        }
        validated = _validate_chief_result(raw)
        self.assertEqual(len(validated["prioritized_roadmap"]), 2)
        self.assertEqual(validated["prioritized_roadmap"][0]["priority"], "P1")
        self.assertEqual(validated["prioritized_roadmap"][0]["title"], "Setup CI/CD pipeline")
        self.assertEqual(validated["differentiation"]["solution_category"], "Not determined")


if __name__ == "__main__":
    unittest.main()
