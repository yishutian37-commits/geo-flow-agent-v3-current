# 项目知识库与内容工程化改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前 GEO Flow Agent 从“企业资料 + 事实库 + 问题库 + 内容生成”升级为“项目知识库驱动的 GEO 内容工程化闭环”。

**Architecture:** 保留现有企业资料库、品牌事实库、问题库、内容任务、监测复测主链路，不推翻现有结构。新增“项目知识库分层”和“知识资产引用”能力，让资料、故事、判断逻辑、竞品/差评、复盘数据都能被问题矩阵、内容任务和复测报告调用。

**Tech Stack:** FastAPI + SQLAlchemy Async + SQLite runtime migrations + React 18 + Ant Design + pytest + React build。

---

## 背景判断

归档文档核心方法论是：

`输入资料/录音/客户对话/竞品资料 -> 知识库沉淀 -> skill/SOP 调用 -> 选题/内容生产 -> 分发 -> 数据复盘 -> 反向沉淀知识库`

当前项目已有对应主线：

`企业资料库 -> 品牌事实库 -> GEO 问题库 -> AI 监测 -> 内容任务 -> 平台草稿 -> 发布记录 -> 复测报告 -> 记忆/模板沉淀`

因此改造目标不是新做一个泛内容系统，而是把现有“企业资料库”升级为“项目知识库”，让内容工程化思想落在 GEO 场景里。

## 文件结构与责任

- Modify: `backend/app/models/corpus_item.py`
  - 扩展语料条目为项目知识资产，增加知识层级、业务用途、来源链接、证据等级、可复用范围等字段。
- Modify: `backend/app/api/v1/endpoints/corpus_items.py`
  - 增加知识层级筛选、批量导入、AI 分层拆解入口。
- Create: `backend/app/services/project_knowledge_service.py`
  - 负责资料拆分、标签归一、知识层级统计、知识资产推荐。
- Create: `backend/app/prompts/geo/project_knowledge_ingest_v1.md`
  - 约束 AI 将长资料拆成“信息、故事、判断、竞品/差评、复盘数据”。
- Modify: `frontend/src/pages/CorpusLibrary.js`
  - 从“企业资料库”升级为“项目知识库”视图，增加分层筛选、统计卡片、AI 拆分入库。
- Modify: `backend/app/data/question_archetypes.json`
  - 增加关键词五层布局配置，支持跨行业问题矩阵更稳定生成。
- Modify: `backend/app/prompts/geo/question_bank_v1.md`
  - 把问题生成从三层意图扩展为“意图层 + 关键词层 + 证据层”。
- Modify: `backend/app/models/question.py`
  - 增加 `keyword_layer`、`knowledge_need`、`search_asset_type` 字段。
- Modify: `backend/app/schemas/question.py`
  - 暴露新增问题字段。
- Modify: `backend/app/api/v1/endpoints/questions.py`
  - 返回和保存新增问题字段，人工修改继续进入模板学习闭环。
- Modify: `frontend/src/pages/ProjectDetail.js` 或实际问题库组件文件
  - 展示关键词层、知识需求和推荐内容资产。
- Modify: `backend/app/models/content_task.py`
  - 增加内容任务引用知识资产的字段或关联表。
- Modify: `backend/app/api/v1/endpoints/content_tasks.py`
  - 创建内容任务时允许关联问题和知识资产。
- Modify: `backend/app/prompts/geo/article_writer_v1.md`
  - 要求文章生成同时使用品牌事实、问题意图、项目知识资产、平台规则。
- Modify: `frontend/src/pages/ContentManagement.js`
  - 新建内容任务时支持选择代表问题和推荐知识资产。
- Modify: `backend/app/services/report_service.py`
  - 报告增加“知识资产缺口”和“复盘回流建议”。
- Create/Modify tests:
  - `backend/tests/test_project_knowledge_library.py`
  - `backend/tests/test_question_archetype.py`
  - `backend/tests/test_logic_chain_flow.py`
  - `backend/tests/test_content_generation.py`

---

## Phase 0：保护现场与基线验证

### Task 0.1：确认当前状态

**Files:** 不修改文件。

- [ ] Run:

```powershell
git status --short
```

Expected: 记录当前未提交改动，后续只处理本次改造相关文件。

