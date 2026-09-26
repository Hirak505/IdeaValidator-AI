import asyncio
from prompts import (
    INNOVATION_JUDGE_PROMPT,
    TECHNICAL_JUDGE_PROMPT,
    BUSINESS_JUDGE_PROMPT,
    PRESENTATION_JUDGE_PROMPT,
    CHIEF_JUDGE_PROMPT,
    ATTACK_MODE_INSTRUCTIONS,
    NORMAL_MODE_INSTRUCTIONS,
)
from gemini_service import call_judge
import json


VALID_EVIDENCE_TYPES = {"documented_fact", "supported_inference", "not_documented", "requires_verification", "unsupported_claim", "not_verified"}
VALID_PRIORITIES = {"P0", "P1", "P2"}
VALID_IMPACT_EFFORT = {"High", "Medium", "Low"}


def _sanitize_string_list(items: list, max_items: int = 5, max_length: int = 300) -> list[str]:
    """Sanitize lists of strings returned from LLM to prevent prompt injection echo attacks."""
    if not isinstance(items, list):
        return ["Not available"]
    cleaned = []
    for item in items[:max_items]:
        if isinstance(item, str):
            clean_item = item.strip()[:max_length]
            if clean_item:
                cleaned.append(clean_item)
    return cleaned if cleaned else ["Not available"]


def _clamp_int(value, lo: int, hi: int, default: int) -> int:
    """Safely clamp a value to [lo, hi], returning default on failure."""
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _validate_finding(finding: dict) -> dict | None:
    """Validate a single key finding from a judge. Returns None if invalid."""
    if not isinstance(finding, dict):
        return None
    f = finding.get("finding", "")
    if not f or not isinstance(f, str):
        return None
    evidence_type = finding.get("evidence_type", "not_verified")
    if evidence_type not in VALID_EVIDENCE_TYPES:
        evidence_type = "not_verified"
    return {
        "finding": str(f).strip()[:300],
        "evidence": str(finding.get("evidence", "Not directly verified")).strip()[:300],
        "source": str(finding.get("source", "N/A")).strip()[:200],
        "evidence_type": evidence_type,
        "confidence": _clamp_int(finding.get("confidence", 50), 0, 100, 50),
    }


def _validate_judge_result(result: dict, judge_type: str) -> dict:
    """Ensure judge result has required fields, correct types, and safe bounded values."""
    if not isinstance(result, dict):
        result = {}

    defaults = {
        "score": 5,
        "strengths": ["Clear project submission"],
        "weaknesses": ["Further details needed"],
        "comments": f"The {judge_type} evaluation was completed with default parameters.",
    }
    for key, default in defaults.items():
        if key not in result or result[key] is None:
            result[key] = default

    # Clamp score to 0-10
    result["score"] = _clamp_int(result["score"], 0, 10, 5)

    result["strengths"] = _sanitize_string_list(result.get("strengths", []))
    result["weaknesses"] = _sanitize_string_list(result.get("weaknesses", []))
    result["comments"] = str(result.get("comments", ""))[:500]

    # Confidence and evidence quality
    result["confidence"] = _clamp_int(result.get("confidence"), 0, 100, 50)
    result["evidence_quality"] = _clamp_int(result.get("evidence_quality"), 0, 100, 50)

    # Validate key_findings
    raw_findings = result.get("key_findings", [])
    if not isinstance(raw_findings, list):
        raw_findings = []
    validated_findings = []
    for finding in raw_findings[:5]:
        validated = _validate_finding(finding)
        if validated:
            validated_findings.append(validated)
    if not validated_findings:
        validated_findings = [{
            "finding": f"General {judge_type} evaluation completed",
            "evidence": "Not directly verified",
            "source": "N/A",
            "evidence_type": "not_verified",
            "confidence": 50,
        }]
    result["key_findings"] = validated_findings

    return {
        "score": result["score"],
        "strengths": result["strengths"],
        "weaknesses": result["weaknesses"],
        "comments": result["comments"],
        "confidence": result["confidence"],
        "evidence_quality": result["evidence_quality"],
        "key_findings": result["key_findings"],
    }


def _validate_roadmap_item(item: dict) -> dict | None:
    """Validate a single prioritized roadmap item. Returns None if invalid."""
    if not isinstance(item, dict):
        return None
    title = str(item.get("title", "")).strip()[:200]
    if not title:
        return None
    return {
        "priority": item.get("priority", "P1") if item.get("priority") in VALID_PRIORITIES else "P1",
        "title": title,
        "reason": str(item.get("reason", "Based on evaluation feedback")).strip()[:300],
        "impact": item.get("impact", "Medium") if item.get("impact") in VALID_IMPACT_EFFORT else "Medium",
        "effort": item.get("effort", "Medium") if item.get("effort") in VALID_IMPACT_EFFORT else "Medium",
    }


