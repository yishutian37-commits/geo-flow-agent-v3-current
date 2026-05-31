"""
预置的LLM提供商配置
覆盖国内外主流模型，全部基于OpenAI兼容API格式
"""
from typing import Dict, Any


PRESET_PROVIDERS: Dict[str, Dict[str, Any]] = {
    # 国外模型
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": {
            "gpt-4o": {"name": "GPT-4o", "context_length": 128000, "input_price_per_1k": 0.005, "output_price_per_1k": 0.015},
            "gpt-4o-mini": {"name": "GPT-4o Mini", "context_length": 128000, "input_price_per_1k": 0.00015, "output_price_per_1k": 0.0006},
            "gpt-4-turbo": {"name": "GPT-4 Turbo", "context_length": 128000, "input_price_per_1k": 0.01, "output_price_per_1k": 0.03},
            "gpt-3.5-turbo": {"name": "GPT-3.5 Turbo", "context_length": 16385, "input_price_per_1k": 0.0005, "output_price_per_1k": 0.0015},
        },
        "docs_url": "https://platform.openai.com/docs",
    },
    # 国内模型
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models": {
            "deepseek-chat": {"name": "DeepSeek-V3", "context_length": 64000, "input_price_per_1k": 0.002, "output_price_per_1k": 0.008},
            "deepseek-reasoner": {"name": "DeepSeek-R1", "context_length": 64000, "input_price_per_1k": 0.004, "output_price_per_1k": 0.016},
        },
        "docs_url": "https://platform.deepseek.com/api-docs",
    },
    "zhipu": {
        "name": "智谱GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": {
            "glm-4-plus": {"name": "GLM-4-Plus", "context_length": 128000, "input_price_per_1k": 0.05, "output_price_per_1k": 0.05},
            "glm-4": {"name": "GLM-4", "context_length": 128000, "input_price_per_1k": 0.05, "output_price_per_1k": 0.05},
            "glm-4-flash": {"name": "GLM-4-Flash", "context_length": 128000, "input_price_per_1k": 0.0, "output_price_per_1k": 0.0},
            "glm-4-air": {"name": "GLM-4-Air", "context_length": 128000, "input_price_per_1k": 0.001, "output_price_per_1k": 0.001},
        },
        "docs_url": "https://open.bigmodel.cn/dev/howuse/glm-4",
    },
    "moonshot": {
        "name": "Moonshot AI (Kimi)",
        "base_url": "https://api.moonshot.cn/v1",
        "models": {
            "moonshot-v1-8k": {"name": "Kimi K1-8K", "context_length": 8192, "input_price_per_1k": 0.012, "output_price_per_1k": 0.012},
            "moonshot-v1-32k": {"name": "Kimi K1-32K", "context_length": 32768, "input_price_per_1k": 0.024, "output_price_per_1k": 0.024},
            "moonshot-v1-128k": {"name": "Kimi K1-128K", "context_length": 131072, "input_price_per_1k": 0.06, "output_price_per_1k": 0.06},
        },
        "docs_url": "https://platform.moonshot.cn/docs",
    },
    "baichuan": {
        "name": "百川智能",
        "base_url": "https://api.baichuan-ai.com/v1",
        "models": {
            "Baichuan4": {"name": "Baichuan4", "context_length": 32768, "input_price_per_1k": 0.1, "output_price_per_1k": 0.1},
            "Baichuan3-Turbo": {"name": "Baichuan3-Turbo", "context_length": 32768, "input_price_per_1k": 0.005, "output_price_per_1k": 0.005},
        },
        "docs_url": "https://platform.baichuan-ai.com/docs",
    },
    "qwen": {
        "name": "通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": {
            "qwen-max": {"name": "Qwen-Max", "context_length": 32768, "input_price_per_1k": 0.02, "output_price_per_1k": 0.06},
            "qwen-plus": {"name": "Qwen-Plus", "context_length": 131072, "input_price_per_1k": 0.0008, "output_price_per_1k": 0.002},
            "qwen-turbo": {"name": "Qwen-Turbo", "context_length": 131072, "input_price_per_1k": 0.0003, "output_price_per_1k": 0.0006},
            "qwen-vl-plus": {"name": "Qwen-VL-Plus", "context_length": 32768, "input_price_per_1k": 0.008, "output_price_per_1k": 0.008},
            "qwen-vl-max": {"name": "Qwen-VL-Max", "context_length": 32768, "input_price_per_1k": 0.02, "output_price_per_1k": 0.02},
        },
        "docs_url": "https://help.aliyun.com/zh/dashscope",
    },
    "xiaomi": {
        "name": "Xiaomi MiMo",
        "base_url": "https://api.platform.xiaomimimo.com/v1",
        "models": {
            "mimo-v2.5": {"name": "MiMo V2.5", "context_length": 128000, "input_price_per_1k": 0.0, "output_price_per_1k": 0.0},
        },
        "docs_url": "https://platform.xiaomimimo.com/docs",
    },
    "doubao": {
        "name": "豆包",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": {
            "doubao-pro-128k": {"name": "Doubao-Pro-128K", "context_length": 131072, "input_price_per_1k": 0.005, "output_price_per_1k": 0.009},
            "doubao-lite-128k": {"name": "Doubao-Lite-128K", "context_length": 131072, "input_price_per_1k": 0.0008, "output_price_per_1k": 0.001},
        },
        "docs_url": "https://www.volcengine.com/docs/82379",
    },
    "minimax": {
        "name": "MiniMax",
        "base_url": "https://api.minimax.chat/v1",
        "models": {
            "abab6.5s-chat": {"name": "MiniMax-6.5s", "context_length": 245000, "input_price_per_1k": 0.01, "output_price_per_1k": 0.01},
        },
        "docs_url": "https://platform.minimaxi.com/document",
    },
    "siliconflow": {
        "name": "硅基流动",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": {
            "deepseek-ai/DeepSeek-V3": {"name": "DeepSeek-V3 (SiliconFlow)", "context_length": 64000, "input_price_per_1k": 0.001, "output_price_per_1k": 0.004},
            "Qwen/Qwen2.5-72B-Instruct": {"name": "Qwen2.5-72B", "context_length": 32768, "input_price_per_1k": 0.004, "output_price_per_1k": 0.004},
        },
        "docs_url": "https://docs.siliconflow.cn/",
    },
}


def get_provider_choices() -> list:
    """返回提供商选择列表，用于前端下拉框"""
    choices = []
    for key, provider in PRESET_PROVIDERS.items():
        for model_key, model_info in provider["models"].items():
            choices.append({
                "provider": key,
                "provider_name": provider["name"],
                "model_id": model_key,
                "model_name": model_info["name"],
                "context_length": model_info["context_length"],
                "base_url": provider["base_url"],
            })
    return choices
