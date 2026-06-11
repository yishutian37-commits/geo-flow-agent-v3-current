"""
内容生产 Agent
负责稿件生成、事实引用清单、公开口径控制、合规检查、质量门、平台适配
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone

from app.prompts.templates import render_prompt_template
from app.services.platform_policy import check_platform_policy, get_platform_policy, platform_policy_prompt_text

if TYPE_CHECKING:
    from app.models.content_task import ContentTask
    from app.models.content_draft import ContentDraft
    from app.models.brand_fact import BrandFact
    from app.models.brand import Brand
    from app.models.project import Project
    from app.models.corpus_item import CorpusItem
    from app.models.experience_skill import ExperienceSkill
    from app.models.writing_memory import ContentFeedback, WritingProfile


def safe_json_loads(value: Optional[str]) -> Dict[str, Any]:
    if not value:
        return {}
    import json
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def json_dumps_safe(value: Dict[str, Any]) -> str:
    import json
    return json.dumps(value or {}, ensure_ascii=False, indent=2)


def _format_dict_value(value: Any) -> str:
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            if item in (None, "", [], {}):
                continue
            parts.append(f"{key}: {_format_dict_value(item)}")
        return "；".join(parts)
    if isinstance(value, list):
        return "、".join(str(item) for item in value if item not in (None, ""))
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def format_writing_profile_for_prompt(writing_profile: Any) -> str:
    if not writing_profile:
        return ""

    style = safe_json_loads(getattr(writing_profile, "style_preferences", None))
    title = safe_json_loads(getattr(writing_profile, "title_preferences", None))
    constraints = safe_json_loads(getattr(writing_profile, "constraints", None))
    platform_habits = safe_json_loads(getattr(writing_profile, "platform_habits", None))

    lines = [
        f"- 画像版本: v{getattr(writing_profile, 'version', '') or 1}",
    ]
    if style:
        if style.get("tone"):
            lines.append(f"- 整体语气: {style['tone']}")
        if style.get("sentence_style"):
            lines.append(f"- 句式要求: {style['sentence_style']}")
        if style.get("banned_words"):
            lines.append(
                "- 必须回避的词或表达: "
                f"{_format_dict_value(style['banned_words'])}。如确需表达客观事实，改成有来源、有边界的温和表述。"
            )
    if title:
        if title.get("must_contain"):
            lines.append(f"- 标题需包含: {_format_dict_value(title['must_contain'])}")
        if title.get("preferred_style"):
            lines.append(f"- 标题风格: {title['preferred_style']}")
        if title.get("examples"):
            lines.append(f"- 标题参考: {_format_dict_value(title['examples'])}")
    if constraints:
        lines.append(f"- 合规边界: {_format_dict_value(constraints)}")
    if platform_habits:
        lines.append(f"- 平台习惯: {_format_dict_value(platform_habits)}")

    return "\n".join(line for line in lines if line.strip())


class ProductionAgent:
    """
    内容生产 Agent
    生成可审核、可追述、低风险的内容草稿
    """

    # 文章类型模板
    ARTICLE_TEMPLATES = {
        "brand_intro": {
            "name": "品牌介绍",
            "structure": ["品牌背景", "核心优势", "服务/产品概览", "资质荣誉", "联系方式"],
            "tone": "专业、客观",
        },
        "product": {
            "name": "产品介绍",
            "structure": ["产品概述", "核心功能/参数", "适用场景", "客户案例", "购买/咨询方式"],
            "tone": "专业、具体",
        },
        "case_study": {
            "name": "案例",
            "structure": ["客户背景", "面临挑战", "解决方案", "实施过程", "成果数据"],
            "tone": "真实、数据驱动",
        },
        "recommendation": {
            "name": "推荐/选购指南",
            "structure": ["场景分析", "选购要点", "品牌推荐", "对比说明", "购买建议"],
            "tone": "客观、有帮助",
        },
        "faq": {
            "name": "FAQ",
            "structure": ["常见问题", "专业解答", "补充说明"],
            "tone": "简洁、准确",
        },
        "pr": {
            "name": "PR稿",
            "structure": ["新闻由头", "事件概述", "各方观点", "背景资料", "联系方式"],
            "tone": "新闻体、客观",
        },
    }

    # 平台适配规则
    PLATFORM_RULES = {
        "media": {
            "name": "媒体稿",
            "style": "新闻体，第三人称，客观报道",
            "length": "800-1500字",
            "format": "标题+导语+正文+背景",
            "taboos": ["第一人称", "直接推销", "夸大承诺"],
        },
        "zhihu": {
            "name": "知乎",
            "style": "专业、理性、解释充分，偏经验分享和避坑分析",
            "length": "1200-2500字",
            "format": "问题切入+判断标准+分场景建议+风险提醒",
            "taboos": ["硬广", "空泛口号", "夸大承诺"],
        },
        "toutiao": {
            "name": "头条号",
            "style": "信息密度高，标题清楚，段落短，适合快速阅读",
            "length": "800-1600字",
            "format": "结论前置+要点展开+行动建议",
            "taboos": ["标题党", "绝对化排名", "无依据推荐"],
        },
        "official_account": {
            "name": "公众号",
            "style": "品牌口吻，可读性强",
            "length": "1000-2000字",
            "format": "标题+引导语+正文+互动结尾",
            "taboos": ["过度营销", "敏感词"],
        },
        "xiaohongshu": {
            "name": "小红书",
            "style": "亲身体验，口语化，emoji",
            "length": "300-800字",
            "format": "场景引入+体验分享+总结",
            "taboos": ["硬广", "虚假宣传", "极限词"],
        },
        "b2b_product": {
            "name": "B2B产品页",
            "style": "专业、参数化、B2B导向",
            "length": "500-1000字",
            "format": "产品名+参数+应用场景+联系方式",
            "taboos": ["B2C口吻", "虚假参数"],
        },
        "official_faq": {
            "name": "官网FAQ",
            "style": "简洁、准确、结构化",
            "length": "100-300字/条",
            "format": "Q+A",
            "taboos": ["模糊回答", "过时信息"],
        },
    }

    ARTICLE_TYPE_DETAILS = {
        "brand_intro": {
            "name": "品牌介绍",
            "instruction": "清楚说明品牌是谁、服务什么人、核心可信依据是什么。重点是建立 AI 可采信的品牌实体和服务边界。",
        },
        "product": {
            "name": "产品介绍",
            "instruction": "围绕产品/服务的适用场景、参数或课程内容、交付流程、适用人群展开，不要空泛写卖点。",
        },
        "case_study": {
            "name": "客户案例",
            "instruction": "用真实案例展示价值。若事实库没有明确客户名或结果数据，只能用匿名案例和已确认事实，不能编造客户评价。",
        },
        "recommendation": {
            "name": "推荐/选购指南",
            "instruction": "站在第三方视角给出选择标准，再说明品牌适配的理由。禁止无脑把自家排第一，必须写清推荐边界。",
        },
        "faq": {
            "name": "FAQ问答",
            "instruction": "围绕用户高频疑问回答，答案短而准，涉及价格、地址、资质、通过率等必须以事实库为准。",
        },
        "pr": {
            "name": "PR稿",
            "instruction": "新闻体、第三人称、客观表达。避免夸张营销口吻和未经证实的市场地位。",
        },
        "comparison": {
            "name": "对比分析",
            "instruction": "深度对比不同方案或机构，维度包括资质、服务、费用、案例、交付和适用人群。没有竞品事实时用选择维度对比，不编造竞品。",
        },
        "ranking": {
            "name": "排名榜单",
            "instruction": "说明榜单筛选标准，使用“推荐清单/参考名单/优质机构盘点”等稳健表达，避免绝对排名和极限词。",
        },
        "tutorial": {
            "name": "实操教程",
            "instruction": "按步骤讲清流程、材料、注意事项和常见问题。流程类信息必须来自事实库或写成待确认提醒。",
        },
    }

    # 合规检查项
    COMPLIANCE_CHECKS = [
        {
            "type": "extreme_words",
            "name": "极限词检查",
            "keywords": ["第一", "唯一", "最权威", "最好", "最强", "顶级", "极致", "绝对", "100%", "保证", "包过"],
            "severity": "high",
        },
        {
            "type": "false_promise",
            "name": "虚假承诺检查",
            "keywords": ["保证收益", "保证通过", "保证就业", "稳赚", "零风险", "包拿证", "包过"],
            "severity": "high",
        },
        {
            "type": "resource_risk",
            "name": "资源风险检查",
            "check": "资质、证书、价格、电话、地址是否在brand_facts中且已确认",
            "severity": "high",
        },
        {
            "type": "sensitive_industry",
            "name": "行业敏感词检查",
            "keywords": ["医疗效果", "金融收益", "保健功效", "投资建议"],
            "severity": "high",
        },
        {
            "type": "expired_info",
            "name": "过期信息检查",
            "check": "价格、电话、地址、资质有效期是否过期",
            "severity": "medium",
        },
        {
            "type": "k12_academic",
            "name": "K12学科类检查",
            "check": "是否涉及K12学科培训内容，是否触发强监管",
            "severity": "high",
        },
    ]

    def __init__(self, llm_client=None, model_id: Optional[str] = None):
        self.llm = llm_client
        self.model_id = model_id

    @staticmethod
    def _fact_is_expired(fact: BrandFact) -> bool:
        valid_until = getattr(fact, "valid_until", None)
        if not valid_until:
            return False
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=timezone.utc)
        return valid_until < datetime.now(timezone.utc)

    async def _get_llm_client(self):
        """获取LLM客户端"""
        if self.llm:
            return self.llm
        from app.llm.client import LLMClientFactory
        from app.llm.registry import get_model_registry
        registry = get_model_registry()
        if self.model_id:
            config = registry.get_model(self.model_id)
        else:
            config = registry.get_default_model()
        if not config:
            raise ValueError("No LLM model configured. Please add a model in AI Model Management.")
        return LLMClientFactory.create_client_from_config({
            "provider": config.provider,
            "model": config.model,
            "api_key": config.api_key,
            "base_url": config.base_url,
            "timeout": 300.0,
            "input_price_per_1k": config.input_price_per_1k,
            "output_price_per_1k": config.output_price_per_1k,
        })

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        agent_name: str = "production_agent",
        project_id: Optional[UUID] = None,
        temperature: float = 0.7,
    ) -> str:
        """调用LLM并记录成本"""
        client = await self._get_llm_client()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response = await client.chat(messages=messages, temperature=temperature)
        from app.llm.cost_tracker import get_cost_tracker
        tracker = get_cost_tracker()
        tracker.record(
            project_id=project_id,
            agent_name=agent_name,
            provider=client.provider,
            model=client.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=response.cost_usd,
            cost_cny=response.cost_cny,
            latency_ms=response.latency_ms,
            status="success",
        )
        return response.content

    @staticmethod
    def parse_llm_output(raw_text: str) -> dict:
        """
        解析LLM结构化输出
        兼容三种常见输出：
        1. [TITLE]/[BODY] 标记格式
        2. JSON 元数据 + ---FULL_CONTENT--- 正文
        3. 纯 JSON（title_candidates/full_content/content 等字段）
        """
        import json
        import re

        def clean_code_fence(value: str) -> str:
            return re.sub(r"```(?:json|markdown|md)?\s*|```", "", value or "", flags=re.IGNORECASE).strip()

        def normalize_title(value: Optional[str]) -> Optional[str]:
            if not value:
                return None
            title = clean_code_fence(str(value))
            title = re.sub(r"^\s{0,3}#{1,6}\s*", "", title).strip()
            title = title.strip(" \t\r\n\"'“”‘’")
            return title[:500] if title else None

        def extract_json_object(value: str):
            text = clean_code_fence(value)
            decoder = json.JSONDecoder()
            for match in re.finditer(r"\{", text):
                try:
                    parsed, end = decoder.raw_decode(text[match.start():])
                    return parsed, match.start(), match.start() + end
                except json.JSONDecodeError:
                    continue
            return None, -1, -1

        def stringify_section(value: Any) -> str:
            if value is None:
                return ""
            if isinstance(value, str):
                return value.strip()
            if isinstance(value, list):
                parts = [stringify_section(item) for item in value]
                return "\n".join([part for part in parts if part])
            if isinstance(value, dict):
                lines = []
                if value.get("goal"):
                    lines.append(str(value["goal"]).strip())
                if value.get("prerequisites"):
                    lines.append("前置条件")
                    lines.extend([f"- {item}" for item in value["prerequisites"]])
                if value.get("steps"):
                    lines.append("操作步骤")
                    for step in value["steps"]:
                        if isinstance(step, dict):
                            title = step.get("title") or f"第{step.get('step', '')}步"
                            detail = step.get("detail") or ""
                            tip = step.get("tip") or ""
                            lines.append(str(title).strip())
                            if detail:
                                lines.append(str(detail).strip())
                            if tip:
                                lines.append(f"提示：{str(tip).strip()}")
                        else:
                            lines.append(str(step))
                if value.get("faq"):
                    lines.append("常见问题")
                    for item in value["faq"]:
                        if isinstance(item, dict):
                            lines.append(str(item.get("q", "")).strip())
                            lines.append(str(item.get("a", "")).strip())
                        else:
                            lines.append(str(item))
                if lines:
                    return "\n\n".join([line for line in lines if line])
                return "\n".join(
                    f"{key}: {stringify_section(val)}"
                    for key, val in value.items()
                    if stringify_section(val)
                )
            return str(value).strip()

        def content_from_json(parsed: Dict[str, Any], allow_aida_fallback: bool = True) -> str:
            for key in ["full_content", "content", "article", "markdown", "body"]:
                content = stringify_section(parsed.get(key))
                if content:
                    return content

            aida = parsed.get("aida")
            if allow_aida_fallback and isinstance(aida, dict):
                aida_text = "\n\n".join(
                    stringify_section(aida.get(key))
                    for key in ["attention", "interest", "desire", "action"]
                    if stringify_section(aida.get(key))
                )
                if aida_text:
                    return aida_text

            sections = []
            for key in ["tutorial", "faq", "ranking", "case_study", "comparison_table", "buying_guide"]:
                section = stringify_section(parsed.get(key))
                if section:
                    sections.append(section)
            return "\n\n".join(sections)

        def extract_marker_sections(content: str) -> Dict[str, str]:
            markers = {"TITLE", "BODY", "FACT_REFS", "COMPLIANCE_CHECK", "COMPLIANCE_CHECKS", "END"}
            sections: Dict[str, str] = {}
            current_section = None
            current_lines = []
            for line in (content or "").split("\n"):
                stripped = line.strip()
                if stripped.startswith("[") and stripped.endswith("]") and stripped.strip("[]") in markers:
                    if current_section:
                        sections[current_section] = "\n".join(current_lines).strip()
                    current_section = stripped.strip("[]")
                    current_lines = []
                elif current_section:
                    current_lines.append(line)
            if current_section:
                sections[current_section] = "\n".join(current_lines).strip()
            if "COMPLIANCE_CHECKS" in sections and "COMPLIANCE_CHECK" not in sections:
                sections["COMPLIANCE_CHECK"] = sections["COMPLIANCE_CHECKS"]
            return sections

        def remove_machine_sections(content: str) -> str:
            body = content or ""
            body = re.sub(
                r"(?ims)^\s*\[FACT_REFS\]\s*.*?(?=^\s*\[(?:COMPLIANCE_CHECKS?|END)\]\s*$|\Z)",
                "\n",
                body,
            )
            body = re.sub(
                r"(?ims)^\s*\[COMPLIANCE_CHECKS?\]\s*.*?(?=^\s*\[END\]\s*$|\Z)",
                "\n",
                body,
            )
            body = re.sub(r"(?ims)^\s*\[END\]\s*.*\Z", "\n", body)
            return body

        def strip_body_artifacts(content: str, title: Optional[str]) -> str:
            body = clean_code_fence(content)
            body = body.strip().strip("\"'")
            body = re.sub(r"^\s*---FULL_CONTENT---\s*", "", body, flags=re.IGNORECASE)
            body = remove_machine_sections(body).strip()
            parsed_prefix, json_start, json_end = extract_json_object(body)
            if isinstance(parsed_prefix, dict) and json_start == 0:
                body = body[json_end:].strip()
                body = re.sub(r"^\s*---FULL_CONTENT---\s*", "", body, flags=re.IGNORECASE).strip()
                body = remove_machine_sections(body).strip()
            if title:
                lines = body.splitlines()
                while lines and not lines[0].strip():
                    lines.pop(0)
                if lines:
                    first = normalize_title(lines[0])
                    if first == title:
                        lines.pop(0)
                        while lines and not lines[0].strip():
                            lines.pop(0)
                        body = "\n".join(lines).strip()
            return body

        result = {
            "title": None,
            "body": None,
            "fact_refs_raw": None,
            "compliance_raw": None,
            "raw": raw_text,
        }

        raw_text = raw_text or ""
        separator = "---FULL_CONTENT---"
        separator_index = raw_text.upper().find(separator)
        if separator_index >= 0:
            meta_text = raw_text[:separator_index]
            body_text = raw_text[separator_index + len(separator):]
            parsed, _, _ = extract_json_object(meta_text)
            title = None
            aida = {}
            if isinstance(parsed, dict):
                candidates = parsed.get("title_candidates")
                if isinstance(candidates, list) and candidates:
                    title = normalize_title(candidates[0])
                title = title or normalize_title(parsed.get("title"))
                aida = parsed.get("aida") or {}
            result["title"] = title or normalize_title(body_text.splitlines()[0] if body_text.splitlines() else None) or "未命名草稿"
            result["body"] = strip_body_artifacts(body_text, result["title"])
            result["aida"] = aida
            return result

        sections = extract_marker_sections(raw_text)
        if sections:
            result["fact_refs_raw"] = sections.get("FACT_REFS", "")
            result["compliance_raw"] = sections.get("COMPLIANCE_CHECK", "")

        if sections and (sections.get("TITLE") or sections.get("BODY")):
            result["title"] = normalize_title(sections.get("TITLE")) or "未命名草稿"
            result["body"] = strip_body_artifacts(sections.get("BODY", raw_text), result["title"])
            return result

        parsed, _, json_end = extract_json_object(raw_text)
        if isinstance(parsed, dict):
            candidates = parsed.get("title_candidates")
            title = None
            if isinstance(candidates, list) and candidates:
                title = normalize_title(candidates[0])
            title = title or normalize_title(parsed.get("title")) or "未命名草稿"
            body = content_from_json(parsed, allow_aida_fallback=False)
            trailing_body = clean_code_fence(raw_text[json_end:]) if json_end >= 0 else ""
            if trailing_body:
                body = trailing_body
            if not body:
                body = content_from_json(parsed, allow_aida_fallback=True)
            result["title"] = title
            result["body"] = strip_body_artifacts(body or raw_text, title)
            result["fact_refs_raw"] = result["fact_refs_raw"] or stringify_section(parsed.get("fact_refs") or parsed.get("FACT_REFS"))
            result["compliance_raw"] = result["compliance_raw"] or stringify_section(parsed.get("compliance_check") or parsed.get("COMPLIANCE_CHECK"))
            result["aida"] = parsed.get("aida") or {}
            return result

        lines = raw_text.strip().split('\n')
        result["title"] = normalize_title(lines[0]) if lines else "未命名草稿"
        result["body"] = strip_body_artifacts(raw_text, result["title"])
        return result

    def generate_article_prompt(
        self,
        content_task: ContentTask,
        brand_facts: List[BrandFact],
        platform: str = "media",
        project: Optional[Project] = None,
        brand: Optional[Brand] = None,
        writing_profile: Optional[WritingProfile] = None,
        active_rules: Optional[List[ContentFeedback]] = None,
        question_context: Optional[Dict[str, Any]] = None,
        knowledge_assets: Optional[List[CorpusItem]] = None,
        experience_skills: Optional[List[ExperienceSkill]] = None,
        feedback_context: Optional[str] = None,
        source_draft_context: Optional[str] = None,
    ) -> str:
        """
        生成文章Prompt（对应PRD附录A6）
        """
        template = self.ARTICLE_TEMPLATES.get(content_task.content_type, self.ARTICLE_TEMPLATES["brand_intro"])
        type_detail = self.ARTICLE_TYPE_DETAILS.get(content_task.content_type, {
            "name": template["name"],
            "instruction": f"按照{template['name']}的目标组织内容，优先补齐AI采信所需的证据。",
        })
        platform_rule = dict(self.PLATFORM_RULES.get(platform, self.PLATFORM_RULES["media"]))
        platform_policy = get_platform_policy(platform)
        platform_rule.update({
            "name": platform_policy.get("name", platform_rule.get("name", platform)),
            "style": platform_policy.get("style", platform_rule.get("style", "")),
            "length": platform_policy.get("length", platform_rule.get("length", "")),
            "format": platform_policy.get("format", platform_rule.get("format", "")),
            "taboos": list(dict.fromkeys(
                list(platform_rule.get("taboos", []))
                + list(platform_policy.get("forbidden_patterns", []))
                + list(platform_policy.get("warning_patterns", []))
            )),
        })

        facts_text = "\n".join([
            f"- [{f.fact_type}] {f.public_wording or f.value} (ID: {f.id})"
            for f in brand_facts
            if f.status == "confirmed" and f.fact_scope == "public" and not self._fact_is_expired(f)
        ]) or "暂无已确认公开事实。当前只能生成资料不足版草稿，不能写确定性的资质、价格、地址、电话、案例、通过率、证书编号等事实。"

        pending_facts_text = "\n".join([
            f"- [{f.status}/{f.fact_scope}/{f.fact_type}] {f.public_wording or f.value}"
            for f in brand_facts
            if f.fact_scope == "public" and (
                f.status != "confirmed" or self._fact_is_expired(f)
            )
        ]) or "暂无"

        has_publishable_facts = facts_text and not facts_text.startswith("暂无")

        profile_text = format_writing_profile_for_prompt(writing_profile)

        memory_feedback = []
        for item in (active_rules or []):
            parts = [
                f"类型: {getattr(item, 'feedback_type', '')}",
                f"评分: {getattr(item, 'rating', '')}" if getattr(item, "rating", None) else "",
                f"优化后重写提示词: {getattr(item, 'diff_summary', '')}" if getattr(item, "diff_summary", None) else "",
                f"规则: {getattr(item, 'rule_text', '')}" if getattr(item, "rule_text", None) else "",
                f"分类: {getattr(item, 'rule_category', '')}" if getattr(item, "rule_category", None) else "",
                f"原始反馈证据: {getattr(item, 'comment', '')}" if getattr(item, "comment", None) and not getattr(item, "diff_summary", None) else "",
            ]
            text = "；".join(part for part in parts if part)
            if text:
                memory_feedback.append(text)
        rules_text = "\n".join(f"{index + 1}. {item}" for index, item in enumerate(memory_feedback))

        project_text = "\n".join([
            f"- 项目: {getattr(project, 'name', '') or ''}",
            f"- 行业: {getattr(project, 'industry', '') or ''}",
            f"- 地区: {getattr(project, 'region', '') or ''}",
            f"- 备注: {getattr(project, 'notes', '') or ''}",
            f"- 品牌: {getattr(brand, 'brand_name', '') or getattr(project, 'name', '') or ''}",
            f"- 公司主体: {getattr(brand, 'company_name', '') or ''}",
            f"- 品牌描述: {getattr(brand, 'description', '') or ''}",
        ]).strip()

        question_text = ""
        if question_context:
            question_text = "\n".join(
                f"- {key}: {value}"
                for key, value in question_context.items()
                if value
            )

        knowledge_assets_text = "\n".join([
            (
                f"- [{getattr(item, 'knowledge_layer', '')}/{getattr(item, 'business_use', '')}/"
                f"{getattr(item, 'evidence_level', '')}] {getattr(item, 'title', '') or '未命名知识资产'}："
                f"{(getattr(item, 'content', '') or '')[:600]}"
                f"{' 来源：' + getattr(item, 'source_url', '') if getattr(item, 'source_url', '') else ''}"
            )
            for item in (knowledge_assets or [])
            if getattr(item, "content", None)
        ]) or "暂无"

        experience_skills_text = "\n".join([
            (
                f"{index + 1}. [{getattr(item, 'scope', '')}/{getattr(item, 'trigger_scene', '')}/"
                f"{getattr(item, 'skill_type', '')}] {getattr(item, 'name', '') or '未命名经验技能'}："
                f"{getattr(item, 'content', '')}"
            )
            for index, item in enumerate(experience_skills or [])
            if getattr(item, "content", None) and getattr(item, "status", "active") == "active"
        ]) or "暂无"

        publishable_fact_contract = (
            "有。可以引用已确认事实。"
            if has_publishable_facts
            else "没有。必须写成资料不足版草稿：只能使用项目名、行业、地区、用户问题和通用选择标准；涉及资质/价格/案例/地址/电话/通过率/证书编号时，必须写成“建议向机构核验/待补充资料”，不能写成品牌已经具备。"
        )

        return render_prompt_template("geo/article_writer_v1.md", {
            "article_type_name": type_detail["name"],
            "platform_name": platform_rule["name"],
            "platform_style": platform_rule["style"],
            "platform_length": platform_rule["length"],
            "platform_format": platform_rule.get("format", ""),
            "template_structure": ", ".join(template["structure"]),
            "type_instruction": type_detail["instruction"],
            "content_layer": content_task.layer,
            "priority": content_task.priority,
            "platform_policy_text": platform_policy_prompt_text(platform),
            "project_text": project_text or "暂无",
            "question_text": question_text or "暂无",
            "knowledge_assets_text": knowledge_assets_text,
            "experience_skills_text": experience_skills_text,
            "source_draft_context": source_draft_context or "暂无",
            "feedback_context": feedback_context or "暂无",
            "facts_text": facts_text,
            "pending_facts_text": pending_facts_text,
            "profile_text": profile_text or "暂无",
            "rules_text": rules_text or "暂无",
            "publishable_fact_contract": publishable_fact_contract,
        })

    def check_compliance(self, draft_text: str, brand_facts: List[BrandFact]) -> List[Dict[str, Any]]:
        """
        合规检查
        """
        import re

        issues = []
        text_lower = draft_text.lower()

        placeholder_matches = sorted({
            match.strip()
            for match in re.findall(r"\[([^\]\n]{1,24})\]", draft_text)
            if any(ch.isalpha() or "\u4e00" <= ch <= "\u9fff" for ch in match)
        })
        if placeholder_matches:
            issues.append({
                "type": "placeholder_artifact",
                "name": "模板占位符残留",
                "severity": "high",
                "message": f"内容仍包含模板占位符：{', '.join(f'[{item}]' for item in placeholder_matches[:8])}",
            })

        for check in self.COMPLIANCE_CHECKS:
            if check["type"] == "resource_risk":
                confirmed_refs = self.generate_fact_references(draft_text, brand_facts)
                high_risk_keywords = [
                    "资质", "证书", "编号", "许可证", "执照", "专利", "软著",
                    "地址", "电话", "价格", "费用", "报价", "案例", "客户",
                    "通过率", "就业", "授权", "认证", "官网",
                ]
                has_high_risk_claim = any(keyword in draft_text for keyword in high_risk_keywords)
                if has_high_risk_claim and not confirmed_refs:
                    issues.append({
                        "type": check["type"],
                        "name": check["name"],
                        "severity": check["severity"],
                        "message": "内容包含资质、案例、价格、联系方式等事实性表述，但未匹配到可公开使用的已确认品牌事实",
                    })

                for fact in brand_facts:
                    candidates = [fact.value, fact.public_wording]
                    matched = any(
                        candidate and len(candidate.strip()) >= 4 and candidate.lower() in text_lower
                        for candidate in candidates
                    )
                    if not matched:
                        continue

                    if fact.status != "confirmed":
                        issues.append({
                            "type": "unconfirmed_fact",
                            "name": check["name"],
                            "severity": "high",
                            "message": f"引用了未确认事实: {fact.fact_type} (status={fact.status})",
                        })
                    elif fact.fact_scope != "public":
                        issues.append({
                            "type": "restricted_fact",
                            "name": check["name"],
                            "severity": "high",
                            "message": f"引用了非公开事实: {fact.fact_type} (scope={fact.fact_scope})",
                        })
                    elif self._fact_is_expired(fact):
                        issues.append({
                            "type": "expired_fact",
                            "name": check["name"],
                            "severity": "high",
                            "message": f"引用了已过期事实: {fact.fact_type}",
                        })
            elif check["type"] == "expired_info":
                expired_facts = [f for f in brand_facts if f.status == "expired"]
                for fact in expired_facts:
                    if fact.value.lower() in text_lower:
                        issues.append({
                            "type": check["type"],
                            "name": check["name"],
                            "severity": check["severity"],
                            "message": f"引用了已过期的事实: {fact.fact_type}",
                        })
            elif check["type"] == "k12_academic":
                if "k12" in text_lower or "学科培训" in text_lower or "应试" in text_lower:
                    issues.append({
                        "type": check["type"],
                        "name": check["name"],
                        "severity": check["severity"],
                        "message": "内容可能涉及K12学科培训，需额外合规审核",
                    })
            else:
                keywords = check.get("keywords", [])
                found = [kw for kw in keywords if kw.lower() in text_lower]
                if found:
                    issues.append({
                        "type": check["type"],
                        "name": check["name"],
                        "severity": check["severity"],
                        "message": f"发现敏感词: {', '.join(found)}",
                    })

        return issues

    def check_platform_compliance(self, draft_text: str, platform: Optional[str]) -> List[Dict[str, Any]]:
        """
        平台发文政策检查。
        与事实/通用合规分开，便于前端展示“平台风险”而不是一概拦截。
        """
        return check_platform_policy(draft_text, platform)

    def generate_platform_rewrite_prompt(
        self,
        *,
        title: str,
        body: str,
        platform: Optional[str],
        platform_issues: List[Dict[str, Any]],
    ) -> str:
        """
        针对平台高风险问题进行一次性修复重写。
        只修平台违规和机器残留，不扩写新事实，避免重写时漂移。
        """
        issues_text = "\n".join(
            f"- {item.get('name', '平台问题')}: {item.get('message', '')}"
            for item in platform_issues
        ) or "- 存在平台高风险问题"
        policy_text = platform_policy_prompt_text(platform)
        return f"""你需要对下面这篇文章进行一次平台合规修复重写。

