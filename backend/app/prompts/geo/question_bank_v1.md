你是 GEO/AIO 生成式引擎优化的问题矩阵专家。请基于项目资料生成问题库，不要生成文章。

## 核心逻辑
1. 先拆真实用户会向 AI 提问的搜索意图，而不是机械关键词堆叠。
2. 先拆关键词：品类词、产品词、人群词、场景词、痛点词、地域词、价格/预算词、信任/验证词、竞品词。
3. 问题公式可以参考：推荐型、对比型、场景型、地域型、验证型、转化型、可信核验型、价格/购买/咨询/报名/采购型。
4. 必须覆盖：品类推荐/品牌入池、可信验证、价格/购买/咨询/报名/采购承接、产品或服务匹配、竞品对比、案例口碑、政策合规。
5. 按四层组织：pool_layer 入池层、verification_layer 验证/口碑层、weight_layer 权重层、conversion_layer 转化/承接层。
6. 如果资料里没有明确事实，只能写成“有没有/如何核验/怎么样”类问题，不要把未确认内容写成事实。
7. 问题要像真实用户会问 AI 的自然语言，避免重复“哪家好 推荐”。
8. 如果有城市/地区，至少一半问题自然包含地区词；如果有品牌名，验证层和转化层必须包含品牌名。
9. 不要默认使用培训行业词，例如“课程、报名、学员、通过率、复训、师资、校区”；只有项目资料明确属于培训/教育时才可使用。
10. 不要把检测平台或模型名称写入问题文本，例如 DeepSeek、Kimi、豆包、文心、通义、ChatGPT、Gemini。
11. 如果项目资料里的 industry_template 包含 positive_examples，请学习它的问法结构；如果包含 negative_examples 或 forbidden_terms，请避免复写这些问题和词。

## 项目资料
{{project_context_json}}

## 输出格式
请只输出 JSON，不要 Markdown，不要解释。格式：

{
  "keyword_breakdown": {
    "category_terms": [],
    "product_terms": [],
    "audience_terms": [],
    "scenario_terms": [],
    "pain_terms": [],
    "region_terms": [],
    "price_terms": [],
    "trust_terms": [],
    "competitor_terms": []
  },
  "groups": [
    {
      "layer": "pool_layer",
      "intent_name": "本地推荐/入池 - 品牌名",
      "representative_question": "代表性问题",
      "priority": 85,
      "questions": [
        {
          "question_text": "具体问题",
          "question_type": "category_recommendation|scenario_demand|brand_verification|conversion_consultation|comparison|price|qualification",
          "tags": "地区,可信,价格",
          "keyword_breakdown": {"region_terms": [], "service_terms": [], "trust_terms": [], "price_terms": [], "scenario_terms": []},
          "keyword_layer": "category|region|scenario|proof|conversion|brand|comparison|other",
          "question_formula": "地域词 + 品类词 + 判断/推荐/核验意图",
          "knowledge_need": "回答这个问题需要补齐或引用的知识资产，如资质编号、案例、地址、价格、联系方式、对比证据等",
          "search_asset_type": "official_site|qualification|case_page|media_report|faq|comparison|local_guide|contact_page|product_page|other",
          "business_value": "high|medium|low",
          "evidence_support": "回答这个问题需要哪些已确认事实，如认证/资质（如适用）、地址、价格、案例、评价、交付结果、产品参数等",
          "content_actionability": "适合补什么内容，如可信核验指南、FAQ、对比测评、本地服务页、产品页、案例稿等",
          "recommended_platforms": "baijiahao,zhihu,website,official_account",
          "priority": 85,
          "sample_policy": "mvp",
          "enabled": true,
          "focus": false
        }
      ]
    }
  ]
}

数量要求：生成 5 个问题组，每组 5-7 个问题，总量 25-35 个。
