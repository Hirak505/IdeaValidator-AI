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
    try:
        result["score"] = max(0, min(10, int(result["score"])))
    except (TypeError, ValueError):
        result["score"] = 5

    result["strengths"] = _sanitize_string_list(result.get("strengths", []))
    result["weaknesses"] = _sanitize_string_list(result.get("weaknesses", []))
    result["comments"] = str(result.get("comments", ""))[:500]

    return {
        "score": result["score"],
        "strengths": result["strengths"],
        "weaknesses": result["weaknesses"],
        "comments": result["comments"],
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

    return {
        "overall_score": result["overall_score"],
        "final_verdict": result["final_verdict"],
        "top_strengths": result["top_strengths"],
        "top_improvements": result["top_improvements"],
        "improvement_roadmap": result["improvement_roadmap"],
        "judge_questions": result["judge_questions"],
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
) -> dict:
    attack_instructions = ATTACK_MODE_INSTRUCTIONS if attack_mode else NORMAL_MODE_INSTRUCTIONS
    attack_mode_label = "ENABLED - Be adversarial and critical" if attack_mode else "DISABLED - Be constructive"

    prompt = CHIEF_JUDGE_PROMPT.format(
        project_context=project_context,
        innovation_report=json.dumps(innovation),
        technical_report=json.dumps(technical),
        business_report=json.dumps(business),
        presentation_report=json.dumps(presentation),
        attack_mode=attack_mode_label,
        attack_instructions=attack_instructions,
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

    # Chief judge synthesizes all results
    chief = await run_chief_judge(
        project_context, innovation, technical, business, presentation, attack_mode
    )

    return {
        "innovation": innovation,
        "technical": technical,
        "business": business,
        "presentation": presentation,
        "chief_judge": chief,
    }
