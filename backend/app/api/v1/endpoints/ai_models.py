from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel

from app.llm.providers import get_provider_choices, PRESET_PROVIDERS
from app.llm.registry import get_model_registry, ModelConfig
from app.llm.client import LLMClientFactory, LLMClientError
from app.llm.cost_tracker import get_cost_tracker


class TestModelRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    message: str = "你好，请简单介绍一下自己。"

router = APIRouter()


@router.get("/providers")
async def list_providers():
    """获取所有预置提供商和模型列表"""
    return {
        "providers": [
            {
                "key": k,
                "name": v["name"],
                "base_url": v["base_url"],
                "models": [
                    {"id": mk, "name": mi["name"], "context_length": mi["context_length"]}
                    for mk, mi in v["models"].items()
                ],
            }
            for k, v in PRESET_PROVIDERS.items()
        ]
    }


@router.get("/providers/choices")
async def list_provider_choices():
    """获取扁平化的模型选择列表（用于下拉框）"""
    return {"choices": get_provider_choices()}


@router.get("/registry")
async def list_registry_models():
    """获取模型注册表中的所有模型"""
    registry = get_model_registry()
    models = registry.list_models(active_only=False)
    return {
        "models": [m.to_dict(mask_api_key=True) for m in models],
        "default_model_id": registry._default_model_id,
        "count": len(models),
    }


@router.post("/registry/add")
async def add_custom_model(
    provider: str,
    model: str,
    api_key: str,
    name: Optional[str] = None,
    base_url: Optional[str] = None,
    input_price: float = 0.0,
    output_price: float = 0.0,
    context_length: int = 4096,
    description: str = "",
    set_as_default: bool = False,
):
    """添加自定义模型到注册表"""
    registry = get_model_registry()
    config = registry.add_custom_model(
        provider=provider,
        model=model,
        api_key=api_key,
        name=name,
        base_url=base_url,
        input_price=input_price,
        output_price=output_price,
        context_length=context_length,
        description=description,
        set_as_default=set_as_default,
    )
    return config.to_dict(mask_api_key=True)


@router.post("/registry/{model_id}/set-default")
async def set_default_model(model_id: str):
    """设置默认模型"""
    registry = get_model_registry()
    success = registry.set_default_model(model_id)
    if not success:
        raise HTTPException(status_code=404, detail="Model not found")
    return {"success": True, "default_model_id": model_id}


@router.post("/registry/{model_id}/update-key")
async def update_model_key(
    model_id: str,
    api_key: str = Body(..., embed=True),
):
    """更新模型API密钥"""
    registry = get_model_registry()
    success = registry.update_api_key(model_id, api_key)
    if not success:
        raise HTTPException(status_code=404, detail="Model not found")
    return {"success": True}


@router.post("/registry/{model_id}/update")
async def update_model_config(
    model_id: str,
    api_key: Optional[str] = Body(None, embed=True),
    base_url: Optional[str] = Body(None, embed=True),
    name: Optional[str] = Body(None, embed=True),
    input_price: Optional[float] = Body(None, embed=True),
    output_price: Optional[float] = Body(None, embed=True),
    context_length: Optional[int] = Body(None, embed=True),
    description: Optional[str] = Body(None, embed=True),
    is_active: Optional[bool] = Body(None, embed=True),
):
    """更新模型配置（支持预置模型）"""
    registry = get_model_registry()
    success = registry.update_model(
        model_id=model_id,
        api_key=api_key,
        base_url=base_url,
        name=name,
        input_price_per_1k=input_price,
        output_price_per_1k=output_price,
        context_length=context_length,
        description=description,
        is_active=is_active,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Model not found")
    return {"success": True}


@router.delete("/registry/{model_id}")
async def remove_custom_model(model_id: str):
    """删除自定义模型（预置模型不可删除）"""
    registry = get_model_registry()
    success = registry.remove_custom_model(model_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot remove preset model or model not found")
    return {"success": True}


@router.post("/test")
async def test_model_connection(req: TestModelRequest):
    """
    测试模型连接
    如果不传参数，使用默认模型
    """
    registry = get_model_registry()
    provider = req.provider
    model = req.model
    api_key = req.api_key
    base_url = req.base_url
    message = req.message

    if req.model_id:
        config = registry.get_model(req.model_id)
        if not config:
            raise HTTPException(status_code=404, detail="Model not found")
        if not config.api_key:
            raise HTTPException(status_code=400, detail="This model has no API key configured.")
        try:
            client = LLMClientFactory.create_client_from_config({
                "provider": config.provider,
                "model": config.model,
                "api_key": config.api_key,
                "base_url": config.base_url,
                "input_price_per_1k": config.input_price_per_1k,
                "output_price_per_1k": config.output_price_per_1k,
            })
        except LLMClientError as e:
            raise HTTPException(status_code=400, detail=str(e))
    elif provider and model and api_key:
        # 使用传入的参数测试
        try:
            client = LLMClientFactory.create_client(
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
            )
        except LLMClientError as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        # 使用默认模型
        default_config = registry.get_default_model()
        if not default_config:
            raise HTTPException(status_code=400, detail="No default model configured. Please add a model first.")
        if not default_config.api_key:
            raise HTTPException(status_code=400, detail="Default model has no API key configured.")

        try:
            client = LLMClientFactory.create_client_from_config({
                "provider": default_config.provider,
                "model": default_config.model,
                "api_key": default_config.api_key,
                "base_url": default_config.base_url,
                "input_price_per_1k": default_config.input_price_per_1k,
                "output_price_per_1k": default_config.output_price_per_1k,
            })
        except LLMClientError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # 发送测试消息
    try:
        response = await client.chat(
            messages=[{"role": "user", "content": message}],
            temperature=0.7,
        )

        # 记录成本
        tracker = get_cost_tracker()
        tracker.record(
            project_id=None,
            agent_name="test_connection",
            provider=client.provider,
            model=client.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=response.cost_usd,
            cost_cny=response.cost_cny,
            latency_ms=response.latency_ms,
            status="success",
        )

        return {
            "success": True,
            "provider": client.provider,
            "model": client.model,
            "response_preview": response.content[:200] + "..." if len(response.content) > 200 else response.content,
            "usage": {
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "total_tokens": response.total_tokens,
            },
            "cost": {
                "usd": round(response.cost_usd, 6),
                "cny": round(response.cost_cny, 6),
            },
            "latency_ms": round(response.latency_ms, 2),
        }
    except LLMClientError as e:
        raise HTTPException(status_code=502, detail=f"LLM API error: {str(e)}")


@router.get("/cost/summary")
async def get_cost_summary():
    """获取成本汇总"""
    tracker = get_cost_tracker()
    return {
        "overall": tracker.get_summary(),
        "daily": tracker.get_daily_cost(),
        "by_agent": tracker.get_by_agent(),
        "by_provider": tracker.get_by_provider(),
        "budget_alert": tracker.check_budget_alert(),
    }


@router.get("/cost/by-project/{project_id}")
async def get_project_cost(project_id: str):
    """获取项目成本"""
    from uuid import UUID
    tracker = get_cost_tracker()
    try:
        pid = UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id")
    return tracker.get_summary(project_id=pid)
