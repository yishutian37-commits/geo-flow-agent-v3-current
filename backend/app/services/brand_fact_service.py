"""
品牌事实库 Service
处理 brand_facts 的 CRUD 和 Extract to Brand Fact 流程
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
import json
import re

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.brand_fact import BrandFact
from app.models.brand_fact_event import BrandFactEvent
from app.models.brand import Brand
from app.models.corpus_item import CorpusItem
from app.schemas.brand_fact import BrandFactCreate


ALLOWED_FACT_TYPES = {
    "qualification",
    "certification",
    "address",
    "phone",
    "contact",
    "price",
    "case_study",
    "founding_date",
    "product",
    "service",
    "company_profile",
    "website",
    "business_hours",
    "teacher",
    "course",
    "honor",
}

ALLOWED_FACT_SCOPES = {"public", "internal", "restricted"}
ALLOWED_RISK_LEVELS = {"low", "medium", "high"}


def _parse_llm_json(raw_text: str) -> Dict[str, Any]:
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("AI did not return valid JSON")
        parsed = json.loads(cleaned[start : end + 1])

    if isinstance(parsed, list):
        return {"facts": parsed}
    if not isinstance(parsed, dict):
        raise ValueError("AI JSON must be an object or array")
    return parsed


def _normalize_fact_candidate(candidate: Dict[str, Any], source: str) -> Optional[Dict[str, Any]]:
    value = str(candidate.get("value") or "").strip()
    if len(value) < 2:
        return None

    fact_type = str(candidate.get("fact_type") or "company_profile").strip()
    if fact_type not in ALLOWED_FACT_TYPES:
        fact_type = "company_profile"

    fact_scope = str(candidate.get("fact_scope") or "public").strip()
    if fact_scope not in ALLOWED_FACT_SCOPES:
        fact_scope = "public"

    risk_level = str(candidate.get("risk_level") or "low").strip()
    if risk_level not in ALLOWED_RISK_LEVELS:
        risk_level = "low"

    public_wording = str(candidate.get("public_wording") or value).strip()
    source_excerpt = str(candidate.get("source_excerpt") or "").strip()
    confidence = candidate.get("confidence")
    note_parts = ["AI extracted from pasted enterprise material"]
    if source_excerpt:
        note_parts.append(f"source_excerpt: {source_excerpt[:300]}")
    if confidence is not None:
        note_parts.append(f"confidence: {confidence}")

    return {
        "fact_type": fact_type,
        "value": value,
        "source": source,
        "evidence_type": "ai_text_extraction",
        "fact_scope": fact_scope,
        "public_wording": public_wording,
        "internal_note": "\n".join(note_parts),
        "risk_level": risk_level,
    }


class BrandFactService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _snapshot_fact(self, fact: BrandFact) -> Dict[str, Any]:
        return {
            "id": str(fact.id) if fact.id else None,
            "brand_id": str(fact.brand_id) if fact.brand_id else None,
            "fact_type": fact.fact_type,
            "value": fact.value,
            "source": fact.source,
            "evidence_file_url": fact.evidence_file_url,
            "evidence_type": fact.evidence_type,
            "fact_scope": fact.fact_scope,
            "public_wording": fact.public_wording,
            "internal_note": fact.internal_note,
            "valid_until": fact.valid_until.isoformat() if fact.valid_until else None,
            "risk_level": fact.risk_level,
            "status": fact.status,
            "confirmed_by": str(fact.confirmed_by) if fact.confirmed_by else None,
            "confirmed_at": fact.confirmed_at.isoformat() if fact.confirmed_at else None,
        }

    async def _record_event(
        self,
        fact: BrandFact,
        action: str,
        actor_id: Optional[UUID] = None,
        previous_status: Optional[str] = None,
        note: Optional[str] = None,
        snapshot: Optional[Dict[str, Any]] = None,
    ) -> BrandFactEvent:
        event = BrandFactEvent(
            fact_id=fact.id,
            action=action,
            actor_id=str(actor_id) if actor_id else None,
            previous_status=previous_status,
            new_status=fact.status,
            snapshot_json=json.dumps(snapshot or self._snapshot_fact(fact), ensure_ascii=False),
            note=note,
        )
        self.db.add(event)
        return event

    async def _ensure_valid_brand(self, brand_id: UUID) -> Brand:
        nil_uuid = "00000000-0000-0000-0000-000000000000"
        if str(brand_id) == nil_uuid:
            raise ValueError("品牌事实必须关联到真实品牌主体，请先选择项目/品牌后再添加事实。")
        result = await self.db.execute(select(Brand).where(Brand.id == brand_id))
        brand = result.scalar_one_or_none()
        if not brand:
            raise ValueError("品牌主体不存在，请先创建或选择正确的品牌。")
        return brand

    async def create_fact(self, data: BrandFactCreate, actor_id: Optional[UUID] = None) -> BrandFact:
        """创建新的事实（初始状态为 draft）"""
        await self._ensure_valid_brand(data.brand_id)
        fact = BrandFact(
            brand_id=data.brand_id,
            fact_type=data.fact_type,
            value=data.value,
            source=data.source,
            evidence_file_url=data.evidence_file_url,
            evidence_type=data.evidence_type,
            fact_scope=data.fact_scope,
            public_wording=data.public_wording,
            internal_note=data.internal_note,
            valid_until=data.valid_until,
            risk_level=data.risk_level,
            status="draft",
        )
        self.db.add(fact)
        await self.db.flush()
        await self._record_event(fact, "created", actor_id=actor_id, note="Brand fact created")
        await self.db.commit()
        await self.db.refresh(fact)
        return fact

    async def get_fact(self, fact_id: UUID) -> Optional[BrandFact]:
        """获取事实详情"""
        result = await self.db.execute(select(BrandFact).where(BrandFact.id == fact_id))
        return result.scalar_one_or_none()

    async def list_events(self, fact_id: UUID, skip: int = 0, limit: int = 100) -> List[BrandFactEvent]:
        result = await self.db.execute(
            select(BrandFactEvent)
            .where(BrandFactEvent.fact_id == fact_id)
            .order_by(BrandFactEvent.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_facts(
        self,
        brand_id: Optional[UUID] = None,
        project_id: Optional[UUID] = None,
        status: Optional[str] = None,
        fact_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[BrandFact]:
        """列表查询事实
        支持通过 project_id 筛选（通过 join brands 表）
        """
        from app.models.brand import Brand

        query = select(BrandFact)
        filters = []

        if project_id:
            # 通过 brand_id 关联到 project_id
            query = query.join(Brand, BrandFact.brand_id == Brand.id)
            filters.append(Brand.project_id == project_id)

        if brand_id:
            filters.append(BrandFact.brand_id == brand_id)
        if status:
            filters.append(BrandFact.status == status)
        if fact_type:
            filters.append(BrandFact.fact_type == fact_type)
        if filters:
            query = query.where(and_(*filters))
        query = query.offset(skip).limit(limit).order_by(BrandFact.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def confirm_fact(
        self,
        fact_id: UUID,
        confirmed_by: UUID,
        public_wording: Optional[str] = None,
        confirmation_note: Optional[str] = None,
        evidence_file_url: Optional[str] = None,
        evidence_type: Optional[str] = None,
    ) -> Optional[BrandFact]:
        """
        客户/品牌方确认事实
        状态从 draft → confirmed
        """
        fact = await self.get_fact(fact_id)
        if not fact:
            return None
        if fact.status != "draft":
            raise ValueError(f"Cannot confirm fact with status '{fact.status}'. Only 'draft' can be confirmed.")

        previous_status = fact.status
        previous_snapshot = self._snapshot_fact(fact)
        fact.status = "confirmed"
        fact.confirmed_by = confirmed_by
        fact.confirmed_at = datetime.now(timezone.utc)
        if public_wording:
            fact.public_wording = public_wording
        if evidence_file_url:
            fact.evidence_file_url = evidence_file_url
        if evidence_type:
            fact.evidence_type = evidence_type
        await self._record_event(
            fact,
            "confirmed",
            actor_id=confirmed_by,
            previous_status=previous_status,
            note=confirmation_note,
            snapshot={"before": previous_snapshot, "after": self._snapshot_fact(fact)},
        )

        await self.db.commit()
        await self.db.refresh(fact)
        return fact

    async def dispute_fact(
        self,
        fact_id: UUID,
        reason: str,
        actor_id: Optional[UUID] = None,
    ) -> Optional[BrandFact]:
        """
        标记事实为争议状态
        状态变为 disputed，进入人工处理
        """
        fact = await self.get_fact(fact_id)
        if not fact:
            return None

        previous_status = fact.status
        previous_snapshot = self._snapshot_fact(fact)
        fact.status = "disputed"
        fact.internal_note = f"{fact.internal_note or ''}\n争议原因: {reason}".strip()

        await self._record_event(
            fact,
            "disputed",
            actor_id=actor_id,
            previous_status=previous_status,
            note=reason,
            snapshot={"before": previous_snapshot, "after": self._snapshot_fact(fact)},
        )
        await self.db.commit()
        await self.db.refresh(fact)
        return fact

    async def expire_fact(self, fact_id: UUID, actor_id: Optional[UUID] = None) -> Optional[BrandFact]:
        """标记事实为过期"""
        fact = await self.get_fact(fact_id)
        if not fact:
            return None

        previous_status = fact.status
        previous_snapshot = self._snapshot_fact(fact)
        fact.status = "expired"
        await self._record_event(
            fact,
            "expired",
            actor_id=actor_id,
            previous_status=previous_status,
            note="Brand fact marked expired",
            snapshot={"before": previous_snapshot, "after": self._snapshot_fact(fact)},
        )
        await self.db.commit()
        await self.db.refresh(fact)
        return fact

    async def restrict_fact(self, fact_id: UUID, actor_id: Optional[UUID] = None) -> Optional[BrandFact]:
        """标记事实为受限（敏感信息，仅内部可见）"""
        fact = await self.get_fact(fact_id)
        if not fact:
            return None

        previous_status = fact.status
        previous_snapshot = self._snapshot_fact(fact)
        fact.status = "restricted"
        fact.fact_scope = "restricted"
        await self._record_event(
            fact,
            "restricted",
            actor_id=actor_id,
            previous_status=previous_status,
            note="Brand fact marked restricted",
            snapshot={"before": previous_snapshot, "after": self._snapshot_fact(fact)},
        )
        await self.db.commit()
        await self.db.refresh(fact)
        return fact

    async def update_fact(
        self,
        fact_id: UUID,
        update_data: Dict[str, Any],
        actor_id: Optional[UUID] = None,
    ) -> Optional[BrandFact]:
        """更新事实字段"""
        fact = await self.get_fact(fact_id)
        if not fact:
            return None

        previous_status = fact.status
        previous_snapshot = self._snapshot_fact(fact)
        allowed_fields = [
            "value", "source", "evidence_file_url", "evidence_type",
            "fact_scope", "public_wording", "internal_note",
            "valid_until", "risk_level"
        ]
        for field, value in update_data.items():
            if field in allowed_fields and hasattr(fact, field):
                setattr(fact, field, value)
        await self._record_event(
            fact,
            "updated",
            actor_id=actor_id,
            previous_status=previous_status,
            note="Brand fact fields updated",
            snapshot={"before": previous_snapshot, "after": self._snapshot_fact(fact)},
        )

        await self.db.commit()
        await self.db.refresh(fact)
        return fact

    async def extract_from_corpus(
        self,
        corpus_item_id: UUID,
        suggested_facts: List[Dict[str, Any]],
        actor_id: Optional[UUID] = None,
    ) -> List[BrandFact]:
        """
        Extract to Brand Fact 流程
        从语料库中提取事实候选，生成 draft 状态的 brand_facts
        """
        corpus_result = await self.db.execute(
            select(CorpusItem).where(CorpusItem.id == corpus_item_id)
        )
        corpus = corpus_result.scalar_one_or_none()
        if not corpus:
            raise ValueError("Corpus item not found")

        created_facts = []
        for suggestion in suggested_facts:
            if not suggestion.get("brand_id"):
                raise ValueError("从语料提取事实时必须提供真实品牌主体。")
            await self._ensure_valid_brand(suggestion["brand_id"])
            fact = BrandFact(
                brand_id=suggestion["brand_id"],
                fact_type=suggestion["fact_type"],
                value=suggestion["value"],
                source=f"Extracted from corpus_item:{corpus_item_id}",
                evidence_file_url=corpus.source_type,  # 简化处理，实际应存原始文件
                evidence_type="corpus_extraction",
                fact_scope=suggestion.get("fact_scope", "public"),
                public_wording=suggestion.get("public_wording"),
                internal_note=suggestion.get("internal_note"),
                status="draft",
            )
            self.db.add(fact)
            await self.db.flush()
            await self._record_event(
                fact,
                "extracted_from_corpus",
                actor_id=actor_id,
                note=f"Extracted from corpus_item:{corpus_item_id}",
            )
            created_facts.append(fact)

        await self.db.commit()
        for fact in created_facts:
            await self.db.refresh(fact)
        return created_facts

    async def extract_from_text(
        self,
        brand_id: UUID,
        content: str,
        source: str = "pasted_enterprise_material",
        model_id: Optional[str] = None,
        max_facts: int = 24,
        actor_id: Optional[UUID] = None,
    ) -> List[BrandFact]:
        """
        Use the configured LLM to extract multiple brand fact candidates from pasted enterprise material.
        Created facts stay in draft status until the user confirms them.
        """
        await self._ensure_valid_brand(brand_id)
        from app.llm.client import LLMClientFactory
        from app.llm.registry import get_model_registry

        registry = get_model_registry()
        config = registry.get_model(model_id) if model_id else registry.get_default_model()
        if not config or not config.api_key:
            raise ValueError("请先在 AI 模型管理中配置默认模型和 API Key，再使用 AI 提取企业资料。")

        client = LLMClientFactory.create_client_from_config({
            "provider": config.provider,
            "model": config.model,
            "api_key": config.api_key,
            "base_url": config.base_url,
            "input_price_per_1k": config.input_price_per_1k,
            "output_price_per_1k": config.output_price_per_1k,
        })

        material = content.strip()
        if len(material) > 30000:
            material = material[:30000]

        system_prompt = """你是企业GEO品牌事实库抽取助手。你的任务是从用户粘贴的企业资料中抽取可核验事实候选，而不是改写文案。

