from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.question_archetype import (
    get_ai_platform_terms,
    get_question_archetype,
    get_service_patterns,
    list_question_archetype_summaries,
    load_question_archetypes,
    save_question_archetype,
)
from app.services.question_template_learning import (
    apply_question_template_suggestion,
    build_question_template_suggestions,
    list_question_template_feedbacks,
)

router = APIRouter()


@router.get("")
async def list_question_archetypes():
    data = load_question_archetypes()
    return {
        "version": data.get("version"),
        "description": data.get("description"),
        "ai_platform_terms": get_ai_platform_terms(),
        "service_patterns": get_service_patterns(),
        "industries": list_question_archetype_summaries(),
    }


@router.get("/learning/feedbacks")
async def list_question_learning_feedbacks(
    industry: str | None = Query(None),
    status: str = Query("pending"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    return {
        "items": await list_question_template_feedbacks(
            db,
            industry=industry,
            status=status,
            limit=limit,
        )
    }


@router.get("/learning/suggestions")
async def list_question_learning_suggestions(
    industry: str | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    return {
        "items": await build_question_template_suggestions(
            db,
            industry=industry,
            limit=limit,
        )
    }


@router.post("/learning/apply")
async def apply_question_learning_suggestion(
    payload: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await apply_question_template_suggestion(
            db,
            industry=str(payload.get("industry") or ""),
            add_forbidden_terms=payload.get("add_forbidden_terms") or [],
            positive_examples=payload.get("positive_examples") or [],
            negative_examples=payload.get("negative_examples") or [],
            feedback_ids=payload.get("feedback_ids") or [],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{industry}")
async def get_question_archetype_detail(industry: str):
    data = load_question_archetypes()
    raw = (data.get("industries") or {}).get(industry)
    if raw is None:
        raise HTTPException(status_code=404, detail="Question archetype not found")
    return {
        "industry": industry,
        "raw": raw,
        "resolved": get_question_archetype(industry),
    }


@router.put("/{industry}")
async def update_question_archetype(industry: str, payload: Dict[str, Any] = Body(...)):
    allowed_fields = {
        "extends",
        "entity_label",
        "fallback_service",
        "fallback_service_suffix",
        "fallback_competitor_prefix",
        "copy",
        "forbidden_terms",
        "positive_examples",
        "negative_examples",
        "service_patterns",
    }
    data = {key: payload.get(key) for key in allowed_fields if key in payload}
    if "copy" in data and not isinstance(data["copy"], dict):
        raise HTTPException(status_code=400, detail="copy must be an object")
    for list_field in ["forbidden_terms", "positive_examples", "negative_examples", "service_patterns"]:
        if list_field in data and data[list_field] is None:
            data[list_field] = []
    try:
        resolved = save_question_archetype(industry, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "industry": industry,
        "resolved": resolved,
    }
