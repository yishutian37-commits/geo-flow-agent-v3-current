"""
主控编排器
协调五大核心Agent的工作流程，驱动GEO全流程闭环
"""
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime, timezone
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.content_task import ContentTask
from app.models.content_draft import ContentDraft
from app.models.monitoring import MonitoringRun
from app.services.state_machine import StateMachine, TaskStatus


class OrchestratorError(Exception):
    pass


class Orchestrator:
    """
    GEO Flow Agent 主控编排器
    负责：
    1. 项目生命周期管理
    2. Agent调度与执行
    3. 状态机驱动
    4. 审批流管理
    5. 成本追踪
    """

    def __init__(self, db: AsyncSession, llm_client=None):
        self.db = db
        self.llm = llm_client

    async def create_project_workflow(
        self,
        project_data: Dict[str, Any],
        owner_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        创建项目完整工作流
        Step 1: 创建项目
        Step 2: 创建品牌主体
        Step 3: 触发资料缺口诊断
        Step 4: 生成待确认事实清单
        """
        from app.services.project_service import ProjectService

        service = ProjectService(self.db)
        project = await service.create_project(project_data, owner_id)

        return {
            "project_id": str(project.id),
            "status": "created",
            "next_steps": [
                "上传品牌资料",
                "确认资料缺口诊断结果",
                "创建品牌事实库",
                "配置检测平台",
            ],
            "workflow_stage": "project_initialized",
        }

    async def run_diagnosis_workflow(
        self,
        project_id: UUID,
    ) -> Dict[str, Any]:
        """
        诊断工作流
        Step 1: 品牌AI体检
        Step 2: 生成三层问题库
        Step 3: 建立基线
        """
        return {
            "project_id": str(project_id),
            "status": "diagnosis_started",
            "workflow_stage": "diagnosis_in_progress",
            "message": "诊断工作流已启动，请配置检测平台并上传初始采样结果",
        }

    async def run_strategy_workflow(
        self,
        project_id: UUID,
        diagnosis_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        策略工作流
        Step 1: 内容触发判断
        Step 2: 生成内容矩阵
        Step 3: 渠道组合建议
        Step 4: 发布排期
        """
        from app.agents.strategy_agent import StrategyAgent

        agent = StrategyAgent(self.llm)
        triggers = agent.determine_content_trigger(diagnosis_results)

        return {
            "project_id": str(project_id),
            "status": "strategy_generated",
            "workflow_stage": "strategy_ready",
            "triggers": triggers,
            "next_steps": [
                "审核内容矩阵",
                "确认渠道组合",
                "批准发布排期",
                "创建内容任务",
            ],
        }

    async def create_content_tasks_from_matrix(
        self,
        project_id: UUID,
        content_matrix: List[Dict[str, Any]],
    ) -> List[ContentTask]:
        """
        根据内容矩阵创建内容任务
        """
        tasks = []
        for item in content_matrix:
            task = ContentTask(
                project_id=project_id,
                content_type=item.get("content_type", "brand_intro"),
                layer=item.get("layer", "verification_layer"),
                priority=item.get("priority", "medium"),
                status=TaskStatus.DRAFT.value,
            )
            self.db.add(task)
            tasks.append(task)

        await self.db.commit()
        for task in tasks:
            await self.db.refresh(task)

        return tasks

    async def run_production_workflow(
        self,
        task_id: UUID,
    ) -> Dict[str, Any]:
        """
        内容生产工作流
        Step 1: 生成草稿
        Step 2: 事实引用检查
        Step 3: 合规检查
        Step 4: 质量门
        Step 5: 进入审核
        """
        return {
            "task_id": str(task_id),
            "status": "production_started",
            "workflow_stage": "draft_generating",
            "message": "内容生产工作流已启动",
        }

    async def run_publish_workflow(
        self,
        draft_id: UUID,
        channel_account_id: UUID,
    ) -> Dict[str, Any]:
        """
        发布工作流
        Step 1: 检查Publish Ready状态
        Step 2: 渠道账号权限检查
        Step 3: 执行发布
        Step 4: 记录发布元数据
        Step 5: 触发收录检测
        """
        from app.agents.production_agent import ProductionAgent
        from app.models.brand import Brand
        from app.models.brand_fact import BrandFact
        from app.models.channel_account import ChannelAccount
        from app.models.compliance_check import ComplianceCheck

        draft_result = await self.db.execute(select(ContentDraft).where(ContentDraft.id == draft_id))
        draft = draft_result.scalar_one_or_none()
        if not draft:
            raise OrchestratorError(f"Draft {draft_id} not found")

        task_result = await self.db.execute(select(ContentTask).where(ContentTask.id == draft.task_id))
        task = task_result.scalar_one_or_none()
        if not task:
            raise OrchestratorError(f"Content task {draft.task_id} not found")

        account_result = await self.db.execute(
            select(ChannelAccount).where(ChannelAccount.id == channel_account_id)
        )
        account = account_result.scalar_one_or_none()
        if not account:
            raise OrchestratorError(f"Channel account {channel_account_id} not found")

        facts_result = await self.db.execute(
            select(BrandFact)
            .join(Brand, BrandFact.brand_id == Brand.id)
            .where(Brand.project_id == task.project_id)
        )
        brand_facts = list(facts_result.scalars().all())
        validation = ProductionAgent().validate_publish_ready(draft, brand_facts)

        self.db.add(ComplianceCheck(
            draft_id=draft.id,
            check_type="publish_ready",
            result="passed" if validation.get("can_publish") else "failed",
            issues=json.dumps(validation.get("issues", []), ensure_ascii=False),
            checked_at=datetime.now(timezone.utc),
        ))

        if validation.get("can_publish"):
            draft.status = "publish_ready"
            if task.status in {"draft", "in_progress", "review", "approved"}:
                task.status = "publish_ready"

        await self.db.commit()

        return {
            "draft_id": str(draft_id),
            "task_id": str(task.id),
            "channel_account_id": str(account.id),
            "status": "publish_ready" if validation.get("can_publish") else "blocked",
            "workflow_stage": "publish_ready" if validation.get("can_publish") else "pre_publish_blocked",
            "validation": validation,
        }

    async def run_monitoring_workflow(
        self,
        project_id: UUID,
        run_type: str = "routine",
    ) -> Dict[str, Any]:
        """
        监测工作流
        Step 1: 创建检测记录
        Step 2: 采样
        Step 3: 计算指标
        Step 4: 对比基线
        Step 5: 生成优化建议
        """
        return {
            "project_id": str(project_id),
            "status": "monitoring_started",
            "workflow_stage": "sampling_in_progress",
            "message": "监测工作流已启动",
        }

    async def transition_task_status(
        self,
        task_id: UUID,
        target_status: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        执行任务状态转换
        """
        result = await self.db.execute(select(ContentTask).where(ContentTask.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise OrchestratorError(f"Task {task_id} not found")

        current = TaskStatus(task.status)
        target = TaskStatus(target_status)

        transition_result = StateMachine.transition(current, target, context)

        if transition_result["success"]:
            task.status = target.value
            task.updated_at = datetime.now(timezone.utc)
            await self.db.commit()

        return transition_result

    async def get_project_dashboard(
        self,
        project_id: UUID,
    ) -> Dict[str, Any]:
        """
        获取项目仪表盘数据
        """
        from app.services.project_service import ProjectService

        service = ProjectService(self.db)
        project = await service.get_project(project_id)
        if not project:
            raise OrchestratorError(f"Project {project_id} not found")

        facts_summary = await service.get_brand_facts_summary(project_id)

        # 统计各状态的任务数
        task_stats = {
            "draft": 0,
            "in_progress": 0,
            "review": 0,
            "approved": 0,
            "publish_ready": 0,
            "published": 0,
            "completed": 0,
        }
        task_result = await self.db.execute(
            select(ContentTask.status).where(ContentTask.project_id == project_id)
        )
        for status in task_result.scalars().all():
            task_stats[status] = task_stats.get(status, 0) + 1

        confirmed_facts = facts_summary.get("confirmed", 0)
        total_tasks = sum(task_stats.values())
        if confirmed_facts == 0:
            workflow_stage = "facts_pending"
            next_action = "请先批量上传企业资料，并确认可公开使用的品牌事实"
        elif total_tasks == 0:
            workflow_stage = "strategy_pending"
            next_action = "请生成问题矩阵，并从问题矩阵创建内容任务"
        elif task_stats.get("published", 0) or task_stats.get("completed", 0):
            workflow_stage = "monitoring_ready"
            next_action = "请开始监测分析，观察 AI 平台对品牌的提及与推荐"
        else:
            workflow_stage = "content_in_progress"
            next_action = "请继续生成、审核并发布内容"

        return {
            "project": {
                "id": str(project.id),
                "name": project.name,
                "industry": project.industry,
                "status": project.status,
            },
            "brand_facts": facts_summary,
            "task_stats": task_stats,
            "workflow_stage": workflow_stage,
            "next_action": next_action,
        }
