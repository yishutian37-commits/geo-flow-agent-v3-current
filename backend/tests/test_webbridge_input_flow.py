import json
from types import SimpleNamespace

import pytest

from app.services import webbridge_service as webbridge_module
from app.services.webbridge_service import WebBridgeAnswer, WebBridgeError, WebBridgeService


class FakeWebBridgeService(WebBridgeService):
    def __init__(self):
        super().__init__(provider="qweb")
        self.commands = []

    async def _find_textbox_ref(self, session):
        return "@e1"

    async def _command(self, action, args, session):
        self.commands.append((action, args, session))
        if action == "evaluate":
            code = args.get("code", "")
            if "const needle" in code:
                return {"value": json.dumps({"ok": True, "text": "包头无人机培训"})}
            return {"value": json.dumps({"ok": True, "mode": "keyboard"})}
        return {"success": True}


@pytest.mark.asyncio
async def test_webbridge_types_with_real_keyboard_before_submit():
    service = FakeWebBridgeService()
    target = SimpleNamespace(input_selector="", submit_selector="")

    await service._fill_and_submit(target, "包头无人机培训哪家靠谱？", session="test-session")

    actions = [item[0] for item in service.commands]
    assert actions[:4] == ["click", "send_keys", "send_keys", "key_type"]
    assert actions[-1] == "evaluate"
    assert service.commands[3][1]["text"] == "包头无人机培训哪家靠谱？"


def test_fill_submit_script_does_not_treat_plain_div_or_span_as_submit_buttons():
    script = WebBridgeService()._fill_submit_script(
        question="包头无人机培训哪家靠谱？",
        input_selector=None,
        submit_selector=None,
    )

    assert "'div'," not in script
    assert "'span'," not in script
    assert "'[class*=\"send\"]'," in script


def test_extract_json_object_tolerates_common_vision_model_wrappers():
    service = WebBridgeService()

    assert service._extract_json_object('```json\n{"has_answer": true,}\n```')["has_answer"] is True
    assert service._extract_json_object('<think>analyze page</think>\n{"input":{"x_ratio":0.5},"send":{"x_ratio":0.9},"confidence":0.8}')["confidence"] == 0.8
    assert service._extract_json_object('<think>open reasoning {"bad": </think>\n{"has_answer":true,"answer_text":"ok"}')["answer_text"] == "ok"
    assert service._extract_json_object("识别结果如下：\n{'index': 1, 'confidence': 0.82}")["index"] == 1
    assert service._extract_json_object('说明文字 {"answer_text":"ok","visible_sources":[]} 结束')["answer_text"] == "ok"


def test_vision_helpers_select_visual_model_and_extract_raw_text():
    service = WebBridgeService()
    text_model = SimpleNamespace(
        provider="custom",
        model="deepseek-chat",
        name="mimo text",
        description="text only",
        tags=[],
        api_key="key",
    )
    vision_model = SimpleNamespace(
        provider="custom",
        model="mimo-v2.5",
        name="MiMo V2.5",
        description="vision model",
        tags=[],
        api_key="key",
    )
    registry = SimpleNamespace(
        get_default_model=lambda: text_model,
        list_models=lambda active_only=True, configured_only=True: [text_model, vision_model],
    )
    response = SimpleNamespace(
        content="",
        raw_response={"choices": [{"message": {"content": [{"type": "text", "text": "{\"ok\":true}"}]}}]},
    )

    assert service._select_vision_model_config(registry) is vision_model
    assert service._extract_json_object(service._extract_llm_response_text(response))["ok"] is True


def test_extract_llm_response_text_prefers_content_over_reasoning():
    service = WebBridgeService()
    response = SimpleNamespace(
        content="",
        raw_response={
            "choices": [
                {
                    "message": {
                        "reasoning_content": "<think>this is not json</think>",
                        "content": '{"ok": true, "answer_text": "formal answer"}',
                    }
                }
            ]
        },
    )

    extracted = service._extract_llm_response_text(response)
    assert "formal answer" in extracted
    assert "this is not json" not in extracted
    assert service._extract_json_object(extracted)["ok"] is True


