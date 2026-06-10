"""
主控编排器
协调五大核心Agent的工作流程，驱动GEO全流程闭环
"""
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime, timezone
import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.brand_fact import BrandFact
from app.models.corpus_item import CorpusItem
from app.models.project import Project
from app.models.content_task import ContentTask
from app.models.content_draft import ContentDraft
from app.models.model_target import ModelTarget
from app.models.monitoring import MonitoringRun, MonitoringSample
from app.models.question import Question, QuestionGroup
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

    async def _get_project_or_raise(self, project_id: UUID) -> Project:
        result = await self.db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            raise OrchestratorError(f"Project {project_id} not found")
        return project

    async def _count(self, statement) -> int:
        result = await self.db.execute(statement)
        return int(result.scalar() or 0)

    async def _project_readiness_counts(self, project_id: UUID) -> Dict[str, int]:
        return {
            "brands": await self._count(
                select(func.count(Brand.id)).where(Brand.project_id == project_id)
            ),
            "corpus_items": await self._count(
                select(func.count(CorpusItem.id)).where(CorpusItem.project_id == project_id)
            ),
            "confirmed_public_facts": await self._count(
                select(func.count(BrandFact.id))
                .join(Brand, BrandFact.brand_id == Brand.id)
                .where(
                    Brand.project_id == project_id,
                    BrandFact.status == "confirmed",
                    BrandFact.fact_scope == "public",
                )
            ),
            "question_groups": await self._count(
                select(func.count(QuestionGroup.id)).where(QuestionGroup.project_id == project_id)
            ),
            "enabled_questions": await self._count(
                select(func.count(Question.id))
                .join(QuestionGroup, Question.group_id == QuestionGroup.id)
                .where(QuestionGroup.project_id == project_id, Question.enabled.is_(True))
            ),
            "model_targets": await self._count(
                select(func.count(ModelTarget.id)).where(ModelTarget.project_id == project_id)
            ),
        }

    def _readiness_blockers(self, counts: Dict[str, int]) -> List[Dict[str, str]]:
        blockers: List[Dict[str, str]] = []
        if counts["corpus_items"] == 0 and counts["confirmed_public_facts"] == 0:
            blockers.append(
                {
                    "code": "missing_brand_materials",
                    "message": "缺少可用于诊断的企业资料或已确认公开品牌事实",
                    "next_step": "先在项目知识库上传企业资料，或在品牌事实库确认可公开使用的基础事实",
                }
            )
        if counts["enabled_questions"] == 0:
            blockers.append(
                {
                    "code": "missing_question_matrix",
                    "message": "缺少启用中的问题矩阵",
                    "next_step": "先生成问题矩阵，并保留至少一条启用的问题",
                }
            )
        if counts["model_targets"] == 0:
            blockers.append(
                {
                    "code": "missing_model_targets",
                    "message": "缺少检测平台配置",
                    "next_step": "先在监测分析中添加至少一个 AI 检测平台",
                }
            )
        return blockers

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
        project = await self._get_project_or_raise(project_id)
        counts = await self._project_readiness_counts(project.id)
        blockers = self._readiness_blockers(counts)

        if blockers:
            if counts["confirmed_public_facts"] == 0 and counts["corpus_items"] == 0:
                workflow_stage = "facts_pending"
            elif counts["enabled_questions"] == 0:
                workflow_stage = "question_matrix_pending"
            else:
                workflow_stage = "platform_pending"

            return {
                "project_id": str(project.id),
                "status": "blocked",
                "workflow_stage": workflow_stage,
                "counts": counts,
                "blockers": blockers,
                "next_steps": [item["next_step"] for item in blockers],
            }

        return {
            "project_id": str(project.id),
            "status": "diagnosis_ready",
            "workflow_stage": "diagnosis_ready",
            "counts": counts,
            "blockers": [],
            "next_steps": [
                "可以开始执行品牌AI体检",
                "体检完成后进入问题矩阵复核和基线监测",
            ],
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
        task_result = await self.db.execute(select(ContentTask).where(ContentTask.id == task_id))
        task = task_result.scalar_one_or_none()
        if not task:
            raise OrchestratorError(f"Content task {task_id} not found")

        confirmed_public_facts = await self._count(
            select(func.count(BrandFact.id))
            .join(Brand, BrandFact.brand_id == Brand.id)
            .where(
                Brand.project_id == task.project_id,
                BrandFact.status == "confirmed",
                BrandFact.fact_scope == "public",
            )
        )
        draft_count = await self._count(
            select(func.count(ContentDraft.id)).where(ContentDraft.task_id == task.id)
        )
        counts = {
            "confirmed_public_facts": confirmed_public_facts,
            "drafts": draft_count,
            "knowledge_assets_bound": 1 if task.knowledge_asset_ids else 0,
        }

        if confirmed_public_facts == 0:
            blocker = {
                "code": "missing_confirmed_public_facts",
                "message": "当前项目没有可公开使用的已确认品牌事实，不能进入可靠稿件生产",
                "next_step": "先在品牌事实库确认资质、产品、地址、案例等基础事实",
            }
            return {
                "task_id": str(task.id),
                "project_id": str(task.project_id),
                "status": "blocked",
                "workflow_stage": "facts_pending",
                "counts": counts,
                "blockers": [blocker],
                "next_steps": [blocker["next_step"]],
            }

        status = "draft_ready_for_review" if draft_count else "production_ready"
        workflow_stage = "draft_review_pending" if draft_count else "draft_generation_ready"
        return {
            "task_id": str(task.id),
            "project_id": str(task.project_id),
            "status": status,
            "workflow_stage": workflow_stage,
            "counts": counts,
            "blockers": [],
            "next_steps": [
                "可以基于已确认事实生成平台草稿" if not draft_count else "请审核已有草稿并执行发布检查",
            ],
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
        project = await self._get_project_or_raise(project_id)
        counts = await self._project_readiness_counts(project.id)
        counts.update(
            {
                "monitoring_runs": await self._count(
                    select(func.count(MonitoringRun.id)).where(MonitoringRun.project_id == project.id)
                ),
                "completed_monitoring_runs": await self._count(
                    select(func.count(MonitoringRun.id)).where(
                        MonitoringRun.project_id == project.id,
                        MonitoringRun.status == "completed",
                    )
                ),
                "monitoring_samples": await self._count(
                    select(func.count(MonitoringSample.id))
                    .join(MonitoringRun, MonitoringSample.run_id == MonitoringRun.id)
                    .where(MonitoringRun.project_id == project.id)
                ),
            }
        )
        blockers = [
            item
            for item in self._readiness_blockers(counts)
            if item["code"] in {"missing_question_matrix", "missing_model_targets"}
        ]

        if blockers:
            return {
                "project_id": str(project.id),
                "status": "blocked",
                "workflow_stage": "monitoring_preflight_blocked",
                "run_type": run_type,
                "counts": counts,
                "blockers": blockers,
                "next_steps": [item["next_step"] for item in blockers],
            }

        return {
            "project_id": str(project.id),
            "status": "monitoring_ready",
            "workflow_stage": "sampling_ready",
            "run_type": run_type,
            "counts": counts,
            "blockers": [],
            "next_steps": [
                "可以选择问题和检测平台后开始自动检测",
                "检测完成后进入来源分析、推荐率分析和内容优化建议",
            ],
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
