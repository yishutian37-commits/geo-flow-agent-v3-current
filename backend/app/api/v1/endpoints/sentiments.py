from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.monitoring import MonitoringSample
from app.models.sentiment import SentimentRecord
from app.schemas.sentiment import SentimentRecordCreate, SentimentRecordUpdate

router = APIRouter()


def _record_to_dict(record: SentimentRecord) -> dict:
    return {
        "id": str(record.id),
        "sample_id": str(record.sample_id),
        "sentiment_type": record.sentiment_type,
        "severity": record.severity,
        "source": record.source,
        "suggested_action": record.suggested_action,
        "status": record.status,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


async def _sample_exists(db: AsyncSession, sample_id: UUID) -> bool:
    result = await db.execute(select(MonitoringSample.id).where(MonitoringSample.id == sample_id))
    return result.scalar_one_or_none() is not None


@router.get("")
async def list_sentiment_records(
    sample_id: Optional[UUID] = Query(None),
    sentiment_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """查询检测样本关联的舆情/风险记录。"""
    filters = []
    if sample_id:
        filters.append(SentimentRecord.sample_id == sample_id)
    if sentiment_type:
        filters.append(SentimentRecord.sentiment_type == sentiment_type)
    if severity:
        filters.append(SentimentRecord.severity == severity)
    if status:
        filters.append(SentimentRecord.status == status)

    query = select(SentimentRecord)
    if filters:
        query = query.where(and_(*filters))
    query = query.order_by(SentimentRecord.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return [_record_to_dict(item) for item in result.scalars().all()]


@router.post("")
async def create_sentiment_record(
    data: SentimentRecordCreate,
    db: AsyncSession = Depends(get_db),
):
    """为一次检测样本登记负面、风险、误答或中性观察。"""
    if not await _sample_exists(db, data.sample_id):
        raise HTTPException(status_code=400, detail="舆情记录必须绑定已存在的检测样本")
    record = SentimentRecord(**data.model_dump())
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return _record_to_dict(record)


@router.put("/{record_id}")
async def update_sentiment_record(
    record_id: UUID,
    data: SentimentRecordUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SentimentRecord).where(SentimentRecord.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Sentiment record not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    await db.commit()
    await db.refresh(record)
    return _record_to_dict(record)


@router.delete("/{record_id}")
async def delete_sentiment_record(
    record_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SentimentRecord).where(SentimentRecord.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Sentiment record not found")
    await db.delete(record)
    await db.commit()
    return {"message": "Deleted"}