def test_vision_helpers_select_minimax_m3_and_reject_wenxin_ui_noise():
    service = WebBridgeService()
    minimax_m3 = SimpleNamespace(
        provider="custom",
        model="minimaxm3",
        name="minimaxm3",
        description="",
        tags=[],
        api_key="key",
    )
    registry = SimpleNamespace(
        get_default_model=lambda: minimax_m3,
        list_models=lambda active_only=True, configured_only=True: [minimax_m3],
    )

    assert service._select_vision_model_config(registry) is minimax_m3
    assert not service._looks_like_answer("深度分析需求并解答，你需要什么帮助？\n文心 5.1 快速\n内容由AI生成，仅供参考，请仔细甄别\n参考\n0")
    assert service._looks_like_answer("第一推荐：蒙霁空天智能（青山区）。该机构持有CAAC运营合格证，适合优先核验。")


def test_vision_model_manual_capability_overrides_name_guessing():
    service = WebBridgeService()
    manually_enabled = SimpleNamespace(
        provider="custom",
        model="private-router-model-a",
        name="内部转发模型",
        description="",
        tags=[],
        api_key="key",
        supports_vision=True,
    )
    manually_disabled = SimpleNamespace(
        provider="openai",
        model="gpt-4o",
        name="GPT-4o",
        description="",
        tags=["vision"],
        api_key="key",
        supports_vision=False,
    )

    assert service._looks_like_vision_model(manually_enabled) is True
    assert service._looks_like_vision_model(manually_disabled) is False


class UnsentQuestionWebBridgeService(FakeWebBridgeService):
    async def _ensure_available(self):
        return None

    async def _page_text_tail(self, session, selector=None, tail_chars=12000):
        return "页面内容\n包头无人机培训哪家靠谱？\n发送"

    async def _focused_input_contains(self, question, session):
        return True