def _validate_chief_result(result: dict) -> dict:
    """Ensure chief judge result has all required fields with strict sanitization."""
    if not isinstance(result, dict):
        result = {}

    defaults = {
        "overall_score": 5.0,
        "final_verdict": "Evaluation completed based on available project materials.",
        "top_strengths": ["Clear project definition"],
        "top_improvements": ["Expand technical implementation details"],
        "improvement_roadmap": ["Review feedback and iterate on core architecture."],
        "judge_questions": [
            "Can you walk us through your core value proposition?",
            "What is your go-to-market strategy?",
            "How does your technical architecture scale?",
            "Who are your target users and how did you validate the problem?",
            "What is your competitive advantage?",
            "What are the next three milestones after this hackathon?",
        ],
    }
    for key, default in defaults.items():
        if key not in result or result[key] is None:
            result[key] = default

    # Clamp overall score
    try:
        result["overall_score"] = round(max(0.0, min(10.0, float(result["overall_score"]))), 1)
    except (TypeError, ValueError):
        result["overall_score"] = 5.0

    result["final_verdict"] = str(result.get("final_verdict", ""))[:1000]
    result["top_strengths"] = _sanitize_string_list(result.get("top_strengths", []))
    result["top_improvements"] = _sanitize_string_list(result.get("top_improvements", []))
    result["improvement_roadmap"] = _sanitize_string_list(result.get("improvement_roadmap", []))
    result["judge_questions"] = _sanitize_string_list(result.get("judge_questions", []), max_items=6, max_length=250)

    # Confidence and evidence quality
    result["confidence"] = _clamp_int(result.get("confidence"), 0, 100, 50)
    result["evidence_quality"] = _clamp_int(result.get("evidence_quality"), 0, 100, 50)

    # Validate prioritized_roadmap
    raw_roadmap = result.get("prioritized_roadmap", [])
    if not isinstance(raw_roadmap, list):
        raw_roadmap = []
    validated_roadmap = []
    for item in raw_roadmap[:5]:
        validated = _validate_roadmap_item(item)
        if validated:
            validated_roadmap.append(validated)
    # Fallback: convert plain improvement_roadmap strings to structured format
    if not validated_roadmap:
        for step in result.get("improvement_roadmap", ["Review feedback and iterate"])[:5]:
            validated_roadmap.append({
                "priority": "P1",
                "title": str(step)[:200],
                "reason": "Based on evaluation feedback",
                "impact": "Medium",
                "effort": "Medium",
            })
    result["prioritized_roadmap"] = validated_roadmap

    # Validate differentiation
    diff = result.get("differentiation", {})
    if not isinstance(diff, dict):
        diff = {}
    # Unsupported claims: empty list is valid (no unsupported claims is good)
    raw_unsupported = diff.get("unsupported_claims", [])
    if not isinstance(raw_unsupported, list):
        raw_unsupported = []
    unsupported_claims = []
    for item in raw_unsupported[:5]:
        if isinstance(item, str) and item.strip():
            unsupported_claims.append(item.strip()[:300])

    result["differentiation"] = {
        "solution_category": str(diff.get("solution_category", "Not determined"))[:200],
        "claimed_differentiators": _sanitize_string_list(diff.get("claimed_differentiators", ["Not identified"]), max_items=5),
        "differentiation_strengths": _sanitize_string_list(diff.get("differentiation_strengths", ["Not determined"]), max_items=5),
        "differentiation_gaps": _sanitize_string_list(diff.get("differentiation_gaps", ["Not determined"]), max_items=5),
        "unsupported_claims": unsupported_claims,
        "limitation_note": str(diff.get("limitation_note", "Analysis based solely on submitted materials without external verification."))[:500],
    }

    return {
        "overall_score": result["overall_score"],
        "final_verdict": result["final_verdict"],
        "top_strengths": result["top_strengths"],
        "top_improvements": result["top_improvements"],
        "improvement_roadmap": result["improvement_roadmap"],
        "judge_questions": result["judge_questions"],
        "confidence": result["confidence"],
        "evidence_quality": result["evidence_quality"],
        "prioritized_roadmap": result["prioritized_roadmap"],
        "differentiation": result["differentiation"],
    }


