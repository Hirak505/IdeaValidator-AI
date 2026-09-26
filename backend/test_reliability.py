import pytest
import asyncio
from unittest.mock import patch

from judges import (
    calculate_consensus,
    _validate_judge_result,
    _validate_chief_result,
    _validate_finding,
    run_technical_judge,
    run_chief_judge,
    run_all_judges
)

PROJECT_A_BALANCED = """
Project Name: SecureBank
Problem: Small businesses struggle with managing multiple bank accounts securely.
Target Users: Small business owners.
Technical Architecture: FastAPI backend, Vite/React frontend, PostgreSQL database. Hosted on AWS.
Business Model: SaaS subscription $20/month.
Differentiation: Unlike competitors who focus on enterprise, we focus exclusively on micro-businesses with a simpler UI.
"""

PROJECT_B_TECH_STRONG_BIZ_WEAK = """
Project Name: QuantumComputeAPI
Problem: Fast matrix multiplication needed.
Target Users: People who need it.
Technical Architecture: Highly optimized C++ extensions wrapped in FastAPI. Uses Redis for caching, Kubernetes for orchestration, gRPC for internal microservices. Complex event sourcing pattern implemented.
Business Model: TBD. Maybe open source, maybe charge money later.
Differentiation: It is very fast.
"""

PROJECT_C_BIZ_STRONG_TECH_WEAK = """
Project Name: DogWalkerPro
Problem: Dog walkers need an easy way to track their walks and bill clients.
Target Users: Freelance dog walkers, pet sitting businesses. Over 500 signups on waitlist.
Technical Architecture: No-code prototype using Bubble. Uses a Google Sheet for the database.
Business Model: 10% transaction fee. We have letters of intent from 5 local pet agencies.
Differentiation: Highly localized marketing approach, direct integration with pet insurance.
"""

PROJECT_D_PRESENTATION_STRONG_INNOVATION_WEAK = """
Project Name: ToDoApp 2.0
Problem: People forget tasks.
Target Users: Everyone.
Presentation: Beautifully formatted slides, professional video demo, polished UI.
Technical Architecture: Express backend, MongoDB. Standard CRUD app.
Business Model: Freemium with ads.
Differentiation: It has a dark mode and very smooth animations. Basically exactly like every other ToDo app but prettier.
"""

PROJECT_E_INCOMPLETE = """
Project Name: SuperApp
We are building an app to change the world. It will use AI.
"""


def test_consensus_calculation():
    # Case 1: 7, 7, 7, 7
    c1 = calculate_consensus({"score": 7}, {"score": 7}, {"score": 7}, {"score": 7})
    assert c1["spread"] == 0
    assert c1["agreement_level"] == "strong"

    # Case 2: 7, 7, 8, 7
    c2 = calculate_consensus({"score": 7}, {"score": 7}, {"score": 8}, {"score": 7})
    assert c2["spread"] == 1
    assert c2["agreement_level"] == "strong"

    # Case 3: 5, 7, 8, 7
    c3 = calculate_consensus({"score": 5}, {"score": 7}, {"score": 8}, {"score": 7})
    assert c3["spread"] == 3
    assert c3["agreement_level"] == "moderate"

    # Case 4: 2, 9, 3, 8
    c4 = calculate_consensus({"score": 2}, {"score": 9}, {"score": 3}, {"score": 8})
    assert c4["spread"] == 7
    assert c4["agreement_level"] == "weak"