要求：
1. 只抽取资料中明确出现的信息，禁止脑补证书编号、资质名称、价格、通过率、电话、地址、成立时间。
2. 每条事实要短、完整、可单独确认。
3. 资质、证书、价格、通过率、就业承诺、联系方式等事实如果原文有明确证据，risk_level 至少为 medium；涉及承诺、效果、包过、包就业等为 high。
4. fact_scope 只能是 public/internal/restricted。无法判断时用 public。
5. fact_type 只能从以下值里选：qualification, certification, address, phone, contact, price, case_study, founding_date, product, service, company_profile, website, business_hours, teacher, course, honor。
6. 输出必须是严格 JSON，不要 markdown，不要解释。

JSON格式：
{
  "facts": [
    {
      "fact_type": "qualification",
      "value": "原文中可核验的事实",
      "public_wording": "对外可使用的谨慎口径",
      "fact_scope": "public",
      "risk_level": "medium",
      "source_excerpt": "原文证据片段",
      "confidence": 0.9
    }
  ]
}"""
        user_prompt = f"""请从以下企业资料中抽取最多 {max_facts} 条品牌事实候选：

{material}"""

        response = await client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=4000,
        )

        parsed = _parse_llm_json(response.content)
        candidates = parsed.get("facts", [])
        if not isinstance(candidates, list):
            raise ValueError("AI 返回格式错误：facts 必须是数组。")

        created_facts: List[BrandFact] = []
        seen = set()
        for candidate in candidates[:max_facts]:
            if not isinstance(candidate, dict):
                continue
            normalized = _normalize_fact_candidate(candidate, source)
            if not normalized:
                continue
            dedupe_key = (normalized["fact_type"], normalized["value"])
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            fact = BrandFact(
                brand_id=brand_id,
                status="draft",
                **normalized,
            )
            self.db.add(fact)
            await self.db.flush()
            await self._record_event(
                fact,
                "extracted_from_text",
                actor_id=actor_id,
                note=f"AI extracted from {source}",
            )
            created_facts.append(fact)

        if not created_facts:
            raise ValueError("AI 没有从资料中提取到可入库的事实，请补充更具体的企业资料。")

        await self.db.commit()
        for fact in created_facts:
            await self.db.refresh(fact)
        return created_facts

    async def check_facts_for_publish(self, fact_ids: List[UUID]) -> Dict[str, Any]:
        """
        检查给定的事实ID列表是否可用于发布
        返回检查结果：所有事实必须是 confirmed 状态
        """
        if not fact_ids:
            return {"can_publish": True, "issues": []}

        result = await self.db.execute(
            select(BrandFact).where(BrandFact.id.in_(fact_ids))
        )
        facts = result.scalars().all()
        fact_map = {str(f.id): f for f in facts}

        issues = []
        for fid in fact_ids:
            fact = fact_map.get(str(fid))
            if not fact:
                issues.append({"fact_id": str(fid), "issue": "fact_not_found", "severity": "high"})
            elif fact.status != "confirmed":
                issues.append({
                    "fact_id": str(fid),
                    "issue": f"status_is_{fact.status}",
                    "severity": "high",
                    "message": f"Fact '{fact.fact_type}' is not confirmed (current: {fact.status})"
                })
            elif fact.fact_scope == "restricted":
                issues.append({
                    "fact_id": str(fid),
                    "issue": "fact_scope_restricted",
                    "severity": "high",
                    "message": f"Fact '{fact.fact_type}' is restricted and cannot be used in public content"
                })
            elif fact.valid_until and fact.valid_until < datetime.now(timezone.utc):
                issues.append({
                    "fact_id": str(fid),
                    "issue": "fact_expired",
                    "severity": "high",
                    "message": f"Fact '{fact.fact_type}' has expired"
                })

        return {
            "can_publish": len(issues) == 0,
            "issues": issues,
            "total_facts": len(fact_ids),
            "valid_facts": len(fact_ids) - len(issues)
        }