- [ ] Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q
```

Expected: 当前后端测试通过；如果已有失败，记录为改造前基线。

- [ ] Run:

```powershell
npm.cmd --prefix frontend run build
```

Expected: 前端构建通过。

---

## Phase 1：企业资料库升级为项目知识库

### Task 1.1：扩展 CorpusItem 数据模型

**Files:**
- Modify: `backend/app/models/corpus_item.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/v1/endpoints/corpus_items.py`
- Test: `backend/tests/test_project_knowledge_library.py`

**字段设计：**

在 `CorpusItem` 增加：

- `knowledge_layer`: `basic_info | story | judgment | competitor_feedback | content_material | review_data | other`
- `business_use`: `fact_extraction | question_generation | content_writing | monitoring_review | compliance | general`
- `source_url`: 原始网页或资料来源链接。
- `evidence_level`: `official | verified | user_feedback | internal | unverified`
- `reusable_scope`: `project | industry | global`

- [ ] 写失败测试：创建知识资产后应返回新增字段。

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_project_knowledge_library.py::test_create_corpus_item_with_knowledge_fields -q
```

Expected: FAIL，字段不存在或响应中没有字段。

- [ ] 修改模型和接口。

实现要求：

- `CorpusItemCreate` 支持新增字段。
- `CorpusItemUpdate` 支持更新新增字段。
- `_corpus_to_dict()` 返回新增字段。
- `list_corpus_items()` 支持按 `knowledge_layer`、`business_use`、`evidence_level` 筛选。
- 依赖 `ensure_sqlite_model_columns()` 自动补列，不单独写危险迁移脚本。

- [ ] 跑测试。

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_project_knowledge_library.py -q
```

Expected: PASS。

### Task 1.2：前端企业资料库改为项目知识库

**Files:**
- Modify: `frontend/src/pages/CorpusLibrary.js`
- Modify: `frontend/src/services/api.js` 如筛选参数封装需要更新。

**页面改造：**

- 页面标题改为“项目知识库”。
- 顶部增加 4 个统计卡：
  - 基础信息
  - 案例/故事
  - 判断逻辑
  - 复盘数据
- 列表增加字段：
  - 知识层级
  - 业务用途
  - 证据等级
  - 来源链接
- 筛选增加：
  - 知识层级
  - 业务用途
  - 证据等级

- [ ] 修改页面表单。
- [ ] Run:

```powershell
npm.cmd --prefix frontend run build
```

Expected: Compiled successfully。

---

## Phase 2：AI 分层入库，让长资料自动变成知识资产

### Task 2.1：新增项目知识拆解 Prompt

**Files:**
- Create: `backend/app/prompts/geo/project_knowledge_ingest_v1.md`
- Modify: `backend/app/prompts/templates.py` 如模板加载需要登记。

**Prompt 输出协议：**

模型必须返回 JSON：

```json
{
  "items": [
    {
      "title": "知识资产标题",
      "content": "可独立复用的资料片段",
      "knowledge_layer": "basic_info",
      "business_use": "content_writing",
      "evidence_level": "verified",
      "tags": ["资质", "地址"],
      "contains_factual_claim": true,
      "reason": "为什么这样分层"
    }
  ]
}
```

约束：

- 不编造未出现的信息。
- 每条 `content` 必须来自原文或对原文的忠实压缩。
- 证书编号、价格、地址、案例等事实保留原始表述。
- 判断逻辑和故事材料不得直接进入公开事实库，除非后续人工确认。

### Task 2.2：新增 AI 拆分入库服务

**Files:**
- Create: `backend/app/services/project_knowledge_service.py`
- Modify: `backend/app/api/v1/endpoints/corpus_items.py`
- Test: `backend/tests/test_project_knowledge_library.py`

**Endpoint:**

```text
POST /api/v1/corpus-items/ingest
```

Request:

```json
{
  "project_id": "uuid",
  "title": "企业长资料",
  "content": "长文本",
  "source_type": "brochure",
  "source_url": "https://example.com",
  "max_items": 20
}
```

Response:

```json
{
  "created": 8,
  "items": []
}
```

- [ ] 写测试：传入一段含资质、案例、判断逻辑的文本，mock LLM 返回 3 条知识资产。
- [ ] 实现服务。
- [ ] 跑测试：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_project_knowledge_library.py -q
```

Expected: PASS。

### Task 2.3：前端增加“AI 拆分入库”

**Files:**
- Modify: `frontend/src/pages/CorpusLibrary.js`
- Modify: `frontend/src/services/api.js`

**交互：**

- 按钮：`AI 拆分入库`
- 弹窗字段：
  - 标题
  - 来源类型
  - 来源链接
  - 长文本
  - 最大拆分条数
- 成功后刷新项目知识库列表。

- [ ] Run:

```powershell
npm.cmd --prefix frontend run build
```

Expected: Compiled successfully。

---

## Phase 3：问题矩阵接入关键词五层布局

### Task 3.1：扩展行业问题模板配置