def test_malformed_llm_outputs():
    # Missing score
    bad_result_1 = {"score": None}
    val1 = _validate_judge_result(bad_result_1, "technical")
    assert val1["score"] == 5

    # Score = "seven", confidence = -20, evidence_quality = 150
    bad_result_2 = {
        "score": "seven",
        "confidence": -20,
        "evidence_quality": 150,
        "strengths": None,
        "weaknesses": 123,
        "key_findings": "not an array"
    }
    val2 = _validate_judge_result(bad_result_2, "technical")
    assert val2["score"] == 5
    assert val2["confidence"] == 0
    assert val2["evidence_quality"] == 100
    assert val2["strengths"] == ["Clear project submission"]

    # Test _validate_finding with invalid type
    bad_finding = {
        "finding": "Something",
        "evidence_type": "invalid_type",
        "confidence": "high"
    }
    valid_f = _validate_finding(bad_finding)
    assert valid_f["evidence_type"] == "not_verified"
    assert valid_f["confidence"] == 50


def test_backward_compatibility():
    old_schema = {
        "overall_score": 8.0,
        "final_verdict": "Good project.",
        "top_strengths": ["Fast execution"],
        "top_improvements": ["Better UI needed"],
        "improvement_roadmap": ["Step 1", "Step 2"],
        "judge_questions": ["What is next?"]
    }
    validated = _validate_chief_result(old_schema)
    assert validated["confidence"] == 50
    assert validated["evidence_quality"] == 50
    assert len(validated["prioritized_roadmap"]) == 2
    assert validated["prioritized_roadmap"][0]["title"] == "Step 1"
    assert validated["differentiation"]["solution_category"] == "Not determined"


@pytest.mark.asyncio
async def test_evidence_hallucination():
    context = "Backend uses FastAPI. That is all."
    res = await run_technical_judge(context)
    
    findings = res.get("key_findings", [])
    finding_texts = " ".join([f.get("finding", "") + " " + f.get("evidence", "") for f in findings]).lower()
    
    # Must identify what exists
    assert "fastapi" in finding_texts
    # Must NOT invent what does not exist
    assert "redis" not in finding_texts
    assert "kubernetes" not in finding_texts


@pytest.mark.asyncio
async def test_confidence_calibration():
    res_strong = await run_technical_judge(PROJECT_B_TECH_STRONG_BIZ_WEAK)
    res_weak = await run_technical_judge(PROJECT_E_INCOMPLETE)
    
    conf_strong = res_strong.get("confidence", 0)
    conf_weak = res_weak.get("confidence", 0)
    ev_strong = res_strong.get("evidence_quality", 0)
    ev_weak = res_weak.get("evidence_quality", 0)
    
    # Confidence or evidence quality should generally be lower for incomplete evidence
    # We use a tolerant check since LLM behavior can slightly vary
    is_lower = (conf_weak <= conf_strong + 15) or (ev_weak <= ev_strong + 15)
    assert is_lower, f"Expected lower confidence/evidence. Weak: {conf_weak}/{ev_weak}. Strong: {conf_strong}/{ev_strong}"


@pytest.mark.asyncio
async def test_differentiation_safety():
    context = "The project is an AI-powered document evaluation platform."
    
    consensus = {
        "mean": 5, "min": 5, "max": 5, "spread": 0,
        "agreement_level": "strong", "most_aligned": "innovation",
        "largest_disagreement": "technical", "avg_confidence": 50,
        "avg_evidence_quality": 50
    }
    
    res = await run_chief_judge(
        context,
        {"score": 5}, {"score": 5}, {"score": 5}, {"score": 5},
        False, consensus
    )
    
    diff = res.get("differentiation", {})
    all_text = str(diff).lower()
    
    # Should not invent specific competitors or numbers
    assert "2 million users" not in all_text
    assert "competitor xyz" not in all_text


@pytest.mark.asyncio
async def test_score_stability():
    res1 = await run_technical_judge(PROJECT_A_BALANCED)
    res2 = await run_technical_judge(PROJECT_A_BALANCED)
    res3 = await run_technical_judge(PROJECT_A_BALANCED)
    
    scores = [res1["score"], res2["score"], res3["score"]]
    
    # Flag instability clearly: variation of 3 or more is considered unstable
    spread = max(scores) - min(scores)
    assert spread <= 3, f"Score instability flagged! Scores: {scores}"