## 平台高风险问题
{issues_text}

## 平台规则
{policy_text}

## 修复要求
1. 只修复平台违规、机器格式残留、引流/高危表达和标题正文格式问题。
2. 不新增资质、价格、地址、案例、证书编号、通过率、联系方式等事实。
3. 保持原主题、原平台、原品牌主体和原内容意图，不要改成另一篇文章。
4. 正文必须是可直接发布的纯文本，不要出现 JSON、代码围栏、Markdown 标题、FACT_REFS、COMPLIANCE_CHECK。
5. 标题只放在 JSON 元数据 title_candidates 中，不要在正文第一行重复标题。

## 原标题
{title or '未命名草稿'}

## 原正文
{body or ''}

## 输出格式
```json
{{
  "title_candidates": ["修复后的标题"],
  "aida": {{
    "attention": "修复说明",
    "interest": "修复说明",
    "desire": "修复说明",
    "action": "修复说明"
  }},
  "platform_notes": "说明已按平台规则修复"
}}
```
---FULL_CONTENT---
这里写修复后的纯文本正文。
"""

    def generate_fact_references(
        self,
        draft_text: str,
        brand_facts: List[BrandFact],
    ) -> List[Dict[str, Any]]:
        """
        生成事实引用清单
        检查每段事实性陈述是否绑定confirmed brand_facts
        """
        references = []
        # 简化实现：匹配brand_facts的public_wording在文本中的位置
        for fact in brand_facts:
            if fact.status != "confirmed" or fact.fact_scope != "public":
                continue
            if self._fact_is_expired(fact):
                continue
            wording = fact.public_wording or fact.value
            if wording and wording.lower() in draft_text.lower():
                references.append({
                    "fact_id": str(fact.id),
                    "fact_type": fact.fact_type,
                    "wording": wording,
                    "status": "bound",
                })

        return references

    def adapt_for_platform(
        self,
        draft_text: str,
        target_platform: str,
    ) -> str:
        """
        平台适配：同一主题按不同平台调整形式
        """
        rule = self.PLATFORM_RULES.get(target_platform)
        if not rule:
            return draft_text

        # 简化实现：返回适配提示
        return f"""【{rule['name']}适配版】
