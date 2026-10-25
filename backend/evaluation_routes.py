"""
Saved evaluation routes for IdeaValidator-AI.

All endpoints require authentication. Ownership is derived from the
server-side JWT identity, never from client-supplied user IDs.

Endpoints:
  POST   /evaluations/save    — Save evaluation results
  GET    /evaluations          — List user's saved evaluations
  GET    /evaluations/{id}     — Get a single saved evaluation
  DELETE /evaluations/{id}     — Delete a saved evaluation
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from auth import (
    count_user_evaluations,
    delete_evaluation,
    get_current_user,
    get_evaluation_by_id,
    list_user_evaluations,
    save_evaluation,
)

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/evaluations", tags=["evaluations"])

# Maximum saved evaluations per user (prevent storage abuse)
MAX_SAVED_EVALUATIONS = 100


class SaveEvaluationRequest(BaseModel):
    title: Optional[str] = "Untitled Evaluation"
    attack_mode: Optional[bool] = False
    results: dict


@router.post("/save")
async def save_eval(body: SaveEvaluationRequest, request: Request):
    """
    Save an evaluation result to the authenticated user's history.
    Owner is derived from the access token, never from client input.
    """
    user = await get_current_user(request)
    user_id = user["id"]

    # Check per-user limit
    count = await count_user_evaluations(user_id)
    if count >= MAX_SAVED_EVALUATIONS:
        raise HTTPException(
            status_code=409,
            detail=f"Maximum saved evaluations ({MAX_SAVED_EVALUATIONS}) reached. "
                   "Please delete older evaluations before saving new ones.",
        )

    # Validate results is non-empty
    if not body.results:
        raise HTTPException(status_code=422, detail="Evaluation results are required.")

    title = (body.title or "").strip() or "Untitled Evaluation"
    if len(title) > 200:
        title = title[:200]

    results_json = json.dumps(body.results, ensure_ascii=False)

    record = await save_evaluation(
        user_id=user_id,
        title=title,
        attack_mode=body.attack_mode or False,
        results_json=results_json,
    )

    return JSONResponse(
        status_code=201,
        content={
            "id": record["id"],
            "title": record["title"],
            "attack_mode": bool(record["attack_mode"]),
            "created_at": record["created_at"],
        },
    )


@router.get("")
async def list_evals(request: Request, limit: int = 50, offset: int = 0):
    """
    List the authenticated user's saved evaluations.
    Returns metadata only (no full results JSON) for list performance.
    """
    user = await get_current_user(request)

    # Clamp limit
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    evaluations = await list_user_evaluations(user["id"], limit=limit, offset=offset)
    total = await count_user_evaluations(user["id"])

    return {
        "evaluations": [
            {
                "id": ev["id"],
                "title": ev["title"],
                "attack_mode": bool(ev["attack_mode"]),
                "overall_score": ev.get("overall_score"),
                "research_assisted": bool(ev.get("research_assisted")),
                "created_at": ev["created_at"],
            }
            for ev in evaluations
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{eval_id}")
async def get_eval(eval_id: str, request: Request):
    """
    Get a single saved evaluation with full results.
    Returns 404 for missing or non-owned evaluations (no info leakage).
    """
    user = await get_current_user(request)

    record = await get_evaluation_by_id(eval_id, user["id"])
    if not record:
        raise HTTPException(status_code=404, detail="Evaluation not found.")

    return {
        "id": record["id"],
        "title": record["title"],
        "attack_mode": bool(record["attack_mode"]),
        "results": json.loads(record["results_json"]),
        "created_at": record["created_at"],
    }


@router.delete("/{eval_id}")
async def delete_eval(eval_id: str, request: Request):
    """
    Delete a saved evaluation. Only the owner can delete.
    Returns 404 for missing or non-owned evaluations (no info leakage).
    """
    user = await get_current_user(request)

    deleted = await delete_evaluation(eval_id, user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Evaluation not found.")

    return {"status": "deleted", "id": eval_id}