def calculate_consensus(innovation: dict, technical: dict, business: dict, presentation: dict) -> dict:
    """Calculate judge consensus statistics programmatically. No AI involved."""
    scores = {
        "innovation": innovation.get("score", 5),
        "technical": technical.get("score", 5),
        "business": business.get("score", 5),
        "presentation": presentation.get("score", 5),
    }
    values = list(scores.values())
    mean = sum(values) / len(values)
    min_score = min(values)
    max_score = max(values)
    spread = max_score - min_score

    # Most aligned = closest to mean
    most_aligned = min(scores.items(), key=lambda x: abs(x[1] - mean))[0]
    # Largest disagreement = farthest from mean
    largest_disagreement = max(scores.items(), key=lambda x: abs(x[1] - mean))[0]

    # Agreement level based on spread
    if spread <= 2:
        agreement_level = "strong"
    elif spread <= 4:
        agreement_level = "moderate"
    else:
        agreement_level = "weak"

    # Deterministic averages of confidence and evidence_quality across judges
    judges = [innovation, technical, business, presentation]
    avg_confidence = round(sum(j.get("confidence", 50) for j in judges) / 4)
    avg_evidence_quality = round(sum(j.get("evidence_quality", 50) for j in judges) / 4)

    return {
        "mean": round(mean, 1),
        "min": min_score,
        "max": max_score,
        "spread": spread,
        "scores": scores,
        "most_aligned": most_aligned,
        "largest_disagreement": largest_disagreement,
        "agreement_level": agreement_level,
        "avg_confidence": avg_confidence,
        "avg_evidence_quality": avg_evidence_quality,
    }


async def run_innovation_judge(project_context: str) -> dict:
    prompt = INNOVATION_JUDGE_PROMPT.format(project_context=project_context)
    result = await call_judge(prompt, "Innovation Judge")
    return _validate_judge_result(result, "innovation")


async def run_technical_judge(project_context: str) -> dict:
    prompt = TECHNICAL_JUDGE_PROMPT.format(project_context=project_context)
    result = await call_judge(prompt, "Technical Judge")
    return _validate_judge_result(result, "technical")


async def run_business_judge(project_context: str) -> dict:
    prompt = BUSINESS_JUDGE_PROMPT.format(project_context=project_context)
    result = await call_judge(prompt, "Business Judge")
    return _validate_judge_result(result, "business")


async def run_presentation_judge(project_context: str) -> dict:
    prompt = PRESENTATION_JUDGE_PROMPT.format(project_context=project_context)
    result = await call_judge(prompt, "Presentation Judge")
    return _validate_judge_result(result, "presentation")


async def run_chief_judge(
    project_context: str,
    innovation: dict,
    technical: dict,
    business: dict,
    presentation: dict,
    attack_mode: bool = False,
    consensus: dict = None,
) -> dict:
    attack_instructions = ATTACK_MODE_INSTRUCTIONS if attack_mode else NORMAL_MODE_INSTRUCTIONS
    attack_mode_label = "ENABLED - Be adversarial and critical" if attack_mode else "DISABLED - Be constructive"

    # Format consensus data for the prompt
    consensus_data = "Not available"
    if consensus:
        consensus_data = (
            f"Mean Score: {consensus['mean']}/10 | "
            f"Score Range: {consensus['min']}-{consensus['max']} | "
            f"Spread: {consensus['spread']} points | "
            f"Agreement Level: {consensus['agreement_level']} | "
            f"Most Aligned Judge: {consensus['most_aligned']} | "
            f"Largest Disagreement: {consensus['largest_disagreement']} | "
            f"Average Judge Confidence: {consensus['avg_confidence']}% | "
            f"Average Evidence Quality: {consensus['avg_evidence_quality']}%"
        )

    prompt = CHIEF_JUDGE_PROMPT.format(
        project_context=project_context,
        innovation_report=json.dumps(innovation),
        technical_report=json.dumps(technical),
        business_report=json.dumps(business),
        presentation_report=json.dumps(presentation),
        attack_mode=attack_mode_label,
        attack_instructions=attack_instructions,
        consensus_data=consensus_data,
    )
    result = await call_judge(prompt, "Chief Judge")
    return _validate_chief_result(result)


async def run_all_judges(project_context: str, attack_mode: bool = False) -> dict:
    """Run all four specialist judges in parallel, then run the chief judge."""
    # Run specialist judges concurrently
    innovation, technical, business, presentation = await asyncio.gather(
        run_innovation_judge(project_context),
        run_technical_judge(project_context),
        run_business_judge(project_context),
        run_presentation_judge(project_context),
    )

    # Calculate consensus programmatically (no AI needed)
    consensus = calculate_consensus(innovation, technical, business, presentation)

    # Chief judge synthesizes all results
    chief = await run_chief_judge(
        project_context, innovation, technical, business, presentation, attack_mode, consensus
    )

    return {
        "innovation": innovation,
        "technical": technical,
        "business": business,
        "presentation": presentation,
        "chief_judge": chief,
        "consensus": consensus,
    }
