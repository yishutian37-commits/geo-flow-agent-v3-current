"""
诊断与意图 Agent
负责品牌AI体检、三层问题库生成、回答模式分析、竞争差距分析、基线建立
"""
from typing import List, Dict, Any, Optional
from uuid import UUID

from app.models.project import Project
from app.models.brand import Brand
from app.models.question import QuestionGroup, Question
from app.models.model_target import ModelTarget
from app.models.baseline_run import BaselineRun
from app.llm.client import LLMClientFactory
from app.llm.registry import get_model_registry
from app.llm.cost_tracker import get_cost_tracker


class DiagnosisAgent:
    """
    诊断与意图 Agent
    """

    def __init__(self, llm_client=None, model_id: Optional[str] = None):
        self.llm = llm_client
        self.model_id = model_id

    async def _get_llm_client(self):
        """获取LLM客户端"""
        if self.llm:
            return self.llm
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
        agent_name: str = "diagnosis_agent",
        project_id: Optional[UUID] = None,
        temperature: float = 0.7,
    ) -> str:
        """调用LLM并记录成本"""
        client = await self._get_llm_client()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = await client.chat(
            messages=messages,
            temperature=temperature,
        )

        # 记录成本
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

    async def run_brand_ai_checkup(
        self,
        brand: Brand,
        model_target: ModelTarget,
        project_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        品牌AI体检：调用LLM分析品牌在检测平台中的认知状态
        """
        system_prompt = "你是GEO品牌AI体检专家。请基于公开信息分析品牌在AI问答产品中的可见性状态，使用客观观察性语言。"

        user_prompt = f"""请对以下品牌进行AI体检分析：

品牌名称: {brand.brand_name}
公司主体: {brand.company_name or '未知'}
行业: {brand.project.industry if brand.project else '未知'}
官网: {brand.official_site or '未知'}
品牌描述: {brand.description or '未知'}

检测平台: {model_target.product_name}
支持机制: {model_target.supported_mechanisms or '未知'}

请生成以下三类问题的初始采样分析：
1. 曝光/推荐层：AI是否知道这个品牌？是否推荐？
2. 验证/口碑层：AI如何描述这个品牌？有无负面？
3. 转化/承接层：AI提供的联系方式、地址、购买路径是否准确？

输出要求：
- 每类问题给出3-5个具体问句
- 对每个问句，给出当前AI可能的回答摘要
- 识别回答中的错误点、负面点、信息缺失点
- 评估品牌当前在AI中的认知状态（未知/知道但不推荐/推荐但排序低/正常推荐）

注意：你只能基于现有公开信息做分析，不得编造客户未提供的数据。"""

        try:
            result = await self._call_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                agent_name="brand_ai_checkup",
                project_id=project_id,
            )
            return {
                "success": True,
                "brand_id": str(brand.id),
                "model_target": model_target.product_name,
                "analysis": result,
                "status": "completed",
            }
        except Exception as e:
            return {
                "success": False,
                "brand_id": str(brand.id),
                "error": str(e),
                "status": "failed",
            }

    async def generate_question_bank(
        self,
        brand: Brand,
        diagnosis_result: Dict[str, Any],
        project_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        调用LLM生成三层问题库
        """
        system_prompt = "你是GEO问题意图分析专家。请基于品牌定位生成可检测、可追踪的三层问题库，输出JSON格式。"

        user_prompt = f"""请基于以下品牌信息，生成三层问题库。

品牌名称: {brand.brand_name}
行业: {brand.project.industry if brand.project else '未知'}
目标客户: {brand.project.notes if brand.project else '未知'}

诊断结果摘要:
{diagnosis_result.get('analysis', '暂无')}

请生成以下三类问题，输出JSON格式：

## 1. 曝光/推荐层（Awareness）
用户尚未明确选择，AI需要知道并可能推荐该品牌的问题。

## 2. 验证/口碑层（Verification）
用户已知道品牌，需要验证其可靠性和口碑的问题。

## 3. 转化/承接层（Conversion）
用户有明确意向，需要获取联系方式、地址、价格、报名路径的问题。

JSON格式要求:
{{
  "question_groups": [
    {{
      "layer": "exposure|verification|conversion",
      "intent_name": "意图名称",
      "representative_question": "代表性问题",
      "priority": 1-100,
      "sample_policy": "quick_diagnosis|mvp|monthly|key|acceptance",
      "questions": [
        {{
          "question_text": "具体问题",
          "priority": 1-100,
          "sample_policy": "..."
        }}
      ]
    }}
  ]
}}

要求：
- 合并相似意图，避免重复
- 每个意图组至少3个问题
- 优先级用数字表示（100最高）
- 采样策略根据重要性选择
"""

        try:
            result = await self._call_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                agent_name="question_bank_generator",
                project_id=project_id,
                temperature=0.8,
            )
            return {
                "success": True,
                "brand_id": str(brand.id),
                "raw_output": result,
                "status": "completed",
            }
        except Exception as e:
            return {
                "success": False,
                "brand_id": str(brand.id),
                "error": str(e),
                "status": "failed",
            }

    async def analyze_answer_pattern(
        self,
        question: Question,
        answer_samples: List[str],
        project_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        调用LLM分析回答模式
        """
        samples_text = "\n\n".join([f"样本{i+1}:\n{s}" for i, s in enumerate(answer_samples)])

        system_prompt = "你是GEO回答模式分析专家。请基于AI回答样本归纳影响因素假设，不得声称知道模型内部排序逻辑。"

        user_prompt = f"""请基于以下通用AI回答样本，归类问题的回答模式和可能影响推荐的因素。

问题: {question.question_text}

回答样本:
{samples_text}

请输出：
1. 高置信信源：回答中引用了哪些权威来源？
2. 推荐维度：AI从哪些维度评估和推荐？
3. 竞品出现原因：为什么竞品会出现？
4. 品牌缺失原因：为什么品牌没出现或没被推荐？
5. 需要补充的内容资源：还缺什么资料？
"""

        try:
            result = await self._call_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                agent_name="answer_pattern_analyzer",
                project_id=project_id,
            )
            return {
                "success": True,
                "question_id": str(question.id),
                "analysis": result,
                "status": "completed",
            }
        except Exception as e:
            return {
                "success": False,
                "question_id": str(question.id),
                "error": str(e),
                "status": "failed",
            }

    async def generate_competitor_gap_analysis(
        self,
        brand: Brand,
        competitor_brands: List[str],
        samples: Dict[str, List[str]],
        project_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        调用LLM进行竞争差距分析
        """
        samples_text = ""
        for comp, compsamples in samples.items():
            samples_text += f"\n\n{comp}的样本:\n" + "\n".join(compsamples[:3])

        system_prompt = "你是GEO竞争分析专家。请客观比较品牌与竞品在AI可见性方面的差距。"

        user_prompt = f"""请比较品牌'{brand.brand_name}'与主要竞品的差距。

竞品列表: {', '.join(competitor_brands)}

样本摘要:
{samples_text}

请从以下维度分析差距：
1. 出现率：在相同问题下，各品牌的出现频率
2. 事实准确率：AI对品牌定位、产品、地址、电话等描述的正确率
3. 案例丰富度：AI是否能引用具体案例
4. 资源完整度：官网、媒体、社媒等资源的覆盖情况
5. 权威信源：是否有第三方权威来源背书

输出：竞争差距表，包含各维度评分（1-10分）和具体建议。
"""

        try:
            result = await self._call_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                agent_name="competitor_gap_analyzer",
                project_id=project_id,
            )
            return {
                "success": True,
                "brand_id": str(brand.id),
                "analysis": result,
                "status": "completed",
            }
        except Exception as e:
            return {
                "success": False,
                "brand_id": str(brand.id),
                "error": str(e),
                "status": "failed",
            }
