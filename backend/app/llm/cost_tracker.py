"""
LLM调用成本追踪器
记录每次API调用的token消耗和成本
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID


@dataclass
class LLMCallRecord:
    """LLM调用记录"""
    id: str
    project_id: Optional[UUID]
    agent_name: str              # 哪个Agent调用的
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    cost_cny: float
    latency_ms: float
    prompt_name: Optional[str]   # 使用的Prompt模板名称
    status: str                  # success / error
    error_message: Optional[str]
    created_at: datetime


class CostTracker:
    """
    成本追踪器
    用于统计各Agent、各项目的LLM调用成本
    """

    def __init__(self):
        self._records: List[LLMCallRecord] = []
        self._daily_budget_limit: float = 100.0  # 默认日预算100美元

    def record(
        self,
        project_id: Optional[UUID],
        agent_name: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        cost_cny: float,
        latency_ms: float,
        prompt_name: Optional[str] = None,
        status: str = "success",
        error_message: Optional[str] = None,
    ) -> LLMCallRecord:
        """记录一次LLM调用"""
        record = LLMCallRecord(
            id=f"{datetime.now(timezone.utc).timestamp():.6f}",
            project_id=project_id,
            agent_name=agent_name,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost_usd=cost_usd,
            cost_cny=cost_cny,
            latency_ms=latency_ms,
            prompt_name=prompt_name,
            status=status,
            error_message=error_message,
            created_at=datetime.now(timezone.utc),
        )
        self._records.append(record)
        return record

    def get_summary(
        self,
        project_id: Optional[UUID] = None,
        agent_name: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取成本汇总"""
        filtered = self._records
        if project_id:
            filtered = [r for r in filtered if r.project_id == project_id]
        if agent_name:
            filtered = [r for r in filtered if r.agent_name == agent_name]
        if provider:
            filtered = [r for r in filtered if r.provider == provider]

        total_calls = len(filtered)
        total_tokens = sum(r.total_tokens for r in filtered)
        total_input = sum(r.input_tokens for r in filtered)
        total_output = sum(r.output_tokens for r in filtered)
        total_usd = sum(r.cost_usd for r in filtered)
        total_cny = sum(r.cost_cny for r in filtered)
        avg_latency = sum(r.latency_ms for r in filtered) / total_calls if total_calls > 0 else 0
        error_count = sum(1 for r in filtered if r.status == "error")

        return {
            "total_calls": total_calls,
            "total_tokens": total_tokens,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cost_usd": round(total_usd, 4),
            "total_cost_cny": round(total_cny, 4),
            "average_latency_ms": round(avg_latency, 2),
            "error_count": error_count,
            "success_rate": round((total_calls - error_count) / total_calls * 100, 1) if total_calls > 0 else 0,
        }

    def get_daily_cost(self, date: Optional[datetime] = None) -> Dict[str, float]:
        """获取某日的成本（默认今天）"""
        if date is None:
            date = datetime.now(timezone.utc)
        date_str = date.strftime("%Y-%m-%d")

        daily_records = [
            r for r in self._records
            if r.created_at.strftime("%Y-%m-%d") == date_str
        ]

        return {
            "usd": round(sum(r.cost_usd for r in daily_records), 4),
            "cny": round(sum(r.cost_cny for r in daily_records), 4),
            "calls": len(daily_records),
            "tokens": sum(r.total_tokens for r in daily_records),
        }

    def get_by_agent(self) -> Dict[str, Dict[str, Any]]:
        """按Agent统计成本"""
        agents = {}
        for r in self._records:
            if r.agent_name not in agents:
                agents[r.agent_name] = {
                    "calls": 0, "tokens": 0, "usd": 0.0, "cny": 0.0
                }
            agents[r.agent_name]["calls"] += 1
            agents[r.agent_name]["tokens"] += r.total_tokens
            agents[r.agent_name]["usd"] += r.cost_usd
            agents[r.agent_name]["cny"] += r.cost_cny

        # 四舍五入
        for name in agents:
            agents[name]["usd"] = round(agents[name]["usd"], 4)
            agents[name]["cny"] = round(agents[name]["cny"], 4)

        return agents

    def get_by_provider(self) -> Dict[str, Dict[str, Any]]:
        """按提供商统计成本"""
        providers = {}
        for r in self._records:
            if r.provider not in providers:
                providers[r.provider] = {
                    "calls": 0, "tokens": 0, "usd": 0.0, "cny": 0.0
                }
            providers[r.provider]["calls"] += 1
            providers[r.provider]["tokens"] += r.total_tokens
            providers[r.provider]["usd"] += r.cost_usd
            providers[r.provider]["cny"] += r.cost_cny

        for name in providers:
            providers[name]["usd"] = round(providers[name]["usd"], 4)
            providers[name]["cny"] = round(providers[name]["cny"], 4)

        return providers

    def check_budget_alert(self) -> Optional[str]:
        """检查预算预警"""
        daily = self.get_daily_cost()
        if daily["usd"] >= self._daily_budget_limit:
            return f"日预算已超支: ${daily['usd']} / ${self._daily_budget_limit}"
        elif daily["usd"] >= self._daily_budget_limit * 0.8:
            return f"日预算即将超支: ${daily['usd']} / ${self._daily_budget_limit} (80%)"
        return None

    def set_daily_budget(self, limit_usd: float):
        """设置日预算上限"""
        self._daily_budget_limit = limit_usd


# 全局追踪器实例
_cost_tracker_instance: Optional[CostTracker] = None


def get_cost_tracker() -> CostTracker:
    """获取全局成本追踪器（单例）"""
    global _cost_tracker_instance
    if _cost_tracker_instance is None:
        _cost_tracker_instance = CostTracker()
    return _cost_tracker_instance
