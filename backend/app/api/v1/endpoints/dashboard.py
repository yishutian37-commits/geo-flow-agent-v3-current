from typing import Dict, Any, List
from uuid import UUID
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.core.database import get_db
from app.models.project import Project
from app.models.brand_fact import BrandFact
from app.models.content_task import ContentTask
from app.models.monitoring import MonitoringRun
from app.models.question import Question

router = APIRouter()


@router.get("/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """获取仪表盘聚合统计数据"""

    # 项目统计
    project_result = await db.execute(
        select(
            func.count(Project.id).label("total"),
            func.count(Project.id).filter(Project.status == "active").label("active"),
        )
    )
    project_stats = project_result.mappings().first()

    # 事实库统计
    fact_result = await db.execute(
        select(
            BrandFact.status,
            func.count(BrandFact.id).label("count")
        ).group_by(BrandFact.status)
    )
    fact_stats = {row.status: row.count for row in fact_result.mappings().all()}

    # 内容任务统计
    task_result = await db.execute(
        select(
            ContentTask.status,
            func.count(ContentTask.id).label("count")
        ).group_by(ContentTask.status)
    )
    task_stats = {row.status: row.count for row in task_result.mappings().all()}

    # 检测记录统计
    monitoring_result = await db.execute(
        select(
            func.count(MonitoringRun.id).label("total"),
            func.count(MonitoringRun.id).filter(MonitoringRun.status == "running").label("running"),
            func.count(MonitoringRun.id).filter(MonitoringRun.status == "completed").label("completed"),
        )
    )
    monitoring_stats = monitoring_result.mappings().first()

    # 问题库统计
    question_result = await db.execute(
        select(func.count(Question.id).label("total"))
    )
    question_total = question_result.scalar() or 0

    # 最近活跃项目（最近7天有更新的）
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_projects_result = await db.execute(
        select(Project).where(Project.updated_at >= week_ago)
        .order_by(Project.updated_at.desc()).limit(5)
    )
    recent_projects = recent_projects_result.scalars().all()

    # 待办事项（需要关注的事项）
    todos: List[Dict[str, Any]] = []

    # 待确认事实
    pending_facts_count = fact_stats.get("draft", 0)
    if pending_facts_count > 0:
        todos.append({
            "type": "pending_facts",
            "title": f"有 {pending_facts_count} 条品牌事实待客户确认",
            "priority": "high",
            "link": "/brand-facts",
        })

    # 过期事实
    expired_facts_result = await db.execute(
        select(func.count(BrandFact.id)).where(
            and_(
                BrandFact.valid_until < datetime.now(timezone.utc),
                BrandFact.status == "confirmed"
            )
        )
    )
    expired_count = expired_facts_result.scalar() or 0
    if expired_count > 0:
        todos.append({
            "type": "expired_facts",
            "title": f"有 {expired_count} 条已确认事实已过期，需更新",
            "priority": "high",
            "link": "/brand-facts",
        })

    # 进行中内容任务
    in_progress_tasks = task_stats.get("in_progress", 0)
    if in_progress_tasks > 0:
        todos.append({
            "type": "in_progress_tasks",
            "title": f"有 {in_progress_tasks} 个内容任务进行中",
            "priority": "medium",
            "link": "/content",
        })

    # 待审核内容
    review_tasks = task_stats.get("review", 0) + task_stats.get("client_review", 0)
    if review_tasks > 0:
        todos.append({
            "type": "review_tasks",
            "title": f"有 {review_tasks} 个内容任务待审核",
            "priority": "medium",
            "link": "/content",
        })

    # 运行中的检测
    running_monitoring = monitoring_stats.get("running", 0) if monitoring_stats else 0
    if running_monitoring > 0:
        todos.append({
            "type": "running_monitoring",
            "title": f"有 {running_monitoring} 个检测记录进行中",
            "priority": "low",
            "link": "/monitoring",
        })

    return {
        "projects": {
            "total": project_stats.get("total", 0) if project_stats else 0,
            "active": project_stats.get("active", 0) if project_stats else 0,
        },
        "facts": {
            "total": sum(fact_stats.values()),
            "draft": fact_stats.get("draft", 0),
            "confirmed": fact_stats.get("confirmed", 0),
            "expired": fact_stats.get("expired", 0),
            "disputed": fact_stats.get("disputed", 0),
            "restricted": fact_stats.get("restricted", 0),
        },
        "tasks": {
            "total": sum(task_stats.values()),
            "draft": task_stats.get("draft", 0),
            "in_progress": task_stats.get("in_progress", 0),
            "review": task_stats.get("review", 0),
            "approved": task_stats.get("approved", 0),
            "publish_ready": task_stats.get("publish_ready", 0),
            "published": task_stats.get("published", 0),
        },
        "monitoring": {
            "total": monitoring_stats.get("total", 0) if monitoring_stats else 0,
            "running": monitoring_stats.get("running", 0) if monitoring_stats else 0,
            "completed": monitoring_stats.get("completed", 0) if monitoring_stats else 0,
        },
        "questions": {
            "total": question_total,
        },
        "todos": todos,
        "recent_projects": [
            {
                "id": str(p.id),
                "name": p.name,
                "industry": p.industry,
                "status": p.status,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in recent_projects
        ],
    }
