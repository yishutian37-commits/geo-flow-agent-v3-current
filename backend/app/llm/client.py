"""
统一的LLM客户端
支持所有OpenAI兼容格式的API（包括国内外主流模型）
"""
from typing import Optional, Dict, Any, List, AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
import json

import httpx


API_COMPATIBILITY_PROFILES = [
    {
        "name": "xiaomi_mimo",
        "markers": ["xiaomimimo", "platform.xiaomimimo.com", "mimo-v2", "mimo_v2"],
        "auth": "api-key",
        "token_field": "max_completion_tokens",
        "chat_path": "/chat/completions",
        "base_suffix": "/v1",
    },
    {
        "name": "openai_compatible",
        "markers": [],
        "auth": "bearer",
        "token_field": "max_tokens",
        "chat_path": "/chat/completions",
        "base_suffix": "",
    },
]


@dataclass
class LLMResponse:
    """标准化的LLM响应"""
    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    cost_cny: float = 0.0
    latency_ms: float = 0.0
    finish_reason: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


class LLMClientError(Exception):
    pass


class LLMClient:
    """
    统一的LLM客户端基类
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        provider: str = "custom",
        timeout: float = 120.0,
        max_retries: int = 2,
        input_price_per_1k: float = 0.0,
        output_price_per_1k: float = 0.0,
        usd_to_cny_rate: float = 7.2,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.provider = provider
        self.timeout = timeout
        self.max_retries = max_retries
        self.input_price_per_1k = input_price_per_1k
        self.output_price_per_1k = output_price_per_1k
        self.usd_to_cny_rate = usd_to_cny_rate

        # 计算价格汇率（如果价格是人民币，按1计算）
        # 国内模型通常直接用人民币计价
        self.is_cny_pricing = provider in ["deepseek", "zhipu", "moonshot", "baichuan", "qwen", "doubao", "minimax", "siliconflow"]

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> tuple:
        """
        计算调用成本
        返回: (usd_cost, cny_cost)
        """
        input_cost = (input_tokens / 1000) * self.input_price_per_1k
        output_cost = (output_tokens / 1000) * self.output_price_per_1k
        total = input_cost + output_cost

        if self.is_cny_pricing:
            # 国内模型价格是人民币，转换为美元显示
            return total / self.usd_to_cny_rate, total
        else:
            return total, total * self.usd_to_cny_rate

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        """
        发送对话请求
        """
        raise NotImplementedError

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        流式对话请求
        """
        raise NotImplementedError

    def format_messages_for_geo(
        self,
        system_prompt: Optional[str] = None,
        user_prompt: str = "",
        context: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        格式化GEO Agent的Prompt为messages格式
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if context:
            messages.append({"role": "user", "content": context})
        messages.append({"role": "user", "content": user_prompt})
        return messages


class OpenAICompatibleClient(LLMClient):
    """
    OpenAI兼容格式的LLM客户端
    支持：OpenAI、DeepSeek、GLM、Kimi、Baichuan、Qwen、Doubao、MiniMax、SiliconFlow、自定义模型
    """

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        """
        发送对话请求（OpenAI兼容格式）
        """
        import time
        start_time = time.time()

        url = f"{self._normalized_base_url()}{self._chat_path()}"
        headers = self._build_headers()

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream,
        }
        if max_tokens:
            payload[self._token_limit_field()] = max_tokens
        if tools:
            payload["tools"] = tools
        payload.update(kwargs)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, headers=headers, json=payload)

            if response.status_code != 200:
                error_text = response.text
                raise LLMClientError(
                    f"LLM API error ({self.provider}/{self.model}): HTTP {response.status_code}, {error_text[:500]}"
                )

            data = response.json()

        # 解析响应
        try:
            choice = data["choices"][0]
            content = self._message_content_to_text(choice["message"].get("content", ""))
            finish_reason = choice.get("finish_reason")

            usage = data.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0) or self._estimate_tokens(messages)
            output_tokens = usage.get("completion_tokens", 0) or self._estimate_tokens([{"content": content}])
            total_tokens = usage.get("total_tokens", input_tokens + output_tokens)
        except (KeyError, IndexError) as e:
            raise LLMClientError(f"Failed to parse LLM response: {e}, raw: {json.dumps(data)[:500]}")

        cost_usd, cost_cny = self._calculate_cost(input_tokens, output_tokens)
        latency_ms = (time.time() - start_time) * 1000

        return LLMResponse(
            content=content,
            model=self.model,
            provider=self.provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            cost_cny=cost_cny,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            raw_response=data,
        )

    def _api_compatibility_profile(self) -> Dict[str, str]:
        text = f"{self.provider or ''} {self.model or ''} {self.base_url or ''}".lower()
        for profile in API_COMPATIBILITY_PROFILES:
            markers = profile.get("markers") or []
            if markers and any(marker in text for marker in markers):
                return profile
        return API_COMPATIBILITY_PROFILES[-1]

    def _uses_xiaomi_mimo_api(self) -> bool:
        return self._api_compatibility_profile().get("name") == "xiaomi_mimo"

    def _token_limit_field(self) -> str:
        return self._api_compatibility_profile().get("token_field") or "max_tokens"

    def _chat_path(self) -> str:
        return self._api_compatibility_profile().get("chat_path") or "/chat/completions"

    def _normalized_base_url(self) -> str:
        base_url = (self.base_url or "").rstrip("/")
        suffix = (self._api_compatibility_profile().get("base_suffix") or "").rstrip("/")
        if suffix and not base_url.lower().endswith(suffix.lower()):
            return f"{base_url}{suffix}"
        return base_url

    def _build_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        auth_scheme = self._api_compatibility_profile().get("auth") or "bearer"
        if auth_scheme == "api-key":
            headers["api-key"] = self.api_key
        else:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _message_content_to_text(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if text:
                        parts.append(str(text))
            return "\n".join(parts).strip()
        return str(content)

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        流式对话请求（SSE格式）
        """
        url = f"{self._normalized_base_url()}{self._chat_path()}"
        headers = self._build_headers()
        headers["Accept"] = "text/event-stream"

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "stream": True,
        }
        if max_tokens:
            payload[self._token_limit_field()] = max_tokens
        payload.update(kwargs)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise LLMClientError(
                        f"LLM streaming error ({self.provider}/{self.model}): HTTP {response.status_code}, {error_text[:500]}"
                    )

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0]["delta"]
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue

    def _estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        """
        粗略估算token数（用于API未返回usage时）
        中文字符按1.5个token估算，英文按1个token估算
        """
        total_chars = sum(len(m.get("content", "")) for m in messages)
        # 简单估算：混合文本平均每个字符约1.2个token
        return int(total_chars * 1.2)


class LLMClientFactory:
    """
    LLM客户端工厂
    根据配置创建对应的客户端实例
    """

    @staticmethod
    def create_client(
        provider: str,
        model: str,
        api_key: str,
        base_url: Optional[str] = None,
        **kwargs
    ) -> LLMClient:
        """
        创建LLM客户端
        """
        from app.llm.providers import PRESET_PROVIDERS

        # 如果是预置提供商，自动填充base_url和价格
        if provider in PRESET_PROVIDERS:
            preset = PRESET_PROVIDERS[provider]
            if not base_url:
                base_url = preset["base_url"]

            model_info = preset["models"].get(model, {})
            kwargs.setdefault("input_price_per_1k", model_info.get("input_price_per_1k", 0.0))
            kwargs.setdefault("output_price_per_1k", model_info.get("output_price_per_1k", 0.0))

        if not base_url:
            raise LLMClientError(f"Base URL is required for provider '{provider}'")

        # 目前所有支持的模型都使用OpenAI兼容格式
        return OpenAICompatibleClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
            provider=provider,
            **kwargs
        )

    @staticmethod
    def create_client_from_config(config: Dict[str, Any]) -> LLMClient:
        """
        从配置字典创建客户端
        """
        return LLMClientFactory.create_client(
            provider=config["provider"],
            model=config["model"],
            api_key=config["api_key"],
            base_url=config.get("base_url"),
            timeout=config.get("timeout", 120.0),
            input_price_per_1k=config.get("input_price_per_1k", 0.0),
            output_price_per_1k=config.get("output_price_per_1k", 0.0),
        )
