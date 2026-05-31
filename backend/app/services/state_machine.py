"""
通用状态机引擎
支持 Draft → In Progress → Review → Approved → Client Review → Publish Ready → Published → Indexed → Monitoring → Completed
以及 Blocked / Cancelled 分支
"""
from enum import Enum
from typing import Dict, List, Optional, Callable, Set
from datetime import datetime, timezone


class TaskStatus(str, Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    REWORK = "rework"
    APPROVED = "approved"
    CLIENT_REVIEW = "client_review"
    PUBLISH_READY = "publish_ready"
    PUBLISHED = "published"
    INDEXED = "indexed"
    MONITORING = "monitoring"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class BlockReason(str, Enum):
    FACT_UNCONFIRMED = "fact_unconfirmed"
    FACT_SCOPE_RESTRICTED = "fact_scope_restricted"
    EXPIRED_CREDENTIAL = "expired_credential"
    COMPLIANCE_HIGH_RISK = "compliance_high_risk"
    INSUFFICIENT_SAMPLE = "insufficient_sample"
    CHANNEL_UNAVAILABLE = "channel_unavailable"
    CLIENT_DISPUTE = "client_dispute"
    NO_PERMISSION = "no_permission"


# 状态流转图：当前状态 → 允许的目标状态
STATE_TRANSITIONS: Dict[TaskStatus, Set[TaskStatus]] = {
    TaskStatus.DRAFT: {
        TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED
    },
    TaskStatus.IN_PROGRESS: {
        TaskStatus.REVIEW, TaskStatus.BLOCKED, TaskStatus.CANCELLED
    },
    TaskStatus.REVIEW: {
        TaskStatus.APPROVED, TaskStatus.REWORK, TaskStatus.BLOCKED
    },
    TaskStatus.REWORK: {
        TaskStatus.IN_PROGRESS, TaskStatus.REVIEW
    },
    TaskStatus.APPROVED: {
        TaskStatus.CLIENT_REVIEW, TaskStatus.PUBLISH_READY
    },
    TaskStatus.CLIENT_REVIEW: {
        TaskStatus.PUBLISH_READY, TaskStatus.REWORK, TaskStatus.BLOCKED
    },
    TaskStatus.PUBLISH_READY: {
        TaskStatus.PUBLISHED, TaskStatus.CANCELLED
    },
    TaskStatus.PUBLISHED: {
        TaskStatus.INDEXED, TaskStatus.MONITORING
    },
    TaskStatus.INDEXED: {
        TaskStatus.MONITORING
    },
    TaskStatus.MONITORING: {
        TaskStatus.COMPLETED, TaskStatus.REWORK
    },
    TaskStatus.COMPLETED: {
        # 已完成，只能重新打开
    },
    TaskStatus.BLOCKED: {
        TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED
    },
    TaskStatus.CANCELLED: {
        # 已取消，不可恢复
    },
}

# 阻塞规则：检查条件 → 阻塞原因
BLOCK_RULES: Dict[BlockReason, Callable[..., bool]] = {
    BlockReason.FACT_UNCONFIRMED: lambda ctx: ctx.get("has_unconfirmed_facts", False),
    BlockReason.FACT_SCOPE_RESTRICTED: lambda ctx: ctx.get("has_restricted_facts", False),
    BlockReason.EXPIRED_CREDENTIAL: lambda ctx: ctx.get("has_expired_credentials", False),
    BlockReason.COMPLIANCE_HIGH_RISK: lambda ctx: ctx.get("compliance_risk_level") == "high",
    BlockReason.INSUFFICIENT_SAMPLE: lambda ctx: ctx.get("sample_sufficient", True) is False,
    BlockReason.CHANNEL_UNAVAILABLE: lambda ctx: ctx.get("channel_available", True) is False,
    BlockReason.CLIENT_DISPUTE: lambda ctx: ctx.get("client_disputed", False),
    BlockReason.NO_PERMISSION: lambda ctx: ctx.get("has_publish_permission", True) is False,
}


class StateMachineError(Exception):
    pass


class StateMachine:
    """通用状态机"""

    @staticmethod
    def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
        """检查状态转换是否合法"""
        if current not in STATE_TRANSITIONS:
            return False
        return target in STATE_TRANSITIONS[current]

    @staticmethod
    def get_allowed_transitions(current: TaskStatus) -> List[TaskStatus]:
        """获取当前状态允许的所有转换目标"""
        return list(STATE_TRANSITIONS.get(current, set()))

    @staticmethod
    def validate_transition(current: TaskStatus, target: TaskStatus) -> None:
        """验证状态转换，不合法则抛出异常"""
        if not StateMachine.can_transition(current, target):
            raise StateMachineError(
                f"Invalid transition from '{current.value}' to '{target.value}'. "
                f"Allowed: {[s.value for s in StateMachine.get_allowed_transitions(current)]}"
            )

    @staticmethod
    def check_block_rules(context: dict) -> List[BlockReason]:
        """检查所有阻塞规则，返回触发的阻塞原因列表"""
        triggered: List[BlockReason] = []
        for reason, checker in BLOCK_RULES.items():
            try:
                if checker(context):
                    triggered.append(reason)
            except Exception:
                # 如果某个规则检查失败，不阻塞，记录日志即可
                pass
        return triggered

    @staticmethod
    def transition(
        current: TaskStatus,
        target: TaskStatus,
        context: Optional[dict] = None,
        skip_block_check: bool = False
    ) -> dict:
        """
        执行状态转换
        返回: {"success": bool, "new_status": str, "blocked_reasons": List[str], "timestamp": datetime}
        """
        context = context or {}

        # 1. 验证转换合法性
        StateMachine.validate_transition(current, target)

        # 2. 检查阻塞规则（除非是向 Cancelled 转换，或显式跳过）
        blocked_reasons: List[BlockReason] = []
        if not skip_block_check and target != TaskStatus.CANCELLED:
            blocked_reasons = StateMachine.check_block_rules(context)
            if blocked_reasons:
                return {
                    "success": False,
                    "new_status": current.value,
                    "blocked_reasons": [r.value for r in blocked_reasons],
                    "timestamp": datetime.now(timezone.utc),
                    "message": f"Transition blocked by: {[r.value for r in blocked_reasons]}"
                }

        # 3. 执行转换
        return {
            "success": True,
            "new_status": target.value,
            "blocked_reasons": [],
            "timestamp": datetime.now(timezone.utc),
            "message": f"Transitioned from {current.value} to {target.value}"
        }


# 快捷状态判断
class StatusHelper:
    @staticmethod
    def is_terminal(status: TaskStatus) -> bool:
        return status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}

    @staticmethod
    def is_active(status: TaskStatus) -> bool:
        return status not in {TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.BLOCKED}

    @staticmethod
    def requires_approval(status: TaskStatus) -> bool:
        return status in {TaskStatus.REVIEW, TaskStatus.CLIENT_REVIEW}

    @staticmethod
    def can_publish(status: TaskStatus) -> bool:
        return status == TaskStatus.PUBLISH_READY