适配规则: {rule['style']}
长度要求: {rule['length']}
格式要求: {rule['format']}
禁忌: {', '.join(rule['taboos'])}

---

{draft_text}
"""

    def validate_publish_ready(
        self,
        draft: ContentDraft,
        brand_facts: List[BrandFact],
        platform_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        验证草稿是否可进入 Publish Ready 状态
        """
        issues = []

        # 1. 检查事实引用
        refs = self.generate_fact_references(draft.body or "", brand_facts)
        ref_ids = {r["fact_id"] for r in refs}

        # 2. 检查是否有未确认的事实引用
        for fact in brand_facts:
            if fact.status != "confirmed":
                # 如果未确认事实被引用，标记问题
                if str(fact.id) in ref_ids:
                    issues.append({
                        "type": "unconfirmed_fact",
                        "severity": "high",
                        "message": f"引用了未确认的事实: {fact.fact_type} (status={fact.status})",
                    })

        # 3. 合规检查
        compliance_issues = self.check_compliance(draft.body or "", brand_facts)
        issues.extend(compliance_issues)

        # 4. 平台政策检查
        platform_issues = self.check_platform_compliance(
            f"{draft.title or ''}\n{draft.body or ''}",
            platform_override or getattr(draft, "platform", None),
        )
        issues.extend(platform_issues)

        # 5. 检查风险等级
        if draft.risk_level == "high":
            issues.append({
                "type": "high_risk",
                "severity": "high",
                "message": "草稿被标记为高风险，需额外审核",
            })

        blocking_issues = [i for i in issues if i.get("severity") == "high"]
        warning_issues = [i for i in issues if i.get("severity") != "high"]

        return {
            "can_publish": len(blocking_issues) == 0,
            "issues": issues,
            "fact_references": refs,
            "total_issues": len(issues),
            "high_severity_issues": len(blocking_issues),
            "warning_issues": len(warning_issues),
        }
