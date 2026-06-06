from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question_template_feedback import QuestionTemplateFeedback
from app.services.question_archetype import get_question_archetype, save_question_archetype


QUESTION_TEMPLATE_ACTIONS = {
    "create_question",
    "update_question",
    "delete_question",
    "toggle_enabled",
    "toggle_focus",
}

COMMON_LOW_VALUE_TERMS = {
    "deepseek",
    "kimi",
    "璞嗗寘",
    "鏂囧績",
    "閫氫箟",
    "鍗冮棶",
    "chatgpt",
    "gemini",
    "mimo",
    "妯″瀷",
    "AI骞冲彴",
}

TRAINING_BIASED_TERMS = {
    "鎶ュ悕",
    "瀛﹀憳",
    "澶嶈",
    "甯堣祫",
    "鏍″尯",
    "閫氳繃鐜?,
    "璇剧▼",
    "寮€鐝?,
    "鎷胯瘉",
}


def _json_dumps(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_loads(value: Optional[str]) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return value


def _clean_text(value: Optional[str], limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _unique_keep_order(items: Iterable[Any], limit: int = 20) -> List[str]:
    result: List[str] = []
    seen = set()
    for item in items:
        text = _clean_text(str(item or ""), 160)
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
        if len(result) >= limit:
            break
    return result


def _extract_candidate_terms(texts: Iterable[str], excluded_texts: Iterable[str] = ()) -> List[str]:
    joined = "\n".join(text for text in texts if text)
    excluded = "\n".join(text for text in excluded_texts if text)
    candidates = []
    for term in sorted(COMMON_LOW_VALUE_TERMS | TRAINING_BIASED_TERMS, key=len, reverse=True):
        if term and term in joined and term not in excluded:
            candidates.append(term)
    return _unique_keep_order(candidates, limit=16)


def _feedback_to_dict(item: QuestionTemplateFeedback) -> Dict[str, Any]:
    return {
        "id": str(item.id),
        "project_id": str(item.project_id),
        "group_id": str(item.group_id) if item.group_id else None,
        "question_id": str(item.question_id) if item.question_id else None,
        "industry": item.industry,
        "action": item.action,
        "before_text": item.before_text,
        "after_text": item.after_text,
        "before_payload": _json_loads(item.before_payload),
        "after_payload": _json_loads(item.after_payload),
        "status": item.status,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


async def record_question_template_feedback(
    db: AsyncSession,
    *,
    project_id: str,
    industry: str,
    action: str,
    group_id: Optional[str] = None,
    question_id: Optional[str] = None,
    before_text: Optional[str] = None,
    after_text: Optional[str] = None,
    before_payload: Optional[Dict[str, Any]] = None,
    after_payload: Optional[Dict[str, Any]] = None,
) -> Optional[QuestionTemplateFeedback]:
    if action not in QUESTION_TEMPLATE_ACTIONS:
        return None
    if not project_id or not industry:
        return None
    before_clean = _clean_text(before_text, 2000)
    after_clean = _clean_text(after_text, 2000)
    if before_clean == after_clean and action == "update_question":
        return None

    feedback = QuestionTemplateFeedback(
        project_id=str(project_id),
        group_id=str(group_id) if group_id else None,
        question_id=str(question_id) if question_id else None,
        industry=str(industry),
        action=action,
        before_text=before_clean or None,
        after_text=after_clean or None,
        before_payload=_json_dumps(before_payload),
        after_payload=_json_dumps(after_payload),
        status="pending",
    )
    db.add(feedback)
    return feedback


async def list_question_template_feedbacks(
    db: AsyncSession,
    *,
    industry: Optional[str] = None,
    status: str = "pending",
    limit: int = 200,
) -> List[Dict[str, Any]]:
    query = select(QuestionTemplateFeedback)
    if industry:
        query = query.where(QuestionTemplateFeedback.industry == industry)
    if status:
        query = query.where(QuestionTemplateFeedback.status == status)
    query = query.order_by(QuestionTemplateFeedback.created_at.desc()).limit(max(1, min(limit, 500)))
    result = await db.execute(query)
    return [_feedback_to_dict(item) for item in result.scalars().all()]


async def build_question_template_suggestions(
    db: AsyncSession,
    *,
    industry: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    feedbacks = await list_question_template_feedbacks(db, industry=industry, status="pending", limit=limit)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in feedbacks:
        grouped.setdefault(item["industry"], []).append(item)

    suggestions: List[Dict[str, Any]] = []
    for industry_key, items in grouped.items():
        negative_question_ids = {
            item.get("question_id")
            for item in items
            if item.get("action") == "delete_question" and item.get("question_id")
        }
        negative_question_ids.update(
            item.get("question_id")
            for item in items
            if item.get("action") == "toggle_enabled"
            and item.get("question_id")
            and isinstance(item.get("after_payload"), dict)
            and item["after_payload"].get("enabled") is False
        )
        created_or_after = [
            item.get("after_text")
            for item in items
            if item.get("action") in {"create_question", "update_question"} and item.get("after_text")
            and item.get("question_id") not in negative_question_ids
        ]
        deleted_or_before = [
            item.get("before_text")
            for item in items
            if item.get("action") in {"delete_question", "update_question"} and item.get("before_text")
        ]
        disabled_texts = [
            item.get("after_text") or item.get("before_text")
            for item in items
            if item.get("action") == "toggle_enabled"
        ]
        negative_examples = _unique_keep_order([*deleted_or_before, *disabled_texts], limit=12)
        positive_examples = _unique_keep_order(created_or_after, limit=12)
        add_forbidden_terms = _extract_candidate_terms([*deleted_or_before, *disabled_texts], created_or_after)

        if not positive_examples and not negative_examples and not add_forbidden_terms:
            continue

        reason_parts = []
        if positive_examples:
            reason_parts.append("妫€娴嬪埌浜哄伐鏂板鎴栨敼鍐欏悗鐨勯珮璐ㄩ噺闂锛屽彲娌夋穩涓烘鍚戞牱渚?)
        if negative_examples:
            reason_parts.append("妫€娴嬪埌浜哄伐鍒犻櫎銆佺鐢ㄦ垨鏀瑰啓鍓嶇殑闂锛屽彲娌夋穩涓哄弽鍚戞牱渚?)
        if add_forbidden_terms:
            reason_parts.append("妫€娴嬪埌琚垹闄ゆ垨鏇挎崲鐨勯棶棰樹腑瀛樺湪鍙鐢ㄧ殑绂佺敤璇?)

        suggestions.append({
            "industry": industry_key,
            "events": len(items),
            "add_forbidden_terms": add_forbidden_terms,
            "positive_examples": positive_examples,
            "negative_examples": negative_examples,
            "feedback_ids": [item["id"] for item in items],
            "reason": "锛?.join(reason_parts) or "鏍规嵁浜哄伐闂璋冩暣鐢熸垚妯℃澘浼樺寲寤鸿",
        })
    return suggestions


async def apply_question_template_suggestion(
    db: AsyncSession,
    *,
    industry: str,
    add_forbidden_terms: Optional[List[str]] = None,
    positive_examples: Optional[List[str]] = None,
    negative_examples: Optional[List[str]] = None,
    feedback_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not industry:
        raise ValueError("industry is required")

    current = get_question_archetype(industry)
    existing_forbidden = current.get("forbidden_terms") or []
    existing_positive = current.get("positive_examples") or []
    existing_negative = current.get("negative_examples") or []
    payload = {
        "forbidden_terms": _unique_keep_order([*existing_forbidden, *(add_forbidden_terms or [])], limit=80),
        "positive_examples": _unique_keep_order([*existing_positive, *(positive_examples or [])], limit=40),
        "negative_examples": _unique_keep_order([*existing_negative, *(negative_examples or [])], limit=40),
    }
    resolved = save_question_archetype(industry, payload)

    ids = [str(item) for item in feedback_ids or [] if str(item).strip()]
    if ids:
        result = await db.execute(
            select(QuestionTemplateFeedback).where(QuestionTemplateFeedback.id.in_(ids))
        )
        now = datetime.now(timezone.utc)
        for feedback in result.scalars().all():
            feedback.status = "applied"
            feedback.applied_at = now
        await db.commit()

    return {
        "industry": industry,
        "applied": payload,
        "resolved": resolved,
    }