**Files:**
- Modify: `backend/app/data/question_archetypes.json`
- Modify: `backend/app/services/question_archetype.py`
- Test: `backend/tests/test_question_archetype.py`

**新增配置结构：**

```json
{
  "keyword_layers": [
    {
      "key": "category",
      "label": "品类词",
      "purpose": "让 AI 知道用户在找哪类服务或产品"
    },
    {
      "key": "region",
      "label": "地域词",
      "purpose": "覆盖本地推荐和附近服务"
    },
    {
      "key": "scenario",
      "label": "场景词",
      "purpose": "覆盖具体需求、用途和人群"
    },
    {
      "key": "proof",
      "label": "验证词",
      "purpose": "覆盖资质、案例、口碑、证书编号"
    },
    {
      "key": "conversion",
      "label": "转化词",
      "purpose": "覆盖价格、流程、地址、联系方式、排期"
    }
  ]
}
```

- [ ] 写测试：读取任意行业模板时能拿到五层关键词配置。
- [ ] 实现默认配置和行业继承。
- [ ] 跑测试。

### Task 3.2：问题模型增加关键词层和知识需求

**Files:**
- Modify: `backend/app/models/question.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/schemas/question.py`
- Modify: `backend/app/api/v1/endpoints/questions.py`
- Test: `backend/tests/test_logic_chain_flow.py`

**新增字段：**

- `keyword_layer`: `category | region | scenario | proof | conversion`
- `knowledge_need`: 该问题需要哪些知识资产支撑。
- `search_asset_type`: 适合补哪类内容资产，如 `本地指南 | 资质核验 | FAQ | 对比测评 | 案例稿`

- [ ] 写测试：创建问题时能保存并返回新增字段。
- [ ] 实现模型、schema、endpoint。
- [ ] 跑相关测试。

### Task 3.3：问题生成 Prompt 接入五层布局

**Files:**
- Modify: `backend/app/prompts/geo/question_bank_v1.md`
- Modify: 现有项目生成问题库的 endpoint/service，优先从 `rg "generate-question-bank"` 定位。
- Test: `backend/tests/test_question_archetype.py`

**生成要求：**

- 每个意图层至少覆盖 3 个关键词层。
- 禁止把 AI 产品名误当服务词，例如 `deepseek`、`kimi`、`豆包` 不应出现在业务问题里。
- 每个问题带：
  - `keyword_layer`
  - `knowledge_need`
  - `search_asset_type`
  - `recommended_platforms`

- [ ] 写测试：切换到制造业、餐饮门店、企业服务项目时，生成问题不包含无人机培训词。
- [ ] 写测试：AI 平台词不会混入业务问题。
- [ ] 实现 prompt 和解析逻辑。
- [ ] 跑测试。

---

## Phase 4：内容任务接入知识资产

### Task 4.1：内容任务支持关联知识资产

**Files:**
- Modify: `backend/app/models/content_task.py`
- Modify: `backend/app/api/v1/endpoints/content_tasks.py`
- Modify: `backend/app/schemas/content_task.py`
- Test: `backend/tests/test_content_generation.py`

**实现方式：**

优先使用 `knowledge_refs_json` 字段保存关联语料 ID 列表和来源摘要，避免一次性引入复杂多对多表。

字段示例：

```json
[
  {
    "corpus_item_id": "uuid",
    "knowledge_layer": "story",
    "title": "客户案例资料"
  }
]
```

- [ ] 写测试：创建内容任务时传入 `knowledge_refs_json`，详情能返回。
- [ ] 实现后端字段和 runtime schema。
- [ ] 跑测试。

### Task 4.2：新建内容任务时推荐知识资产

**Files:**
- Modify: `frontend/src/pages/ContentManagement.js`
- Modify: `frontend/src/services/api.js`

**交互：**

- 用户选择项目后，系统加载该项目知识资产。
- 用户选择关联问题后，按问题的 `knowledge_need` 推荐资料。
- 用户可勾选资料作为文章输入。

- [ ] 实现前端选择器。
- [ ] Run:

```powershell
npm.cmd --prefix frontend run build
```

Expected: Compiled successfully。

### Task 4.3：文章生成 Prompt 使用知识资产

**Files:**
- Modify: `backend/app/prompts/geo/article_writer_v1.md`
- Modify: `backend/app/api/v1/endpoints/content_drafts.py` 或实际生成草稿 service。
- Test: `backend/tests/test_content_generation.py`

**规则：**

- 品牌事实仍是硬边界。
- 项目知识资产可作为表达素材、案例线索、用户场景、判断逻辑。
- 未确认事实不得从知识资产直接写成确定性公开事实。
- 输出仍必须拆成 `title`、`body`、`summary`、`platform_notes`。

