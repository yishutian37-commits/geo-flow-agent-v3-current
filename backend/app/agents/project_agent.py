"""
项目与诊断 Agent
负责项目创建、资料缺口诊断、品牌事实库构建
"""
from typing import List, Dict, Any, Optional
from uuid import UUID

from app.models.project import Project
from app.models.brand import Brand
from app.models.corpus_item import CorpusItem
from app.models.brand_fact import BrandFact


class ProjectAgent:
    """
    项目与诊断 Agent
    把客户零散资料转化为可复用项目档案和事实库
    """

    # 资料缺口分析Prompt模板（对应PRD附录A1）
    GAP_ANALYSIS_PROMPT = """你是GEO项目资料审查员。请基于以下品牌资料和行业模板，判断资料是否足以支持AI品牌可见性项目。

品牌资料:
{materials}

行业模板: {industry}

请输出：
1. 已有资料清单
2. 缺失资料清单（按严重程度高/中/低分类）
3. 必须客户确认的事实
4. 可能影响AI推荐的弱项
5. 下一步采集清单

不得编造客户未提供的信息。"""

    # 资料事实提取Prompt模板（对应PRD附录A2）
    FACT_EXTRACTION_PROMPT = """请从以下corpus_items中识别可能用于对外内容的事实性陈述。

语料内容:
{corpus_content}

请输出待确认brand_facts草稿，包含：
- fact_type（资质/案例/价格/地址/电话/证书有效期等）
- value（原文提取）
- source（来源）
- public_wording建议（对外表述）
- fact_scope建议（public/internal/restricted）

注意：未确认事实不得直接用于对外稿件。"""

    def __init__(self, llm_client=None):
        self.llm = llm_client

    async def analyze_material_gaps(
        self,
        project: Project,
        materials: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        分析资料缺口
        结合行业模板和已提供资料，输出缺口报告
        """
        from app.services.project_service import ProjectService, INDUSTRY_TEMPLATES

        template = INDUSTRY_TEMPLATES.get(project.industry)
        provided_fields = [m.get("field_type") for m in materials if m.get("field_type")]

        service = ProjectService(None)  # db不需要，因为diagnose_gaps是纯逻辑
        # 注意：这里简化处理，实际应传入db session
        # 实际调用时应通过API层调用ProjectService

        return {
            "project_id": str(project.id),
            "industry": project.industry,
            "provided_materials": provided_fields,
            "template": template.get("name") if template else "通用",
            "gap_summary": "请调用 /api/v1/projects/{id}/diagnose-gaps 获取详细诊断",
        }

    async def extract_facts_from_corpus(
        self,
        corpus_items: List[CorpusItem],
        brand_id: UUID,
    ) -> List[Dict[str, Any]]:
        """
        从语料库中提取事实候选
        生成fact_candidates，等待客户确认
        """
        candidates = []

        for item in corpus_items:
            if not item.contains_factual_claim:
                continue

            # 简化实现：根据内容关键词匹配事实类型
            content = item.content.lower()

            if "资质" in content or "证书" in content or "执照" in content:
                candidates.append({
                    "brand_id": str(brand_id),
                    "fact_type": "qualification",
                    "value": item.content[:500],  # 截取前500字符
                    "source": item.source_type or "corpus",
                    "evidence_type": "corpus_extraction",
                    "fact_scope": "public",
                    "corpus_item_id": str(item.id),
                })

            if "地址" in content or "位于" in content:
                candidates.append({
                    "brand_id": str(brand_id),
                    "fact_type": "address",
                    "value": item.content[:500],
                    "source": item.source_type or "corpus",
                    "evidence_type": "corpus_extraction",
                    "fact_scope": "public",
                    "corpus_item_id": str(item.id),
                })

            if "电话" in content or "联系" in content or "400" in content:
                candidates.append({
                    "brand_id": str(brand_id),
                    "fact_type": "contact",
                    "value": item.content[:500],
                    "source": item.source_type or "corpus",
                    "evidence_type": "corpus_extraction",
                    "fact_scope": "public",
                    "corpus_item_id": str(item.id),
                })

            if "价格" in content or "费用" in content or "元" in content:
                candidates.append({
                    "brand_id": str(brand_id),
                    "fact_type": "price",
                    "value": item.content[:500],
                    "source": item.source_type or "corpus",
                    "evidence_type": "corpus_extraction",
                    "fact_scope": "public",
                    "corpus_item_id": str(item.id),
                })

            if "案例" in content or "客户" in content or "成功" in content:
                candidates.append({
                    "brand_id": str(brand_id),
                    "fact_type": "case_study",
                    "value": item.content[:500],
                    "source": item.source_type or "corpus",
                    "evidence_type": "corpus_extraction",
                    "fact_scope": "public",
                    "corpus_item_id": str(item.id),
                })

        return candidates

    async def evaluate_material_quality(
        self,
        materials: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        评估资料质量
        按完整性、一致性、可证明性、时效性评分
        """
        scores = {
            "completeness": 0.0,  # 完整性：必填项覆盖比例
            "consistency": 0.0,   # 一致性：不同来源信息是否冲突
            "provability": 0.0,   # 可证明性：是否有证据附件
            "timeliness": 0.0,    # 时效性：信息是否在有效期内
        }

        total = len(materials)
        if total == 0:
            return {**scores, "overall": 0.0, "grade": "F"}

        # 完整性：有内容的项占比
        has_content = sum(1 for m in materials if m.get("content"))
        scores["completeness"] = has_content / total

        # 可证明性：有证据的项占比
        has_evidence = sum(1 for m in materials if m.get("evidence_url") or m.get("attachment"))
        scores["provability"] = has_evidence / total

        # 时效性：有过期日期的项中，未过期的占比
        from datetime import datetime, timezone
        timely = 0
        timely_total = 0
        for m in materials:
            valid_until = m.get("valid_until")
            if valid_until:
                timely_total += 1
                if isinstance(valid_until, str):
                    try:
                        valid_until = datetime.fromisoformat(valid_until.replace('Z', '+00:00'))
                    except:
                        continue
                if valid_until > datetime.now(timezone.utc):
                    timely += 1
        scores["timeliness"] = timely / timely_total if timely_total > 0 else 1.0

        # 一致性：简化处理，默认满分（需要更复杂的NLP分析）
        scores["consistency"] = 1.0

        overall = sum(scores.values()) / len(scores)

        grade = "F"
        if overall >= 0.9:
            grade = "A"
        elif overall >= 0.8:
            grade = "B"
        elif overall >= 0.7:
            grade = "C"
        elif overall >= 0.6:
            grade = "D"

        return {
            **scores,
            "overall": round(overall, 3),
            "grade": grade,
            "total_materials": total,
        }
