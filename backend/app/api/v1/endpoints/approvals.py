from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, require_roles, user_has_any_role
from app.core.database import get_db
from app.models.approval import Approval
from app.models.user import User
from app.schemas.approval import ApprovalCreate, ApprovalDecision

router = APIRouter()

VALID_DECISIONS = {"pending", "approved", "rejected", "changes_requested"}

APPROVAL_CREATE_ROLES = ("strategist", "editor", "compliance_reviewer", "project_owner")
APPROVAL_STEP_ROLES = {
    "compliance_review": ("compliance_reviewer", "project_owner"),
    "project_owner_review": ("project_owner",),
    "client_review": ("client", "project_owner"),
}


def _approval_to_dict(approval: Approval) -> dict:
    return {
        "id": str(approval.id),
        "object_type": approval.object_type,
        "object_id": str(approval.object_id),
        "step": approval.step,
        "approver_id": str(approval.approver_id) if approval.approver_id else None,
        "decision": approval.decision,
        "comment": approval.comment,
        "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
        "created_at": approval.created_at.isoformat() if approval.created_at else None,
    }


@router.get("")
async def list_approvals(
    object_type: Optional[str] = Query(None),
    object_id: Optional[UUID] = Query(None),
    decision: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """查询审批/确认记录。"""
    filters = []
    if object_type:
        filters.append(Approval.object_type == object_type)
    if object_id:
        filters.append(Approval.object_id == object_id)
    if decision:
        filters.append(Approval.decision == decision)

    query = select(Approval)
    if filters:
        query = query.where(and_(*filters))
    query = query.order_by(Approval.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return [_approval_to_dict(item) for item in result.scalars().all()]


@router.post("")
async def create_approval(
    data: ApprovalCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(*APPROVAL_CREATE_ROLES)),
):
    """创建一个待审批记录。"""
    approval = Approval(
        object_type=data.object_type,
        object_id=data.object_id,
        step=data.step,
        approver_id=data.approver_id,
        decision="pending",
        comment=data.comment,
    )
    db.add(approval)
    await db.commit()
    await db.refresh(approval)
    return _approval_to_dict(approval)


@router.post("/{approval_id}/decision")
async def decide_approval(
    approval_id: UUID,
    data: ApprovalDecision,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """记录审批结论。"""
    decision = data.decision.strip()
    if decision not in VALID_DECISIONS:
        raise HTTPException(status_code=400, detail=f"无效审批结论: {decision}")

    result = await db.execute(select(Approval).where(Approval.id == approval_id))
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    allowed_roles = APPROVAL_STEP_ROLES.get(
        approval.step,
        ("compliance_reviewer", "project_owner", "client"),
    )
    if not user_has_any_role(user, allowed_roles):
        raise HTTPException(status_code=403, detail="Current user is not allowed to decide this approval step")

    approval.decision = decision
    approval.comment = data.comment
    approval.approver_id = user.id
    approval.decided_at = None if decision == "pending" else datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(approval)
    return _approval_to_dict(approval)
