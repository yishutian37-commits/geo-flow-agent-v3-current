"""
监测与分析 Agent Service
处理检测记录创建、样本录入、指标计算
"""
import json
import os
from collections import Counter
from pathlib import Path
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, delete
from sqlalchemy.orm import selectinload

from app.models.monitoring import MonitoringRun, MonitoringSample
from app.models.question import Question, QuestionGroup
from app.models.model_target import ModelTarget
from app.models.project import Project
from app.models.recommendation import Recommendation
from app.models.sentiment import SentimentRecord
from app.services.wilson_stats import (
    calculate_brand_mention_rate,
    calculate_recommendation_rate,
    calculate_negative_mention_rate,
    proportion_confidence_interval,
    calculate_visibility_score,
    calculate_position_score,
    determine_confidence_level,
    format_ci_report,
)


NEGATIVE_SENTIMENT_TYPES = {
    "negative",
    "complaint",
    "risk",
    "misinformation",
    "wrong_answer",
    "bad_review",
    "brand_confusion",
}


def _is_negative_sentiment(record: SentimentRecord) -> bool:
    sentiment_type = (record.sentiment_type or "").strip().lower()
    severity = (record.severity or "").strip().lower()
    if sentiment_type in {"positive", "neutral"}:
        return False
    return sentiment_type in NEGATIVE_SENTIMENT_TYPES or severity in {"high", "critical"}


