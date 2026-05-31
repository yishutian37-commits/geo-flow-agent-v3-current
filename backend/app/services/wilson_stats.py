"""
Wilson 置信区间计算模块
PRD V2.3 核心统计指标
"""
from dataclasses import dataclass
from typing import Optional, Tuple
import math


@dataclass
class ConfidenceInterval:
    """Wilson 置信区间结果"""
    center: float           # Wilson 中心（修正后的点估计）
    lower: float            # 置信区间下限
    upper: float            # 置信区间上限
    half_width: float       # 区间半宽
    point_estimate: float   # 原始点估计值 p = x/n
    n: int                  # 样本量
    x: int                  # 成功次数
    confidence: float       # 置信水平（默认0.95）


def proportion_confidence_interval(
    x: int,
    n: int,
    confidence: float = 0.95
) -> ConfidenceInterval:
    """
    计算 Wilson 置信区间

    Args:
        x: 成功次数（如品牌被提及的样本数）
        n: 总样本数
        confidence: 置信水平，默认0.95

    Returns:
        ConfidenceInterval 对象

    Raises:
        ValueError: 当 n <= 0 或 x < 0 或 x > n 时
    """
    if n <= 0:
        raise ValueError("Sample size n must be positive")
    if x < 0 or x > n:
        raise ValueError("Success count x must be in [0, n]")

    # Z值对应置信水平
    z_map = {
        0.90: 1.645,
        0.95: 1.96,
        0.99: 2.576,
    }
    z = z_map.get(confidence, 1.96)

    p = x / n
    z2 = z * z
    z2_n = z2 / n

    # Wilson 中心
    center = (p + z2 / (2 * n)) / (1 + z2_n)

    # Wilson 半宽
    half_width = z * math.sqrt(
        (p * (1 - p) / n) + (z2 / (4 * n * n))
    ) / (1 + z2_n)

    lower = max(0.0, center - half_width)
    upper = min(1.0, center + half_width)

    return ConfidenceInterval(
        center=center,
        lower=lower,
        upper=upper,
        half_width=half_width,
        point_estimate=p,
        n=n,
        x=x,
        confidence=confidence,
    )


def calculate_brand_mention_rate(
    mentioned_count: int,
    total_samples: int,
    confidence: float = 0.95
) -> ConfidenceInterval:
    """计算品牌提及率及其Wilson置信区间"""
    return proportion_confidence_interval(mentioned_count, total_samples, confidence)


def calculate_recommendation_rate(
    recommended_count: int,
    total_samples: int,
    confidence: float = 0.95
) -> ConfidenceInterval:
    """计算推荐率及其Wilson置信区间"""
    return proportion_confidence_interval(recommended_count, total_samples, confidence)


def calculate_negative_mention_rate(
    negative_count: int,
    total_samples: int,
    confidence: float = 0.95
) -> ConfidenceInterval:
    """计算负面出现率及其Wilson置信区间"""
    return proportion_confidence_interval(negative_count, total_samples, confidence)


def calculate_visibility_score(
    position: Optional[int],
    list_length: Optional[int]
) -> Optional[float]:
    """
    计算 Visibility Score（归一化可见性分数）

    公式:
    - 品牌排名为 r，候选列表长度为 L: VS = (L - r + 1) / L
    - 品牌未出现: VS = 0
    - 无可识别候选: 返回 None（不计入）

    Args:
        position: 品牌排名（1-based），None表示未出现
        list_length: 候选列表长度

    Returns:
        0.0 ~ 1.0 之间的分数，或 None
    """
    if position is None:
        return 0.0
    if list_length is None or list_length <= 0:
        return None
    if position < 1 or position > list_length:
        return 0.0
    return (list_length - position + 1) / list_length


def calculate_position_score(
    position: Optional[int],
    list_length: Optional[int],
    answer_type: str = "list"
) -> Optional[float]:
    """
    计算 Position Score（平均位置分）

    Args:
        position: 品牌位置
        list_length: 列表长度
        answer_type: "list" | "prose" | "no_candidate"
    """
    if answer_type == "no_candidate":
        return None
    if position is None:
        # 未出现：罚分 = list_length + 3（若已知）
        if list_length and list_length > 0:
            return float(list_length + 3)
        return 30.0  # 默认值
    return float(position)


def determine_confidence_level(
    n: int,
    wilson_half_width: float,
    time_window_days: int,
    mechanism_type: str = "B"
) -> str:
    """
    确定置信等级（高 / 中 / 低）

    PRD规则：取三个维度中的最低档
    - 样本量 N: >=20=高, 10~19=中, <10=低
    - Wilson半宽: <=10%=高, 10~20%=中, >20%=低
    - 时间窗口: 同日=高, 3日内=中, 超过3日=低
    - 非联网生成型(A类): 单期置信等级上限为"中"

    Returns:
        "high" | "medium" | "low"
    """
    # 样本量维度
    if n >= 20:
        sample_level = "high"
    elif n >= 10:
        sample_level = "medium"
    else:
        sample_level = "low"

    # Wilson半宽维度（半宽是百分比，传入时应该是小数如0.15表示15%）
    hw_percent = wilson_half_width * 100 if wilson_half_width <= 1 else wilson_half_width
    if hw_percent <= 10:
        wilson_level = "high"
    elif hw_percent <= 20:
        wilson_level = "medium"
    else:
        wilson_level = "low"

    # 时间窗口维度
    if time_window_days < 1:
        time_level = "high"
    elif time_window_days <= 3:
        time_level = "medium"
    else:
        time_level = "low"

    # 取最低档
    levels = [sample_level, wilson_level, time_level]
    if "low" in levels:
        result = "low"
    elif "medium" in levels:
        result = "medium"
    else:
        result = "high"

    # A类机制上限为"中"
    if mechanism_type == "A" and result == "high":
        result = "medium"

    return result


def format_ci_report(ci: ConfidenceInterval) -> dict:
    """将置信区间格式化为报告友好的字典"""
    return {
        "point_estimate": round(ci.point_estimate * 100, 2),  # 百分比
        "center": round(ci.center * 100, 2),
        "lower": round(ci.lower * 100, 2),
        "upper": round(ci.upper * 100, 2),
        "half_width": round(ci.half_width * 100, 2),
        "n": ci.n,
        "x": ci.x,
        "confidence": f"{int(ci.confidence * 100)}%",
    }
