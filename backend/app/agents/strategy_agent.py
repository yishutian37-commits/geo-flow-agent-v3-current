"""
内容策略 Agent
负责内容触发判断、内容矩阵生成、渠道组合、发布排期、预算估算
"""
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timedelta

from app.models.project import Project
from app.models.brand import Brand
from app.models.question import QuestionGroup
from app.models.content_task import ContentTask


class StrategyAgent:
    """
    内容策略 Agent
    依据诊断结果动态生成内容矩阵和发布策略
    """

    # 诊断状态 → 优先动作的映射规则
    TRIGGER_RULES = [
        {
            "condition": "ai_does_not_know_brand",
            "priority_action": "verification_layer",
            "content_types": ["brand_intro", "official_faq", "百科/企业资料页"],
            "channels": ["官网", "官方自媒体", "媒体", "百科/企业信息平台"],
            "description": "AI不知道品牌：先补基础验证层"
        },
        {
            "condition": "ai_intro_wrong",
            "priority_action": "correct_and_unify",
            "content_types": ["品牌介绍", "产品体系说明", "FAQ", "错误澄清内容"],
            "channels": ["官网", "官方号", "媒体", "客户确认资料"],
            "description": "AI介绍错误：统一口径并纠错"
        },
        {
            "condition": "ai_knows_but_not_recommend",
            "priority_action": "pool_layer",
            "content_types": ["单一品牌推荐", "选购指南", "场景匹配", "细分服务/设备文章"],
            "channels": ["媒体", "自媒体", "垂直平台", "B2B"],
            "description": "AI知道但不推荐：做入池层"
        },
        {
            "condition": "ai_recommends_but_low_rank",
            "priority_action": "weight_layer",
            "content_types": ["PR稿", "案例稿", "行业媒体", "榜单/评选", "重大合作"],
            "channels": ["权威媒体", "行业媒体", "地方媒体"],
            "description": "AI推荐但排序低：做权重提升层"
        },
        {
            "condition": "ai_mentions_negative",
            "priority_action": "sentiment_first",
            "content_types": ["售后说明", "事实解释", "处理进度", "公关声明", "FAQ"],
            "channels": ["官方渠道", "平台申诉", "媒体解释稿"],
            "description": "AI提到负面：先做舆情分类，不直接覆盖"
        },
        {
            "condition": "contact_info_wrong",
            "priority_action": "conversion_layer",
            "content_types": ["官网联系方式页", "地图POI", "B2B店铺", "FAQ"],
            "channels": ["官网", "地图", "官方号", "B2B"],
            "description": "联系方式不准：做转化承接层"
        },
        {
            "condition": "competitors_appear_frequently",
            "priority_action": "differentiation",
            "content_types": ["竞品对比", "行业场景", "特定人群需求", "案例证据"],
            "channels": ["媒体", "行业平台", "官网"],
            "description": "竞品频繁出现：做差异化和场景细分"
        },
        {
            "condition": "local_search_weak",
            "priority_action": "local_info",
            "content_types": ["地址", "地标距离", "路线", "门店介绍", "服务范围"],
            "channels": ["地图", "点评", "小红书", "本地媒体"],
            "description": "本地搜索弱：做本地信息与地图基建"
        },
    ]

    def __init__(self, llm_client=None, model_id: Optional[str] = None):
        self.llm = llm_client
        self.model_id = model_id

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
            "input_price_per_1k": config.input_price_per_1k,
            "output_price_per_1k": config.output_price_per_1k,
        })

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        agent_name: str = "strategy_agent",
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

    def determine_content_trigger(
        self,
        diagnosis_results: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        根据诊断状态决定内容触发动作
        """
        triggered = []
        for rule in self.TRIGGER_RULES:
            condition = rule["condition"]
            if diagnosis_results.get(condition, False):
                triggered.append(rule)
        return triggered

    def generate_content_matrix(
        self,
        project: Project,
        diagnosis_results: Dict[str, Any],
        question_groups: List[QuestionGroup],
    ) -> List[Dict[str, Any]]:
        """
        生成内容矩阵
        四层结构：基础验证层、入池层、权重提升层、转化承接层
        """
        triggers = self.determine_content_trigger(diagnosis_results)
        matrix = []

        for trigger in triggers:
            layer = trigger["priority_action"]
            for content_type in trigger.get("content_types", []):
                for channel in trigger.get("channels", []):
                    matrix.append({
                        "layer": layer,
                        "trigger_condition": trigger["condition"],
                        "content_type": content_type,
                        "target_channel": channel,
                        "priority": "high" if layer in ["verification_layer", "sentiment_first"] else "medium",
                        "description": trigger["description"],
                        "estimated_articles": 3 if layer == "verification_layer" else 2,
                    })

        return matrix

    def generate_channel_recommendation(
        self,
        industry: str,
        content_type: str,
        layer: str,
    ) -> List[Dict[str, Any]]:
        """
        按行业和内容类型推荐渠道组合
        """
        channel_map = {
            "local_life": {
                "verification_layer": ["官网/落地页", "地图", "点评"],
                "pool_layer": ["小红书", "抖音", "本地攻略"],
                "weight_layer": ["本地媒体", "公众号"],
                "conversion_layer": ["地图POI", "官网联系方式页"],
            },
            "education_training": {
                "verification_layer": ["官网", "官方号", "媒体", "百科"],
                "pool_layer": ["媒体", "自媒体", "垂直平台", "B2B"],
                "weight_layer": ["权威媒体", "行业媒体"],
                "conversion_layer": ["官网", "地图", "B2B"],
            },
            "manufacturing_b2b": {
                "verification_layer": ["官网", "B2B平台", "行业百科"],
                "pool_layer": ["B2B平台", "行业媒体", "技术文档"],
                "weight_layer": ["行业媒体", "展会", "案例发布"],
                "conversion_layer": ["官网", "B2B产品页"],
            },
            "consumer_brand": {
                "verification_layer": ["官网", "电商页", "社媒"],
                "pool_layer": ["小红书", "抖音", "测评"],
                "weight_layer": ["媒体", "KOL", "奖项"],
                "conversion_layer": ["电商", "官网", "私域"],
            },
            "professional_service": {
                "verification_layer": ["官网", "专业平台", "案例"],
                "pool_layer": ["行业平台", "专业媒体", "白皮书"],
                "weight_layer": ["权威背书", "行业奖项", "重大项目"],
                "conversion_layer": ["官网", "专业平台", "咨询入口"],
            },
        }

        default_channels = ["官网", "官方自媒体"]
        channels = channel_map.get(industry, {}).get(layer, default_channels)

        return [
            {"channel": c, "priority": "high" if i < 2 else "medium"}
            for i, c in enumerate(channels)
        ]

    def generate_publish_calendar(
        self,
        content_matrix: List[Dict[str, Any]],
        start_date: datetime,
        budget: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        生成30/60天发布日历
        """
        calendar = []
        current_date = start_date

        # 第0-3天：补基建与事实库
        calendar.append({
            "week": "第0-3天",
            "goal": "补基建与事实库",
            "content_focus": "资质、案例、联系方式、地址、地图、官网、资料缺口",
            "quantity": "不追求发文",
            "date_range": [current_date, current_date + timedelta(days=3)],
        })

        # 第1周：让AI认识品牌
        week1_start = current_date + timedelta(days=3)
        calendar.append({
            "week": "第1周",
            "goal": "让AI认识品牌",
            "content_focus": "品牌介绍、产品介绍、服务/资质、案例、FAQ",
            "quantity": "5-6篇",
            "layer": "verification_layer",
            "date_range": [week1_start, week1_start + timedelta(days=7)],
        })

        # 第2周：进入推荐候选
        week2_start = week1_start + timedelta(days=7)
        calendar.append({
            "week": "第2周",
            "goal": "进入推荐候选",
            "content_focus": "单一推荐、选购指南、场景匹配、细分服务/设备",
            "quantity": "5-6篇",
            "layer": "pool_layer",
            "date_range": [week2_start, week2_start + timedelta(days=7)],
        })

        # 第3周：补弱项和加权
        week3_start = week2_start + timedelta(days=7)
        calendar.append({
            "week": "第3周",
            "goal": "补弱项和加权",
            "content_focus": "媒体稿、案例稿、行业稿、售后/服务稿",
            "quantity": "4-6篇",
            "layer": "weight_layer",
            "date_range": [week3_start, week3_start + timedelta(days=7)],
        })

        # 第4周：检测收数
        week4_start = week3_start + timedelta(days=7)
        calendar.append({
            "week": "第4周",
            "goal": "检测收数",
            "content_focus": "根据检测结果补缺口，不盲目堆量",
            "quantity": "2-4篇",
            "layer": "mixed",
            "date_range": [week4_start, week4_start + timedelta(days=7)],
        })

        return calendar

    def estimate_budget(
        self,
        content_matrix: List[Dict[str, Any]],
        article_count: int = 20,
    ) -> Dict[str, Any]:
        """
        估算内容生产、媒体投放、API检测、人工审核成本
        """
        # 内容生产
        content_production = article_count * 500  # 假设每篇500元

        # API检测
        api_cost = article_count * 3 * 5 * 0.1  # 3个模型 * 5次采样 * 0.1元/次

        # 人工审核
        labor_hours = article_count * 0.5  # 每篇0.5小时
        labor_cost = labor_hours * 200  # 200元/小时

        # 媒体投放（如需要）
        media_cost = article_count * 100  # 每篇100元

        total = content_production + api_cost + labor_cost + media_cost

        return {
            "content_production": round(content_production, 2),
            "api_monitoring": round(api_cost, 2),
            "labor_review": round(labor_cost, 2),
            "media_placement": round(media_cost, 2),
            "total_estimated": round(total, 2),
            "article_count": article_count,
            "details": {
                "production_per_article": 500,
                "api_per_article": round(api_cost / article_count, 2) if article_count > 0 else 0,
                "labor_hours_per_article": 0.5,
                "labor_rate": 200,
            }
        }