def _sample_analysis_sentiment(sample: MonitoringSample) -> Optional[str]:
    try:
        analysis = json.loads(sample.analysis_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(analysis, dict):
        return None
    sentiment = str(analysis.get("sentiment") or "").strip().lower()
    return sentiment or None


class MonitoringService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_run(
        self,
        project_id: UUID,
        run_type: str,
        mechanism_type: str,
        model_target_id: Optional[UUID] = None,
        sample_policy: str = "mvp",
        call_mode_detail: Optional[str] = None,
    ) -> MonitoringRun:
        """创建检测记录"""
        model_target = await self._resolve_model_target(project_id, model_target_id, mechanism_type)
        run = MonitoringRun(
            project_id=project_id,
            run_type=run_type,
            mechanism_type=mechanism_type,
            model_target_id=model_target.id,
            sample_policy=sample_policy,
            call_mode_detail=call_mode_detail,
            status="running",
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def _resolve_model_target(
        self,
        project_id: UUID,
        model_target_id: Optional[UUID],
        mechanism_type: str,
    ) -> ModelTarget:
        project_result = await self.db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalar_one_or_none()
        if not project:
            raise ValueError("Project not found")

        if model_target_id:
            result = await self.db.execute(
                select(ModelTarget).where(
                    ModelTarget.id == model_target_id,
                    ModelTarget.project_id == project_id,
                )
            )
            model_target = result.scalar_one_or_none()
            if model_target:
                return model_target

        result = await self.db.execute(
            select(ModelTarget)
            .where(ModelTarget.project_id == project_id)
            .order_by(ModelTarget.created_at.asc())
        )
        model_target = result.scalars().first()
        if model_target:
            return model_target

        default_target = ModelTarget(
            project_id=project_id,
            product_name="人工检测平台",
            supported_mechanisms=mechanism_type,
            api_available=False,
            access_method="manual",
            notes="系统自动创建，用于人工检测样本归档。",
        )
        self.db.add(default_target)
        await self.db.flush()
        return default_target

    async def get_run(self, run_id: UUID) -> Optional[MonitoringRun]:
        """获取检测记录"""
        result = await self.db.execute(select(MonitoringRun).where(MonitoringRun.id == run_id))
        return result.scalar_one_or_none()

    async def update_run_status(self, run_id: UUID, status: str) -> MonitoringRun:
        """更新检测记录状态，确保异常/取消流程不会长期停留在 running。"""
        allowed = {"running", "completed", "failed", "cancelled"}
        if status not in allowed:
            raise ValueError(f"Invalid monitoring run status: {status}")
        run = await self.get_run(run_id)
        if not run:
            raise ValueError("Monitoring run not found")
        run.status = status
        run.updated_at = datetime.now(timezone.utc)
        if status in {"completed", "failed", "cancelled"} and not run.ended_at:
            run.ended_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def list_runs(
        self,
        project_id: Optional[UUID] = None,
        mechanism_type: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[MonitoringRun]:
        """获取检测记录列表"""
        query = select(MonitoringRun)
        conditions = []
        if project_id:
            conditions.append(MonitoringRun.project_id == project_id)
        if mechanism_type:
            conditions.append(MonitoringRun.mechanism_type == mechanism_type)
        if status:
            conditions.append(MonitoringRun.status == status)
        if conditions:
            query = query.where(and_(*conditions))
        query = query.offset(skip).limit(limit).order_by(MonitoringRun.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def add_sample(
        self,
        run_id: UUID,
        question_id: UUID,
        answer_text: Optional[str] = None,
        brand_mentioned: bool = False,
        recommended: bool = False,
        position: Optional[int] = None,
        list_length: Optional[int] = None,
        explicit_citations: int = 0,
        inferred_source_matches: int = 0,
        screenshot_url: Optional[str] = None,
        sources: Optional[List[Dict[str, Any]]] = None,
        analysis: Optional[Dict[str, Any]] = None,
    ) -> MonitoringSample:
        """添加样本"""
        run = await self.get_run(run_id)
        if not run:
            raise ValueError("Monitoring run not found")
        question_result = await self.db.execute(select(Question).where(Question.id == question_id))
        question = question_result.scalar_one_or_none()
        if not question:
            raise ValueError("Question not found")
        group_result = await self.db.execute(
            select(QuestionGroup.project_id).where(QuestionGroup.id == question.group_id)
        )
        question_project_id = group_result.scalar_one_or_none()
        if str(question_project_id or "") != str(run.project_id):
            raise ValueError("检测问题不属于当前检测记录所在项目")
        if question.enabled is False:
            raise ValueError("检测问题已停用，不能写入检测样本")
        visibility = calculate_visibility_score(position, list_length)

        sample = MonitoringSample(
            run_id=run_id,
            question_id=question_id,
            answer_text=answer_text,
            brand_mentioned=brand_mentioned,
            recommended=recommended,
            position=position,
            list_length=list_length,
            visibility_score=visibility,
            explicit_citations=explicit_citations,
            inferred_source_matches=inferred_source_matches,
            sources_json=json.dumps(sources or [], ensure_ascii=False),
            analysis_json=json.dumps(analysis or {}, ensure_ascii=False),
            screenshot_url=screenshot_url,
        )
        self.db.add(sample)
        await self.db.commit()
        await self.db.refresh(sample)
        return sample

    async def delete_sample(self, sample_id: UUID) -> Optional[Dict[str, str]]:
        """删除单条检测样本，并清理关联舆情记录。"""
        result = await self.db.execute(
            select(MonitoringSample).where(MonitoringSample.id == sample_id)
        )
        sample = result.scalar_one_or_none()
        if not sample:
            return None

        run_id = sample.run_id
        self._delete_sample_screenshot_file(sample.screenshot_url)
        await self.db.execute(
            delete(SentimentRecord).where(SentimentRecord.sample_id == sample_id)
        )
        await self.db.delete(sample)
        await self.db.commit()
        return {"id": str(sample_id), "run_id": str(run_id)}

    async def delete_run(self, run_id: UUID) -> Optional[Dict[str, str]]:
        """删除检测记录，并清理该记录下的本地截图证据文件。"""
        run = await self.get_run(run_id)
        if not run:
            return None

        samples_result = await self.db.execute(
            select(MonitoringSample.screenshot_url).where(MonitoringSample.run_id == run_id)
        )
        for screenshot_url in samples_result.scalars().all():
            self._delete_sample_screenshot_file(screenshot_url)

        await self.db.delete(run)
        await self.db.commit()
        return {"id": str(run_id)}

    def _delete_sample_screenshot_file(self, screenshot_url: Optional[str]) -> None:
        """Best-effort cleanup for locally stored WebBridge screenshots."""
        if not screenshot_url or "/monitoring/screenshots/" not in screenshot_url:
            return
        filename = Path(str(screenshot_url).split("/monitoring/screenshots/", 1)[-1]).name
        if not filename or filename != str(screenshot_url).split("/monitoring/screenshots/", 1)[-1]:
            return
        storage_dir = Path(os.getenv("GEO_SCREENSHOT_DIR") or Path.cwd() / "monitoring_screenshots")
        file_path = (storage_dir / filename).resolve()
        try:
            if storage_dir.resolve() in file_path.parents and file_path.is_file():
                file_path.unlink()
        except Exception:
            return

    async def calculate_run_metrics(self, run_id: UUID, finalize: bool = True) -> Dict[str, Any]:
        """
        计算检测记录的所有指标
        """
        run = await self.get_run(run_id)
        if not run:
            return {"error": "Monitoring run not found"}

        result = await self.db.execute(
            select(MonitoringSample).where(MonitoringSample.run_id == run_id)
        )
        samples = list(result.scalars().all())
        n = len(samples)

        if n == 0:
            if finalize:
                run.ended_at = datetime.now(timezone.utc)
                run.status = "failed"
                await self.db.commit()
            return {
                "run_id": str(run_id),
                "sample_count": 0,
                "message": "No samples recorded yet"
            }

        # 基础计数
        mentioned_count = sum(1 for s in samples if s.brand_mentioned)
        recommended_count = sum(1 for s in samples if s.recommended)

        sample_ids = [sample.id for sample in samples]
        sentiment_records: List[SentimentRecord] = []
        if sample_ids:
            sentiment_result = await self.db.execute(
                select(SentimentRecord).where(SentimentRecord.sample_id.in_(sample_ids))
            )
            sentiment_records = list(sentiment_result.scalars().all())
        open_sentiments = [record for record in sentiment_records if record.status != "resolved"]
        negative_sample_ids = {
            record.sample_id
            for record in open_sentiments
            if _is_negative_sentiment(record)
        }
        analysis_negative_sample_ids = {
            sample.id
            for sample in samples
            if _sample_analysis_sentiment(sample) == "negative"
        }
        negative_sample_ids.update(analysis_negative_sample_ids)
        negative_count = len(negative_sample_ids)

        # 位置相关（仅列表型）
        list_samples = [s for s in samples if s.position is not None and s.list_length is not None]
        avg_position = None
        avg_visibility = None
        if list_samples:
            positions = [s.position for s in list_samples]
            visibilities = [s.visibility_score for s in list_samples if s.visibility_score is not None]
            avg_position = sum(positions) / len(positions) if positions else None
            avg_visibility = sum(visibilities) / len(visibilities) if visibilities else None

        # Citation
        total_explicit = sum(s.explicit_citations for s in samples)
        total_inferred = sum(s.inferred_source_matches for s in samples)
        explicit_sample_count = sum(1 for s in samples if (s.explicit_citations or 0) > 0)
        inferred_sample_count = sum(1 for s in samples if (s.inferred_source_matches or 0) > 0)

        # Wilson 置信区间
        mention_ci = calculate_brand_mention_rate(mentioned_count, n)
        recommend_ci = calculate_recommendation_rate(recommended_count, n)
        negative_ci = calculate_negative_mention_rate(negative_count, n)
        explicit_ci = proportion_confidence_interval(explicit_sample_count, n)
        inferred_ci = proportion_confidence_interval(inferred_sample_count, n)

        # 计算时间窗口（简化：用最后一个样本和第一个样本的时间差）
        time_window_days = 0
        if samples:
            first = min(s.sampled_at for s in samples)
            last = max(s.sampled_at for s in samples)
            if first and last:
                time_window_days = (last - first).total_seconds() / 86400

        # 置信等级
        confidence_level = determine_confidence_level(
            n=n,
            wilson_half_width=mention_ci.half_width,
            time_window_days=time_window_days,
            mechanism_type=run.mechanism_type
        )

        if finalize:
            run.ended_at = datetime.now(timezone.utc)
            run.status = "completed"
            await self.db.commit()

        return {
            "run_id": str(run_id),
            "mechanism_type": run.mechanism_type,
            "sample_count": n,
            "time_window_days": round(time_window_days, 1),
            "metrics": {
                "brand_mention_rate": format_ci_report(mention_ci),
                "recommendation_rate": format_ci_report(recommend_ci),
                "negative_mention_rate": format_ci_report(negative_ci),
                "average_position": round(avg_position, 2) if avg_position is not None else None,
                "average_visibility_score": round(avg_visibility, 4) if avg_visibility is not None else None,
                "total_explicit_citations": total_explicit,
                "total_inferred_source_matches": total_inferred,
                "explicit_citation_rate": format_ci_report(explicit_ci),
                "inferred_source_match_rate": format_ci_report(inferred_ci),
                "sentiment_summary": {
                    "total_records": len(sentiment_records),
                    "open_records": len(open_sentiments),
                    "negative_samples": negative_count,
                    "analysis_negative_samples": len(analysis_negative_sample_ids),
                    "by_type": dict(Counter(record.sentiment_type for record in sentiment_records)),
                    "by_severity": dict(Counter(record.severity for record in sentiment_records)),
                },
            },
            "confidence_level": confidence_level,
            "raw_counts": {
                "mentioned": mentioned_count,
                "recommended": recommended_count,
                "negative": negative_count,
                "explicit_citation_samples": explicit_sample_count,
                "inferred_source_match_samples": inferred_sample_count,
            }
        }

    async def calculate_project_runs_metrics(
        self,
        project_id: UUID,
        run_ids: List[UUID],
    ) -> Dict[str, Any]:
        """
        Aggregate monitoring metrics across multiple runs in the same project.

        This is used by report generation when one platform is tested per run
        and the user wants one consolidated report.
        """
        normalized_run_ids = [str(item) for item in run_ids if item]
        if not normalized_run_ids:
            return {
                "sample_count": 0,
                "confidence_level": None,
                "message": "No monitoring runs selected",
            }

        run_result = await self.db.execute(
            select(MonitoringRun)
            .where(
                MonitoringRun.project_id == project_id,
                MonitoringRun.id.in_(normalized_run_ids),
            )
            .options(selectinload(MonitoringRun.model_target))
            .order_by(MonitoringRun.created_at.desc())
        )
        runs = list(run_result.scalars().all())
        if not runs:
            return {"error": "Monitoring runs not found"}

        found_ids = {str(run.id) for run in runs}
        missing_ids = [run_id for run_id in normalized_run_ids if run_id not in found_ids]

        result = await self.db.execute(
            select(MonitoringSample).where(MonitoringSample.run_id.in_(found_ids))
        )
        samples = list(result.scalars().all())
        n = len(samples)

        run_sample_counts = Counter(str(sample.run_id) for sample in samples)
        run_summaries = [
            {
                "run_id": str(run.id),
                "run_type": run.run_type,
                "mechanism_type": run.mechanism_type,
                "status": run.status,
                "model_target_id": str(run.model_target_id),
                "model_target_name": run.model_target.product_name if run.model_target else None,
                "sample_count": run_sample_counts.get(str(run.id), 0),
                "created_at": run.created_at.isoformat() if run.created_at else None,
            }
            for run in runs
        ]

        if n == 0:
            return {
                "run_id": None,
                "run_ids": [str(run.id) for run in runs],
                "aggregation_mode": "multi_run",
                "selected_run_count": len(runs),
                "missing_run_ids": missing_ids,
                "run_summaries": run_summaries,
                "sample_count": 0,
                "message": "Selected monitoring runs have no samples",
            }

        mentioned_count = sum(1 for sample in samples if sample.brand_mentioned)
        recommended_count = sum(1 for sample in samples if sample.recommended)

        sample_ids = [sample.id for sample in samples]
        sentiment_records: List[SentimentRecord] = []
        if sample_ids:
            sentiment_result = await self.db.execute(
                select(SentimentRecord).where(SentimentRecord.sample_id.in_(sample_ids))
            )
            sentiment_records = list(sentiment_result.scalars().all())
        open_sentiments = [record for record in sentiment_records if record.status != "resolved"]
        negative_sample_ids = {
            record.sample_id
            for record in open_sentiments
            if _is_negative_sentiment(record)
        }
        analysis_negative_sample_ids = {
            sample.id
            for sample in samples
            if _sample_analysis_sentiment(sample) == "negative"
        }
        negative_sample_ids.update(analysis_negative_sample_ids)
        negative_count = len(negative_sample_ids)

        list_samples = [
            sample
            for sample in samples
            if sample.position is not None and sample.list_length is not None
        ]
        avg_position = None
        avg_visibility = None
        if list_samples:
            positions = [sample.position for sample in list_samples]
            visibilities = [
                sample.visibility_score
                for sample in list_samples
                if sample.visibility_score is not None
            ]
            avg_position = sum(positions) / len(positions) if positions else None
            avg_visibility = sum(visibilities) / len(visibilities) if visibilities else None

        total_explicit = sum(sample.explicit_citations for sample in samples)
        total_inferred = sum(sample.inferred_source_matches for sample in samples)
        explicit_sample_count = sum(1 for sample in samples if (sample.explicit_citations or 0) > 0)
        inferred_sample_count = sum(1 for sample in samples if (sample.inferred_source_matches or 0) > 0)

        mention_ci = calculate_brand_mention_rate(mentioned_count, n)
        recommend_ci = calculate_recommendation_rate(recommended_count, n)
        negative_ci = calculate_negative_mention_rate(negative_count, n)
        explicit_ci = proportion_confidence_interval(explicit_sample_count, n)
        inferred_ci = proportion_confidence_interval(inferred_sample_count, n)

        sampled_times = [sample.sampled_at for sample in samples if sample.sampled_at]
        if sampled_times:
            first = min(sampled_times)
            last = max(sampled_times)
            time_window_days = (last - first).total_seconds() / 86400
        else:
            time_window_days = 0

        mechanism_types = sorted({run.mechanism_type for run in runs if run.mechanism_type})
        mechanism_type = mechanism_types[0] if len(mechanism_types) == 1 else "mixed"
        confidence_level = determine_confidence_level(
            n=n,
            wilson_half_width=mention_ci.half_width,
            time_window_days=time_window_days,
            mechanism_type=mechanism_type,
        )

        return {
            "run_id": None,
            "run_ids": [str(run.id) for run in runs],
            "aggregation_mode": "multi_run",
            "selected_run_count": len(runs),
            "missing_run_ids": missing_ids,
            "run_summaries": run_summaries,
            "mechanism_type": mechanism_type,
            "sample_count": n,
            "time_window_days": round(time_window_days, 1),
            "metrics": {
                "brand_mention_rate": format_ci_report(mention_ci),
                "recommendation_rate": format_ci_report(recommend_ci),
                "negative_mention_rate": format_ci_report(negative_ci),
                "average_position": round(avg_position, 2) if avg_position is not None else None,
                "average_visibility_score": round(avg_visibility, 4) if avg_visibility is not None else None,
                "total_explicit_citations": total_explicit,
                "total_inferred_source_matches": total_inferred,
                "explicit_citation_rate": format_ci_report(explicit_ci),
                "inferred_source_match_rate": format_ci_report(inferred_ci),
                "sentiment_summary": {
                    "total_records": len(sentiment_records),
                    "open_records": len(open_sentiments),
                    "negative_samples": negative_count,
                    "analysis_negative_samples": len(analysis_negative_sample_ids),
                    "by_type": dict(Counter(record.sentiment_type for record in sentiment_records)),
                    "by_severity": dict(Counter(record.severity for record in sentiment_records)),
                },
            },
            "confidence_level": confidence_level,
            "raw_counts": {
                "mentioned": mentioned_count,
                "recommended": recommended_count,
                "negative": negative_count,
                "explicit_citation_samples": explicit_sample_count,
                "inferred_source_match_samples": inferred_sample_count,
            },
        }

    async def compare_with_baseline(
        self,
        run_id: UUID,
        baseline_run_id: UUID
    ) -> Dict[str, Any]:
        """
        对比检测结果与基线
        """
        run_metrics = await self.calculate_run_metrics(run_id, finalize=False)
        if "error" in run_metrics:
            return run_metrics

        baseline_metrics = await self.calculate_run_metrics(baseline_run_id, finalize=False)
        if "error" in baseline_metrics:
            return {"error": "Baseline run not found"}

        def point(metrics: Dict[str, Any], key: str) -> Optional[float]:
            try:
                value = metrics.get("metrics", {}).get(key, {}).get("point_estimate")
                return float(value)
            except (TypeError, ValueError, AttributeError):
                return None

        mention_delta = None
        recommend_delta = None
        baseline_mention = point(baseline_metrics, "brand_mention_rate")
        run_mention = point(run_metrics, "brand_mention_rate")
        baseline_recommend = point(baseline_metrics, "recommendation_rate")
        run_recommend = point(run_metrics, "recommendation_rate")
        if baseline_mention is not None and run_mention is not None:
            mention_delta = round(run_mention - baseline_mention, 2)
        if baseline_recommend is not None and run_recommend is not None:
            recommend_delta = round(run_recommend - baseline_recommend, 2)

        return {
            "run_id": str(run_id),
            "baseline_run_id": str(baseline_run_id),
            "run_metrics": run_metrics,
            "baseline_metrics": baseline_metrics,
            "comparison": {
                "mention_delta": mention_delta,
                "recommend_delta": recommend_delta,
                "significant_change": (
                    (mention_delta is not None and abs(mention_delta) >= 10)
                    or (recommend_delta is not None and abs(recommend_delta) >= 10)
                ),
            }
        }

    async def generate_recommendations_for_run(self, run_id: UUID) -> Dict[str, Any]:
        """根据检测指标沉淀下一轮 GEO 优化建议。"""
        run = await self.get_run(run_id)
        if not run:
            return {"error": "Monitoring run not found"}

        metrics = await self.calculate_run_metrics(run_id, finalize=False)
        if "error" in metrics:
            return metrics

        sample_count = metrics.get("sample_count", 0)
        metric_values = metrics.get("metrics", {})
        confidence_level = metrics.get("confidence_level") or ""
        if not isinstance(confidence_level, str):
            confidence_level = ""
        explicit_citations = metric_values.get("total_explicit_citations", 0) or 0
        inferred_matches = metric_values.get("total_inferred_source_matches", 0) or 0

        def point(key: str) -> Optional[float]:
            value = metric_values.get(key, {})
            if isinstance(value, dict):
                value = value.get("point_estimate")
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        mention_rate = point("brand_mention_rate")
        recommendation_rate = point("recommendation_rate")
        visibility_score = metric_values.get("average_visibility_score")
        try:
            visibility_score = float(visibility_score) if visibility_score is not None else None
        except (TypeError, ValueError):
            visibility_score = None

        candidates: List[Dict[str, str]] = []
        if sample_count == 0:
            candidates.append({
                "recommendation_type": "补充检测样本",
                "reason": "当前检测记录还没有样本，无法判断品牌是否被生成式引擎稳定识别。",
                "priority": "high",
                "linked_metric": "sample_count",
            })
        elif sample_count < 5:
            candidates.append({
                "recommendation_type": "扩大采样量",
                "reason": f"当前仅有 {sample_count} 条样本，建议至少补到 5-10 条，避免单次回答波动误导判断。",
                "priority": "medium",
                "linked_metric": "sample_count",
            })

        if mention_rate is not None and mention_rate < 50:
            candidates.append({
                "recommendation_type": "补强入池内容",
                "reason": f"品牌提及率为 {mention_rate:.1f}%，说明模型回答中还不稳定出现品牌，需要增加本地推荐、品牌介绍、资质验证类内容。",
                "priority": "high",
                "linked_metric": "brand_mention_rate",
            })

        if recommendation_rate is not None and recommendation_rate < 30:
            candidates.append({
                "recommendation_type": "补强推荐理由",
                "reason": f"推荐率为 {recommendation_rate:.1f}%，需要补充可对比的优势、案例、价格流程和第三方背书内容。",
                "priority": "high",
                "linked_metric": "recommendation_rate",
            })

        if visibility_score is not None and visibility_score < 0.5:
            candidates.append({
                "recommendation_type": "优化榜单位置",
                "reason": f"平均可见性得分为 {visibility_score:.2f}，品牌即使出现也可能位置偏后，建议制作对比测评和权重层内容。",
                "priority": "medium",
                "linked_metric": "average_visibility_score",
            })

        if explicit_citations == 0 and inferred_matches == 0:
            candidates.append({
                "recommendation_type": "补充可引用事实源",
                "reason": "回答中没有出现明确引用或来源匹配，建议补充官网、资质证书、案例页、媒体报道等可被引用的公开资料。",
                "priority": "medium",
                "linked_metric": "citations",
            })

        if confidence_level in {"low", "very_low"}:
            candidates.append({
                "recommendation_type": "延长观察窗口",
                "reason": "当前置信等级偏低，建议增加检测轮次或跨模型采样后再做结论。",
                "priority": "medium",
                "linked_metric": "confidence_level",
            })

        existing_result = await self.db.execute(
            select(Recommendation).where(
                Recommendation.project_id == run.project_id,
                Recommendation.status == "open",
            )
        )
        existing_keys = {
            (item.recommendation_type, item.linked_metric)
            for item in existing_result.scalars().all()
        }

        created: List[Recommendation] = []
        skipped = 0
        for item in candidates:
            key = (item["recommendation_type"], item["linked_metric"])
            if key in existing_keys:
                skipped += 1
                continue
            recommendation = Recommendation(
                project_id=run.project_id,
                recommendation_type=item["recommendation_type"],
                reason=item["reason"],
                priority=item["priority"],
                linked_metric=item["linked_metric"],
                status="open",
            )
            self.db.add(recommendation)
            created.append(recommendation)
            existing_keys.add(key)

        await self.db.commit()
        for item in created:
            await self.db.refresh(item)

        return {
            "run_id": str(run_id),
            "project_id": str(run.project_id),
            "created_recommendations": len(created),
            "skipped_recommendations": skipped,
            "recommendations": [
                {
                    "id": str(item.id),
                    "recommendation_type": item.recommendation_type,
                    "reason": item.reason,
                    "priority": item.priority,
                    "linked_metric": item.linked_metric,
                    "status": item.status,
                }
                for item in created
            ],
            "metrics_snapshot": metrics,
        }