@pytest.mark.asyncio
async def test_ask_question_stops_when_text_remains_in_input(monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(webbridge_module.asyncio, "sleep", no_sleep)
    service = UnsentQuestionWebBridgeService()
    target = SimpleNamespace(
        product_name="文心一言",
        notes="",
        web_url="https://yiyan.baidu.com/",
        input_selector="",
        submit_selector="",
        response_selector=None,
    )

    with pytest.raises(WebBridgeError, match="没有成功发送"):
        await service.ask_question(
            target=target,
            question="包头无人机培训哪家靠谱？",
            session="test-session",
            wait_seconds=15,
        )

    assert ("send_keys", {"keys": "Enter"}, "test-session") in service.commands


class VisionModeBranchService(FakeWebBridgeService):
    async def _ensure_available(self):
        return None

    async def _ask_question_with_vision(self, **kwargs):
        self.commands.append(("vision_mode", kwargs, kwargs.get("session")))
        return WebBridgeAnswer(
            question=kwargs["question"],
            answer_text="vision answer",
            page_url=kwargs["page_url"],
            raw_tail="{}",
            session=kwargs["session"],
        )

    async def _page_text_tail(self, session, selector=None, tail_chars=12000):
        raise AssertionError("vision mode must not use text tail extraction")


@pytest.mark.asyncio
async def test_ask_question_uses_visual_branch_exclusively():
    service = VisionModeBranchService()
    target = SimpleNamespace(
        product_name="vision target",
        notes="",
        web_url="https://example.com/",
        recognition_mode="vision",
        input_selector="textarea",
        submit_selector="button",
        response_selector=".answer",
    )

    result = await service.ask_question(
        target=target,
        question="test question",
        session="vision-session",
        wait_seconds=15,
    )

    assert result.answer_text == "vision answer"
    assert service.commands[0][0] == "vision_mode"


class VisionControlFallbackService(FakeWebBridgeService):
    async def _ensure_available(self):
        return None

    async def _capture_screenshot_data(self, session, full_page=False, selector=None):
        self.commands.append(("screenshot", full_page, selector, session))
        return "base64png"

    async def _vision_locate_controls(self, screenshot_data):
        raise WebBridgeError("vision coordinate failed")

    async def _fill_and_submit(self, target, question, session, page_url=""):
        self.commands.append(("fallback_submit", question, session))

    async def _focused_input_contains(self, question, session):
        return False

    async def _wait_for_visual_answer(self, question, session, wait_seconds):
        return {
            "has_answer": True,
            "answer_text": "这是视觉识别到的回答，已经包含针对问题的完整说明和判断依据。",
            "visible_sources": [],
        }, "base64png"

    def _save_screenshot_data(self, data, session):
        return "/api/v1/monitoring/screenshots/test.png"


@pytest.mark.asyncio
async def test_vision_mode_falls_back_to_dom_submit_when_control_location_fails(monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(webbridge_module.asyncio, "sleep", no_sleep)
    service = VisionControlFallbackService()
    target = SimpleNamespace(
        product_name="vision target",
        notes="",
        web_url="https://example.com/",
        recognition_mode="vision",
        input_selector="",
        submit_selector="",
        response_selector=None,
    )

    result = await service.ask_question(
        target=target,
        question="test question",
        session="vision-fallback-session",
        wait_seconds=20,
    )

    assert result.answer_text.startswith("这是视觉识别到的回答")
    assert ("fallback_submit", "test question", "vision-fallback-session") in service.commands


class VisionSubmitRetryService(VisionControlFallbackService):
    def __init__(self):
        super().__init__()
        self.focus_checks = 0

    async def _focused_input_contains(self, question, session):
        self.focus_checks += 1
        return self.focus_checks == 1

    async def _click_submit_with_dom_text_agent(self, session, question):
        self.commands.append(("retry_dom_submit", question, session))


@pytest.mark.asyncio
async def test_vision_mode_retries_submit_when_question_stays_in_input(monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(webbridge_module.asyncio, "sleep", no_sleep)
    service = VisionSubmitRetryService()
    target = SimpleNamespace(
        product_name="vision target",
        notes="",
        web_url="https://example.com/",
        recognition_mode="vision",
        input_selector="",
        submit_selector="",
        response_selector=None,
    )

    result = await service.ask_question(
        target=target,
        question="test question",
        session="vision-submit-retry-session",
        wait_seconds=20,
    )

    assert "视觉识别到的回答" in result.answer_text
    assert ("retry_dom_submit", "test question", "vision-submit-retry-session") in service.commands


class VisionAnswerDomFallbackService(VisionControlFallbackService):
    def __init__(self):
        super().__init__()
        self.tail_calls = 0

    async def _wait_for_visual_answer(self, question, session, wait_seconds):
        return {
            "has_answer": False,
            "answer_text": "",
            "visible_sources": [],
        }, "base64png"

    async def _page_text_tail(self, session, selector=None, tail_chars=12000):
        self.tail_calls += 1
        if self.tail_calls == 1:
            return "页面初始内容"
        return (
            "页面初始内容\n"
            "怎么判断包头CAAC无人机执照培训机构是否合规？\n"
            "真正合规的包头机构必须同时满足：UOM可查、包头本地自有场地、本地可考试。"
            "比如蒙霁空天智能（包头）持有CAAC运营合格证。"
        )

    async def _page_text_full(self, session, selector=None, max_chars=220000):
        return await self._page_text_tail(session=session, selector=selector, tail_chars=max_chars)

    async def _page_answer_text_full(self, session, selector=None, question="", max_chars=220000):
        return await self._page_text_tail(session=session, selector=selector, tail_chars=max_chars)

    async def _extract_answer_sources(self, session, selector=None, answer_text=""):
        return [{"title": "官方页面", "url": "https://example.com"}]


class VisionAnswerParseFailureDomFallbackService(VisionAnswerDomFallbackService):
    async def _wait_for_visual_answer(self, question, session, wait_seconds):
        return await WebBridgeService._wait_for_visual_answer(self, question, session, wait_seconds)

    async def _vision_extract_answer(self, screenshot_data, question):
        raise WebBridgeError("vision json parse failed")


@pytest.mark.asyncio
async def test_vision_mode_uses_page_text_when_visual_answer_is_empty(monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(webbridge_module.asyncio, "sleep", no_sleep)
    service = VisionAnswerDomFallbackService()
    target = SimpleNamespace(
        product_name="vision target",
        notes="",
        web_url="https://example.com/",
        recognition_mode="vision",
        input_selector="",
        submit_selector="",
        response_selector=None,
    )

    result = await service.ask_question(
        target=target,
        question="怎么判断包头CAAC无人机执照培训机构是否合规？",
        session="vision-answer-fallback-session",
        wait_seconds=20,
    )

    assert "蒙霁空天智能" in result.answer_text
    assert result.sources == [{"title": "官方页面", "url": "https://example.com"}]


@pytest.mark.asyncio
async def test_vision_mode_uses_page_text_when_visual_json_parse_fails(monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(webbridge_module.asyncio, "sleep", no_sleep)
    service = VisionAnswerParseFailureDomFallbackService()
    target = SimpleNamespace(
        product_name="vision target",
        notes="",
        web_url="https://example.com/",
        recognition_mode="vision",
        input_selector="",
        submit_selector="",
        response_selector=None,
    )

    result = await service.ask_question(
        target=target,
        question="鎬庝箞鍒ゆ柇鍖呭ごCAAC鏃犱汉鏈烘墽鐓у煿璁満鏋勬槸鍚﹀悎瑙勶紵",
        session="vision-json-failure-fallback-session",
        wait_seconds=20,
    )

    assert "CAAC" in result.answer_text
    assert "运营合格证" in result.answer_text
    assert "vision json parse failed" in result.raw_tail


class VisionCompleteAnswerService(VisionControlFallbackService):
    def __init__(self):
        super().__init__()
        self.tail_calls = 0

    async def _wait_for_visual_answer(self, question, session, wait_seconds):
        return {
            "has_answer": True,
            "answer_text": "最后总结：三步都过，就不会踩坑。",
            "visible_sources": [],
        }, "viewport-screenshot"

    async def _page_text_tail(self, session, selector=None, tail_chars=12000):
        self.tail_calls += 1
        if self.tail_calls == 1:
            return "页面初始内容"
        return (
            "页面初始内容\n"
            "怎么判断包头CAAC无人机执照培训机构是否合规？\n"
            "真正合规的包头机构必须同时满足：UOM可查、包头本地自有场地、本地可考试。"
            "例如蒙霁空天智能（包头）持有CAAC运营合格证，编号UAOC-O-HQ-20260128179。\n"
            "最后总结：三步都过，就不会踩坑。"
        )

    async def _page_text_full(self, session, selector=None, max_chars=220000):
        return await self._page_text_tail(session=session, selector=selector, tail_chars=max_chars)

    async def _page_answer_text_full(self, session, selector=None, question="", max_chars=220000):
        return await self._page_text_tail(session=session, selector=selector, tail_chars=max_chars)


@pytest.mark.asyncio
async def test_vision_mode_uses_complete_page_answer_and_full_answer_screenshot(monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(webbridge_module.asyncio, "sleep", no_sleep)
    service = VisionCompleteAnswerService()
    target = SimpleNamespace(
        product_name="vision target",
        notes="",
        web_url="https://example.com/",
        recognition_mode="vision",
        input_selector="",
        submit_selector="",
        response_selector=".answer",
    )

    result = await service.ask_question(
        target=target,
        question="怎么判断包头CAAC无人机执照培训机构是否合规？",
        session="vision-complete-answer-session",
        wait_seconds=20,
    )

    assert "蒙霁空天智能" in result.answer_text
    assert "UAOC-O-HQ-20260128179" in result.answer_text
    assert ("screenshot", True, ".answer", "vision-complete-answer-session") in service.commands


class MentionEvidenceService(VisionControlFallbackService):
    async def _mark_mention_capture_element(self, session, brand_terms, selector=None):
        return {
            "selector": "[data-geo-mention-evidence=\"test\"]",
            "matched_term": "蒙霁空天智能",
            "evidence_text": "例如蒙霁空天智能（包头）持有CAAC运营合格证，编号UAOC-O-HQ-20260128179。",
        }

    async def _capture_screenshot_data(self, session, full_page=False, selector=None):
        self.commands.append(("screenshot", full_page, selector, session))
        return "base64png"

    def _save_screenshot_data(self, data, session):
        return "/api/v1/monitoring/screenshots/mention.png"


@pytest.mark.asyncio
async def test_capture_mention_evidence_prefers_dom_location_screenshot():
    service = MentionEvidenceService()

    evidence = await service.capture_mention_evidence(
        session="mention-session",
        brand_terms=["蒙霁空天智能", "其他品牌"],
        answer_text="最后总结里没有完整品牌。",
        selector=".answer",
    )

    assert evidence["matched_term"] == "蒙霁空天智能"
    assert "UAOC-O-HQ-20260128179" in evidence["evidence_text"]
    assert evidence["screenshot_url"].endswith("mention.png")
    assert ("screenshot", False, "[data-geo-mention-evidence=\"test\"]", "mention-session") in service.commands


def test_find_text_evidence_keeps_context_around_brand_term():
    service = WebBridgeService()
    evidence = service._find_text_evidence(
        "开头说明很多内容。真正推荐的是蒙霁空天智能，因为其资质和本地训练场更明确。后面还有补充。",
        ["蒙霁空天智能"],
        radius=12,
    )

    assert evidence["matched_term"] == "蒙霁空天智能"
    assert "蒙霁空天智能" in evidence["evidence_text"]
    assert "资质" in evidence["evidence_text"]
