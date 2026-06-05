from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


ARCHETYPE_PATH = Path(__file__).resolve().parents[1] / "data" / "question_archetypes.json"


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


@lru_cache(maxsize=1)
def load_question_archetypes() -> Dict[str, Any]:
    with ARCHETYPE_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError("question_archetypes.json must contain an object")
    return data


def get_ai_platform_terms() -> List[str]:
    data = load_question_archetypes()
    terms = data.get("ai_platform_terms") or []
    return [str(term) for term in terms if str(term).strip()]


def get_question_archetype(industry: Optional[str]) -> Dict[str, Any]:
    data = load_question_archetypes()
    default = data.get("default") or {}
    industries = data.get("industries") or {}
    key = industry or ""
    raw = industries.get(key) or {}
    if raw.get("extends"):
        parent = get_question_archetype(raw.get("extends"))
        child = {field: value for field, value in raw.items() if field != "extends"}
        resolved = _deep_merge(parent, child)
        resolved["extends"] = raw.get("extends")
        return resolved
    return _deep_merge(default, raw)


def get_service_patterns(industry: Optional[str] = None) -> List[Dict[str, str]]:
    data = load_question_archetypes()
    patterns = list(data.get("service_patterns") or [])
    archetype = get_question_archetype(industry)
    patterns = list(archetype.get("service_patterns") or []) + patterns
    return [
        {"label": str(item.get("label") or "").strip(), "pattern": str(item.get("pattern") or "").strip()}
        for item in patterns
        if item.get("label") and item.get("pattern")
    ]


def normalize_brand_short_name(brand_name: str) -> str:
    return re.sub(
        r"(有限责任公司|有限公司|科技发展|科技|公司|集团|（.*?）|\(.*?\))",
        "",
        brand_name or "",
    ).strip()


def infer_service_from_archetype(
    industry: Optional[str],
    text: str,
    brand_name: str,
    industry_label: str = "通用行业",
) -> str:
    for item in get_service_patterns(industry):
        if re.search(item["pattern"], text or "", flags=re.I):
            return item["label"]

    archetype = get_question_archetype(industry)
    if archetype.get("fallback_service"):
        return str(archetype["fallback_service"])

    name = normalize_brand_short_name(brand_name)
    suffix = str(archetype.get("fallback_service_suffix") or "服务")
    return f"{name or industry_label}{suffix}"


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _format_copy(copy: Dict[str, Any], variables: Dict[str, Any]) -> Dict[str, str]:
    formatted: Dict[str, str] = {}
    safe_vars = _SafeFormatDict({key: str(value or "") for key, value in variables.items()})
    for key, value in (copy or {}).items():
        text = str(value or "")
        formatted[key] = text.format_map(safe_vars)
    return formatted


def service_subject(service: str, entity_label: str) -> str:
    service = service or "服务"
    if re.search(r"(机构|门店|供应商|服务商|品牌|厂家|公司)$", service):
        return service
    return f"{service}{entity_label}"


def get_industry_question_copy(
    industry: Optional[str],
    service: str,
    region: Optional[str] = None,
) -> Dict[str, str]:
    archetype = get_question_archetype(industry)
    entity_label = str(archetype.get("entity_label") or "服务商")
    subject = service_subject(service, entity_label)
    copy = _format_copy(
        archetype.get("copy") or {},
        {
            "service": service,
            "entity_label": entity_label,
            "subject": subject,
            "region": region or "本地",
        },
    )
    copy["entity_label"] = entity_label
    copy["subject"] = subject
    copy.setdefault("trust_subject", subject)
    return copy


def get_industry_forbidden_terms(industry: Optional[str]) -> List[str]:
    terms = get_question_archetype(industry).get("forbidden_terms") or []
    return [str(term) for term in terms if str(term).strip()]


def list_question_archetype_summaries() -> List[Dict[str, Any]]:
    data = load_question_archetypes()
    industries = data.get("industries") or {}
    summaries = []
    for industry in sorted(industries.keys()):
        raw = industries.get(industry) or {}
        resolved = get_question_archetype(industry)
        summaries.append({
            "industry": industry,
            "extends": raw.get("extends"),
            "entity_label": resolved.get("entity_label"),
            "fallback_service": resolved.get("fallback_service"),
            "fallback_service_suffix": resolved.get("fallback_service_suffix"),
            "forbidden_terms": resolved.get("forbidden_terms") or [],
            "positive_examples": resolved.get("positive_examples") or [],
            "negative_examples": resolved.get("negative_examples") or [],
            "copy": resolved.get("copy") or {},
            "raw": raw,
        })
    return summaries


def save_question_archetype(industry: str, archetype: Dict[str, Any]) -> Dict[str, Any]:
    key = (industry or "").strip()
    if not key:
        raise ValueError("industry is required")
    data = deepcopy(load_question_archetypes())
    industries = data.setdefault("industries", {})
    existing = industries.get(key) or {}
    merged = _deep_merge(existing, archetype or {})
    industries[key] = merged
    with ARCHETYPE_PATH.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
    load_question_archetypes.cache_clear()
    return get_question_archetype(key)
