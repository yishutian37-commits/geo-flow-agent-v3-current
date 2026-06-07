"""
模型注册表
管理项目中可用的LLM模型配置
支持预置模型 + 用户自定义模型，支持持久化到JSON文件
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from uuid import UUID, uuid4
import json
import os
import re

from app.llm.providers import PRESET_PROVIDERS


@dataclass
class ModelConfig:
    """模型配置"""
    id: str                          # 唯一标识
    provider: str                    # 提供商key: openai/deepseek/zhipu/...
    model: str                       # 模型ID: gpt-4o/deepseek-chat/...
    name: str                        # 显示名称
    api_key: str = ""                # API密钥（加密存储）
    base_url: Optional[str] = None   # 自定义Base URL
    is_custom: bool = False          # 是否用户自定义
    is_active: bool = True           # 是否启用
    is_default: bool = False         # 是否为默认模型
    input_price_per_1k: float = 0.0  # 输入价格（每1K token）
    output_price_per_1k: float = 0.0 # 输出价格（每1K token）
    context_length: int = 4096       # 上下文长度
    description: str = ""            # 描述
    tags: List[str] = field(default_factory=list)  # 标签: fast/cheap/reasoning/long-context
    supports_vision: Optional[bool] = None  # 是否明确支持图片理解；None 表示按模型名自动判断
    created_at: str = ""             # 创建时间

    def to_dict(self, mask_api_key: bool = True) -> dict:
        """转换为字典，可选隐藏API密钥"""
        d = asdict(self)
        if mask_api_key:
            d["api_key"] = "***" if self.api_key else ""
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ModelConfig":
        """从字典创建实例"""
        # 过滤掉类中不存在的字段
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


class ModelRegistry:
    """
    模型注册表
    管理项目中所有可用的LLM模型
    支持持久化到JSON文件
    """

    def __init__(self, save_path: Optional[str] = None):
        self._models: Dict[str, ModelConfig] = {}
        self._default_model_id: Optional[str] = None
        if save_path is None:
            save_path = os.getenv("GEO_LLM_REGISTRY_PATH")
        if save_path is None:
            # 默认保存到 backend/app/data/llm_registry.json；桌面模式下写入用户数据目录
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            save_path = os.path.join(base_dir, "data", "llm_registry.json")
        self._save_path = save_path

    def load_presets(self, filter_active: bool = True):
        """
        加载预置模型配置
        """
        for provider_key, provider_info in PRESET_PROVIDERS.items():
            for model_key, model_info in provider_info["models"].items():
                config_id = f"{provider_key}:{model_key}"
                tags = self._infer_tags(provider_key, model_key, model_info)
                config = ModelConfig(
                    id=config_id,
                    provider=provider_key,
                    model=model_key,
                    name=f"{provider_info['name']} - {model_info['name']}",
                    base_url=provider_info["base_url"],
                    input_price_per_1k=model_info.get("input_price_per_1k", 0.0),
                    output_price_per_1k=model_info.get("output_price_per_1k", 0.0),
                    context_length=model_info.get("context_length", 4096),
                    description=f"{model_info['name']} | 上下文: {model_info.get('context_length', 4096)}",
                    tags=tags,
                    supports_vision=bool(model_info.get("supports_vision") or "vision" in tags),
                )
                self._models[config_id] = config

    def _infer_tags(self, provider: str, model: str, model_info: dict) -> List[str]:
        """根据模型特性推断标签"""
        tags = []
        ctx = model_info.get("context_length", 4096)
        if ctx >= 64000:
            tags.append("long-context")
        if "flash" in model.lower() or "lite" in model.lower() or model_info.get("input_price_per_1k", 0) < 0.005:
            tags.append("cheap")
        if "reasoner" in model.lower() or "r1" in model.lower():
            tags.append("reasoning")
        if "turbo" in model.lower() or "fast" in model.lower():
            tags.append("fast")
        vision_markers = [
            "vision", "visual", "image", "multimodal", "multi-modal", "omni",
            "视觉", "图像", "图片", "多模态", "截图",
            "gpt-4o", "qwen-vl", "qvq", "glm-4v", "doubao-vision",
            "mimo-v2.5", "mimo-v2-5", "gemini", "claude-3", "vl",
        ]
        text = f"{provider} {model} {model_info.get('name', '')}".lower()
        compact_text = re.sub(r"[^a-z0-9]+", "", text)
        if "minimaxm3" in compact_text or ("minimax" in text and re.search(r"(^|[^a-z0-9])m3([^a-z0-9]|$)", text)):
            tags.append("vision")
            return tags
        if any(marker in text for marker in vision_markers):
            tags.append("vision")
        return tags

    @staticmethod
    def _is_configured(config: ModelConfig) -> bool:
        return bool(config.api_key) or config.is_custom

    def save_to_file(self):
        """保存当前配置到JSON文件"""
        data = {
            "models": [
                m.to_dict(mask_api_key=False)
                for m in self._models.values()
                if self._is_configured(m)
            ],
            "default_model_id": self._default_model_id,
        }
        os.makedirs(os.path.dirname(self._save_path), exist_ok=True)
        with open(self._save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_from_file(self):
        """从JSON文件加载用户自定义配置（覆盖预置模型）"""
        if not os.path.exists(self._save_path):
            return
        try:
            with open(self._save_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 恢复模型配置
            for m_data in data.get("models", []):
                model_id = m_data.get("id")
                if not model_id:
                    continue
                if model_id in self._models:
                    # 预置模型：用保存的值覆盖可变字段
                    existing = self._models[model_id]
                    existing.api_key = m_data.get("api_key", existing.api_key)
                    existing.base_url = m_data.get("base_url", existing.base_url)
                    existing.name = m_data.get("name", existing.name)
                    existing.input_price_per_1k = m_data.get("input_price_per_1k", existing.input_price_per_1k)
                    existing.output_price_per_1k = m_data.get("output_price_per_1k", existing.output_price_per_1k)
                    existing.context_length = m_data.get("context_length", existing.context_length)
                    existing.description = m_data.get("description", existing.description)
                    existing.is_active = m_data.get("is_active", existing.is_active)
                    existing.is_default = m_data.get("is_default", existing.is_default)
                    if "supports_vision" in m_data:
                        existing.supports_vision = m_data.get("supports_vision")
                        self._sync_vision_tag(existing)
                else:
                    # 自定义模型：直接添加
                    config = ModelConfig.from_dict(m_data)
                    self._sync_vision_tag(config)
                    self._models[model_id] = config

            # 恢复默认模型
            saved_default = data.get("default_model_id")
            if saved_default and saved_default in self._models:
                self._default_model_id = saved_default
                # 确保只有一个默认
                for m in self._models.values():
                    m.is_default = (m.id == saved_default)
        except Exception as e:
            print(f"[LLM Registry] 加载持久化配置失败: {e}")

    def add_custom_model(
        self,
        provider: str,
        model: str,
        api_key: str,
        name: Optional[str] = None,
        base_url: Optional[str] = None,
        input_price: float = 0.0,
        output_price: float = 0.0,
        context_length: int = 4096,
        description: str = "",
        supports_vision: Optional[bool] = None,
        set_as_default: bool = False,
    ) -> ModelConfig:
        """添加自定义模型"""
        config_id = f"custom:{uuid4().hex[:8]}"
        config = ModelConfig(
            id=config_id,
            provider=provider,
            model=model,
            name=name or f"自定义 - {model}",
            api_key=api_key,
            base_url=base_url,
            is_custom=True,
            is_active=True,
            input_price_per_1k=input_price,
            output_price_per_1k=output_price,
            context_length=context_length,
            description=description,
            supports_vision=supports_vision,
        )
        self._sync_vision_tag(config)
        self._models[config_id] = config

        if set_as_default or not self._default_model_id:
            self._default_model_id = config_id
            for m in self._models.values():
                m.is_default = (m.id == config_id)

        self.save_to_file()
        return config

    def get_model(self, model_id: str) -> Optional[ModelConfig]:
        """获取模型配置"""
        return self._models.get(model_id)

    def get_default_model(self) -> Optional[ModelConfig]:
        """获取默认模型"""
        if self._default_model_id:
            config = self._models.get(self._default_model_id)
            if config and config.is_active and config.api_key:
                return config
        for config in self._models.values():
            if config.is_active and config.api_key:
                return config
        return None

    def set_default_model(self, model_id: str) -> bool:
        """设置默认模型"""
        if model_id not in self._models:
            return False
        for config in self._models.values():
            config.is_default = False
        self._models[model_id].is_default = True
        self._default_model_id = model_id
        self.save_to_file()
        return True

    def list_models(
        self,
        provider: Optional[str] = None,
        tag: Optional[str] = None,
        active_only: bool = True,
        configured_only: bool = True,
    ) -> List[ModelConfig]:
        """列出模型"""
        results = []
        for config in self._models.values():
            if configured_only and not self._is_configured(config):
                continue
            if active_only and not config.is_active:
                continue
            if provider and config.provider != provider:
                continue
            if tag and tag not in config.tags:
                continue
            results.append(config)
        return results

    def deactivate_model(self, model_id: str) -> bool:
        """停用模型"""
        if model_id not in self._models:
            return False
        self._models[model_id].is_active = False
        self.save_to_file()
        return True

    def remove_custom_model(self, model_id: str) -> bool:
        """移除自定义模型（预置模型不可删除）"""
        config = self._models.get(model_id)
        if not config or not config.is_custom:
            return False
        del self._models[model_id]
        if self._default_model_id == model_id:
            self._default_model_id = None
        self.save_to_file()
        return True

    def update_api_key(self, model_id: str, api_key: str) -> bool:
        """更新模型API密钥"""
        if model_id not in self._models:
            return False
        self._models[model_id].api_key = api_key
        self.save_to_file()
        return True

    def update_model(
        self,
        model_id: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        name: Optional[str] = None,
        input_price_per_1k: Optional[float] = None,
        output_price_per_1k: Optional[float] = None,
        context_length: Optional[int] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
        supports_vision: Optional[bool] = None,
    ) -> bool:
        """更新模型配置（支持预置模型和自定义模型）"""
        if model_id not in self._models:
            return False
        config = self._models[model_id]
        if api_key is not None:
            config.api_key = api_key
        if base_url is not None:
            config.base_url = base_url
        if name is not None:
            config.name = name
        if input_price_per_1k is not None:
            config.input_price_per_1k = input_price_per_1k
        if output_price_per_1k is not None:
            config.output_price_per_1k = output_price_per_1k
        if context_length is not None:
            config.context_length = context_length
        if description is not None:
            config.description = description
        if is_active is not None:
            config.is_active = is_active
        if supports_vision is not None:
            config.supports_vision = supports_vision
            self._sync_vision_tag(config)
        self.save_to_file()
        return True

    @staticmethod
    def _sync_vision_tag(config: ModelConfig) -> None:
        tags = list(config.标签 or [])
        if config.supports_vision is True and "vision" not in tags:
            tags.append("vision")
        if config.supports_vision is False:
            tags = [tag for tag in标签if tag != "vision"]
        config.标签 = tags

    def to_json(self, mask_api_key: bool = True) -> str:
        """导出为JSON"""
        data = {
            "models": [m.to_dict(mask_api_key) for m in self._models.values()],
            "default_model_id": self._default_model_id,
        }
        return json.dumps(data, ensure_ascii=False, indent=2)


# 全局注册表实例
_registry_instance: Optional[ModelRegistry] = None


def get_model_registry() -> ModelRegistry:
    """获取全局模型注册表（单例）"""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ModelRegistry()
        _registry_instance.load_presets()
        _registry_instance.load_from_file()
    return _registry_instance


def reset_registry():
    """重置注册表（主要用于测试）"""
    global _registry_instance
    _registry_instance = None
