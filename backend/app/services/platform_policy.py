from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional


POLICY_PATH = Path(__file__).resolve().parents[1] / "data" / "platform_policies.json"


@lru_cache(maxsize=1)
def load_platform_policies() -> Dict[str, Dict[str, Any]]:
    if not POLICY_PATH.exists():
        return {}
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def save_platform_policy(platform: str, policy: Dict[str, Any]) -> Dict[str, Any]:
    key = (platform or "").strip()
    if not key:
        raise ValueError("platform is required")
    policies = load_platform_policies().copy()
    existing = dict(policies.get(key) or {})
    existing.update(policy or {})
    existing.pop("platform", None)
    policies[key] = existing
    POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    POLICY_PATH.write_text(json.dumps(policies, ensure_ascii=False, indent=2), encoding="utf-8")
    load_platform_policies.cache_clear()
    return existing


def get_platform_policy(platform: Optional[str]) -> Dict[str, Any]:
    policies = load_platform_policies()
    key = (platform or "media").strip()
    return policies.get(key) or policies.get("other") or {
        "name": key or "其他平台",
        "style": "稳健、事实充分、弱广告",
        "length": "800-1500字",
        "format": "结论+依据+建议",
        "contact_policy": "soft_reference_only",
        "ai_label_required": True,
        "title_rules": ["题文一致", "不夸大"],
        "forbidden_patterns": [],
        "warning_patterns": [],
    }


def platform_policy_prompt_text(platform: Optional[str]) -> str:
    policy = get_platform_policy(platform)
    lines = [
        f"- 平台名称: {policy.get('name', platform or '其他平台')}",
        f"- 推荐风格: {policy.get('style', '-')}",
        f"- 字数范围: {policy.get('length', '-')}",
        f"- 推荐结构: {policy.get('format', '-')}",
        f"- 引流策略: {policy.get('contact_policy', '-')}",
        f"- AIGC标识: {'建议/需要标识' if policy.get('ai_label_required') else '不强制，但仍建议人工复核'}",
    ]
    title_rules = policy.get("title_rules") or []
    if title_rules:
        lines.append(f"- 标题规则: {'；'.join(title_rules)}")
    forbidden = policy.get("forbidden_patterns") or []
    if forbidden:
        lines.append(f"- 禁止/高危表达: {'；'.join(forbidden)}")
    warning = policy.get("warning_patterns") or []
    if warning:
        lines.append(f"- 谨慎表达: {'；'.join(warning)}")
    recommended = policy.get("recommended_content_types") or []
    if recommended:
        lines.append(f"- 适合内容: {'；'.join(recommended)}")
    return "\n".join(lines)


def check_platform_policy(text: str, platform: Optional[str]) -> List[Dict[str, Any]]:
    policy = get_platform_policy(platform)
    content = text or ""
    issues: List[Dict[str, Any]] = []
    compact_text = re.sub(r"\s+", "", content)
    word_count = len(re.findall(r"[\u4e00-\u9fff]", content))

    min_words = policy.get("min_words")
    max_words = policy.get("max_words")
    if isinstance(min_words, int) and word_count and word_count < min_words:
        issues.append({
            "type": "platform_word_count",
            "name": "平台字数建议",
            "severity": "medium",
            "platform": platform or "media",
            "message": f"{policy.get('name', platform)}建议不少于{min_words}个中文字符，当前约{word_count}个，可能影响推荐或完整度。",
        })
    if isinstance(max_words, int) and word_count > max_words:
        issues.append({
            "type": "platform_word_count",
            "name": "平台字数建议",
            "severity": "medium",
            "platform": platform or "media",
            "message": f"{policy.get('name', platform)}建议不超过{max_words}个中文字符，当前约{word_count}个，建议压缩。",
        })

    for pattern in policy.get("forbidden_patterns") or []:
        if pattern and pattern in compact_text:
            issues.append({
                "type": "platform_forbidden_pattern",
                "name": "平台禁止/高危表达",
                "severity": "high",
                "platform": platform or "media",
                "message": f"{policy.get('name', platform)}高风险表达：{pattern}",
            })

    for pattern in policy.get("warning_patterns") or []:
        if pattern and pattern in compact_text:
            issues.append({
                "type": "platform_warning_pattern",
                "name": "平台谨慎表达",
                "severity": "medium",
                "platform": platform or "media",
                "message": f"{policy.get('name', platform)}建议谨慎使用：{pattern}",
            })

    contact_policy = policy.get("contact_policy")
    if contact_policy in {"avoid_direct_contact", "soft_reference_only"}:
        direct_contact_patterns = ["二维码", "微信号", "加微信", "扫码", "QQ", "手机号"]
        if contact_policy == "avoid_direct_contact":
            direct_contact_patterns.extend(["电话", "热线"])
        found = [item for item in direct_contact_patterns if item in compact_text]
        if found:
            issues.append({
                "type": "platform_contact_policy",
                "name": "平台引流限制",
                "severity": "high" if contact_policy == "avoid_direct_contact" else "medium",
                "platform": platform or "media",
                "message": f"{policy.get('name', platform)}对直接引流较敏感，建议移除或弱化：{', '.join(found[:6])}",
            })

    if policy.get("ai_label_required") and "AI生成" not in content and "AI辅助" not in content:
        issues.append({
            "type": "ai_label_suggestion",
            "name": "AIGC标识建议",
            "severity": "low",
            "platform": platform or "media",
            "message": f"{policy.get('name', platform)}发布含AI辅助生成内容时，建议按平台要求添加“AI生成/AI辅助生成并经人工审核”标识。",
        })

    return issues
