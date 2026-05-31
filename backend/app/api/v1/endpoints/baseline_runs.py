from collections import defaultdict
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.baseline_run import BaselineRun
from app.models.model_target import ModelTarget
from app.models.monitoring import MonitoringRun, MonitoringSample
from app.models.project import Project
from app.models.question import Question
from app.schemas.baseline_run import BaselineRunCreate, BaselineRunUpdate, BaselinePromoteRequest
from app.services.monitoring_service import MonitoringService

router = APIRouter()


def _baseline_to_dict(item: BaselineRun, question: Optional[Question] = None, target: Optional[ModelTarget] = None) -> dict:
    return {
        "id": str(item.id),
        "project_id": str(item.project_id),
        "question_id": str(item.question_id),
        "question_text": question.question_text if question else None,
        "model_target_id": str(item.model_target_id),
        "model_target_name": target.product_name if target else None,
        "mechanism_type": item.mechanism_type,
        "call_mode_detail": item.call_mode_detail,
        "sample_policy": item.sample_policy,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "ended_at": item.ended_at.isoformat() if item.ended_at else None,
        "confidence_level": item.confidence_level,
        "valid_status": item.valid_status,
        "invalid_reason": item.invalid_reason,
    }


async def _validate_baseline_links(db: AsyncSession, project_id: UUID, question_id: UUID, model_target_id: UUID) -> tuple[Question, ModelTarget]:
    project_result = await db.execute(select(Project.id).where(Project.id == project_id))
    if project_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=400, detail="基线必须绑定已存在项目")

    question_result = await db.execute(select(Question).where(Question.id == question_id))
    question = question_result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=400, detail="基线问题不存在")

    target_result = await db.execute(
        select(ModelTarget).where(
            ModelTarget.id == model_target_id,
            ModelTarget.project_id == project_id,
        )
    )
    target = target_result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=400, detail="检测平台不存在，或不属于当前项目")

    return question, target


@router.get("")
async def list_baseline_runs(
    project_id: Optional[UUID] = Query(None),
    question_id: Optional[UUID] = Query(None),
    model_target_id: Optional[UUID] = Query(None),
    valid_status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """查询验收/观察基线。"""
    filters = []
    if project_id:
        filters.append(BaselineRun.project_id == project_id)
    if question_id:
        filters.append(BaselineRun.question_id == question_id)
    if model_target_id:
        filters.append(BaselineRun.model_target_id == model_target_id)
    if valid_status:
        filters.append(BaselineRun.valid_status == valid_status)

    query = select(BaselineRun)
    if filters:
        query = query.where(and_(*filters))
    query = query.order_by(BaselineRun.started_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    baselines = list(result.scalars().all())

    questions_by_id = {}
    targets_by_id = {}
    question_ids = sorted({str(item.question_id) for item in baselines})
    target_ids = sorted({str(item.model_target_id) for item in baselines})
    if question_ids:
        q_result = await db.execute(select(Question).where(Question.id.in_(question_ids)))
        questions_by_id = {str(item.id): item for item in q_result.scalars().all()}
    if target_ids:
        t_result = await db.execute(select(ModelTarget).where(ModelTarget.id.in_(target_ids)))
        targets_by_id = {str(item.id): item for item in t_result.scalars().all()}

    return [
        _baseline_to_dict(
            item,
            questions_by_id.get(str(item.question_id)),
            targets_by_id.get(str(item.model_target_id)),
        )
        for item in baselines
    ]


@router.post("")
async def create_baseline_run(
    data: BaselineRunCreate,
    db: AsyncSession = Depends(get_db),
):
    question, target = await _validate_baseline_links(db, data.project_id, data.question_id, data.model_target_id)
    baseline = BaselineRun(**data.model_dump())
    db.add(baseline)
    await db.commit()
    await db.refresh(baseline)
    return _baseline_to_dict(baseline, question, target)


@router.put("/{baseline_id}")
async def update_baseline_run(
    baseline_id: UUID,
    data: BaselineRunUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BaselineRun).where(BaselineRun.id == baseline_id))
    baseline = result.scalar_one_or_none()
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline run not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(baseline, field, value)

    await db.commit()
    await db.refresh(baseline)
    return _baseline_to_dict(baseline)


@router.post("/{baseline_id}/invalidate")
async def invalidate_baseline_run(
    baseline_id: UUID,
    reason: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BaselineRun).where(BaselineRun.id == baseline_id))
    baseline = result.scalar_one_or_none()
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline run not found")
    baseline.valid_status = "invalid"
    baseline.invalid_reason = reason
    await db.commit()
    await db.refresh(baseline)
    return _baseline_to_dict(baseline)


@router.post("/from-monitoring-run/{run_id}")
async def promote_monitoring_run_to_baseline(
    run_id: UUID,
    data: BaselinePromoteRequest,
    db: AsyncSession = Depends(get_db),
):
    """把一次检测批次中的问题样本沉淀为基线记录。"""
    run_result = await db.execute(select(MonitoringRun).where(MonitoringRun.id == run_id))
    run = run_result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Monitoring run not found")

    metrics = await MonitoringService(db).calculate_run_metrics(run_id, finalize=False)
    if "error" in metrics:
        raise HTTPException(status_code=404, detail=metrics["error"])

    if data.require_acceptance_grade:
        if metrics.get("sample_count", 0) < 20 or metrics.get("confidence_level") != "high":
            raise HTTPException(
                status_code=400,
                detail="该检测批次未达到验收基线要求：N≥20 且置信等级为高",
            )

    sample_result = await db.execute(select(MonitoringSample).where(MonitoringSample.run_id == run_id))
    samples = list(sample_result.scalars().all())
    by_question = defaultdict(int)
    for sample in samples:
        by_question[str(sample.question_id)] += 1

    existing_result = await db.execute(
        select(BaselineRun).where(
            BaselineRun.project_id == run.project_id,
            BaselineRun.model_target_id == run.model_target_id,
            BaselineRun.mechanism_type == run.mechanism_type,
            BaselineRun.valid_status == "valid",
        )
    )
    existing_keys = {str(item.question_id) for item in existing_result.scalars().all()}

    created = []
    skipped = 0
    run.run_type = "baseline"
    for question_id, count in by_question.items():
        if question_id in existing_keys:
            skipped += 1
            continue
        baseline = BaselineRun(
            project_id=run.project_id,
            question_id=question_id,
            model_target_id=run.model_target_id,
            mechanism_type=run.mechanism_type,
            call_mode_detail=run.call_mode_detail,
            sample_policy=run.sample_policy,
            started_at=run.started_at,
            ended_at=run.ended_at,
            confidence_level=metrics.get("confidence_level", "low"),
            valid_status="valid",
            invalid_reason=data.invalid_reason,
        )
        db.add(baseline)
        created.append((baseline, count))

    await db.commit()
    for baseline, _ in created:
        await db.refresh(baseline)

    return {
        "run_id": str(run_id),
        "baseline_run_id": str(run.id),
        "run_marked_as_baseline": True,
        "created_baselines": len(created),
        "skipped_existing": skipped,
        "confidence_level": metrics.get("confidence_level"),
        "sample_count": metrics.get("sample_count", 0),
        "baselines": [
            {
                **_baseline_to_dict(item),
                "question_sample_count": count,
            }
            for item, count in created
        ],
    }
