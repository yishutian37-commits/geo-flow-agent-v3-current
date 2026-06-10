from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.corpus_item import CorpusItem
from app.models.project import Project
from app.prompts.templates import render_prompt_template


ALLOWED_KNOWLEDGE_LAYERS = {
    "basic_info",
    "story",
    "judgment",
    "competitor_feedback",
    "content_material",
    "review_data",
    "other",
}
ALLOWED_BUSINESS_USES = {
    "fact_extraction",
    "question_generation",
    "content_writing",
    "monitoring_review",
    "compliance",
    "general",
}
ALLOWED_EVIDENCE_LEVELS = {
    "official",
    "verified",
    "user_feedback",
    "internal",
    "unverified",
}


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    cleaned = (raw_text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    if not cleaned:
        raise ValueError("AI 没有返回可解析的知识库 JSON。")

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("AI 没有返回可解析的知识库 JSON。")
        parsed = json.loads(cleaned[start : end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("AI 知识库入库结果必须是 JSON 对象。")
    return parsed


def _normalize_choice(value: Any, allowed: set[str], fallback: str) -> str:
    normalized = str(value or "").strip()
    return normalized if normalized in allowed else fallback


def _normalize_tags(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, list):
        tags = [str(item).strip() for item in value if str(item).strip()]
        return ",".join(tags[:12]) if tags else None
    tags = str(value).strip()
    return tags or None


class ProjectKnowledgeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _build_llm_client(self, model_id: Optional[str] = None):
        from app.llm.client import LLMClientFactory
        from app.llm.registry import get_model_registry

        registry = get_model_registry()
        config = registry.get_model(model_id) if model_id else registry.get_default_model()
        if not config or not config.api_key:
            raise ValueError("请先在 AI 模型管理中配置默认模型和 API Key，再使用 AI 分层入库。")
        return LLMClientFactory.create_client_from_config(config.to_dict(mask_api_key=False))

    async def _ensure_project_exists(self, project_id: UUID) -> None:
        result = await self.db.execute(select(Project).where(Project.id == project_id))
        if not result.scalar_one_or_none():
            raise ValueError("项目不存在，无法写入项目知识库。")

    def _normalize_item(
        self,
        raw_item: Dict[str, Any],
        *,
        default_title: str,
        source_type: Optional[str],
        source_url: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        content = str(raw_item.get("content") or "").strip()
        if len(content) < 2:
            return None

        title = str(raw_item.get("title") or default_title or "未命名知识").strip()[:500]
        knowledge_layer = _normalize_choice(
            raw_item.get("knowledge_layer"),
            ALLOWED_KNOWLEDGE_LAYERS,
            "other",
        )
        business_use = _normalize_choice(
            raw_item.get("business_use"),
            ALLOWED_BUSINESS_USES,
            "general",
        )
        evidence_level = _normalize_choice(
            raw_item.get("evidence_level"),
            ALLOWED_EVIDENCE_LEVELS,
            "unverified",
        )

        return {
            "title": title,
            "content": content,
            "source_type": source_type,
            "source_url": source_url,
            "tags": _normalize_tags(raw_item.get("tags")),
            "knowledge_layer": knowledge_layer,
            "business_use": business_use,
            "evidence_level": evidence_level,
            "reusable_scope": "project",
            "contains_factual_claim": bool(raw_item.get("contains_factual_claim")),
        }

    async def ingest_material(
        self,
        *,
        project_id: UUID,
        title: Optional[str],
        content: str,
        source_type: Optional[str] = None,
        source_url: Optional[str] = None,
        max_items: int = 20,
        model_id: Optional[str] = None,
    ) -> List[CorpusItem]:
        await self._ensure_project_exists(project_id)
        material = (content or "").strip()
        if len(material) < 10:
            raise ValueError("用于 AI 分层入库的资料内容太短。")

        max_items = max(1, min(int(max_items or 20), 50))
        prompt = render_prompt_template(
            "geo/project_knowledge_ingest_v1.md",
            {
                "title": title or "未命名资料",
                "content": material[:50000],
                "max_items": max_items,
            },
        )
        client = self._build_llm_client(model_id=model_id)
        response = await client.chat(
            messages=[
                {"role": "system", "content": "你是严谨的 GEO 项目知识库入库助手，只输出严格 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=5000,
        )

        parsed = _extract_json_object(response.content)
        raw_items = parsed.get("items", [])
        if not isinstance(raw_items, list):
            raise ValueError("AI 知识库入库结果中的 items 必须是数组。")

        normalized_items: List[Dict[str, Any]] = []
        seen = set()
        for raw_item in raw_items[:max_items]:
            if not isinstance(raw_item, dict):
                continue
            normalized = self._normalize_item(
                raw_item,
                default_title=title or "未命名资料",
                source_type=source_type,
                source_url=source_url,
            )
            if not normalized:
                continue
            dedupe_key = (normalized["title"], normalized["content"])
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            normalized_items.append(normalized)

        if not normalized_items:
            raise ValueError("AI 没有拆分出可入库的知识资产，请补充更具体的资料后重试。")

        created_items: List[CorpusItem] = []
        for normalized in normalized_items:
            item = CorpusItem(project_id=project_id, **normalized)
            self.db.add(item)
            created_items.append(item)

        await self.db.commit()
        for item in created_items:
            await self.db.refresh(item)
        return created_items
