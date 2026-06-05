from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException

from app.services.platform_policy import (
    check_platform_policy,
    get_platform_policy,
    load_platform_policies,
    platform_policy_prompt_text,
    save_platform_policy,
)

router = APIRouter()


def _policy_to_dict(platform: str, policy: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "platform": platform,
        "name": policy.get("name") or platform,
        "style": policy.get("style"),
        "length": policy.get("length"),
        "min_words": policy.get("min_words"),
        "max_words": policy.get("max_words"),
        "format": policy.get("format"),
        "contact_policy": policy.get("contact_policy"),
        "ai_label_required": bool(policy.get("ai_label_required")),
        "title_rules": policy.get("title_rules") or [],
        "forbidden_patterns": policy.get("forbidden_patterns") or [],
        "warning_patterns": policy.get("warning_patterns") or [],
        "recommended_content_types": policy.get("recommended_content_types") or [],
        "prompt_text": platform_policy_prompt_text(platform),
    }


@router.get("")
async def list_platform_policies():
    policies = load_platform_policies()
    return [
        _policy_to_dict(platform, policy)
        for platform, policy in policies.items()
    ]


@router.get("/{platform}")
async def get_platform_policy_detail(platform: str):
    policies = load_platform_policies()
    if platform not in policies:
        raise HTTPException(status_code=404, detail="Platform policy not found")
    return _policy_to_dict(platform, get_platform_policy(platform))


@router.put("/{platform}")
async def update_platform_policy(platform: str, payload: Dict[str, Any] = Body(...)):
    allowed_fields = {
        "name",
        "style",
        "length",
        "min_words",
        "max_words",
        "format",
        "contact_policy",
        "ai_label_required",
        "title_rules",
        "forbidden_patterns",
        "warning_patterns",
        "recommended_content_types",
    }
    data = {key: payload.get(key) for key in allowed_fields if key in payload}
    if "min_words" in data and data["min_words"] not in (None, ""):
        data["min_words"] = int(data["min_words"])
    if "max_words" in data and data["max_words"] not in (None, ""):
        data["max_words"] = int(data["max_words"])
    for list_field in ["title_rules", "forbidden_patterns", "warning_patterns", "recommended_content_types"]:
        if list_field in data and data[list_field] is None:
            data[list_field] = []
    saved = save_platform_policy(platform, data)
    return _policy_to_dict(platform, saved)


@router.post("/check")
async def check_platform_policy_endpoint(payload: Dict[str, Any] = Body(...)):
    text = str(payload.get("text") or "")
    platform = str(payload.get("platform") or "media")
    return {
        "platform": platform,
        "issues": check_platform_policy(text, platform),
    }
