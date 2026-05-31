"""
报告系统 Service。

客户报告只输出阶段观察和可交付进度；内部报告在此基础上补充执行缺口、
风险判断和下一轮策略。所有检测结论都必须带样本量、置信等级和基线状态。
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.brand import Brand
from app.models.brand_fact import BrandFact
from app.models.content_task import ContentTask
from app.models.monitoring import MonitoringRun
from app.models.project import Project
from app.models.publish_record import PublishRecord
from app.models.question import QuestionGroup
from app.models.source_asset import SourceAsset
from app.services.monitoring_service import MonitoringService


ACCEPTANCE_MIN_SAMPLE_SIZE = 20
ACCEPTANCE_REQUIRED_CONFIDENCE = "high"


LAYER_LABELS = {
    "pool_layer": "入池层",
    "verification_layer": "验证/口碑层",
    "weight_layer": "权重层",
    "conversion_layer": "转化/承接层",
}


CONFIDENCE_LABELS = {
    "high": "高",
    "medium": "中",
    "low": "低",
    "very_low": "很低",
    None: "暂无",
}


class ReportService:
    """报告生成服务。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_client_report(
        self,
        project_id: UUID,
        run_id: Optional[UUID] = None,
        baseline_run_id: Optional[UUID] = None,
        time_window_days: int = 30,
        run_ids: Optional[list[UUID]] = None,
    ) -> Dict[str, Any]:
        """生成客户可读报告，使用观察性语言。"""
        data = await self._collect_project_report_data(project_id, run_id, baseline_run_id, time_window_days, run_ids)
        if "error" in data:
            return data

        monitoring = data["monitoring_results"]
        baseline_comparison = data.get("baseline_comparison")
        acceptance_baseline = self._build_acceptance_baseline_summary(monitoring, baseline_comparison)
        summary = self._build_client_summary(data, acceptance_baseline)
        next_steps = self._build_next_steps(data, internal=False)
        selected_run_ids = (
            monitoring.get("run_ids")
            or ([monitoring.get("run_id")] if monitoring.get("run_id") else [])
            or ([str(run_id)] if run_id else [])
        )

        report = {
            "report_type": "client",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project": data["project"],
            "selected_run_ids": selected_run_ids,
            "observation_period": f"最近{time_window_days}天",
            "executive_summary": summary,
            "key_metrics": {
                "confirmed_public_facts": data["facts_summary"]["confirmed_public"],
                "question_groups": data["question_summary"]["active_groups"],
                "questions_estimated": data["question_summary"]["estimated_questions"],
                "content_tasks": data["content_summary"]["total_tasks"],
                "content_published": data["publish_summary"]["total_published"],
                "source_assets": data["source_summary"]["total"],
                "active_source_assets": data["source_summary"]["active"],
                "monitoring_sample_count": monitoring.get("sample_count", 0),
                "confidence_level": monitoring.get("confidence_level"),
            },
            "facts_summary": data["facts_summary"],
            "source_summary": data["source_summary"],
            "question_summary": data["question_summary"],
            "content_summary": data["content_summary"],
            "publish_summary": data["publish_summary"],
            "monitoring_results": monitoring,
            "baseline_comparison": baseline_comparison,
            "acceptance_baseline": acceptance_baseline,
            "report_guardrails": self._build_report_guardrails("client"),
            "published_content": data["published_content"],
            "next_steps": next_steps,
            "disclaimer": (
                "本报告基于当前系统内记录、发布记录和检测样本形成，结果应理解为阶段性观察。"
                "报告不承诺控制 AI 推荐结果，不把推定信源匹配表述为 AI 已明确引用；"
                "用于验收时需满足样本量、置信等级和可比基线要求。"
            ),
        }
        report["markdown"] = self._format_markdown(report)
        return report

    async def generate_internal_report(
        self,
        project_id: UUID,
        run_id: Optional[UUID] = None,
        baseline_run_id: Optional[UUID] = None,
        time_window_days: int = 30,
        run_ids: Optional[list[UUID]] = None,
    ) -> Dict[str, Any]:
        """生成内部报告，可包含运营判断和缺口。"""
        client_report = await self.generate_client_report(project_id, run_id, baseline_run_id, time_window_days, run_ids)
        if "error" in client_report:
            return client_report

        internal_report = {
            **client_report,
            "report_type": "internal",
            "report_guardrails": self._build_report_guardrails("internal"),
            "internal_findings": self._build_internal_findings(client_report),
            "next_steps": self._build_next_steps(client_report, internal=True),
            "internal_note": "内部报告包含执行判断、缺口和下一轮策略，不建议直接发给客户。",
        }
        internal_report["markdown"] = self._format_markdown(internal_report)
        return internal_report

    async def _collect_project_report_data(
        self,
        project_id: UUID,
        run_id: Optional[UUID],
        baseline_run_id: Optional[UUID],
        time_window_days: int,
        run_ids: Optional[list[UUID]] = None,
    ) -> Dict[str, Any]:
        project_result = await self.db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalar_one_or_none()
        if not project:
            return {"error": "Project not found"}

        since = datetime.now(timezone.utc) - timedelta(days=time_window_days)

        brands_result = await self.db.execute(select(Brand).where(Brand.project_id == project_id))
        brands = list(brands_result.scalars().all())
        brand_ids = [brand.id for brand in brands]

        facts = []
        if brand_ids:
            facts_result = await self.db.execute(select(BrandFact).where(BrandFact.brand_id.in_(brand_ids)))
            facts = list(facts_result.scalars().all())

        groups_result = await self.db.execute(
            select(QuestionGroup)
            .where(
                QuestionGroup.project_id == project_id,
                QuestionGroup.status != "archived",
            )
            .options(selectinload(QuestionGroup.questions))
        )
        question_groups = list(groups_result.scalars().all())

        source_result = await self.db.execute(select(SourceAsset).where(SourceAsset.project_id == project_id))
        source_assets = list(source_result.scalars().all())

        tasks_result = await self.db.execute(select(ContentTask).where(ContentTask.project_id == project_id))
        content_tasks = list(tasks_result.scalars().all())
        task_ids = [task.id for task in content_tasks]

        publish_records = []
        if task_ids:
            publish_result = await self.db.execute(
                select(PublishRecord)
                .where(
                    PublishRecord.task_id.in_(task_ids),
                    PublishRecord.created_at >= since,
                )
                .order_by(PublishRecord.created_at.desc())
            )
            publish_records = list(publish_result.scalars().all())

        monitoring_results = await self._load_monitoring_results(project_id, run_id, run_ids)
        baseline_comparison = None
        effective_run_ids = self._normalize_run_ids(run_id, run_ids)
        if len(effective_run_ids) == 1 and baseline_run_id:
            run_id = effective_run_ids[0]
            baseline_comparison = await MonitoringService(self.db).compare_with_baseline(run_id, baseline_run_id)

        return {
            "project": {
                "id": str(project.id),
                "name": project.name,
                "industry": project.industry,
                "region": project.region,
                "status": project.status,
                "budget": float(project.budget) if project.budget is not None else None,
            },
            "brands": [
                {
                    "id": str(brand.id),
                    "brand_name": brand.brand_name,
                    "company_name": brand.company_name,
                }
                for brand in brands
            ],
            "facts_summary": self._summarize_facts(facts),
            "source_summary": self._summarize_source_assets(source_assets),
            "question_summary": self._summarize_questions(question_groups),
            "content_summary": self._summarize_content(content_tasks),
            "publish_summary": self._summarize_publish_records(publish_records),
            "published_content": [
                {
                    "title": record.title,
                    "platform": record.platform,
                    "url": record.url,
                    "published_at": record.published_at.isoformat() if record.published_at else None,
                    "status": record.status,
                    "is_indexed": record.is_indexed,
                }
                for record in publish_records[:30]
            ],
            "monitoring_results": monitoring_results,
            "baseline_comparison": baseline_comparison,
        }

    async def _load_monitoring_results(
        self,
        project_id: UUID,
        run_id: Optional[UUID],
        run_ids: Optional[list[UUID]] = None,
    ) -> Dict[str, Any]:
        monitoring_service = MonitoringService(self.db)
        selected_run_ids = self._normalize_run_ids(run_id, run_ids)
        if len(selected_run_ids) > 1:
            return await monitoring_service.calculate_project_runs_metrics(project_id, selected_run_ids)
        if len(selected_run_ids) == 1:
            selected_run_id = selected_run_ids[0]
            run_result = await self.db.execute(
                select(MonitoringRun).where(
                    MonitoringRun.id == selected_run_id,
                    MonitoringRun.project_id == project_id,
                )
            )
            if not run_result.scalar_one_or_none():
                return {"error": "Monitoring run not found in current project"}
            return await monitoring_service.calculate_run_metrics(selected_run_id, finalize=False)

        target_run_id = run_id
        if not target_run_id:
            run_result = await self.db.execute(
                select(MonitoringRun)
                .where(MonitoringRun.project_id == project_id)
                .order_by(MonitoringRun.created_at.desc())
                .limit(1)
            )
            latest_run = run_result.scalar_one_or_none()
            target_run_id = latest_run.id if latest_run else None

        if not target_run_id:
            return {
                "sample_count": 0,
                "confidence_level": None,
                "message": "当前项目暂无检测样本，报告仅展示资料、内容与发布进度。",
            }

        return await monitoring_service.calculate_run_metrics(target_run_id, finalize=False)

    def _normalize_run_ids(
        self,
        run_id: Optional[UUID],
        run_ids: Optional[list[UUID]] = None,
    ) -> list[UUID]:
        seen = set()
        normalized: list[UUID] = []
        for item in (run_ids or []):
            if not item:
                continue
            key = str(item)
            if key not in seen:
                seen.add(key)
                normalized.append(item)
        if run_id and str(run_id) not in seen:
            normalized.append(run_id)
        return normalized

    def _summarize_facts(self, facts: list[BrandFact]) -> Dict[str, Any]:
        status_counter = Counter(fact.status for fact in facts)
        type_counter = Counter(fact.fact_type for fact in facts)
        confirmed_public = [
            fact for fact in facts
            if fact.status == "confirmed" and fact.fact_scope == "public"
        ]
        high_risk = [fact for fact in facts if fact.risk_level == "high"]
        return {
            "total": len(facts),
            "confirmed_public": len(confirmed_public),
            "draft_or_pending": len(facts) - len(confirmed_public),
            "high_risk": len(high_risk),
            "by_status": dict(status_counter),
            "by_type": dict(type_counter),
        }

    def _summarize_source_assets(self, source_assets: list[SourceAsset]) -> Dict[str, Any]:
        type_counter = Counter(asset.source_type for asset in source_assets)
        authority_counter = Counter(asset.authority_level for asset in source_assets)
        crawlability_counter = Counter(asset.crawlability for asset in source_assets)
        active_assets = [asset for asset in source_assets if asset.status == "active"]
        return {
            "total": len(source_assets),
            "active": len(active_assets),
            "by_type": dict(type_counter),
            "by_authority": dict(authority_counter),
            "by_crawlability": dict(crawlability_counter),
            "high_authority": sum(1 for asset in source_assets if asset.authority_level == "high"),
        }

    def _summarize_questions(self, question_groups: list[QuestionGroup]) -> Dict[str, Any]:
        layer_counter = Counter(group.layer for group in question_groups)
        estimated_questions = sum(len(group.questions) for group in question_groups)
        representative_questions = [
            {
                "layer": group.layer,
                "layer_label": LAYER_LABELS.get(group.layer, group.layer),
                "intent_name": group.intent_name,
                "question": group.representative_question,
                "priority": group.priority,
            }
            for group in sorted(question_groups, key=lambda item: item.priority or 0, reverse=True)[:8]
        ]
        return {
            "active_groups": len(question_groups),
            "estimated_questions": estimated_questions,
            "by_layer": dict(layer_counter),
            "representative_questions": representative_questions,
        }

    def _summarize_content(self, content_tasks: list[ContentTask]) -> Dict[str, Any]:
        status_counter = Counter(task.status for task in content_tasks)
        layer_counter = Counter(task.layer for task in content_tasks)
        type_counter = Counter(task.content_type for task in content_tasks)
        return {
            "total_tasks": len(content_tasks),
            "by_status": dict(status_counter),
            "by_layer": dict(layer_counter),
            "by_content_type": dict(type_counter),
        }

    def _summarize_publish_records(self, records: list[PublishRecord]) -> Dict[str, Any]:
        platform_counter = Counter(record.platform for record in records)
        status_counter = Counter(record.status for record in records)
        indexed = sum(1 for record in records if record.is_indexed)
        return {
            "total_records": len(records),
            "total_published": sum(1 for record in records if record.status == "published"),
            "indexed": indexed,
            "by_platform": dict(platform_counter),
            "by_status": dict(status_counter),
        }

    def _build_report_guardrails(self, report_type: str) -> Dict[str, Any]:
        return {
            "report_language": "阶段观察" if report_type == "client" else "内部诊断",
            "citation_policy": "明确引用与推定信源匹配分开展示；推定匹配不能写成 AI 已明确引用。",
            "causality_policy": "只描述检测样本中的变化，不承诺控制或保证 AI 推荐结果。",
            "acceptance_policy": f"作为验收依据时，当前批次需 N≥{ACCEPTANCE_MIN_SAMPLE_SIZE} 且置信等级为高，并选择可比基线。",
            "internal_only_fields_hidden": report_type == "client",
        }

    def _build_acceptance_baseline_summary(
        self,
        monitoring: Dict[str, Any],
        baseline_comparison: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        comparison = baseline_comparison or {}
        has_baseline = bool(comparison.get("comparison")) and "error" not in comparison
        current_n = int(monitoring.get("sample_count") or 0)
        current_confidence = monitoring.get("confidence_level")

        baseline_metrics = comparison.get("baseline_metrics") or {}
        baseline_n = baseline_metrics.get("sample_count")
        baseline_confidence = baseline_metrics.get("confidence_level")
        baseline_sample_pass = bool(has_baseline and (baseline_n or 0) >= ACCEPTANCE_MIN_SAMPLE_SIZE)
        baseline_confidence_pass = bool(has_baseline and baseline_confidence == ACCEPTANCE_REQUIRED_CONFIDENCE)

        sample_pass = current_n >= ACCEPTANCE_MIN_SAMPLE_SIZE
        confidence_pass = current_confidence == ACCEPTANCE_REQUIRED_CONFIDENCE
        acceptance_ready = has_baseline and sample_pass and confidence_pass and baseline_sample_pass and baseline_confidence_pass

        notes = []
        if monitoring.get("aggregation_mode") == "multi_run":
            notes.append("当前报告聚合了多组检测记录；基线验收对比需使用单组检测记录生成。")
        if not has_baseline:
            notes.append("未选择可比基线，本报告只能作为阶段观察，不能作为验收对比结论。")
        if current_n == 0:
            notes.append("当前没有检测样本，建议先完成一轮检测。")
        elif not sample_pass:
            notes.append(f"当前样本量 N={current_n}，低于验收建议的 N≥{ACCEPTANCE_MIN_SAMPLE_SIZE}。")
        if current_n > 0 and not confidence_pass:
            notes.append(f"当前置信等级为{CONFIDENCE_LABELS.get(current_confidence, '暂无')}，尚未达到验收建议的高置信。")
        if has_baseline and not baseline_sample_pass:
            notes.append(f"基线样本量 N={baseline_n or 0}，低于验收建议的 N≥{ACCEPTANCE_MIN_SAMPLE_SIZE}。")
        if has_baseline and not baseline_confidence_pass:
            notes.append(f"基线置信等级为{CONFIDENCE_LABELS.get(baseline_confidence, '暂无')}，尚未达到高置信。")
        if acceptance_ready:
            notes.append("当前批次和基线均满足验收样本与置信度要求，可进入人工复核和验收判断。")

        return {
            "has_baseline": has_baseline,
            "acceptance_ready": acceptance_ready,
            "criteria": {
                "minimum_sample_count": ACCEPTANCE_MIN_SAMPLE_SIZE,
                "required_confidence_level": ACCEPTANCE_REQUIRED_CONFIDENCE,
            },
            "current_run_id": monitoring.get("run_id"),
            "current_run_ids": monitoring.get("run_ids") or ([monitoring.get("run_id")] if monitoring.get("run_id") else []),
            "aggregation_mode": monitoring.get("aggregation_mode"),
            "selected_run_count": monitoring.get("selected_run_count"),
            "baseline_run_id": comparison.get("baseline_run_id"),
            "current_sample_count": current_n,
            "baseline_sample_count": baseline_n,
            "current_confidence_level": current_confidence,
            "baseline_confidence_level": baseline_confidence,
            "current_sample_size_pass": sample_pass,
            "current_confidence_pass": confidence_pass,
            "baseline_sample_size_pass": baseline_sample_pass,
            "baseline_confidence_pass": baseline_confidence_pass,
            "notes": notes,
        }

    def _build_client_summary(self, data: Dict[str, Any], acceptance: Dict[str, Any]) -> str:
        project = data["project"]
        facts = data["facts_summary"]
        sources = data.get("source_summary", {})
        questions = data["question_summary"]
        publish = data["publish_summary"]
        monitoring = data["monitoring_results"]
        comparison = data.get("baseline_comparison") or {}
        sample_count = monitoring.get("sample_count", 0)
        confidence = CONFIDENCE_LABELS.get(monitoring.get("confidence_level"), "暂无")
        comparison_text = ""

        if comparison.get("comparison"):
            comp = comparison["comparison"]
            comparison_text = (
                f" 与所选基线相比，品牌提及率变化 {self._fmt(comp.get('mention_delta'))} 个百分点，"
                f"推荐率变化 {self._fmt(comp.get('recommend_delta'))} 个百分点。"
            )

        acceptance_text = "当前已满足验收样本与置信度要求。" if acceptance.get("acceptance_ready") else (
            "当前仍需补充基线或样本，暂按阶段观察解读。"
        )

        return (
            f"本阶段围绕「{project['name']}」完成了品牌事实整理、问题矩阵建设、内容任务推进与发布记录沉淀。"
            f"系统内当前有 {facts['confirmed_public']} 条可公开使用的已确认事实，"
            f"{sources.get('active', 0)} 个有效信源资产，"
            f"{questions['active_groups']} 个有效问题组，"
            f"{publish['total_published']} 条已发布内容记录。"
            f"最新检测样本数为 N={sample_count}，当前置信等级为{confidence}。"
            f"{comparison_text}{acceptance_text}"
        )

    def _build_next_steps(self, data: Dict[str, Any], internal: bool = False) -> list[str]:
        facts = data.get("facts_summary", {})
        sources = data.get("source_summary", {})
        questions = data.get("question_summary", {})
        publish = data.get("publish_summary", {})
        monitoring = data.get("monitoring_results", {})
        acceptance = data.get("acceptance_baseline", {})
        metrics = monitoring.get("metrics", {}) if isinstance(monitoring, dict) else {}
        explicit_rate = (metrics.get("explicit_citation_rate") or {}).get("point_estimate")
        inferred_rate = (metrics.get("inferred_source_match_rate") or {}).get("point_estimate")
        steps = []

        if facts.get("confirmed_public", 0) < 5:
            steps.append("继续补充并确认可公开使用的资质、地址、产品/服务、案例、价格/流程等基础事实。")
        if sources.get("active", 0) < 3:
            steps.append("补齐官网、资质页、案例页、媒体报道等公开信源资产，方便回答形成可追溯引用。")
        if questions.get("active_groups", 0) < 4:
            steps.append("补齐入池、验证、权重、转化四层问题矩阵，避免只围绕单一推荐类问题优化。")
        if publish.get("total_published", 0) < 3:
            steps.append("优先完成基础验证层和转化承接层内容发布，形成可被引用的公开信息资产。")
        if monitoring.get("sample_count", 0) < 5:
            steps.append("完成至少 5 个样本的检测，记录品牌提及、推荐、引用和可见度。")
        elif not acceptance.get("acceptance_ready"):
            steps.append(f"若要用于验收，补齐到 N≥{ACCEPTANCE_MIN_SAMPLE_SIZE} 且置信等级为高，并选择可比基线。")
        elif explicit_rate is not None and inferred_rate is not None and explicit_rate == 0 and inferred_rate == 0:
            steps.append("当前检测未形成引用线索，下一轮优先发布可抓取的资质、案例和问答内容，并记录引用匹配。")
        if not steps:
            steps.append("进入下一轮检测，对比发布前后品牌提及率、推荐率、引用线索和可见度变化。")
        if internal:
            steps.append("内部侧建议补充渠道归因和内容批次记录，便于判断哪类内容真正影响回答样本。")
        return steps

    def _build_internal_findings(self, report: Dict[str, Any]) -> Dict[str, Any]:
        facts = report.get("facts_summary", {})
        sources = report.get("source_summary", {})
        publish = report.get("publish_summary", {})
        monitoring = report.get("monitoring_results", {})
        acceptance = report.get("acceptance_baseline", {})
        metrics = monitoring.get("metrics", {}) if isinstance(monitoring, dict) else {}
        sentiment = metrics.get("sentiment_summary", {}) if isinstance(metrics, dict) else {}
        comparison = report.get("baseline_comparison") or {}
        gaps = []
        risks = []

        if facts.get("draft_or_pending", 0) > facts.get("confirmed_public", 0):
            gaps.append("未确认事实偏多，内容生成和发布检查仍可能被事实门槛阻塞。")
        if publish.get("total_published", 0) == 0:
            gaps.append("尚无发布记录，无法形成发布后检测和报告闭环。")
        if sources.get("active", 0) == 0:
            gaps.append("尚无有效信源资产，引用率指标缺少可优化对象。")
        if monitoring.get("sample_count", 0) == 0:
            gaps.append("尚无检测样本，报告无法证明阶段性变化。")
        if not acceptance.get("acceptance_ready"):
            gaps.append("验收基线尚未就绪，当前报告只能用于阶段复盘，不能直接作为交付验收。")
        if monitoring.get("confidence_level") in {"low", "very_low"}:
            risks.append("当前样本量或时间窗口不足，客户侧不宜解读为稳定趋势。")
        if sentiment.get("negative_samples", 0) > 0:
            risks.append(f"当前存在 {sentiment.get('negative_samples')} 个负面或风险样本，需先处理误答、混淆或投诉线索。")
        if comparison.get("comparison") and not comparison["comparison"].get("significant_change"):
            risks.append("当前前后变化未达到内部显著变化阈值，应继续补样本或观察更长周期。")

        return {
            "execution_gaps": gaps or ["当前基础闭环可继续推进，主要缺口集中在长期检测和渠道归因。"],
            "risks": risks or ["暂无高风险，但仍需避免使用确定性承诺话术。"],
            "operator_notes": [
                "客户报告只使用观察性语言；内部报告可保留归因假设和执行判断。",
                "明确引用和推定信源匹配必须分开，避免误把匹配线索说成模型已引用。",
                "下一轮应优先补基线对比和检测显著性判断。",
            ],
        }

    def _format_markdown(self, report: Dict[str, Any]) -> str:
        project = report["project"]
        metrics = report["key_metrics"]
        monitoring = report.get("monitoring_results", {})
        comparison = report.get("baseline_comparison") or {}
        acceptance = report.get("acceptance_baseline") or {}
        guardrails = report.get("report_guardrails") or {}
        published = report.get("published_content", [])
        lines = [
            f"# {project['name']} GEO阶段报告",
            "",
            f"- 报告类型：{'客户报告' if report['report_type'] == 'client' else '内部报告'}",
            f"- 观察周期：{report['observation_period']}",
            f"- 生成时间：{report['generated_at']}",
            "",
            "## 报告边界",
            f"- 语言口径：{guardrails.get('report_language', '-')}",
            f"- 引用口径：{guardrails.get('citation_policy', '-')}",
            f"- 因果口径：{guardrails.get('causality_policy', '-')}",
            f"- 验收口径：{guardrails.get('acceptance_policy', '-')}",
            "",
            "## 阶段摘要",
            report["executive_summary"],
            "",
            "## 关键指标",
            f"- 已确认公开事实：{metrics['confirmed_public_facts']} 条",
            f"- 有效信源资产：{metrics.get('active_source_assets', 0)} 个",
            f"- 有效问题组：{metrics['question_groups']} 个",
            f"- 估算问题量：{metrics['questions_estimated']} 条",
            f"- 内容任务：{metrics['content_tasks']} 个",
            f"- 已发布内容：{metrics['content_published']} 条",
            f"- 检测样本数：N={metrics['monitoring_sample_count']}",
            f"- 置信等级：{CONFIDENCE_LABELS.get(metrics['confidence_level'], '暂无')}",
            "",
            "## 验收基线状态",
            f"- 是否选择可比基线：{'是' if acceptance.get('has_baseline') else '否'}",
            f"- 当前样本量：N={acceptance.get('current_sample_count', 0)}",
            f"- 当前置信等级：{CONFIDENCE_LABELS.get(acceptance.get('current_confidence_level'), '暂无')}",
            f"- 基线样本量：N={acceptance.get('baseline_sample_count') if acceptance.get('baseline_sample_count') is not None else '-'}",
            f"- 基线置信等级：{CONFIDENCE_LABELS.get(acceptance.get('baseline_confidence_level'), '暂无')}",
            f"- 是否可作为验收依据：{'是' if acceptance.get('acceptance_ready') else '否'}",
        ]
        for note in acceptance.get("notes", []):
            lines.append(f"- 说明：{note}")
        lines.append("")

        if monitoring.get("metrics"):
            m = monitoring["metrics"]
            mention = m.get("brand_mention_rate", {})
            recommend = m.get("recommendation_rate", {})
            explicit_rate = m.get("explicit_citation_rate", {})
            inferred_rate = m.get("inferred_source_match_rate", {})
            sentiment = m.get("sentiment_summary", {})
            lines.append("## 检测观察")
            if monitoring.get("aggregation_mode") == "multi_run":
                lines.append(f"- 检测口径：聚合 {monitoring.get('selected_run_count', 0)} 组检测记录")
                for item in monitoring.get("run_summaries", []):
                    target_name = item.get("model_target_name") or item.get("mechanism_type") or "检测"
                    lines.append(f"- {target_name}：N={item.get('sample_count', 0)}")
            lines.extend([
                f"- 品牌提及率：{self._format_rate_ci(mention)}",
                f"- 推荐率：{self._format_rate_ci(recommend)}",
                f"- 明确引用：{m.get('total_explicit_citations', 0)} 次，明确引用率：{self._fmt(explicit_rate.get('point_estimate'))}%",
                f"- 推定信源匹配：{m.get('total_inferred_source_matches', 0)} 次，匹配率：{self._fmt(inferred_rate.get('point_estimate'))}%",
                f"- 舆情/风险记录：{sentiment.get('open_records', 0)} 条未关闭，负面样本 {sentiment.get('negative_samples', 0)} 个",
                "",
            ])
            if comparison.get("comparison"):
                comp = comparison["comparison"]
                lines.extend([
                    "## 基线对比",
                    f"- 品牌提及率变化：{self._fmt(comp.get('mention_delta'))} 个百分点",
                    f"- 推荐率变化：{self._fmt(comp.get('recommend_delta'))} 个百分点",
                    f"- 是否达到内部显著变化阈值：{'是' if comp.get('significant_change') else '否'}",
                    "",
                ])
        elif monitoring.get("message"):
            lines.extend(["## 检测观察", f"- {monitoring['message']}", ""])

        lines.append("## 已发布内容")
        if published:
            for item in published[:10]:
                title = item.get("title") or "未命名内容"
                platform = item.get("platform") or "-"
                url = item.get("url") or "-"
                lines.append(f"- {title}｜{platform}｜{url}")
        else:
            lines.append("- 暂无发布记录")
        lines.append("")

        lines.append("## 下一步建议")
        for step in report.get("next_steps", []):
            lines.append(f"- {step}")
        lines.append("")

        if report.get("internal_findings"):
            lines.append("## 内部执行判断")
            findings = report["internal_findings"]
            for item in findings.get("execution_gaps", []):
                lines.append(f"- 缺口：{item}")
            for item in findings.get("risks", []):
                lines.append(f"- 风险：{item}")
            for item in findings.get("operator_notes", []):
                lines.append(f"- 操作备注：{item}")
            lines.append("")

        lines.extend(["## 说明", report["disclaimer"]])
        return "\n".join(lines)

    def _format_rate_ci(self, metric: Dict[str, Any]) -> str:
        return (
            f"{self._fmt(metric.get('point_estimate'))}%"
            f"（95% CI：{self._fmt(metric.get('lower'))}% ~ {self._fmt(metric.get('upper'))}%）"
        )

    def _fmt(self, value: Any) -> str:
        if value is None:
            return "--"
        if isinstance(value, float):
            return f"{value:.2f}".rstrip("0").rstrip(".")
        return str(value)