- [ ] 写测试：知识资产里有故事片段时，生成请求 payload 包含该片段。
- [ ] 写测试：未确认资质不得作为 confirmed fact 写入正文。
- [ ] 实现 prompt 拼装。
- [ ] 跑测试。

---

## Phase 5：复盘数据反向沉淀知识库

### Task 5.1：发布记录和监测结果可沉淀为复盘知识

**Files:**
- Modify: `backend/app/api/v1/endpoints/monitoring.py`
- Modify: `backend/app/api/v1/endpoints/reports.py`
- Modify: `frontend/src/pages/MonitoringAnalysis.js`
- Modify: `frontend/src/pages/ReportCenter.js`
- Test: `backend/tests/test_project_knowledge_library.py`

**新增动作：**

- 在 AI 搜索详情中增加：`沉淀为复盘资料`
- 在报告详情中增加：`生成知识库补丁建议`

沉淀内容格式：

```json
{
  "knowledge_layer": "review_data",
  "business_use": "monitoring_review",
  "evidence_level": "internal",
  "title": "2026-06-08 文心一言推荐率复盘",
  "content": "本次检测中，品牌在 9 个样本中被提及 3 次..."
}
```

- [ ] 写测试：监测样本沉淀后创建一条 `review_data` CorpusItem。
- [ ] 实现后端动作。
- [ ] 前端增加按钮和确认弹窗。

### Task 5.2：项目详情增加知识闭环视图

**Files:**
- Modify: `frontend/src/pages/ProjectDetail.js`

**展示：**

- 知识资产总数。
- 已确认品牌事实数。
- 问题库覆盖数。
- 内容任务数。
- 检测样本数。
- 复盘资料数。

并显示一条链路提示：

`资料 -> 事实 -> 问题 -> 内容 -> 发布 -> 复测 -> 复盘资料`

- [ ] 前端实现。
- [ ] Run:

```powershell
npm.cmd --prefix frontend run build
```

Expected: Compiled successfully。

---

## Phase 6：验收、文档和打包

### Task 6.1：更新文档

**Files:**
- Modify: `README.md`
- Modify: `GEO-Flow-Agent-V2.3-详细使用说明.md`
- Modify: `GEO-Flow-Agent-V2.3-Agent介绍.md`

**必须说明：**

- 企业资料库已升级为项目知识库。
- 知识层级：基础信息、案例故事、判断逻辑、竞品/差评、复盘数据。
- 问题矩阵支持关键词五层布局。
- 内容任务可以引用知识资产。
- 监测和发布复盘可以沉淀回知识库。

### Task 6.2：完整验证

- [ ] Run backend tests:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q
```

Expected: 全部通过。

- [ ] Run frontend build:

```powershell
npm.cmd --prefix frontend run build
```

Expected: Compiled successfully。

- [ ] 如果用户要求打包，Run:

```powershell
$env:CSC_IDENTITY_AUTO_DISCOVERY='false'
$env:ELECTRON_MIRROR='https://npmmirror.com/mirrors/electron/'
npm.cmd run dist:win
```

Expected:

- `release/GEO Flow Agent Setup 2.3.0.exe`
- `release/GEO-Flow-Agent-2.3.0-Portable.exe`

---

## 推荐施工顺序

1. P0：Phase 1 项目知识库字段和页面。
2. P0：Phase 2 AI 拆分入库。
3. P0：Phase 3 问题矩阵五层布局。
4. P1：Phase 4 内容任务关联知识资产。
5. P1：Phase 5 复盘数据回流。
6. P2：Phase 6 文档、完整测试、打包。

## 不建议现在做的事

- 不建议马上做全自动发布。
- 不建议把所有知识都自动写入行业模板，必须保持管理员确认。
- 不建议把未确认知识资产直接当公开品牌事实。
- 不建议重做整体 UI，只做现有页面的链路增强。
- 不建议引入向量数据库；当前 SQLite + 标签/分层检索足够支撑本地应用第一版。

## 验收标准

改造完成后，业务用户应该能完成这条闭环：

1. 上传一大段企业资料。
2. AI 自动拆成基础信息、案例故事、判断逻辑等知识资产。
3. 从知识资产中抽取并确认品牌事实。
4. 用事实和知识资产生成更真实的问题矩阵。
5. 从问题矩阵创建内容任务，并自动带出相关知识资产。
6. 生成平台化文章，正文不残留 JSON，不编造事实。
7. 发布后记录平台和链接。
8. 复测 AI 是否提及/推荐。
9. 把复测结果沉淀成复盘资料。
10. 下一轮内容和问题生成能利用这些复盘资料。

