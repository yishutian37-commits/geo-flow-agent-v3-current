import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.report_archive import ReportArchive
from app.schemas.report_archive import ReportArchiveGenerateRequest
from app.services.report_service import ReportService

router = APIRouter()


def _archive_summary(item: ReportArchive) -> dict:
    payload = {}
    try:
        payload = json.loads(item.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    selected_run_ids = payload.get("selected_run_ids") or []
    return {
        "id": str(item.id),
        "project_id": str(item.project_id),
        "report_type": item.report_type,
        "title": item.title,
        "run_id": str(item.run_id) if item.run_id else None,
        "run_ids": selected_run_ids,
        "baseline_run_id": str(item.baseline_run_id) if item.baseline_run_id else None,
        "time_window_days": item.time_window_days,
        "acceptance_ready": item.acceptance_ready,
        "confidence_level": item.confidence_level,
        "sample_count": item.sample_count,
        "generated_at": item.generated_at.isoformat() if item.generated_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _archive_detail(item: ReportArchive) -> dict:
    payload = {}
    try:
        payload = json.loads(item.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {"error": "归档 payload 解析失败"}
    return {
        **_archive_summary(item),
        "markdown": item.markdown,
        "payload": payload,
    }


def _default_archive_title(report: dict) -> str:
    project_name = report.get("project", {}).get("name") or "未命名项目"
    report_type = "客户报告" if report.get("report_type") == "client" else "内部报告"
    run_count = len(report.get("selected_run_ids") or [])
    suffix = f" 聚合{run_count}组检测" if run_count > 1 else ""
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    return f"{project_name} {report_type}{suffix} {generated_at}"


def _primary_run_id(run_id: Optional[UUID], run_ids: Optional[list[UUID]]) -> Optional[str]:
    if run_id:
        return str(run_id)
    if run_ids:
        return str(run_ids[0])
    return None


@router.get("")
async def generate_report(
    project_id: UUID = Query(..., description="项目ID"),
    report_type: str = Query("client", pattern="^(client|internal)$"),
    run_id: Optional[UUID] = Query(None, description="可选检测记录ID"),
    run_ids: Optional[list[UUID]] = Query(None, description="可选多条检测记录ID，用于聚合报告"),
    baseline_run_id: Optional[UUID] = Query(None, description="可选基线检测记录ID"),
    time_window_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """生成结构化报告。支持单组检测记录，也支持多组检测记录聚合。"""
    service = ReportService(db)
    if report_type == "internal":
        report = await service.generate_internal_report(project_id, run_id, baseline_run_id, time_window_days, run_ids)
    else:
        report = await service.generate_client_report(project_id, run_id, baseline_run_id, time_window_days, run_ids)
    if "error" in report:
        raise HTTPException(status_code=404, detail=report["error"])
    return report


@router.get("/markdown", response_class=PlainTextResponse)
async def generate_report_markdown(
    project_id: UUID = Query(..., description="项目ID"),
    report_type: str = Query("client", pattern="^(client|internal)$"),
    run_id: Optional[UUID] = Query(None, description="可选检测记录ID"),
    run_ids: Optional[list[UUID]] = Query(None, description="可选多条检测记录ID，用于聚合报告"),
    baseline_run_id: Optional[UUID] = Query(None, description="可选基线检测记录ID"),
    time_window_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """生成 Markdown 报告文本，方便复制给客户或保存归档。"""
    service = ReportService(db)
    if report_type == "internal":
        report = await service.generate_internal_report(project_id, run_id, baseline_run_id, time_window_days, run_ids)
    else:
        report = await service.generate_client_report(project_id, run_id, baseline_run_id, time_window_days, run_ids)
    if "error" in report:
        raise HTTPException(status_code=404, detail=report["error"])
    return report.get("markdown", "")


@router.post("/archives")
async def generate_and_archive_report(
    data: ReportArchiveGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """生成一份报告并保存归档，后续可查看、复制 Markdown 或删除。"""
    service = ReportService(db)
    if data.report_type == "internal":
        report = await service.generate_internal_report(
            data.project_id,
            data.run_id,
            data.baseline_run_id,
            data.time_window_days,
            data.run_ids,
        )
    else:
        report = await service.generate_client_report(
            data.project_id,
            data.run_id,
            data.baseline_run_id,
            data.time_window_days,
            data.run_ids,
        )
    if "error" in report:
        raise HTTPException(status_code=404, detail=report["error"])

    acceptance = report.get("acceptance_baseline") or {}
    monitoring = report.get("monitoring_results") or {}
    item = ReportArchive(
        project_id=str(data.project_id),
        report_type=data.report_type,
        title=data.title or _default_archive_title(report),
        run_id=_primary_run_id(data.run_id, data.run_ids),
        baseline_run_id=str(data.baseline_run_id) if data.baseline_run_id else None,
        time_window_days=data.time_window_days,
        acceptance_ready=bool(acceptance.get("acceptance_ready")),
        confidence_level=monitoring.get("confidence_level"),
        sample_count=int(monitoring.get("sample_count") or 0),
        markdown=report.get("markdown") or "",
        payload_json=json.dumps(report, ensure_ascii=False, default=str),
        generated_at=datetime.now(timezone.utc),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _archive_detail(item)


@router.get("/archives")
async def list_report_archives(
    project_id: Optional[UUID] = Query(None),
    report_type: Optional[str] = Query(None, pattern="^(client|internal)$"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ReportArchive)
    if project_id:
        stmt = stmt.where(ReportArchive.project_id == str(project_id))
    if report_type:
        stmt = stmt.where(ReportArchive.report_type == report_type)
    stmt = stmt.order_by(ReportArchive.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return [_archive_summary(item) for item in result.scalars().all()]


@router.get("/archives/{archive_id}")
async def get_report_archive(
    archive_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ReportArchive).where(ReportArchive.id == str(archive_id)))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Report archive not found")
    return _archive_detail(item)


@router.get("/archives/{archive_id}/markdown", response_class=PlainTextResponse)
async def get_report_archive_markdown(
    archive_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ReportArchive).where(ReportArchive.id == str(archive_id)))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Report archive not found")
    return item.markdown


@router.delete("/archives/{archive_id}")
async def delete_report_archive(
    archive_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ReportArchive).where(ReportArchive.id == str(archive_id)))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Report archive not found")
    await db.delete(item)
    await db.commit()
    return {"deleted": True, "id": str(archive_id)}
