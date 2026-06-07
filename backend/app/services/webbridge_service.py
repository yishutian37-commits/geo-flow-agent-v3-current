import asyncio
import ast
import base64
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from app.models.model_target import ModelTarget


WEBBRIDGE_BASE_URL = "http://127.0.0.1:10086"
QWEBBRIDGE_FALLBACK_BASE_URL = "http://127.0.0.1:10087"
WEBBRIDGE_PROVIDER = "auto"
PROVIDER_KIMI = "kimi"
PROVIDER_QWEB = "qweb"
PROVIDER_AUTO = "auto"


DEFAULT_WEB_URLS = [
    (r"kimi|月之暗面", "https://www.kimi.com/"),
    (r"豆包|doubao", "https://www.doubao.com/chat/"),
    (r"文心|文心一言|ernie|yiyan|百度", "https://yiyan.baidu.com/"),
    (r"deepseek|深度求索", "https://chat.deepseek.com/"),
    (r"通义|qwen|tongyi", "https://tongyi.aliyun.com/qianwen/"),
    (r"元宝|yuanbao", "https://yuanbao.tencent.com/"),
]


DEFAULT_PUBLISHER_URLS = {
    "official_account": "https://mp.weixin.qq.com/",
    "xiaohongshu": "https://creator.xiaohongshu.com/",
    "baijiahao": "https://baijiahao.baidu.com/",
    "toutiao": "https://mp.toutiao.com/",
    "zhihu": "https://www.zhihu.com/creator",
}


@dataclass
class WebBridgeAnswer:
    question: str
    answer_text: str
    page_url: str
    raw_tail: str
    session: str
    status_warning: Optional[str] = None
    bridge_provider: str = PROVIDER_KIMI
    sources: Optional[List[Dict[str, str]]] = None
    screenshot_url: Optional[str] = None


class WebBridgeError(RuntimeError):
    pass


def default_web_url(target: ModelTarget) -> Optional[str]:
    text = f"{target.product_name or ''} {target.notes or ''}".lower()
    for pattern, url in DEFAULT_WEB_URLS:
        if re.search(pattern, text, flags=re.I):
            return url
    return None


