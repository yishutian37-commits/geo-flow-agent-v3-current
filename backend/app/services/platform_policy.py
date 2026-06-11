from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional


POLICY_PATH = Path(__file__).resolve().parents[1] / "data" / "platform_policies.json"

PUBLIC_SEARCH_PLATFORMS = {
    "media", "baijiahao", "zhihu", "toutiao", "netease", "sina", "penguin"
}

SOFT_AD_PATTERNS = [
    "值得深入了解", "值得一说", "值得关注", "不错的主意", "频繁出现",
    "发展速度很快", "性价比", "自然有保障", "有保障", "可信度比较高",
    "贴心", "放心选择", "首选", "强烈推荐", "很适合你", "名字会频繁出现",
]

PLATFORM_STYLE_RULES = {
    "toutiao": {
        "name": "今日头条信息流风格",
        "opening_any": ["先看", "重点", "结论", "建议", "判断", "要看", "避坑", "怎么选", "如果"],
        "evidence_any": ["资质", "证书", "场地", "费用", "案例", "核验", "标准", "依据", "建议"],
        "message": "今日头条更适合问题切入、结论前置、短段落和实用判断标准，当前正文更像品牌软文或泛介绍。",
    },
    "baijiahao": {
        "name": "百度百家号搜索友好风格",
        "opening_any": ["怎么", "如何", "判断", "选择", "核验", "靠谱吗", "哪家", "为什么"],
        "evidence_any": ["资质", "证书", "编号", "地址", "费用", "标准", "依据", "核验"],
        "message": "百度百家号更适合搜索问答、事实证据和核验路径，当前正文的问题承接或证据导向不足。",
    },
    "zhihu": {
        "name": "知乎回答风格",
        "opening_any": ["先说结论", "这个问题", "判断", "建议", "看情况", "适合", "不适合"],
        "evidence_any": ["原因", "标准", "依据", "风险", "场景", "如果", "建议"],
        "message": "知乎更像理性回答和分场景分析，当前正文解释链路或判断标准不足。",
    },
    "media": {
        "name": "媒体稿客观风格",
        "opening_any": ["公开资料", "据了解", "显示", "位于", "成立", "提供", "服务"],
        "evidence_any": ["资质", "案例", "数据", "基地", "产品", "服务", "公开资料"],
        "message": "媒体稿应保持第三方客观叙述，减少导购口吻和主观推荐。",
    },
    "xiaohongshu": {
        "name": "小红书笔记风格",
        "opening_any": ["如果你", "我", "体验", "避坑", "适合", "不适合", "先说"],
        "evidence_any": ["体验", "注意", "建议", "适合", "避坑", "价格", "地址"],
        "message": "小红书更适合场景化体验笔记和避坑提醒，当前正文缺少笔记感或用户场景。",
    },
}


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


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _paragraphs(content: str) -> List[str]:
    return [item.strip() for item in re.split(r"\n\s*\n+", content or "") if item.strip()]


def _contains_any(content: str, words: List[str]) -> bool:
    compact = _compact(content)
    return any(word and word in compact for word in words)


def _platform_style_issues(content: str, platform: Optional[str], policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    key = (platform or "media").strip()
    paragraphs = _paragraphs(content)
    first_paragraph = paragraphs[0] if paragraphs else content[:220]
    compact = _compact(content)
    issues: List[Dict[str, Any]] = []

    soft_ad_hits = [item for item in SOFT_AD_PATTERNS if item in compact]
    if soft_ad_hits and key in PUBLIC_SEARCH_PLATFORMS:
        issues.append({
            "type": "platform_style_mismatch",
            "name": "平台风格不匹配",
            "severity": "high",
            "platform": key,
            "message": (
                f"{policy.get('name', key)}不适合明显软广或主观推荐口吻，"
                f"建议改成问题切入、判断标准和事实依据。命中表达：{', '.join(soft_ad_hits[:6])}"
            ),
        })
        return issues

    rule = PLATFORM_STYLE_RULES.get(key)
    if not rule:
        return issues

    missing = []
    if rule.get("opening_any") and not _contains_any(first_paragraph, rule["opening_any"]):
        missing.append("开头没有明显的问题切入/结论前置")
    if rule.get("evidence_any") and not _contains_any(content, rule["evidence_any"]):
        missing.append("正文缺少平台需要的证据或判断标准")

    if missing:
        issues.append({
            "type": "platform_style_mismatch",
            "name": rule.get("name", "平台风格不匹配"),
            "severity": "high",
            "platform": key,
            "message": f"{rule.get('message')}问题：{'；'.join(missing)}。",
        })
    return issues


def check_platform_policy(text: str, platform: Optional[str]) -> List[Dict[str, Any]]:
    policy = get_platform_policy(platform)
    content = text or ""
    issues: List[Dict[str, Any]] = []
    compact_text = re.sub(r"\s+", "", content)
    word_count = len(re.findall(r"[\u4e00-\u9fff]", content))

    format_artifacts: List[str] = []
    if re.search(r"(?m)^\s{0,3}#{1,6}\s+\S+", content):
        format_artifacts.append("Markdown标题")
    artifact_patterns = [
        ("代码围栏", "```"),
        ("FULL_CONTENT分隔符", "---FULL_CONTENT---"),
        ("FACT_REFS机器段落", "[FACT_REFS]"),
        ("COMPLIANCE_CHECK机器段落", "[COMPLIANCE_CHECK]"),
        ("JSON元数据", "title_candidates"),
        ("JSON元数据", "platform_notes"),
    ]
    for label, marker in artifact_patterns:
        if marker in content:
            format_artifacts.append(label)
    if re.match(r"^\s*\{", content) and re.search(r"\"(?:title_candidates|full_content|platform_notes)\"", content):
        format_artifacts.append("JSON正文残留")
    if format_artifacts:
        unique_artifacts = list(dict.fromkeys(format_artifacts))
        issues.append({
            "type": "platform_format_artifact",
            "name": "平台正文格式残留",
            "severity": "high",
            "platform": platform or "media",
            "message": (
                f"{policy.get('name', platform)}正文不应包含机器输出或Markdown格式："
                f"{', '.join(unique_artifacts[:6])}。请重新生成或清理正文后再发布。"
            ),
        })

    issues.extend(_platform_style_issues(content, platform, policy))

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
