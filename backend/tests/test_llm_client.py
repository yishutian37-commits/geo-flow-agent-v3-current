from app.llm.client import OpenAICompatibleClient


def test_mimo_client_uses_xiaomi_headers_and_token_field():
    client = OpenAICompatibleClient(
        api_key="test-key",
        base_url="https://api.platform.xiaomimimo.com",
        model="mimo-v2.5",
        provider="custom",
    )

    assert client._uses_xiaomi_mimo_api() is True
    assert client._api_compatibility_profile()["name"] == "xiaomi_mimo"
    assert client._build_headers()["api-key"] == "test-key"
    assert "Authorization" not in client._build_headers()
    assert client._token_limit_field() == "max_completion_tokens"
    assert client._normalized_base_url() == "https://api.platform.xiaomimimo.com/v1"


def test_mimo_client_does_not_duplicate_v1_suffix():
    client = OpenAICompatibleClient(
        api_key="test-key",
        base_url="https://api.platform.xiaomimimo.com/v1",
        model="mimo-v2.5",
        provider="custom",
    )

    assert client._normalized_base_url() == "https://api.platform.xiaomimimo.com/v1"


def test_openai_compatible_profile_uses_bearer_and_max_tokens():
    client = OpenAICompatibleClient(
        api_key="test-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen-vl-plus",
        provider="qwen",
    )

    assert client._api_compatibility_profile()["name"] == "openai_compatible"
    assert client._build_headers()["Authorization"] == "Bearer test-key"
    assert client._token_limit_field() == "max_tokens"


def test_message_content_to_text_supports_list_content():
    client = OpenAICompatibleClient(
        api_key="test-key",
        base_url="https://example.com/v1",
        model="test-model",
        provider="custom",
    )

    text = client._message_content_to_text([
        {"type": "text", "text": "first"},
        {"type": "text", "text": "second"},
    ])

    assert text == "first\nsecond"