class WebBridgeService:
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 75.0,
        provider: Optional[str] = None,
    ):
        self.base_url = (base_url or os.getenv("WEBBRIDGE_BASE_URL") or WEBBRIDGE_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.provider = (provider or os.getenv("WEBBRIDGE_PROVIDER") or WEBBRIDGE_PROVIDER).strip().lower()
        if self.provider not in {PROVIDER_AUTO, PROVIDER_KIMI, PROVIDER_QWEB}:
            self.provider = PROVIDER_AUTO
        self._resolved_provider: Optional[str] = None
        self.kimi_base_url = (os.getenv("KIMI_WEBBRIDGE_BASE_URL") or self.base_url).rstrip("/")
        self.qweb_base_url = (
            os.getenv("QWEBBRIDGE_BASE_URL")
            or os.getenv("WEBBRIDGE_QWEB_BASE_URL")
            or QWEBBRIDGE_FALLBACK_BASE_URL
        ).rstrip("/")
        self._resolved_base_url: Optional[str] = None

    async def ask_question(
        self,
        target: ModelTarget,
        question: str,
        session: str,
        wait_seconds: int = 60,
    ) -> WebBridgeAnswer:
        status_warning = await self._ensure_available()
        page_url = target.web_url or default_web_url(target)
        if not page_url:
            raise WebBridgeError("检测平台未配置网页版地址，也无法按平台名称推断默认地址")

        if self._target_recognition_mode(target) == "vision":
            return await self._ask_question_with_vision(
                target=target,
                question=question,
                session=session,
                wait_seconds=wait_seconds,
                page_url=page_url,
                status_warning=status_warning,
            )

        await self._command(
            "navigate",
            {
                "url": page_url,
                "newTab": True,
                "group_title": "GEO自动检测",
            },
            session=session,
        )
        await asyncio.sleep(5)
        before_tail = await self._page_text_tail(session=session, selector=target.response_selector)
        await self._fill_and_submit(target, question, session=session, page_url=page_url)
        await asyncio.sleep(1.5)
        if await self._focused_input_contains(question, session=session):
            try:
                await self._click_submit_with_dom_text_agent(session=session, question=question)
                await asyncio.sleep(2)
            except WebBridgeError:
                pass
        if await self._focused_input_contains(question, session=session):
            try:
                await self._command("send_keys", {"keys": "Enter"}, session=session)
                await asyncio.sleep(2)
            except WebBridgeError:
                pass
        if await self._focused_input_contains(question, session=session):
            candidates_hint = await self._submit_candidates_error_hint(session=session)
            raise WebBridgeError(
                "问题已输入到网页，但输入框仍保留该问题，说明没有成功发送。"
                "请在检测平台为该 AI 产品配置 submit_selector，或确认网页发送按钮可见且未禁用。"
                f"{candidates_hint}已停止本次检测，不会继续打开下一题"
            )
        raw_tail = await self._wait_for_answer_tail(
            session=session,
            before_tail=before_tail,
            wait_seconds=max(15, min(wait_seconds, 300)),
            selector=target.response_selector,
            question=question,
        )
        answer_text = self._extract_answer(question, raw_tail, before_tail)
        full_page_text = await self._safe_page_answer_text_full(
            session=session,
            selector=target.response_selector,
            question=question,
        )
        page_answer = self._extract_answer(question, full_page_text, before_tail)
        if self._should_use_page_answer(visual_answer=answer_text, page_answer=page_answer):
            answer_text = page_answer
            raw_tail = full_page_text or raw_tail
        if not self._looks_like_answer(answer_text):
            if await self._focused_input_contains(question, session=session):
                raise WebBridgeError("问题已输入到网页，但没有成功发送，未产生可抓取的回复。已停止本次检测，请检查发送按钮选择器或目标页面状态")
            raise WebBridgeError("未检测到有效回复文本，已停止本次检测。请确认问题已发送、目标页面已登录且回答生成完成")
        sources = await self._extract_answer_sources(
            session=session,
            selector=target.response_selector,
            answer_text=answer_text,
        )
        evidence_screenshot = await self._capture_answer_evidence_screenshot(
            session=session,
            selector=target.response_selector,
            answer_text=answer_text,
        )
        screenshot_url = self._save_screenshot_data(evidence_screenshot, session=session)
        return WebBridgeAnswer(
            question=question,
            answer_text=answer_text,
            page_url=page_url,
            raw_tail=raw_tail,
            session=session,
            status_warning=status_warning,
            bridge_provider=self._resolved_provider or self.provider or PROVIDER_KIMI,
            sources=sources,
            screenshot_url=screenshot_url,
        )

    def _target_recognition_mode(self, target: ModelTarget) -> str:
        mode = str(getattr(target, "recognition_mode", None) or "text").strip().lower()
        return "vision" if mode == "vision" else "text"

    async def capture_mention_evidence(
        self,
        session: str,
        brand_terms: List[str],
        answer_text: str = "",
        selector: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        terms = self._normalize_evidence_terms(brand_terms)
        if not terms:
            return None

        text_evidence = self._find_text_evidence(answer_text, terms)
        dom_evidence = await self._mark_mention_capture_element(
            session=session,
            brand_terms=terms,
            selector=selector,
        )
        evidence = dom_evidence or text_evidence
        if not evidence:
            return None

        screenshot_url = ""
        evidence_selector = evidence.get("selector") if isinstance(evidence, dict) else ""
        screenshot_data = None
        if evidence_selector:
            screenshot_data = await self._capture_screenshot_data(
                session=session,
                selector=evidence_selector,
            )
        if not screenshot_data:
            screenshot_data = await self._capture_answer_evidence_screenshot(
                session=session,
                selector=selector,
                answer_text=answer_text or str(evidence.get("evidence_text") or ""),
            )
        if screenshot_data:
            screenshot_url = self._save_screenshot_data(screenshot_data, session=session) or ""

        return {
            "matched_term": str(evidence.get("matched_term") or ""),
            "evidence_text": str(evidence.get("evidence_text") or ""),
            "screenshot_url": screenshot_url,
            "source": "page_dom" if dom_evidence else "answer_text",
        }

    async def _ask_question_with_vision(
        self,
        target: ModelTarget,
        question: str,
        session: str,
        wait_seconds: int,
        page_url: str,
        status_warning: Optional[str] = None,
    ) -> WebBridgeAnswer:
        await self._command(
            "navigate",
            {
                "url": page_url,
                "newTab": True,
                "group_title": "GEO视觉检测",
            },
            session=session,
        )
        await asyncio.sleep(5)

        screenshot_data = await self._capture_screenshot_data(session=session)
        if not screenshot_data:
            raise WebBridgeError("视觉识别模式无法获取网页截图，请确认 WebBridge 浏览器助手已连接。")

        before_text = await self._safe_page_text_full(session=session, selector=target.response_selector)
        control_warning = ""
        try:
            controls = await self._vision_locate_controls(screenshot_data=screenshot_data)
        except WebBridgeError as exc:
            controls = {}
            control_warning = str(exc)
        input_point = controls.get("input") or {}
        send_point = controls.get("send") or {}
        confidence = float(controls.get("confidence") or 0)
        if input_point and send_point and confidence >= 0.35:
            viewport = await self._viewport_size(session=session)
            input_x, input_y = self._ratio_point_to_viewport(input_point, viewport)
            send_x, send_y = self._ratio_point_to_viewport(send_point, viewport)

            await self._click_point_with_events(input_x, input_y, session=session)
            await asyncio.sleep(0.3)
            await self._command("send_keys", {"keys": "Control+A"}, session=session)
            await self._command("send_keys", {"keys": "Backspace"}, session=session)
            await self._command("key_type", {"text": question}, session=session)
            await asyncio.sleep(0.8)
            await self._click_point_with_events(send_x, send_y, session=session)
        else:
            try:
                await self._fill_and_submit(target, question, session=session, page_url=page_url)
            except WebBridgeError as exc:
                detail = f"视觉定位失败：{control_warning}；" if control_warning else ""
                raise WebBridgeError(
                    f"{detail}网页操作兜底也未能输入或发送问题：{exc}"
                ) from exc

        await asyncio.sleep(1.5)
        if not await self._ensure_question_submitted(question=question, session=session):
            detail = f"视觉定位失败：{control_warning}；" if control_warning else ""
            candidates_hint = await self._submit_candidates_error_hint(session=session)
            raise WebBridgeError(
                f"{detail}问题已输入到网页，但没有成功发送。请确认目标网页已登录、输入框可用，"
                f"或为该检测平台配置 submit_selector。{candidates_hint}"
            )

        answer_result, final_screenshot = await self._wait_for_visual_answer(
            question=question,
            session=session,
            wait_seconds=max(20, min(wait_seconds, 360)),
        )
        answer_text = self._normalize_answer_text_from_model(answer_result.get("answer_text"))
        full_page_text = await self._safe_page_answer_text_full(
            session=session,
            selector=target.response_selector,
            question=question,
        )
        page_answer = self._extract_answer(question, full_page_text, before_text)
        used_dom_answer_fallback = False
        if self._should_use_page_answer(visual_answer=answer_text, page_answer=page_answer):
            answer_text = page_answer
            used_dom_answer_fallback = True
            answer_result = {
                **answer_result,
                "has_answer": True,
                "is_generating": False,
                "answer_text": answer_text,
                "parse_warning": "vision_used_complete_page_text",
            }
        if not self._looks_like_answer(answer_text):
            raise WebBridgeError("视觉识别模式未从截图中识别到有效回答，请适当增加等待时间或确认目标网页已经完成回答。")

        sources = self._normalize_visual_sources(answer_result.get("visible_sources") or [])
        if used_dom_answer_fallback and not sources:
            sources = await self._extract_answer_sources(
                session=session,
                selector=target.response_selector,
                answer_text=answer_text,
            )
        evidence_screenshot = await self._capture_answer_evidence_screenshot(
            session=session,
            selector=target.response_selector,
            answer_text=answer_text,
        )
        screenshot_url = self._save_screenshot_data(evidence_screenshot or final_screenshot, session=session)
        return WebBridgeAnswer(
            question=question,
            answer_text=answer_text,
            page_url=page_url,
            raw_tail=json.dumps(answer_result, ensure_ascii=False),
            session=session,
            bridge_provider=self._resolved_provider or self.provider or PROVIDER_KIMI,
            sources=sources,
            screenshot_url=screenshot_url,
            status_warning=status_warning or control_warning or None,
        )

    async def _vision_locate_controls(self, screenshot_data: str) -> Dict[str, Any]:
        prompt = (
            "请观察截图，定位聊天页面的提问输入框中心点和发送按钮中心点。"
            "返回严格 JSON，不要解释。坐标必须用 0 到 1 的相对比例，基于截图左上角。"
            "格式：{\"input\":{\"x_ratio\":0.5,\"y_ratio\":0.8},"
            "\"send\":{\"x_ratio\":0.9,\"y_ratio\":0.8},\"confidence\":0.0到1.0,"
            "\"reason\":\"一句话\"}。"
            "如果无法确认，confidence 低于 0.35。"
        )
        return await self._call_vision_json(prompt=prompt, screenshot_data=screenshot_data, max_tokens=320)

    async def _wait_for_visual_answer(
        self,
        question: str,
        session: str,
        wait_seconds: int,
    ) -> tuple[Dict[str, Any], str]:
        deadline = asyncio.get_event_loop().time() + wait_seconds
        max_checks = 8
        interval = max(8, min(24, wait_seconds // max_checks or 8))
        best: Dict[str, Any] = {}
        best_screenshot = ""
        last_answer = ""
        stable_hits = 0

        for _ in range(max_checks):
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(interval, max(1, remaining)))
            screenshot_data = await self._capture_screenshot_data(session=session)
            if not screenshot_data:
                continue
            parsed = await self._vision_extract_answer(
                screenshot_data=screenshot_data,
                question=question,
            )
            answer = str(parsed.get("answer_text") or "").strip()
            if answer:
                best = parsed
                best_screenshot = screenshot_data
                normalized = re.sub(r"\s+", " ", answer)
                if normalized == last_answer:
                    stable_hits += 1
                else:
                    stable_hits = 0
                    last_answer = normalized
                if parsed.get("has_answer") and not parsed.get("is_generating") and stable_hits >= 1:
                    return parsed, screenshot_data

        if best:
            return best, best_screenshot
        final_screenshot = await self._capture_screenshot_data(session=session)
        return {}, final_screenshot or ""

    async def _vision_extract_answer(self, screenshot_data: str, question: str) -> Dict[str, Any]:
        prompt = (
            "你正在帮 GEO 监测系统读取 AI 网页回答。请只根据截图里可见内容识别，不要补写、不要猜测。"
            f"用户问题是：{question}\n"
            "只要截图里已经出现 AI 对该问题的回答正文，即使不是完整全文，也要把可见正文提取到 answer_text。"
            "不要因为回答未完全显示、没有来源链接、或没有看到提问文本就返回空。"
            "请忽略页面导航、输入框占位符、按钮、推荐问题、广告和无关菜单。"
            "返回严格 JSON：{\"has_answer\":true/false,\"is_generating\":true/false,"
            "\"answer_text\":\"截图中可见的完整回答文本\","
            "\"visible_sources\":[{\"title\":\"可见来源标题\",\"url\":\"可见URL\"}],"
            "\"confidence\":0.0到1.0}。"
            "如果回答仍在生成，is_generating=true；如果没有看到回答，has_answer=false 且 answer_text 为空。"
        )
        return await self._call_vision_json(
            prompt=prompt,
            screenshot_data=screenshot_data,
            max_tokens=1800,
            allow_text_fallback=True,
        )

    async def _call_vision_json(
        self,
        prompt: str,
        screenshot_data: str,
        max_tokens: int = 800,
        allow_text_fallback: bool = False,
    ) -> Dict[str, Any]:
        try:
            from app.llm.client import LLMClientFactory
            from app.llm.registry import get_model_registry

            registry = get_model_registry()
            config = self._select_vision_model_config(registry)
            if not config or not config.api_key:
                raise WebBridgeError(
                    "视觉识别模式需要先在 AI 模型里配置一个支持图片理解的大模型。"
                    "当前默认模型很可能是纯文本模型，所以截图识别会返回空。"
                    "建议新增或设为默认：gpt-4o、gpt-4.1、qwen-vl、glm-4v、doubao-vision、moonshot vision 等视觉模型。"
                )
            client = LLMClientFactory.create_client_from_config(config.to_dict(mask_api_key=False))
            image_url = f"data:image/png;base64,{screenshot_data}"
            response = await client.chat(
                messages=[
                    {"role": "system", "content": "你是网页视觉识别助手。只输出 JSON，不输出解释。"},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    },
                ],
                temperature=0,
                max_tokens=max_tokens,
            )
            response_text = self._extract_llm_response_text(response)
            parsed = self._extract_json_object(response_text)
            if not parsed:
                raw_text = self._clean_model_text(response_text)
                if allow_text_fallback and raw_text:
                    return {
                        "has_answer": True,
                        "is_generating": False,
                        "answer_text": self._limit_answer_text(raw_text),
                        "visible_sources": [],
                        "confidence": 0.35,
                        "parse_warning": "vision_model_returned_plain_text",
                    }
                preview = raw_text[:240] if raw_text else self._summarize_llm_raw_response(response)
                raise WebBridgeError(f"视觉识别模型没有返回可解析的 JSON。模型原始输出：{preview}")
            return parsed
        except WebBridgeError:
            raise
        except Exception as exc:
            detail = str(exc).strip() or repr(exc) or exc.__class__.__name__
            raise WebBridgeError(f"视觉识别模式调用多模态模型失败：{detail}") from exc

    async def _ensure_question_submitted(self, question: str, session: str) -> bool:
        if not await self._focused_input_contains(question, session=session):
            return True
        try:
            await self._click_submit_with_dom_text_agent(session=session, question=question)
            await asyncio.sleep(2)
        except WebBridgeError:
            pass
        if not await self._focused_input_contains(question, session=session):
            return True
        try:
            await self._command("send_keys", {"keys": "Enter"}, session=session)
            await asyncio.sleep(2)
        except WebBridgeError:
            pass
        return not await self._focused_input_contains(question, session=session)

    def _select_vision_model_config(self, registry):
        configured = registry.list_models(active_only=True, configured_only=True)
        default = registry.get_default_model()
        if default and self._looks_like_vision_model(default):
            return default
        for config in configured:
            if self._looks_like_vision_model(config):
                return config
        return None

    def _looks_like_vision_model(self, config) -> bool:
        explicit_supports_vision = getattr(config, "supports_vision", None)
        if explicit_supports_vision is True:
            return True
        if explicit_supports_vision is False:
            return False
        text = " ".join([
            str(getattr(config, "provider", "") or ""),
            str(getattr(config, "model", "") or ""),
            str(getattr(config, "name", "") or ""),
            str(getattr(config, "description", "") or ""),
            " ".join(getattr(config, "tags", []) or []),
        ]).lower()
        vision_markers = [
            "vision", "visual", "image", "multimodal", "multi-modal", "omni",
            "视觉", "图像", "图片", "多模态", "截图",
            "gpt-4o", "gpt-4.1", "qwen-vl", "qvq", "glm-4v", "glm-4.5v",
            "moonshot-v1-8k-vision", "doubao-vision", "yi-vision", "step-1v",
            "mimo-v2.5", "mimo-v2-5", "mimo-v2-omni", "mimo-v2.5-omni",
            "claude-3", "gemini", "vl",
        ]
        compact_text = re.sub(r"[^a-z0-9]+", "", text)
        if "minimaxm3" in compact_text or ("minimax" in text and re.search(r"(^|[^a-z0-9])m3([^a-z0-9]|$)", text)):
            return True
        return any(marker in text for marker in vision_markers)

    def _extract_llm_response_text(self, response) -> str:
        parts: List[str] = []
        content = getattr(response, "content", None)
        self._append_text_parts(content, parts)
        raw = getattr(response, "raw_response", None)
        if raw:
            self._append_text_parts(raw, parts, keys={"content", "text", "output_text", "reasoning_content"})
        return "\n".join(part for part in parts if part).strip()

    def _append_text_parts(self, value, parts: List[str], keys: Optional[set[str]] = None) -> None:
        if value is None:
            return
        if isinstance(value, str):
            if value.strip():
                parts.append(value.strip())
            return
        if isinstance(value, dict):
            for key, nested in value.items():
                if keys is None or key in keys:
                    self._append_text_parts(nested, parts, keys=None)
                elif isinstance(nested, (dict, list)):
                    self._append_text_parts(nested, parts, keys=keys)
            return
        if isinstance(value, list):
            for item in value:
                self._append_text_parts(item, parts, keys=keys)

    def _summarize_llm_raw_response(self, response) -> str:
        raw = getattr(response, "raw_response", None)
        if not raw:
            return (
                "空。模型没有返回任何文本，通常说明当前选择的不是视觉模型，"
                "或该接口不支持 image_url 图片输入。"
            )
        try:
            summary = json.dumps(raw, ensure_ascii=False)[:500]
        except Exception:
            summary = str(raw)[:500]
        return summary or "空"

    async def _viewport_size(self, session: str) -> Dict[str, float]:
        code = """
(() => JSON.stringify({
  width: window.innerWidth || document.documentElement.clientWidth || 1366,
  height: window.innerHeight || document.documentElement.clientHeight || 768
}))()
"""
        try:
            result = await self._command("evaluate", {"code": code}, session=session)
            value = result.get("value")
            parsed = json.loads(value) if isinstance(value, str) else value
            if isinstance(parsed, dict):
                return {"width": float(parsed.get("width") or 1366), "height": float(parsed.get("height") or 768)}
        except Exception:
            pass
        return {"width": 1366.0, "height": 768.0}

    def _ratio_point_to_viewport(self, point: Dict[str, Any], viewport: Dict[str, float]) -> tuple[int, int]:
        x_ratio = max(0.0, min(1.0, float(point.get("x_ratio") or point.get("x") or 0.5)))
        y_ratio = max(0.0, min(1.0, float(point.get("y_ratio") or point.get("y") or 0.5)))
        return (
            int(round(x_ratio * float(viewport.get("width") or 1366))),
            int(round(y_ratio * float(viewport.get("height") or 768))),
        )

    def _normalize_visual_sources(self, sources: Any) -> List[Dict[str, str]]:
        if not isinstance(sources, list):
            return []
        normalized: List[Dict[str, str]] = []
        seen: set[str] = set()
        for item in sources:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or "").strip()
            if not url or not re.match(r"^https?://", url, flags=re.I):
                continue
            if url in seen:
                continue
            seen.add(url)
            normalized.append(
                {
                    "title": title or url,
                    "url": url,
                    "source_type": "vision_ocr",
                    "context": "视觉识别模式从截图中识别到的可见来源",
                }
            )
        return normalized[:20]

    async def open_publish_page(
        self,
        page_url: str,
        title: str,
        body: str,
        session: str,
        title_selector: Optional[str] = None,
        body_selector: Optional[str] = None,
    ) -> Dict[str, Any]:
        """打开发布编辑页并尽量预填标题正文；不会点击发布按钮。"""
        status_warning = await self._ensure_available()
        if not page_url:
            raise WebBridgeError("发布渠道未配置发布编辑页 URL")

        await self._command(
            "navigate",
            {
                "url": page_url,
                "newTab": True,
                "group_title": "GEO发布助手",
            },
            session=session,
        )
        await asyncio.sleep(3)
        result = await self._command(
            "evaluate",
            {
                "code": self._publish_prefill_script(
                    title=title,
                    body=body,
                    title_selector=title_selector,
                    body_selector=body_selector,
                )
            },
            session=session,
        )
        value = result.get("value")
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
        except json.JSONDecodeError:
            parsed = {"ok": False, "error": value}
        if not isinstance(parsed, dict):
            parsed = {"ok": False, "error": str(parsed)}
        return {
            **parsed,
            "page_url": page_url,
            "session": session,
            "status_warning": status_warning,
            "bridge_provider": self._resolved_provider or self.provider or PROVIDER_KIMI,
        }

    async def _legacy_kimi_get_status(self) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                response = await client.get(f"{self.base_url}/status")
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError as exc:
            raise WebBridgeError("Kimi WebBridge 未启动或端口 10086 不可用，请先启动浏览器桥接服务") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response else 0
            if status_code in {502, 503, 504}:
                return await self._probe_command_status(f"状态接口返回 HTTP {status_code}")
            raise WebBridgeError(f"Kimi WebBridge 状态检查失败：HTTP {exc.response.status_code}") from exc
        except httpx.TimeoutException as exc:
            raise WebBridgeError("Kimi WebBridge 状态检查超时，请重启浏览器桥接服务后再试") from exc
        except Exception as exc:
            raise WebBridgeError(f"Kimi WebBridge 状态检查失败：{exc}") from exc
        return data if isinstance(data, dict) else {}

    async def _probe_command_status(self, status_error: str) -> Dict[str, Any]:
        payload = {"action": "list_tabs", "args": {}, "session": "geo-status-probe"}
        try:
            async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
                response = await client.post(f"{self.kimi_base_url}/command", json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise WebBridgeError(f"Kimi WebBridge {status_error}，且命令探测也失败：{exc}") from exc

        if not isinstance(data, dict) or data.get("ok") is False:
            raise WebBridgeError(
                f"Kimi WebBridge {status_error}，命令探测返回失败：{self._payload_error_message(data.get('error') if isinstance(data, dict) else data)}"
            )
        return {
            "running": True,
            "extension_connected": True,
            "version": None,
            "extension_version": None,
            "status_endpoint_error": status_error,
            "command_probe_ok": True,
        }

    async def get_status(self) -> Dict[str, Any]:
        errors: list[str] = []
        warnings: list[str] = []
        for provider in self._provider_candidates():
            try:
                status = await self._get_provider_status(provider)
                # auto 模式下，优先选择扩展已连接的 provider
                if self.provider == PROVIDER_AUTO and not status.get("extension_connected"):
                    warnings.append(f"{provider}: 服务运行中但浏览器扩展未连接")
                    continue
                self._resolved_provider = provider
                return status
            except WebBridgeError as exc:
                errors.append(f"{provider}: {exc}")
        all_issues = errors + warnings
        if all_issues:
            raise WebBridgeError("；".join(all_issues))
        raise WebBridgeError("未找到可用的 WebBridge Provider")

    def _provider_candidates(self) -> list[str]:
        if self.provider == PROVIDER_QWEB:
            return [PROVIDER_QWEB]
        if self.provider == PROVIDER_KIMI:
            return [PROVIDER_KIMI]
        return [PROVIDER_QWEB, PROVIDER_KIMI]

    async def _get_provider_status(self, provider: str) -> Dict[str, Any]:
        if provider == PROVIDER_QWEB:
            return await self._qweb_status()
        return await self._kimi_status()

    async def _kimi_status(self) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                response = await client.get(f"{self.kimi_base_url}/status")
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError as exc:
            raise WebBridgeError("官方 Kimi WebBridge 未启动或端口不可用") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response else 0
            if status_code in {502, 503, 504}:
                return await self._probe_kimi_command_status(f"状态接口返回 HTTP {status_code}")
            raise WebBridgeError(f"官方 Kimi WebBridge 状态检查失败：HTTP {status_code}") from exc
        except httpx.TimeoutException as exc:
            raise WebBridgeError("官方 Kimi WebBridge 状态检查超时") from exc
        except Exception as exc:
            raise WebBridgeError(f"官方 Kimi WebBridge 状态检查失败：{exc}") from exc

        if not isinstance(data, dict):
            raise WebBridgeError("官方 Kimi WebBridge 状态响应格式异常")
        self._resolved_base_url = self.kimi_base_url
        data["bridge_provider"] = PROVIDER_KIMI
        data["provider_name"] = "Kimi WebBridge"
        data["base_url"] = self.kimi_base_url
        return data

    async def _qweb_status(self) -> Dict[str, Any]:
        last_error: Optional[Exception] = None
        for base_url in self._qweb_base_candidates():
            try:
                async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                    response = await client.get(f"{base_url}/health")
                    response.raise_for_status()
                    data = response.json()
                self._resolved_base_url = base_url
                break
            except (httpx.ConnectError, httpx.HTTPStatusError, httpx.TimeoutException, Exception) as exc:
                last_error = exc
                continue
        else:
            raise WebBridgeError(f"QWebBridge 未启动或健康检查失败：{last_error}") from last_error

        if not isinstance(data, dict):
            raise WebBridgeError("QWebBridge 健康检查响应格式异常")
        return {
            **data,
            "bridge_provider": PROVIDER_QWEB,
            "provider_name": "QWebBridge",
            "version": data.get("version") or "1.0.0",
            "extension_version": data.get("extension_version") or data.get("version") or "1.0.0",
            "extension_connected": bool(data.get("extensions_connected")),
            "extensions_connected": bool(data.get("extensions_connected")),
            "base_url": self._resolved_base_url,
            "extension_path": os.getenv("QWEBBRIDGE_EXTENSION_PATH"),
        }

    def _qweb_base_candidates(self) -> list[str]:
        candidates = [self.qweb_base_url]
        if self.provider == PROVIDER_AUTO and QWEBBRIDGE_FALLBACK_BASE_URL not in candidates:
            candidates.append(QWEBBRIDGE_FALLBACK_BASE_URL)
        return candidates

    async def _probe_kimi_command_status(self, status_error: str) -> Dict[str, Any]:
        payload = {"action": "list_tabs", "args": {}, "session": "geo-status-probe"}
        try:
            async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
                response = await client.post(f"{self.base_url}/command", json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise WebBridgeError(f"官方 Kimi WebBridge {status_error}，且命令探测也失败：{exc}") from exc

        if not isinstance(data, dict) or data.get("ok") is False:
            raise WebBridgeError(
                f"官方 Kimi WebBridge {status_error}，命令探测返回失败：{self._payload_error_message(data.get('error') if isinstance(data, dict) else data)}"
            )
        self._resolved_base_url = self.kimi_base_url
        return {
            "running": True,
            "extension_connected": True,
            "version": None,
            "extension_version": None,
            "status_endpoint_error": status_error,
            "command_probe_ok": True,
            "bridge_provider": PROVIDER_KIMI,
            "provider_name": "Kimi WebBridge",
            "base_url": self.kimi_base_url,
        }

    async def _legacy_kimi_ensure_available(self) -> Optional[str]:
        status = await self.get_status()
        if status.get("running") is False:
            raise WebBridgeError("Kimi WebBridge 后台服务未运行，请先启动 WebBridge")
        if status.get("extension_connected") is False:
            raise WebBridgeError("Kimi WebBridge 浏览器扩展未连接，请打开浏览器并确认扩展已启用")

        daemon_version = self._normalize_version(status.get("version"))
        extension_version = self._normalize_version(status.get("extension_version"))
        if daemon_version and extension_version and daemon_version != extension_version:
            return (
                f"Kimi WebBridge 后台版本为 {status.get('version')}，浏览器扩展版本为 "
                f"{status.get('extension_version')}，两者不一致时可能导致网页命令 502 或超时。"
            )
        return None

    async def _ensure_available(self) -> Optional[str]:
        status = await self.get_status()
        provider_name = status.get("provider_name") or status.get("bridge_provider") or "WebBridge"
        if status.get("running") is False:
            raise WebBridgeError(f"{provider_name} 后台服务未运行，请先启动浏览器桥接服务")
        if status.get("extension_connected") is False:
            raise WebBridgeError(f"{provider_name} 浏览器扩展未连接，请打开浏览器并确认扩展已启用")

        daemon_version = self._normalize_version(status.get("version"))
        extension_version = self._normalize_version(status.get("extension_version"))
        if status.get("bridge_provider") == PROVIDER_KIMI and daemon_version and extension_version and daemon_version != extension_version:
            return (
                f"Kimi WebBridge 后台版本为 {status.get('version')}，浏览器扩展版本为 "
                f"{status.get('extension_version')}，两者不一致时可能导致网页命令 502 或超时。"
            )
        return None

    def _normalize_version(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        return text[1:] if text.startswith("v") else text

    async def _legacy_kimi_command(self, action: str, args: Dict[str, Any], session: str) -> Dict[str, Any]:
        payload = {"action": action, "args": args, "session": session}
        last_error: Optional[WebBridgeError] = None
        data: Dict[str, Any] = {}

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                    response = await client.post(f"{self.base_url}/command", json=payload)
                    if response.status_code >= 400:
                        error = WebBridgeError(self._http_error_detail(response, action))
                        if response.status_code in {502, 503, 504} and attempt < 2:
                            last_error = error
                            await asyncio.sleep(1.2 * (attempt + 1))
                            continue
                        raise error
                    try:
                        parsed = response.json()
                    except json.JSONDecodeError as exc:
                        raise WebBridgeError(f"Kimi WebBridge 返回了无法解析的响应：{response.text[:500]}") from exc
                    if not isinstance(parsed, dict):
                        raise WebBridgeError(f"Kimi WebBridge 返回了异常响应：{str(parsed)[:500]}")
                    data = parsed
                    break
            except httpx.ConnectError as exc:
                raise WebBridgeError("Kimi WebBridge 未启动或端口 10086 不可用，请先安装并启动浏览器桥接插件") from exc
            except httpx.TimeoutException as exc:
                if attempt < 2:
                    await asyncio.sleep(1.2 * (attempt + 1))
                    continue
                status = await self._status_summary()
                raise WebBridgeError(f"Kimi WebBridge 调用超时，请确认目标网页已打开、已登录且没有卡在验证页面。{status}") from exc
            except WebBridgeError:
                raise
            except Exception as exc:
                raise WebBridgeError(f"Kimi WebBridge 调用失败：{exc}") from exc
        else:
            if last_error:
                raise last_error
            raise WebBridgeError("Kimi WebBridge 调用失败：未知错误")

        if data.get("ok") is False:
            raise WebBridgeError(self._payload_error_message(data.get("error")) or "Kimi WebBridge 返回失败")
        command_data = data.get("data", data)
        if isinstance(command_data, dict) and command_data.get("success") is False:
            raise WebBridgeError(self._payload_error_message(command_data.get("error")) or "Kimi WebBridge 命令执行失败")
        return command_data

    async def _command(self, action: str, args: Dict[str, Any], session: str) -> Dict[str, Any]:
        provider = self._resolved_provider or (await self.get_status()).get("bridge_provider") or PROVIDER_KIMI
        if provider == PROVIDER_QWEB:
            return await self._qweb_command(action, args, session)
        return await self._kimi_command(action, args, session)

    async def _kimi_command(self, action: str, args: Dict[str, Any], session: str) -> Dict[str, Any]:
        payload = {"action": action, "args": args, "session": session}
        last_error: Optional[WebBridgeError] = None
        data: Dict[str, Any] = {}
        base_url = self._resolved_base_url or self.kimi_base_url

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                    response = await client.post(f"{base_url}/command", json=payload)
                    if response.status_code >= 400:
                        error = WebBridgeError(self._http_error_detail(response, action))
                        if response.status_code in {502, 503, 504} and attempt < 2:
                            last_error = error
                            await asyncio.sleep(1.2 * (attempt + 1))
                            continue
                        raise error
                    data = self._parse_json_response(response, "Kimi WebBridge")
                    break
            except httpx.ConnectError as exc:
                raise WebBridgeError("Kimi WebBridge 未启动或端口不可用，请先安装并启动浏览器桥接插件") from exc
            except httpx.TimeoutException as exc:
                if attempt < 2:
                    await asyncio.sleep(1.2 * (attempt + 1))
                    continue
                status = await self._status_summary()
                raise WebBridgeError(f"Kimi WebBridge 调用超时，请确认目标网页已打开、已登录且没有卡在验证页面。{status}") from exc
            except WebBridgeError:
                raise
            except Exception as exc:
                raise WebBridgeError(f"Kimi WebBridge 调用失败：{exc}") from exc
        else:
            if last_error:
                raise last_error
            raise WebBridgeError("Kimi WebBridge 调用失败：未知错误")

        if data.get("ok") is False:
            raise WebBridgeError(self._payload_error_message(data.get("error")) or "Kimi WebBridge 返回失败")
        command_data = data.get("data", data)
        if isinstance(command_data, dict) and command_data.get("success") is False:
            raise WebBridgeError(self._payload_error_message(command_data.get("error")) or "Kimi WebBridge 命令执行失败")
        return command_data if isinstance(command_data, dict) else {"value": command_data}

    async def _qweb_command(self, action: str, args: Dict[str, Any], session: str) -> Dict[str, Any]:
        payload = {**(args or {}), "_session": session}
        last_error: Optional[WebBridgeError] = None
        data: Dict[str, Any] = {}
        base_url = self._resolved_base_url or self.qweb_base_url

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                    response = await client.post(f"{base_url}/api/tool/{action}", json=payload)
                    if response.status_code >= 400:
                        error = WebBridgeError(self._qweb_http_error_detail(response, action))
                        if response.status_code in {500, 502, 503, 504} and attempt < 2:
                            last_error = error
                            await asyncio.sleep(1.2 * (attempt + 1))
                            continue
                        raise error
                    data = self._parse_json_response(response, "QWebBridge")
                    break
            except httpx.ConnectError as exc:
                raise WebBridgeError("QWebBridge 未启动或端口不可用，请先启动 qweb-bridge 并确认浏览器扩展已连接") from exc
            except httpx.TimeoutException as exc:
                if attempt < 2:
                    await asyncio.sleep(1.2 * (attempt + 1))
                    continue
                status = await self._status_summary()
                raise WebBridgeError(f"QWebBridge 调用超时，请确认目标网页已打开、已登录且没有卡在验证页面。{status}") from exc
            except WebBridgeError:
                raise
            except Exception as exc:
                raise WebBridgeError(f"QWebBridge 调用失败：{exc}") from exc
        else:
            if last_error:
                raise last_error
            raise WebBridgeError("QWebBridge 调用失败：未知错误")

        if data.get("success") is False:
            raise WebBridgeError(self._payload_error_message(data.get("error")) or "QWebBridge 命令执行失败")
        result = data.get("result", data)
        if isinstance(result, dict) and result.get("success") is False:
            raise WebBridgeError(self._payload_error_message(result.get("error")) or "QWebBridge 命令执行失败")
        if action == "evaluate" and not isinstance(result, dict):
            return {"value": result}
        if action == "snapshot" and isinstance(result, list):
            return {"tree": result}
        return result if isinstance(result, dict) else {"value": result}

    def _parse_json_response(self, response: httpx.Response, provider_name: str) -> Dict[str, Any]:
        try:
            parsed = response.json()
        except json.JSONDecodeError as exc:
            raise WebBridgeError(f"{provider_name} 返回了无法解析的响应：{response.text[:500]}") from exc
        if not isinstance(parsed, dict):
            raise WebBridgeError(f"{provider_name} 返回了异常响应：{str(parsed)[:500]}")
        return parsed

    def _qweb_http_error_detail(self, response: httpx.Response, action: str) -> str:
        body = (response.text or "").strip()
        if len(body) > 700:
            body = f"{body[:700]}..."
        return f"QWebBridge HTTP {response.status_code}：动作 {action} 执行失败。原始响应：{body or response.reason_phrase}"

    async def _legacy_status_summary(self) -> str:
        try:
            status = await self.get_status()
        except WebBridgeError as exc:
            return f"状态检查也失败：{exc}"
        daemon = status.get("version") or "未知"
        extension = status.get("extension_version") or "未知"
        connected = status.get("extension_connected")
        return f"当前状态：daemon={daemon}，extension={extension}，extension_connected={connected}。"

    async def _status_summary(self) -> str:
        try:
            status = await self.get_status()
        except WebBridgeError as exc:
            return f"状态检查也失败：{exc}"
        provider = status.get("provider_name") or status.get("bridge_provider") or "WebBridge"
        daemon = status.get("version") or "未知"
        extension = status.get("extension_version") or "未知"
        connected = status.get("extension_connected")
        return f"当前状态：provider={provider}，daemon={daemon}，extension={extension}，extension_connected={connected}。"

    def _legacy_http_error_detail(self, response: httpx.Response, action: str) -> str:
        body = (response.text or "").strip()
        if len(body) > 700:
            body = f"{body[:700]}..."
        if response.status_code == 502:
            return (
                f"Kimi WebBridge 返回 502：动作 {action} 执行失败。"
                "常见原因是目标 AI 网页未登录、页面仍在加载/验证、当前选择器不匹配，"
                f"或浏览器标签页被关闭。WebBridge 原始响应：{body or '空'}"
            )
        return f"Kimi WebBridge HTTP {response.status_code}：{body or response.reason_phrase}"

    def _http_error_detail(self, response: httpx.Response, action: str) -> str:
        body = (response.text or "").strip()
        if len(body) > 700:
            body = f"{body[:700]}..."
        if response.status_code == 502:
            return (
                f"Kimi WebBridge 返回 502：动作 {action} 执行失败。"
                "常见原因是官方桥接服务/扩展连接不稳定、目标 AI 网页未登录、页面仍在加载或验证、"
                f"当前选择器不匹配，或浏览器标签页被关闭。WebBridge 原始响应：{body or '空'}"
            )
        return f"Kimi WebBridge HTTP {response.status_code}：{body or response.reason_phrase}"

    def _legacy_payload_error_message(self, error: Any) -> str:
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message")
            return "：".join(str(item) for item in [code, message] if item)
        return str(error or "")

    def _payload_error_message(self, error: Any) -> str:
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message")
            return "：".join(str(item) for item in [code, message] if item)
        return str(error or "")

    def _default_submit_selector(self, target: ModelTarget, page_url: Optional[str] = None) -> str:
        text = " ".join(
            str(value or "")
            for value in [
                getattr(target, "product_name", ""),
                getattr(target, "notes", ""),
                getattr(target, "web_url", ""),
                page_url or "",
            ]
        ).lower()
        if re.search(r"文心|文心一言|ernie|yiyan|百度|baidu", text, flags=re.I):
            return '[class*="send__"]'
        return ""

    async def _fill_and_submit(
        self,
        target: ModelTarget,
        question: str,
        session: str,
        page_url: Optional[str] = None,
    ) -> None:
        native_error: Optional[str] = None
        configured_input_selector = (target.input_selector or "").strip()
        configured_submit_selector = (target.submit_selector or "").strip() or self._default_submit_selector(target, page_url)
        input_selector = configured_input_selector or await self._find_textbox_ref(session)
        if input_selector:
            try:
                await self._type_question_like_user(input_selector, question, session=session)
                if configured_submit_selector:
                    await self._click_selector_with_events(configured_submit_selector, session=session)
                else:
                    await self._click_submit_or_press_enter(session)
                return
            except WebBridgeError as exc:
                native_error = str(exc)

        code = self._fill_submit_script(
            question=question,
            input_selector=None if native_error else configured_input_selector,
            submit_selector=None if native_error else configured_submit_selector,
        )
        result = await self._command("evaluate", {"code": code}, session=session)
        value = result.get("value")
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
        except json.JSONDecodeError:
            parsed = {"ok": False, "error": value}
        if not parsed or not parsed.get("ok"):
            snapshot = await self._snapshot_excerpt(session)
            error = parsed.get("error") if isinstance(parsed, dict) else "未能输入问题"
            native_note = f"原生 fill/click 也失败：{native_error}。" if native_error else ""
            raise WebBridgeError(f"{native_note}{error}。页面快照：{snapshot}")

    async def _type_question_like_user(self, input_selector: str, question: str, session: str) -> None:
        key_type_error: Optional[str] = None
        try:
            await self._command("click", {"selector": input_selector}, session=session)
            await asyncio.sleep(0.2)
            await self._clear_focused_input(input_selector, session=session)
            await self._command("key_type", {"text": question}, session=session)
            await asyncio.sleep(0.5)
            if await self._focused_input_contains(question, session=session):
                return
            key_type_error = "真实键盘输入后页面仍未识别到问题文本"
        except WebBridgeError as exc:
            key_type_error = str(exc)

        try:
            await self._command("fill", {"selector": input_selector, "value": question}, session=session)
            await asyncio.sleep(0.5)
            if await self._focused_input_contains(question, session=session):
                return
        except WebBridgeError as exc:
            raise WebBridgeError(f"真实键盘输入失败：{key_type_error}；fill 兜底也失败：{exc}") from exc

        raise WebBridgeError(
            "已尝试真实键盘输入和 fill 兜底，但目标网页没有识别到问题文本。"
            f"真实键盘输入失败原因：{key_type_error}"
        )

    async def _clear_focused_input(self, input_selector: str, session: str) -> None:
        try:
            await self._command("send_keys", {"keys": "Control+A"}, session=session)
            await self._command("send_keys", {"keys": "Backspace"}, session=session)
            return
        except WebBridgeError:
            pass

        if str(input_selector).startswith("@"):
            return

        selector_literal = json.dumps(input_selector)
        code = f"""
(() => {{
  const selector = {selector_literal};
  const input = document.querySelector(selector);
  if (!input) return JSON.stringify({{ok:false,error:'未找到输入框'}});
  input.focus();
  if (input.isContentEditable || input.getAttribute('contenteditable') === 'true' || input.getAttribute('role') === 'textbox') {{
    const range = document.createRange();
    range.selectNodeContents(input);
    const selection = window.getSelection();
    if (selection) {{
      selection.removeAllRanges();
      selection.addRange(range);
    }}
    document.execCommand('delete', false, null);
    input.dispatchEvent(new InputEvent('input', {{bubbles:true, inputType:'deleteContentBackward'}}));
  }} else {{
    const proto = input.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    if (setter) setter.call(input, ''); else input.value = '';
    input.dispatchEvent(new Event('input', {{bubbles:true}}));
    input.dispatchEvent(new Event('change', {{bubbles:true}}));
  }}
  return JSON.stringify({{ok:true}});
}})()
"""
        await self._command("evaluate", {"code": code}, session=session)

    async def _focused_input_contains(self, question: str, session: str) -> bool:
        needle = (question or "").strip()[:12]
        needle_literal = json.dumps(needle)
        code = f"""
(() => {{
  const needle = {needle_literal};
  const visible = (el) => {{
    if (!el) return false;
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  }};
  const editableSelector = '[role="textbox"], textarea, [contenteditable="true"], [contenteditable="plaintext-only"], input[type="text"], input:not([type])';
  const active = document.activeElement;
  const input = active && active.matches && active.matches(editableSelector)
    ? active
    : Array.from(document.querySelectorAll(editableSelector)).reverse().find(visible);
  if (!input) return JSON.stringify({{ok:false,text:''}});
  const text = ('value' in input ? input.value : '') || input.innerText || input.textContent || '';
  const normalized = String(text).replace(/\\s+/g, ' ').trim();
  return JSON.stringify({{ok: Boolean(needle && normalized.includes(needle)), text: normalized.slice(-160)}});
}})()
"""
        try:
            result = await self._command("evaluate", {"code": code}, session=session)
            value = result.get("value")
            parsed = json.loads(value) if isinstance(value, str) else value
            return bool(isinstance(parsed, dict) and parsed.get("ok"))
        except Exception:
            return False

    async def _find_textbox_ref(self, session: str) -> Optional[str]:
        try:
            data = await self._command("snapshot", {}, session=session)
        except WebBridgeError:
            return None
        return self._find_ref_by_role(data.get("tree") if isinstance(data, dict) else data, "textbox")

    def _find_ref_by_role(self, node: Any, role: str) -> Optional[str]:
        if isinstance(node, dict):
            if node.get("role") == role and node.get("ref"):
                return str(node["ref"])
            for value in node.values():
                found = self._find_ref_by_role(value, role)
                if found:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = self._find_ref_by_role(item, role)
                if found:
                    return found
        return None

    async def _press_enter(self, session: str) -> None:
        code = """
(() => {
  const input = Array.from(document.querySelectorAll('[role="textbox"], textarea, [contenteditable="true"], [contenteditable="plaintext-only"]'))
    .reverse()
    .find((el) => {
      const rect = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
    });
  if (!input) return JSON.stringify({ok:false,error:'未找到可提交的问题文本框'});
  input.focus();
  const init = {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true, cancelable:true};
  input.dispatchEvent(new KeyboardEvent('keydown', init));
  input.dispatchEvent(new KeyboardEvent('keypress', init));
  input.dispatchEvent(new KeyboardEvent('keyup', init));
  return JSON.stringify({ok:true});
})()
"""
        result = await self._command("evaluate", {"code": code}, session=session)
        value = result.get("value")
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
        except json.JSONDecodeError:
            parsed = {"ok": False, "error": value}
        if not parsed or not parsed.get("ok"):
            raise WebBridgeError(parsed.get("error") if isinstance(parsed, dict) else "未能提交问题")

    async def _click_submit_or_press_enter(self, session: str) -> Dict[str, Any]:
        code = """
(() => {
  const visible = (el) => {
    if (!el) return false;
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const enabled = (el) => !el.disabled && el.getAttribute('aria-disabled') !== 'true' && !String(el.className || '').toLowerCase().includes('disabled');
  const labelOf = (btn) => (btn.innerText || btn.getAttribute('aria-label') || btn.title || btn.getAttribute('data-testid') || String(btn.className || '') || '').trim();
  const submitLabelPattern = /发送|提交|Send|Submit|Ask|send__|send-btn|send-button|send_button/i;
  const clickable = (el) => {
    if (!el) return false;
    const style = getComputedStyle(el);
    const label = labelOf(el);
    return style.cursor === 'pointer' || typeof el.onclick === 'function' || el.getAttribute('role') === 'button' || submitLabelPattern.test(label);
  };
  const input = Array.from(document.querySelectorAll('[role="textbox"], textarea, [contenteditable="true"], [contenteditable="plaintext-only"], input[type="text"], input:not([type])'))
    .reverse()
    .find(visible);
  if (!input) return JSON.stringify({ok:false,error:'未找到可提交的问题文本框'});
  input.focus();
  const submitLikeSelector = [
    'button',
    '[role="button"]',
    '[class*="send__"]',
    '[class*="send"]',
    '[class*="send-button"]',
    '[class*="send_button"]',
    '[class*="submit"]',
    '[data-testid*="send"]',
    '[data-testid*="submit"]',
    '[aria-label*="发送"]',
    '[aria-label*="Send"]'
  ].join(',');
  const buttons = Array.from(document.querySelectorAll(submitLikeSelector)).filter((btn) => {
    if (!visible(btn) || !enabled(btn)) return false;
    const rect = btn.getBoundingClientRect();
    return rect.width <= 120 && rect.height <= 80;
  });
  const byText = buttons.find((btn) => btn.tagName === 'BUTTON' && submitLabelPattern.test(labelOf(btn)))
    || buttons.find((btn) => submitLabelPattern.test(labelOf(btn)));
  const inputRect = input.getBoundingClientRect();
  const nearIconSelector = 'button,[role="button"],[onclick],svg,path,[class*="send__"],[class*="send"],[class*="submit"],[aria-label*="发送"],[aria-label*="Send"]';
  const iconRoots = Array.from(document.querySelectorAll(nearIconSelector))
    .map((node) => node.closest('button,[role="button"],[onclick],[class*="send__"],[class*="submit"]') || node)
    .filter((node, index, arr) => arr.indexOf(node) === index)
    .filter((node) => {
      if (!visible(node) || !enabled(node)) return false;
      const rect = node.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      const nearRight = centerX >= inputRect.right - 220 && centerX <= inputRect.right + 120;
      const nearVertical = centerY >= inputRect.top - 30 && centerY <= inputRect.bottom + 50;
      const smallEnough = rect.width <= 96 && rect.height <= 96;
      return nearRight && nearVertical && smallEnough && clickable(node);
    });
  const nearCandidates = [...buttons, ...iconRoots]
    .filter((btn, index, arr) => arr.indexOf(btn) === index)
    .map((btn) => {
      const rect = btn.getBoundingClientRect();
      const dx = Math.abs((rect.left + rect.width / 2) - (inputRect.right - 20));
      const dy = Math.abs((rect.top + rect.height / 2) - (inputRect.bottom - 20));
      const className = String(btn.className || '');
      let score = dx + dy;
      if (/send__|submit/i.test(className)) score -= 90;
      if (/inner|lottie/i.test(className) || btn.tagName === 'SVG' || btn.tagName === 'PATH') score += 80;
      return {btn, score};
    })
    .sort((a, b) => a.score - b.score);
  const isButtonLike = (btn) => btn.tagName === 'BUTTON' || btn.getAttribute('role') === 'button' || submitLabelPattern.test(labelOf(btn));
  const nearInput = nearCandidates.find((item) => {
      const rect = item.btn.getBoundingClientRect();
      return isButtonLike(item.btn) && item.score < 220 && rect.left >= inputRect.right - 180 && rect.top >= inputRect.top - 40;
    })?.btn || nearCandidates.find((item) => {
      const rect = item.btn.getBoundingClientRect();
      return isButtonLike(item.btn) && item.score < 160 && rect.left >= inputRect.right - 180 && rect.top >= inputRect.top - 40;
    })?.btn;
  const button = byText || nearInput;
  if (button) {
    button.scrollIntoView({block:'center', inline:'nearest'});
    const rect = button.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    ['mousemove', 'mousedown', 'mouseup', 'click'].forEach((type) => {
      button.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window, clientX:cx, clientY:cy, button:0, buttons:type === 'mousedown' ? 1 : 0}));
    });
    return JSON.stringify({ok:true,mode:'click',buttonText:labelOf(button).slice(0,80), x:Math.round(cx), y:Math.round(cy)});
  }
  const init = {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true, cancelable:true};
  input.dispatchEvent(new KeyboardEvent('keydown', init));
  input.dispatchEvent(new KeyboardEvent('keypress', init));
  input.dispatchEvent(new KeyboardEvent('keyup', init));
  return JSON.stringify({ok:true,mode:'keyboard'});
})()
"""
        result = await self._command("evaluate", {"code": code}, session=session)
        value = result.get("value")
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
        except json.JSONDecodeError:
            parsed = {"ok": False, "error": value}
        if not parsed or not parsed.get("ok"):
            raise WebBridgeError(parsed.get("error") if isinstance(parsed, dict) else "未能提交问题")
        return parsed

    async def _click_submit_with_dom_text_agent(self, session: str, question: Optional[str] = None) -> Dict[str, Any]:
        candidates = await self._collect_submit_candidates(session=session)
        if not candidates:
            raise WebBridgeError("未找到输入框附近的可点击发送候选按钮")

        selected = await self._choose_submit_candidate_with_llm(candidates)
        ordered_candidates = []
        if selected is not None:
            ordered_candidates.append(selected)
        ordered_candidates.extend(
            candidate
            for candidate in candidates
            if selected is None or candidate.get("selector") != selected.get("selector")
        )

        last_error = ""
        for candidate in ordered_candidates[:8]:
            selector = candidate.get("selector")
            if not selector:
                continue
            for mode in ("mouse_click", "events"):
                try:
                    if mode == "mouse_click":
                        result = await self._command("mouse_click", {"selector": selector}, session=session)
                    else:
                        result = await self._click_selector_with_events(selector=selector, session=session)
                    await asyncio.sleep(1.2)
                    if not question or not await self._focused_input_contains(question, session=session):
                        if isinstance(result, dict):
                            result["candidate_selector"] = selector
                            result["candidate_index"] = candidate.get("index")
                            result["click_mode"] = mode
                        return result if isinstance(result, dict) else {"ok": True, "click_mode": mode}
                    last_error = f"{mode} clicked {selector}, but the input still contains the question"
                except WebBridgeError as exc:
                    last_error = str(exc)
                    continue

        raise WebBridgeError(f"已尝试多个发送候选按钮，但都未触发提交。最后一次结果：{last_error}")

    async def _collect_submit_candidates(self, session: str) -> list[dict]:
        code = """
(() => {
  const visible = (el) => {
    if (!el) return false;
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const cssEscape = (value) => {
    if (window.CSS && CSS.escape) return CSS.escape(value);
    return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\\\$&');
  };
  const selectorFor = (el) => {
    if (!el || !el.tagName) return '';
    if (el.id) return `#${cssEscape(el.id)}`;
    const attrs = ['data-testid', 'data-test-id', 'data-cy', 'aria-label', 'title'];
    for (const attr of attrs) {
      const value = el.getAttribute(attr);
      if (value && value.length < 80) {
        const selector = `${el.tagName.toLowerCase()}[${attr}="${String(value).replace(/"/g, '\\"')}"]`;
        try {
          if (document.querySelectorAll(selector).length === 1) return selector;
        } catch (_e) {}
      }
    }
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && node !== document.body && parts.length < 6) {
      const tag = node.tagName.toLowerCase();
      const siblings = Array.from(node.parentElement ? node.parentElement.children : []).filter((item) => item.tagName === node.tagName);
      const index = siblings.indexOf(node) + 1;
      parts.unshift(`${tag}:nth-of-type(${index})`);
      node = node.parentElement;
    }
    return parts.length ? `body > ${parts.join(' > ')}` : '';
  };
  const labelOf = (el) => (el.innerText || el.getAttribute('aria-label') || el.title || el.getAttribute('data-testid') || String(el.className || '') || '').trim();
  const sendPattern = /发送|提交|send|submit|ask|arrow|paper|plane|enter|send-btn|send-button|send_button/i;
  const input = Array.from(document.querySelectorAll('[role="textbox"], textarea, [contenteditable="true"], [contenteditable="plaintext-only"], input[type="text"], input:not([type])'))
    .reverse()
    .find(visible);
  if (!input) return JSON.stringify({ok:false,error:'未找到输入框',candidates:[]});
  const inputRect = input.getBoundingClientRect();
  const rawNodes = Array.from(document.querySelectorAll('button,[role="button"],[onclick],a,svg,path,[aria-label],[title],[data-testid],[class]'));
  const roots = [];
  for (const node of rawNodes) {
    let root = node.closest('button,[role="button"],[onclick],a,[class*="send__"],[class*="Send__"],[class*="submit"],[class*="Submit"]') || node;
    for (let i = 0; i < 2 && root && root.parentElement; i += 1) {
      const style = getComputedStyle(root);
      const text = labelOf(root);
      if (style.cursor === 'pointer' || sendPattern.test(text) || root.getAttribute('role') === 'button' || typeof root.onclick === 'function') break;
      root = root.parentElement;
    }
    if (root && !roots.includes(root)) roots.push(root);
  }
  const candidates = roots
    .filter((node) => {
      if (!visible(node)) return false;
      const style = getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const nearRight = cx >= inputRect.right - 260 && cx <= inputRect.right + 160;
      const nearVertical = cy >= inputRect.top - 60 && cy <= inputRect.bottom + 80;
      const smallEnough = rect.width <= 140 && rect.height <= 120;
      const text = labelOf(node);
      const clickable = style.cursor === 'pointer' || typeof node.onclick === 'function' || node.getAttribute('role') === 'button' || node.tagName === 'BUTTON' || sendPattern.test(text);
      const enabled = !node.disabled && node.getAttribute('aria-disabled') !== 'true' && !String(node.className || '').toLowerCase().includes('disabled');
      return nearRight && nearVertical && smallEnough && clickable && enabled;
    })
    .map((node, index) => {
      const style = getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const dx = Math.abs(cx - (inputRect.right - 20));
      const dy = Math.abs(cy - (inputRect.bottom - 20));
      const text = labelOf(node);
      const className = String(node.className || '');
      let score = dx + dy;
      if (sendPattern.test(text)) score -= 120;
      if (/send(__|btn|button)|submit/i.test(className)) score -= 90;
      if (/inner|lottie|svg|path/i.test(className) || node.tagName === 'SVG' || node.tagName === 'PATH') score += 70;
      if (node.tagName === 'BUTTON' || node.getAttribute('role') === 'button') score -= 40;
      if (style.cursor === 'pointer') score -= 20;
      return {
        index,
        selector: selectorFor(node),
        tag: node.tagName.toLowerCase(),
        role: node.getAttribute('role') || '',
        text: text.slice(0, 80),
        ariaLabel: (node.getAttribute('aria-label') || '').slice(0, 80),
        title: (node.getAttribute('title') || '').slice(0, 80),
        className: className.slice(0, 140),
        cursor: style.cursor,
        rect: {left: Math.round(rect.left), top: Math.round(rect.top), width: Math.round(rect.width), height: Math.round(rect.height)},
        distanceScore: Math.round(score)
      };
    })
    .filter((item) => item.selector)
    .sort((a, b) => a.distanceScore - b.distanceScore)
    .slice(0, 20)
    .map((item, index) => ({...item, index}));
  return JSON.stringify({ok:true,candidates});
})()
"""
        result = await self._command("evaluate", {"code": code}, session=session)
        value = result.get("value")
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
        except json.JSONDecodeError as exc:
            raise WebBridgeError(f"无法解析发送按钮候选列表：{value}") from exc
        if not isinstance(parsed, dict) or not parsed.get("ok"):
            raise WebBridgeError(parsed.get("error") if isinstance(parsed, dict) else "未能收集发送按钮候选")
        return parsed.get("candidates") or []

    async def _submit_candidates_error_hint(self, session: str) -> str:
        try:
            candidates = await self._collect_submit_candidates(session=session)
        except Exception:
            return ""
        if not candidates:
            return ""
        lines = []
        for item in candidates[:5]:
            selector = item.get("selector") or ""
            label = item.get("text") or item.get("ariaLabel") or item.get("title") or item.get("className") or ""
            score = item.get("distanceScore")
            lines.append(f"{item.get('index')}: selector={selector} label={label[:40]} score={score}")
        return "候选发送按钮如下，可复制最像的 selector 填入检测平台 submit_selector：\n" + "\n".join(lines) + "\n"

    async def _choose_submit_candidate_with_llm(self, candidates: list[dict]) -> Optional[dict]:
        try:
            from app.llm.client import LLMClientFactory
            from app.llm.registry import get_model_registry

            config = get_model_registry().get_default_model()
            if not config or not config.api_key:
                return None
            client = LLMClientFactory.create_client_from_config(config.to_dict(mask_api_key=False))
            prompt = (
                "你是网页自动化选择器诊断助手。下面是聊天网页输入框附近的可点击 DOM 候选元素。"
                "请只根据文本 DOM 信息判断哪个最可能是“发送消息/提交问题”的按钮。"
                "返回严格 JSON：{\"index\": 数字或null, \"confidence\": 0到1, \"reason\": \"一句话\"}。"
                "如果都不像发送按钮，index 返回 null。\n\n候选元素：\n"
                f"{json.dumps(candidates, ensure_ascii=False, indent=2)}"
            )
            response = await client.chat(
                messages=[
                    {"role": "system", "content": "只输出 JSON，不要输出解释文字。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=180,
            )
            parsed = self._extract_json_object(response.content)
            index = parsed.get("index")
            confidence = float(parsed.get("confidence") or 0)
            if index is None or confidence < 0.45:
                return None
            for candidate in candidates:
                if int(candidate.get("index", -1)) == int(index):
                    return candidate
        except Exception:
            return None
        return None

    def _extract_json_object(self, text: str) -> Dict[str, Any]:
        clean = self._clean_model_text(text)
        parsed = self._parse_json_like_object(clean)
        if isinstance(parsed, dict):
            return parsed

        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", clean):
            candidate = clean[match.start():]
            try:
                parsed, _ = decoder.raw_decode(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

        for candidate in self._balanced_json_candidates(clean):
            parsed = self._parse_json_like_object(candidate)
            if isinstance(parsed, dict):
                return parsed
        return {}

    def _clean_model_text(self, text: str) -> str:
        clean = (text or "").replace("\ufeff", "").strip()
        clean = re.sub(r"```(?:json|javascript|js)?\s*", "", clean, flags=re.I).replace("```", "").strip()
        clean = clean.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
        return clean

    def _parse_json_like_object(self, value: str) -> Optional[Dict[str, Any]]:
        if not value:
            return None
        candidates = [
            value,
            re.sub(r",\s*([}\]])", r"\1", value),
        ]
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
            try:
                parsed = ast.literal_eval(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except (ValueError, SyntaxError):
                pass
        return None

    def _balanced_json_candidates(self, text: str) -> List[str]:
        candidates: List[str] = []
        starts = [match.start() for match in re.finditer(r"\{", text or "")]
        for start in starts:
            depth = 0
            in_string = False
            quote = ""
            escape = False
            for idx in range(start, len(text)):
                ch = text[idx]
                if in_string:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == quote:
                        in_string = False
                    continue
                if ch in {"'", '"'}:
                    in_string = True
                    quote = ch
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidates.append(text[start:idx + 1])
                        break
        return candidates

    async def _click_selector_with_events(self, selector: str, session: str) -> Dict[str, Any]:
        selector_literal = json.dumps(selector)
        code = f"""
(() => {{
  const selector = {selector_literal};
  const visible = (node) => {{
    if (!node) return false;
    const style = getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  }};
  const matches = Array.from(document.querySelectorAll(selector));
  const el = matches.find(visible) || matches[0];
  if (!el) return JSON.stringify({{ok:false,error:'候选发送按钮不存在',selector}});
  const labelOf = (node) => (node.innerText || node.getAttribute('aria-label') || node.title || node.getAttribute('data-testid') || String(node.className || '') || '').trim();
  const scoreTarget = (node) => {{
    const text = labelOf(node);
    const className = String(node.className || '');
    let score = 100;
    if (node.tagName === 'BUTTON' || node.getAttribute('role') === 'button') score -= 60;
    if (typeof node.onclick === 'function') score -= 40;
    if (/send(__|btn|button)|submit/i.test(className)) score -= 70;
    if (/发送|提交|send|submit/i.test(text)) score -= 60;
    if (/inner|lottie/i.test(className) || node.tagName === 'SVG' || node.tagName === 'PATH') score += 50;
    return score;
  }};
  const chain = [];
  let node = el;
  for (let i = 0; i < 6 && node && node.nodeType === 1; i += 1) {{
    if (visible(node)) chain.push(node);
    node = node.parentElement;
  }}
  const clickRoot = chain.sort((a, b) => scoreTarget(a) - scoreTarget(b))[0] || el;
  clickRoot.scrollIntoView({{block:'center', inline:'nearest'}});
  const rect = clickRoot.getBoundingClientRect();
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;
  const target = document.elementFromPoint(cx, cy) || clickRoot;
  ['pointermove', 'mousemove', 'pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach((type) => {{
    target.dispatchEvent(new MouseEvent(type, {{
      bubbles:true,
      cancelable:true,
      view:window,
      clientX:cx,
      clientY:cy,
      button:0,
      buttons:type === 'mousedown' || type === 'pointerdown' ? 1 : 0
    }}));
  }});
  if (typeof clickRoot.click === 'function') clickRoot.click();
  if (target !== clickRoot && typeof target.click === 'function') target.click();
  return JSON.stringify({{ok:true,selector,x:Math.round(cx),y:Math.round(cy),tag:target.tagName,rootTag:clickRoot.tagName,text:(target.innerText || target.getAttribute('aria-label') || target.title || '').slice(0,80)}});
}})()
"""
        result = await self._command("evaluate", {"code": code}, session=session)
        value = result.get("value")
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
        except json.JSONDecodeError:
            parsed = {"ok": False, "error": value}
        if not parsed or not parsed.get("ok"):
            raise WebBridgeError(parsed.get("error") if isinstance(parsed, dict) else "未能点击发送候选按钮")
        return parsed

    async def _click_point_with_events(self, x: int, y: int, session: str) -> Dict[str, Any]:
        code = f"""
(() => {{
  const x = {int(x)};
  const y = {int(y)};
  const target = document.elementFromPoint(x, y);
  if (!target) return JSON.stringify({{ok:false,error:'坐标位置没有可点击元素',x,y}});
  const clickRoot = target.closest('button,[role="button"],a,[onclick],textarea,input,[contenteditable="true"],[contenteditable="plaintext-only"]') || target;
  if (typeof clickRoot.focus === 'function') clickRoot.focus();
  ['pointermove', 'mousemove', 'pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach((type) => {{
    const eventInit = {{
      bubbles:true,
      cancelable:true,
      view:window,
      clientX:x,
      clientY:y,
      button:0,
      buttons:type === 'mousedown' || type === 'pointerdown' ? 1 : 0
    }};
    target.dispatchEvent(new MouseEvent(type, eventInit));
    if (clickRoot !== target) clickRoot.dispatchEvent(new MouseEvent(type, eventInit));
  }});
  if (typeof clickRoot.click === 'function') clickRoot.click();
  return JSON.stringify({{
    ok:true,
    x,
    y,
    tag: target.tagName,
    rootTag: clickRoot.tagName,
    text: (target.innerText || target.getAttribute('aria-label') || target.title || '').slice(0,80)
  }});
}})()
"""
        result = await self._command("evaluate", {"code": code}, session=session)
        value = result.get("value")
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
        except json.JSONDecodeError:
            parsed = {"ok": False, "error": value}
        if not parsed or not parsed.get("ok"):
            raise WebBridgeError(parsed.get("error") if isinstance(parsed, dict) else "视觉识别模式点击坐标失败")
        return parsed

    async def _snapshot_excerpt(self, session: str) -> str:
        try:
            data = await self._command("snapshot", {}, session=session)
        except WebBridgeError as exc:
            return f"无法读取页面快照：{exc}"
        tree = data.get("tree") if isinstance(data, dict) else data
        text = str(tree or "").strip()
        text = re.sub(r"\s+", " ", text)
        return text[:900] or "页面快照为空"

    async def _page_text_tail(self, session: str, selector: Optional[str] = None, tail_chars: int = 12000) -> str:
        selector_literal = json.dumps(selector or "")
        tail_chars_literal = json.dumps(max(1000, min(int(tail_chars or 12000), 100000)))
        code = f"""
(() => {{
  const selector = {selector_literal};
  const tailChars = {tail_chars_literal};
  const safeQuery = (value) => {{
    if (!value) return document.body;
    try {{
      return document.querySelector(value) || document.body;
    }} catch (error) {{
      return document.body;
    }}
  }};
  const root = safeQuery(selector);
  const text = (root ? root.innerText : document.body.innerText) || '';
  return text.slice(-tailChars);
}})()
"""
        result = await self._command("evaluate", {"code": code}, session=session)
        return str(result.get("value") or "")

    async def _page_text_full(self, session: str, selector: Optional[str] = None, max_chars: int = 220000) -> str:
        selector_literal = json.dumps(selector or "")
        max_chars_literal = json.dumps(max(1000, min(int(max_chars or 220000), 500000)))
        code = f"""
(() => {{
  const selector = {selector_literal};
  const maxChars = {max_chars_literal};
  const safeQuery = (value) => {{
    if (!value) return document.body;
    try {{
      return document.querySelector(value) || document.body;
    }} catch (error) {{
      return document.body;
    }}
  }};
  const root = safeQuery(selector);
  const text = (root ? root.innerText : document.body.innerText) || '';
  if (text.length <= maxChars) return text;
  const headSize = Math.floor(maxChars * 0.55);
  const tailSize = Math.max(1000, maxChars - headSize);
  return text.slice(0, headSize) + '\\n...\\n' + text.slice(-tailSize);
}})()
"""
        result = await self._command("evaluate", {"code": code}, session=session)
        return str(result.get("value") or "")

    async def _page_answer_text_full(
        self,
        session: str,
        selector: Optional[str] = None,
        question: str = "",
        max_chars: int = 220000,
    ) -> str:
        selector_literal = json.dumps(selector or "")
        question_literal = json.dumps(question or "")
        max_chars_literal = json.dumps(max(1000, min(int(max_chars or 220000), 500000)))
        code = f"""
(() => {{
  const selector = {selector_literal};
  const question = {question_literal};
  const maxChars = {max_chars_literal};
  const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
  const normalizeCompact = (value) => String(value || '').replace(/\\s+/g, '');
  const safeQuery = (value) => {{
    if (!value) return document.body;
    try {{
      return document.querySelector(value) || document.body;
    }} catch (error) {{
      return document.body;
    }}
  }};
  const root = safeQuery(selector);
  const visible = (el) => {{
    if (!el) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.visibility !== 'hidden'
      && style.display !== 'none'
      && rect.width > 80
      && rect.height > 24;
  }};
  const noisePattern = /(深度分析需求并解答|你需要什么帮助|内容由AI生成|仅供参考|请仔细甄别|参考\\s*0|输入消息|新对话|我的收藏|智能翻译|网页工坊)/i;
  const answerPattern = /(推荐|第一|第二|第三|靠谱|机构|培训|资质|证书|编号|CAAC|UOM|合规|地址|费用|通过率|建议|优先|理由|总结)/i;
  const questionCompact = normalizeCompact(question);
  const selectors = [
    'article', 'main', 'section', '[role="article"]', '[data-message-author-role]',
    '[class*="answer"]', '[class*="message"]', '[class*="markdown"]',
    '[class*="content"]', '[class*="chat"]', '[class*="result"]', 'div'
  ].join(',');
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1366;
  const candidates = Array.from(root.querySelectorAll(selectors))
    .filter((el) => visible(el))
    .map((el) => {{
      let text = normalize(el.innerText || el.textContent || '');
      if (!text || text.length < 30) return null;
      const compact = normalizeCompact(text);
      const rect = el.getBoundingClientRect();
      let answerText = text;
      const questionIndex = questionCompact ? compact.lastIndexOf(questionCompact) : -1;
      if (questionIndex >= 0) {{
        const rawIndex = text.lastIndexOf(question);
        if (rawIndex >= 0) answerText = normalize(text.slice(rawIndex + question.length));
      }}
      const answerCompact = normalizeCompact(answerText);
      const hasQuestion = questionCompact && compact.includes(questionCompact);
      const hasAnswerMarker = answerPattern.test(answerText);
      const hasNoise = noisePattern.test(answerText);
      let score = 0;
      score += Math.min(answerCompact.length, 5000) / 18;
      if (hasQuestion) score += 120;
      if (hasAnswerMarker) score += 180;
      if (/第一推荐|推荐：|我的建议|总结一句话/.test(answerText)) score += 160;
      if (hasNoise) score -= 260;
      if (answerCompact.length < 80) score -= 140;
      if (rect.left < viewportWidth * 0.16 && rect.width < viewportWidth * 0.32) score -= 220;
      if (el === document.body || el === document.documentElement) score -= 450;
      return {{ el, text: answerText || text, score, length: answerCompact.length }};
    }})
    .filter(Boolean)
    .filter((item) => item.length >= 40 && item.score > 0)
    .sort((a, b) => b.score - a.score);
  let text = candidates[0]?.text || ((root ? root.innerText : document.body.innerText) || '');
  if (question) {{
    const index = text.lastIndexOf(question);
    if (index >= 0) text = text.slice(index);
  }}
  if (text.length <= maxChars) return text;
  const headSize = Math.floor(maxChars * 0.65);
  const tailSize = Math.max(1000, maxChars - headSize);
  return text.slice(0, headSize) + '\\n...\\n' + text.slice(-tailSize);
}})()
"""
        result = await self._command("evaluate", {"code": code}, session=session)
        return str(result.get("value") or "")

    async def _safe_page_text_tail(
        self,
        session: str,
        selector: Optional[str] = None,
        tail_chars: int = 12000,
    ) -> str:
        try:
            return await self._page_text_tail(session=session, selector=selector, tail_chars=tail_chars)
        except TypeError:
            try:
                return await self._page_text_tail(session=session, selector=selector)
            except Exception:
                return ""
        except Exception:
            return ""

    async def _safe_page_text_full(
        self,
        session: str,
        selector: Optional[str] = None,
        max_chars: int = 220000,
    ) -> str:
        try:
            return await self._page_text_full(session=session, selector=selector, max_chars=max_chars)
        except TypeError:
            try:
                return await self._page_text_tail(session=session, selector=selector, tail_chars=max_chars)
            except Exception:
                return ""
        except Exception:
            return ""

    async def _safe_page_answer_text_full(
        self,
        session: str,
        selector: Optional[str] = None,
        question: str = "",
        max_chars: int = 220000,
    ) -> str:
        try:
            return await self._page_answer_text_full(
                session=session,
                selector=selector,
                question=question,
                max_chars=max_chars,
            )
        except TypeError:
            try:
                return await self._page_text_full(session=session, selector=selector, max_chars=max_chars)
            except Exception:
                return await self._safe_page_text_tail(session=session, selector=selector, tail_chars=max_chars)
        except Exception:
            return await self._safe_page_text_full(session=session, selector=selector, max_chars=max_chars)

    async def _wait_for_answer_tail(
        self,
        session: str,
        before_tail: str,
        wait_seconds: int,
        selector: Optional[str] = None,
        question: Optional[str] = None,
    ) -> str:
        poll_interval = 3
        stable_required_hits = 3
        min_elapsed_for_stable_exit = min(45, max(18, wait_seconds * 0.25))
        last_tail = ""
        last_answer = ""
        stable_answer_hits = 0
        started_at = asyncio.get_event_loop().time()
        deadline = started_at + wait_seconds
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(poll_interval)
            tail = await self._page_text_tail(session=session, selector=selector)
            if tail and tail != before_tail:
                if question and await self._focused_input_contains(question, session=session):
                    last_tail = tail
                    stable_answer_hits = 0
                    continue
                answer = self._extract_answer(question or "", tail, before_tail)
                if not self._looks_like_answer(answer):
                    last_tail = tail
                    stable_answer_hits = 0
                    continue

                normalized_answer = re.sub(r"\s+", " ", answer).strip()
                if normalized_answer and normalized_answer == last_answer:
                    stable_answer_hits += 1
                else:
                    stable_answer_hits = 0
                    last_answer = normalized_answer
                last_tail = tail

                elapsed = asyncio.get_event_loop().time() - started_at
                is_generating = await self._is_answer_generating(session=session)
                if (
                    not is_generating
                    and elapsed >= min_elapsed_for_stable_exit
                    and stable_answer_hits >= stable_required_hits
                ):
                    break
        return last_tail or await self._page_text_tail(session=session, selector=selector)

    async def _is_answer_generating(self, session: str) -> bool:
        code = r"""
(() => {
  const visible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const textOf = (el) => [
    el.innerText,
    el.textContent,
    el.getAttribute('aria-label'),
    el.getAttribute('title'),
    el.getAttribute('data-testid'),
    el.className,
  ].filter(Boolean).join(' ');
  const stopPattern = /(停止生成|停止回答|停止响应|终止回答|停止|Stop generating|Stop responding|Cancel response|Abort response)/i;
  const submitPattern = /(发送|send|submit)/i;
  const buttons = Array.from(document.querySelectorAll('button,[role="button"],[aria-label],[title]'));
  const activeStopButton = buttons.some((el) => {
    const text = textOf(el);
    return visible(el) && stopPattern.test(text) && !submitPattern.test(text) && !el.disabled;
  });
  const busyRegion = Array.from(document.querySelectorAll('[aria-busy="true"],[data-generating="true"],[data-loading="true"]'))
    .some((el) => visible(el));
  return JSON.stringify({ generating: Boolean(activeStopButton || busyRegion) });
})()
"""
        try:
            result = await self._command("evaluate", {"code": code}, session=session)
            value = result.get("value")
            parsed = json.loads(value) if isinstance(value, str) else value
            return bool(isinstance(parsed, dict) and parsed.get("generating"))
        except Exception:
            return False

    async def _capture_answer_screenshot(self, session: str) -> Optional[str]:
        data = await self._capture_screenshot_data(session=session)
        return self._save_screenshot_data(data, session=session)

    async def _capture_answer_evidence_screenshot(
        self,
        session: str,
        selector: Optional[str],
        answer_text: str,
    ) -> Optional[str]:
        preferred_selector = selector or await self._mark_answer_capture_element(session=session, answer_text=answer_text)
        if preferred_selector:
            data = await self._capture_screenshot_data(
                session=session,
                full_page=True,
                selector=preferred_selector,
            )
            if data:
                return data
        return await self._capture_screenshot_data(session=session, full_page=True)

    async def _mark_mention_capture_element(
        self,
        session: str,
        brand_terms: List[str],
        selector: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        terms = self._normalize_evidence_terms(brand_terms)
        if not terms:
            return None
        token = f"geo-mention-{int(time.time() * 1000)}"
        code = f"""
(() => {{
  const selector = {json.dumps(selector or "")};
  const terms = {json.dumps(terms, ensure_ascii=False)};
  const token = {json.dumps(token)};
  const safeQuery = (value) => {{
    if (!value) return document.body;
    try {{
      return document.querySelector(value) || document.body;
    }} catch (error) {{
      return document.body;
    }}
  }};
  const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
  const visible = (el) => {{
    if (!el) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.visibility !== 'hidden'
      && style.display !== 'none'
      && rect.width > 20
      && rect.height > 8;
  }};
  const root = safeQuery(selector);
  const chooseBlock = (el) => {{
    let node = el;
    let best = el;
    while (node && node !== document.body && visible(node)) {{
      const text = clean(node.innerText || node.textContent || '');
      if (text.length >= 20 && text.length <= 2800) best = node;
      if (node === root) break;
      node = node.parentElement;
    }}
    return best || el;
  }};
  const mark = (el, matchedTerm) => {{
    const block = chooseBlock(el);
    const text = clean(block.innerText || block.textContent || '');
    if (!text) return null;
    block.setAttribute('data-geo-mention-evidence', token);
    block.style.outline = '3px solid #ff4d4f';
    block.style.outlineOffset = '4px';
    block.style.backgroundColor = 'rgba(255, 77, 79, 0.08)';
    block.scrollIntoView({{ block: 'center', inline: 'nearest' }});
    return {{
      selector: `[data-geo-mention-evidence="${{token}}"]`,
      matched_term: matchedTerm,
      evidence_text: text.slice(0, 1800),
    }};
  }};
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {{
    acceptNode(node) {{
      const value = node.nodeValue || '';
      if (!clean(value)) return NodeFilter.FILTER_REJECT;
      const parent = node.parentElement;
      if (!visible(parent)) return NodeFilter.FILTER_REJECT;
      const tag = (parent.tagName || '').toLowerCase();
      if (['script', 'style', 'noscript', 'textarea', 'input'].includes(tag)) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    }}
  }});
  let node;
  while ((node = walker.nextNode())) {{
    const value = node.nodeValue || '';
    for (const term of terms) {{
      if (term && value.includes(term)) {{
        const marked = mark(node.parentElement, term);
        if (marked) return JSON.stringify(marked);
      }}
    }}
  }}
  const candidates = Array.from(root.querySelectorAll('article,section,main,p,li,div,[class*="answer"],[class*="message"],[class*="markdown"],[class*="content"]'))
    .filter(visible);
  for (const el of candidates) {{
    const text = clean(el.innerText || el.textContent || '');
    for (const term of terms) {{
      if (term && text.includes(term)) {{
        const marked = mark(el, term);
        if (marked) return JSON.stringify(marked);
      }}
    }}
  }}
  return JSON.stringify({{ ok: false }});
}})()
"""
        try:
            result = await self._command("evaluate", {"code": code}, session=session)
            parsed = self._extract_json_object(str(result.get("value") or ""))
        except Exception:
            return None
        if not isinstance(parsed, dict) or not parsed.get("selector"):
            return None
        return {
            "selector": str(parsed.get("selector") or ""),
            "matched_term": str(parsed.get("matched_term") or ""),
            "evidence_text": str(parsed.get("evidence_text") or ""),
        }

    async def _mark_answer_capture_element(self, session: str, answer_text: str) -> Optional[str]:
        compact = re.sub(r"\s+", "", answer_text or "")
        if len(compact) < 20:
            return None
        snippet = compact[:80]
        token = f"geo-answer-{int(time.time() * 1000)}"
        code = f"""
(() => {{
  const needle = {json.dumps(snippet)};
  const token = {json.dumps(token)};
  const normalize = (value) => String(value || '').replace(/\\s+/g, '');
  const visible = (el) => {{
    if (!el) return false;
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 80 && rect.height > 30;
  }};
  const selector = [
    'article', 'main', 'section',
    '[role="article"]', '[data-message-author-role]',
    '[class*="answer"]', '[class*="message"]', '[class*="markdown"]',
    '[class*="content"]', '[class*="chat"]'
  ].join(',');
  const candidates = Array.from(document.querySelectorAll(selector))
    .filter(visible)
    .map((el) => {{
      const text = el.innerText || el.textContent || '';
      const normalized = normalize(text);
      const rect = el.getBoundingClientRect();
      return {{
        el,
        textLength: normalized.length,
        area: rect.width * rect.height,
        contains: needle && normalized.includes(needle),
      }};
    }})
    .filter((item) => item.contains || item.textLength >= Math.min(needle.length, 40));
  candidates.sort((a, b) => {{
    if (a.contains !== b.contains) return a.contains ? -1 : 1;
    return a.area - b.area;
  }});
  const picked = candidates[0]?.el;
  if (!picked) return JSON.stringify({{ ok: false }});
  document.querySelectorAll('[data-geo-answer-capture]').forEach((el) => el.removeAttribute('data-geo-answer-capture'));
  picked.setAttribute('data-geo-answer-capture', token);
  picked.scrollIntoView({{ block: 'start', inline: 'nearest' }});
  return JSON.stringify({{ ok: true, selector: `[data-geo-answer-capture="${{token}}"]` }});
}})()
"""
        try:
            result = await self._command("evaluate", {"code": code}, session=session)
            value = result.get("value")
            parsed = json.loads(value) if isinstance(value, str) else value
            if isinstance(parsed, dict) and parsed.get("ok") and parsed.get("selector"):
                return str(parsed["selector"])
        except Exception:
            return None
        return None

    async def _capture_screenshot_data(
        self,
        session: str,
        full_page: bool = False,
        selector: Optional[str] = None,
    ) -> Optional[str]:
        args = {"format": "png", "fullPage": full_page}
        if selector:
            args["selector"] = selector
        try:
            result = await self._command("screenshot", args, session=session)
        except Exception:
            if selector:
                try:
                    result = await self._command(
                        "screenshot",
                        {"format": "png", "fullPage": full_page},
                        session=session,
                    )
                except Exception:
                    return None
            else:
                return None

        data = result.get("data") or result.get("base64") or result.get("value")
        if not isinstance(data, str) or not data:
            return None
        if data.startswith("data:image"):
            data = data.split(",", 1)[-1]
        return data

    def _save_screenshot_data(self, data: Optional[str], session: str) -> Optional[str]:
        if not isinstance(data, str) or not data:
            return None
        if data.startswith("data:image"):
            data = data.split(",", 1)[-1]
        try:
            image_bytes = base64.b64decode(data)
        except Exception:
            return None
        if not image_bytes:
            return None

        storage_dir = Path(os.getenv("GEO_SCREENSHOT_DIR") or Path.cwd() / "monitoring_screenshots")
        storage_dir.mkdir(parents=True, exist_ok=True)
        safe_session = re.sub(r"[^a-zA-Z0-9_-]+", "-", session or "geo-monitor").strip("-")[:80] or "geo-monitor"
        filename = f"{safe_session}-{int(time.time() * 1000)}.png"
        file_path = storage_dir / filename
        file_path.write_bytes(image_bytes)
        return f"/api/v1/monitoring/screenshots/{filename}"

    async def _extract_answer_sources(
        self,
        session: str,
        selector: Optional[str] = None,
        answer_text: str = "",
    ) -> List[Dict[str, str]]:
        selector_literal = json.dumps(selector or "")
        answer_literal = json.dumps((answer_text or "")[-3000:])
        code = f"""
(() => {{
  const selector = {selector_literal};
  const answerText = {answer_literal};
  const safeQuery = (value) => {{
    if (!value) return document.body;
    try {{
      return document.querySelector(value) || document.body;
    }} catch (error) {{
      return document.body;
    }}
  }};
  const root = safeQuery(selector);
  const visible = (el) => {{
    if (!el) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.visibility !== 'hidden'
      && style.display !== 'none'
      && rect.width > 0
      && rect.height > 0;
  }};
  const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
  const links = [];
  const seen = new Set();
  const answerCompact = clean(answerText);
  const pushLink = (title, href, sourceType, context) => {{
    try {{
      const url = new URL(href, location.href);
      if (!/^https?:$/.test(url.protocol)) return;
      const normalized = url.href;
      if (seen.has(normalized)) return;
      seen.add(normalized);
      links.push({{
        title: clean(title) || normalized,
        url: normalized,
        source_type: sourceType || 'ai_link',
        context: clean(context).slice(0, 260),
      }});
    }} catch (error) {{}}
  }};
  const anchors = Array.from(root.querySelectorAll('a[href]')).filter(visible);
  for (const a of anchors) {{
    const href = a.getAttribute('href') || '';
    const title = clean(a.innerText || a.textContent || a.getAttribute('title') || a.getAttribute('aria-label'));
    const parentText = clean(a.closest('li,p,section,article,div')?.innerText || '');
    const isAnswerNearby = !answerCompact
      || answerCompact.includes(title)
      || (title && parentText && answerCompact.includes(parentText.slice(0, 50)))
      || parentText.includes(title);
    const isLikelySource = /来源|引用|参考|出处|source|citation|参考资料|信息来源/i.test(parentText)
      || /^https?:\\/\\//i.test(href)
      || isAnswerNearby;
    if (isLikelySource) pushLink(title, href, 'ai_citation', parentText);
    if (links.length >= 30) break;
  }}
  return JSON.stringify(links);
}})()
"""
        try:
            result = await self._command("evaluate", {"code": code}, session=session)
            value = result.get("value")
            parsed = json.loads(value) if isinstance(value, str) else value
            if not isinstance(parsed, list):
                return []
            sources: List[Dict[str, str]] = []
            seen_urls = set()
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                sources.append({
                    "title": str(item.get("title") or url).strip()[:300],
                    "url": url,
                    "source_type": str(item.get("source_type") or "ai_link").strip()[:50],
                    "context": str(item.get("context") or "").strip()[:500],
                })
                if len(sources) >= 20:
                    break
            return sources
        except Exception:
            return []

    def _extract_answer(self, question: str, raw_tail: str, before_tail: str) -> str:
        text = raw_tail or ""
        if before_tail and text.startswith(before_tail):
            text = text[len(before_tail):]
        if question and question in text:
            text = text.rsplit(question, 1)[-1]
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]
        noise_pattern = re.compile(
            r"^(发送|重新生成|复制|点赞|点踩|分享|停止|联网搜索|深度思考|输入消息|编辑|"
            r"尽管问.*|K\d+(\.\d+)?\s*快速|Agent|WebBridge 接入浏览器|让 AI 像人一样使用浏览器|"
            r"Kimi Claw.*|一键部署.*|你能做些什么？|你叫什么名字？|你是如何被训练的？|"
            r"快速|图像生成|编程|超能模式|PPT 生成|帮我写作|更多|Beta|"
            r"Send|Regenerate|Copy|Like|Dislike)$",
            re.I,
        )
        useful = [line for line in lines if not noise_pattern.search(line)]
        answer = "\n".join(useful).strip()
        return self._limit_answer_text(answer)

    def _limit_answer_text(self, answer: str, max_chars: int = 50000) -> str:
        text = (answer or "").strip()
        if len(text) <= max_chars:
            return text
        head_size = int(max_chars * 0.64)
        tail_size = max_chars - head_size
        return f"{text[:head_size]}\n...\n{text[-tail_size:]}"

    def _normalize_evidence_terms(self, terms: List[str]) -> List[str]:
        seen: List[str] = []
        for term in terms or []:
            value = str(term or "").strip()
            if len(value) < 2:
                continue
            if value not in seen:
                seen.append(value)
        return sorted(seen, key=len, reverse=True)[:20]

    def _find_text_evidence(self, text: str, terms: List[str], radius: int = 420) -> Optional[Dict[str, str]]:
        content = str(text or "")
        if not content:
            return None
        for term in self._normalize_evidence_terms(terms):
            index = content.find(term)
            if index < 0:
                continue
            start = max(0, index - radius)
            end = min(len(content), index + len(term) + radius)
            snippet = content[start:end].strip()
            if start > 0:
                snippet = f"...{snippet}"
            if end < len(content):
                snippet = f"{snippet}..."
            return {
                "matched_term": term,
                "evidence_text": snippet,
            }
        return None

    def _looks_like_answer(self, answer: str) -> bool:
        compact = re.sub(r"\s+", "", answer or "")
        if len(compact) < 12:
            return False
        ui_noise_phrases = [
            "深度分析需求并解答",
            "你需要什么帮助",
            "内容由AI生成",
            "请仔细甄别",
            "参考0",
        ]
        noise_hits = sum(1 for phrase in ui_noise_phrases if phrase in compact)
        answer_markers = re.compile(
            r"推荐|靠谱|机构|培训|资质|证书|编号|CAAC|UOM|合规|地址|费用|通过率|建议|优先|总结|理由|第一|第二|第三",
            re.I,
        )
        if noise_hits >= 2 and len(compact) < 180 and not answer_markers.search(compact):
            return False
        if "你需要什么帮助" in compact and len(compact) < 120:
            return False
        ui_only_pattern = re.compile(
            r"^(发送|提交|输入消息|请输入|登录|注册|联网搜索|深度思考|换一换|重新生成|复制|点赞|点踩|分享|更多)+$",
            re.I,
        )
        return not ui_only_pattern.fullmatch(compact)

    def _normalize_answer_text_from_model(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        parsed = self._extract_json_object(text)
        if isinstance(parsed, dict):
            nested = parsed.get("answer_text") or parsed.get("answer") or parsed.get("content")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        return self._clean_model_text(text)

    def _should_use_page_answer(self, visual_answer: str, page_answer: str) -> bool:
        if not self._looks_like_answer(page_answer):
            return False
        if not self._looks_like_answer(visual_answer):
            return True

        visual_compact = re.sub(r"\s+", "", visual_answer or "")
        page_compact = re.sub(r"\s+", "", page_answer or "")
        if len(page_compact) >= max(len(visual_compact) + 80, int(len(visual_compact) * 1.25)):
            return True

        visual_head = visual_compact[:120]
        page_head = page_compact[:120]
        if visual_head and page_head and visual_head not in page_compact and page_head not in visual_compact:
            return len(page_compact) >= len(visual_compact)
        return False

    def _fill_submit_script(
        self,
        question: str,
        input_selector: Optional[str],
        submit_selector: Optional[str],
    ) -> str:
        question_literal = json.dumps(question)
        input_selector_literal = json.dumps(input_selector or "")
        submit_selector_literal = json.dumps(submit_selector or "")
        return f"""
(() => {{
  const question = {question_literal};
  const inputSelector = {input_selector_literal};
  const submitSelector = {submit_selector_literal};
  const visible = (el) => {{
    if (!el) return false;
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  }};
  const editableSelector = 'textarea, [contenteditable="true"], [contenteditable="plaintext-only"], [role="textbox"], input[type="text"], input:not([type])';
  const input = inputSelector
    ? document.querySelector(inputSelector)
    : Array.from(document.querySelectorAll(editableSelector)).reverse().find(visible);
  if (!input) return JSON.stringify({{ok:false,error:'未找到可输入的问题文本框，可在检测平台中配置 input_selector'}});
  input.scrollIntoView({{block:'center', inline:'nearest'}});
  input.focus();
  const isEditable = input.isContentEditable || input.getAttribute('contenteditable') === 'true' || input.getAttribute('role') === 'textbox';
  if (isEditable) {{
    document.execCommand('selectAll', false, null);
    document.execCommand('insertText', false, question);
    input.dispatchEvent(new InputEvent('input', {{bubbles:true, inputType:'insertText', data:question}}));
  }} else {{
    const proto = input.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    if (setter) setter.call(input, question); else input.value = question;
    input.dispatchEvent(new Event('input', {{bubbles:true}}));
    input.dispatchEvent(new Event('change', {{bubbles:true}}));
  }}
  const pressEnter = () => {{
    const init = {{key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true, cancelable:true}};
    input.dispatchEvent(new KeyboardEvent('keydown', init));
    input.dispatchEvent(new KeyboardEvent('keypress', init));
    input.dispatchEvent(new KeyboardEvent('keyup', init));
  }};
  const bySelector = submitSelector ? Array.from(document.querySelectorAll(submitSelector)).find(visible) : null;
  const enabled = (el) => !el.disabled && el.getAttribute('aria-disabled') !== 'true' && !String(el.className || '').toLowerCase().includes('disabled');
  const submitLikeSelector = [
    'button',
    '[role="button"]',
    '[class*="send__"]',
    '[class*="send"]',
    '[class*="send-button"]',
    '[class*="send_button"]',
    '[class*="submit"]',
    '[data-testid*="send"]',
    '[data-testid*="submit"]',
    '[aria-label*="发送"]',
    '[aria-label*="Send"]'
  ].join(',');
  const buttons = Array.from(document.querySelectorAll(submitLikeSelector)).filter((btn) => {{
    if (!visible(btn) || !enabled(btn)) return false;
    const rect = btn.getBoundingClientRect();
    return rect.width <= 120 && rect.height <= 80;
  }});
  const labelOf = (btn) => (btn.innerText || btn.getAttribute('aria-label') || btn.title || btn.getAttribute('data-testid') || String(btn.className || '') || '').trim();
  const submitLabelPattern = /发送|提交|Send|Submit|Ask|send__|send-btn|send-button|send_button/i;
  const byText = buttons.find((btn) => btn.tagName === 'BUTTON' && submitLabelPattern.test(labelOf(btn)))
    || buttons.find((btn) => submitLabelPattern.test(labelOf(btn)));
  const inputRect = input.getBoundingClientRect();
  const nearCandidates = buttons
    .map((btn) => {{
      const rect = btn.getBoundingClientRect();
      const dx = Math.abs((rect.left + rect.width / 2) - (inputRect.right - 20));
      const dy = Math.abs((rect.top + rect.height / 2) - (inputRect.bottom - 20));
      const className = String(btn.className || '');
      let score = dx + dy;
      if (/send__|submit/i.test(className)) score -= 90;
      if (/inner|lottie/i.test(className) || btn.tagName === 'SVG' || btn.tagName === 'PATH') score += 80;
      return {{btn, score}};
    }})
    .sort((a, b) => a.score - b.score);
  const isButtonLike = (btn) => btn.tagName === 'BUTTON' || btn.getAttribute('role') === 'button' || submitLabelPattern.test(labelOf(btn));
  const nearInput = nearCandidates.find((item) => {{
      const rect = item.btn.getBoundingClientRect();
      return isButtonLike(item.btn) && item.score < 220 && rect.left >= inputRect.right - 180 && rect.top >= inputRect.top - 40;
    }})?.btn || nearCandidates.find((item) => {{
      const rect = item.btn.getBoundingClientRect();
      return isButtonLike(item.btn) && item.score < 160 && rect.left >= inputRect.right - 180 && rect.top >= inputRect.top - 40;
    }})?.btn;
  const button = bySelector || byText || nearInput;
  if (!button) {{
    pressEnter();
    return JSON.stringify({{ok:true,mode:'keyboard'}});
  }}
  button.scrollIntoView({{block:'center', inline:'nearest'}});
  button.click();
  return JSON.stringify({{ok:true,mode:'click',buttonText:labelOf(button).slice(0,80)}});
}})()
"""

    def _publish_prefill_script(
        self,
        title: str,
        body: str,
        title_selector: Optional[str],
        body_selector: Optional[str],
    ) -> str:
        title_literal = json.dumps(title or "")
        body_literal = json.dumps(body or "")
        title_selector_literal = json.dumps(title_selector or "")
        body_selector_literal = json.dumps(body_selector or "")
        return f"""
(() => {{
  const title = {title_literal};
  const body = {body_literal};
  const titleSelector = {title_selector_literal};
  const bodySelector = {body_selector_literal};
  const visible = (el) => {{
    if (!el) return false;
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  }};
  const setValue = (el, value) => {{
    if (!el) return false;
    el.scrollIntoView({{block:'center', inline:'nearest'}});
    el.focus();
    const isEditable = el.isContentEditable || el.getAttribute('contenteditable') === 'true' || el.getAttribute('role') === 'textbox';
    if (isEditable) {{
      el.innerText = value;
      el.dispatchEvent(new InputEvent('input', {{bubbles:true, inputType:'insertText', data:value}}));
      el.dispatchEvent(new Event('change', {{bubbles:true}}));
      return true;
    }}
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    if (setter) setter.call(el, value); else el.value = value;
    el.dispatchEvent(new Event('input', {{bubbles:true}}));
    el.dispatchEvent(new Event('change', {{bubbles:true}}));
    return true;
  }};
  const safeQuery = (selector) => {{
    if (!selector) return null;
    try {{ return document.querySelector(selector); }} catch (error) {{ return null; }}
  }};
  const inputs = Array.from(document.querySelectorAll('input[type="text"], input:not([type]), textarea, [contenteditable="true"], [contenteditable="plaintext-only"], [role="textbox"]')).filter(visible);
  const titleInput = safeQuery(titleSelector)
    || inputs.find((el) => /title|标题|subject/i.test(`${{el.placeholder || ''}} ${{el.getAttribute('aria-label') || ''}} ${{el.name || ''}} ${{el.id || ''}}`))
    || inputs.find((el) => el.tagName === 'INPUT');
  const bodyInput = safeQuery(bodySelector)
    || inputs.filter((el) => el !== titleInput).sort((a, b) => {{
      const ar = a.getBoundingClientRect();
      const br = b.getBoundingClientRect();
      return (br.width * br.height) - (ar.width * ar.height);
    }})[0];
  const titleFilled = setValue(titleInput, title);
  const bodyFilled = setValue(bodyInput, body);
  return JSON.stringify({{
    ok: titleFilled || bodyFilled,
    title_filled: titleFilled,
    body_filled: bodyFilled,
    warning: titleFilled && bodyFilled ? null : '页面已打开，但未能完整识别标题或正文输入框，可手动粘贴。'
  }});
}})()
"""
