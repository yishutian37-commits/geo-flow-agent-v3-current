# GEO Flow Agent V2.3

GEO Flow Agent V2.3 是一个本地运行的 GEO / AIO 工作台，用来把「品牌资料、品牌事实、问题库、AI 搜索监测、内容生产、发布记录、复测报告」串成一条可执行的优化链路。

它不是单纯的 AI 写作工具，而是围绕生成式搜索场景设计的项目操作系统：先沉淀可验证事实，再生成真实用户会问的问题，随后监测各 AI 产品的回答表现，并把未提及、未推荐、来源不足等问题回流为内容任务。

当前仓库包含完整的前端、后端、桌面壳和 QWebBridge 集成源码，可开发运行，也可打包成 Windows 桌面应用。

## 核心链路

```text
项目/品牌资料
  -> 项目知识库（分层资料、案例、判断逻辑、复盘数据）
  -> 品牌事实库
  -> GEO 问题库
  -> 多平台 AI 检测
  -> 原始回答、截图、信息来源
  -> 推荐率/提及率/来源覆盖分析
  -> 内容任务
  -> 平台化草稿
  -> 发布检查与发布记录
  -> 复测与报告
  -> 复盘资料回流项目知识库
```

## 当前主要能力

- 项目管理：创建、编辑、删除项目，查看项目详情、内容任务、检测记录。
- 项目知识库：企业资料库已升级为项目知识资产库，支持基础信息、案例故事、判断逻辑、竞品/差评、内容素材、复盘数据等分层管理。
- 品牌事实库：支持一次性粘贴企业资料，由 AI 自动抽取候选事实，再人工确认。
- 资料缺口诊断：检查企业主体、资质、证书编号、地址、价格、案例、联系方式等缺口。
- 问题库：按曝光/推荐、验证/口碑、转化/承接、权威/对比等层级生成问题。
- 问题增强字段：问题关键词拆解、问题公式、商业价值、证据支撑、内容可执行性、推荐发布平台。
- 行业问题模板库：把不同行业的问题主体称呼、典型问法、禁用词、正向样例和反向样例抽成配置，避免问题矩阵只适配单一行业。
- 问题模板学习闭环：人工新增、改写、禁用或删除问题后，系统会记录调整意图，汇总成模板优化建议，经管理员确认后写入行业模板库。
- 提示词模板库：问题生成、推荐逻辑、内容规划、文章生成、反馈改写记忆等 prompt 已从代码中抽离。
- 平台规则库：内置自媒体平台标题、字数、引流、AIGC 标识、风险表达等规则，并支持在系统设置中编辑。
- 内容管理：从问题矩阵生成内容任务，按平台生成草稿，支持平台化改写、发布检查、发布记录。
- 知识资产引用：新建内容任务时可手动选择项目知识资产；留空时系统会按关联问题的知识需求自动推荐资料，并注入文章生成 Prompt。
- 发布记录：支持一篇文章记录到多个平台；若已有真实发布但存在风险提示，可选择继续保存并留存风险。
- 记忆库：沉淀用户反馈，由 AI 总结成可复用写作规则，再参与后续文章改写。
- 经验技能库：把项目反馈、文章修改、监测复盘和发布检查沉淀成待确认技能建议，人工确认后成为项目级/行业级/全局级经验技能。
- 技能版本管理：已启用技能支持编辑修订、记录原因、查看历史版本、回滚旧版本和调整项目级/行业级/全局级作用域。
- 监测分析：通过 WebBridge / QWebBridge 操控真实浏览器访问 AI 网页，自动提问、等待回答、抓取回答、截图和来源链接。
- 文本/视觉识别：默认使用文本抓取模式，也可在检测平台中开启视觉识别模式。
- AI 搜索详情：查看问题、平台、原始回答、是否提及/推荐、判断依据、截图、信息来源。
- 复盘回流：AI 搜索详情可一键沉淀为复盘资料，保存到项目知识库，供后续问题矩阵、内容任务和报告复用。
- 项目知识闭环视图：项目详情展示知识资产、已确认事实、问题覆盖、内容任务、检测样本、复盘资料等关键数量，帮助判断链路是否断档。
- 技能调用链：文章生成会自动读取已启用的项目级、行业级和全局级文章写作技能；技能只影响表达、结构和证据组织，不能突破已确认事实边界。
- 检测明细：按「问题 × 平台」展示，可删除明细，并可把未提及/未推荐的检测短板一键生成内容任务。
- 报告中心：支持选择多组检测记录生成聚合报告。
- AI 模型管理：配置 OpenAI 兼容模型、Mimo、小米 TokenPlan 等模型服务。
- 系统设置：管理用户、角色、账号状态和密码。
- 桌面应用：Electron + FastAPI + SQLite 本地运行，可打包为 Windows 安装包或便携包。

## 技术栈

| 模块 | 技术 |
|---|---|
| 前端 | React 18 + Ant Design |
| 后端 | FastAPI + SQLAlchemy Async |
| 本地数据库 | SQLite |
| 可选数据库 | PostgreSQL |
| 桌面应用 | Electron + electron-builder |
| 后端打包 | PyInstaller |
| 浏览器桥接 | Kimi WebBridge / QWebBridge |
| 测试 | pytest + React build |

## 目录结构

```text
geo-flow-agent-v2/
├─ backend/                 # FastAPI 后端
│  ├─ app/
│  │  ├─ api/               # API 路由
│  │  ├─ agents/            # 生产、策略、编排 Agent
│  │  ├─ data/              # 平台规则、行业问题模板等结构化数据
│  │  ├─ models/            # SQLAlchemy 模型
│  │  ├─ prompts/geo/       # GEO 提示词模板库
│  │  └─ services/          # 业务服务
│  ├─ tests/                # 后端测试
│  └─ geo-flow-backend.spec # PyInstaller 后端打包配置
├─ frontend/                # React 前端
│  └─ src/
├─ desktop/                 # Electron 主进程、预加载脚本、图标
├─ _external/QWebBridge/    # 集成并改造过的 QWebBridge 源码
├─ docs/                    # 打包和桥接说明
├─ skills/                  # 项目沉淀的 Codex skills
├─ scripts/                 # 构建脚本
├─ release/                 # 本地打包产物，默认不提交 Git
└─ package.json             # 桌面端构建入口
```

## 快速使用桌面版

如果只是使用应用，不需要安装开发环境。

当前本地打包产物位于：

```text
release/GEO Flow Agent Setup 2.3.0.exe
release/GEO-Flow-Agent-2.3.0-Portable.exe
```

说明：

- `Setup` 是安装版。
- `Portable` 是便携版。
- `release/` 已被 `.gitignore` 忽略，不会提交到 GitHub；需要发布安装包时请在本地重新打包或单独上传 Release 附件。

## 默认项目负责人账号

应用会在本地环境中自动准备一个项目负责人账号：

```text
用户名：pm01
密码：Pm@20260529
角色：项目负责人
邮箱：pm01@geoflow.app
```

旧版本曾使用 `.local` 邮箱，当前版本启动时会自动修复为 `.app` 域名，避免 Pydantic 邮箱校验失败。

## 本地开发

### 1. 安装 Node 依赖

```powershell
npm install
```

### 2. 安装前端依赖

```powershell
npm --prefix frontend install
```

### 3. 准备后端虚拟环境

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
cd ..
```

### 4. 启动后端

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 5. 启动前端

```powershell
npm --prefix frontend start
```

### 6. 启动桌面开发模式

```powershell
npm run desktop:dev
```

## 浏览器桥接

监测分析依赖浏览器桥接服务控制真实 AI 网页。

### Kimi WebBridge

用于控制用户真实浏览器，适合复用已登录的 AI 网页。

常用检查：

```powershell
$env:USERPROFILE\.kimi-webbridge\bin\kimi-webbridge.exe status
```

如果状态异常，可重新安装：

```powershell
irm https://cdn.kimi.com/webbridge/install.ps1 | iex
```

### QWebBridge

项目已集成并改造 QWebBridge，源码目录：

```text
_external/QWebBridge/
```

浏览器扩展目录：

```text
qwebbridge-extension-fixed/
```

常用检查：

```text
http://127.0.0.1:10087/health
```

如果网页检测提示 502，优先检查：

- 本地桥接服务是否启动。
- 浏览器扩展是否连接。
- 目标 AI 网页是否已登录。
- 检测平台的输入框、发送按钮、回答容器 selector 是否失效。
- 页面是否仍在加载、验证或弹出登录拦截。

## 监测平台配置建议

每个 AI 平台建议配置：

- 平台名称。
- 首页 URL。
- 输入框 selector。
- 发送按钮 selector。
- 回答容器 selector。
- 等待时间。
- 是否启用视觉识别模式。
- 是否抓取信息来源链接。

默认优先使用文本抓取模式。只有当目标网页结构频繁变化、文本抓取失效时，再切换到视觉识别模式。

## 行业问题模板和学习闭环

问题库生成不再只依赖固定代码逻辑。系统会优先读取：

```text
backend/app/data/question_archetypes.json
```

该配置用于控制不同行业的问题主体称呼、兜底服务词、可信验证问法、转化承接问法、行业禁用词、正向样例和反向样例。

使用方式：

1. 在项目详情中生成问题库。
2. 运营人员按实际业务修改、新增、禁用或删除问题。
3. 系统自动记录这些人工调整。
4. 进入 `系统设置 -> 问题模板优化建议` 查看待沉淀建议。
5. 管理员确认后，建议会写入行业模板库。
6. 后续同一行业的新项目或重新生成问题库时，会复用这些经验。

这个机制解决的是“越用越好用”的问题：不是让系统擅自学习，而是先生成建议，再由管理员确认，避免错误经验污染模板库。

## 视觉识别模式说明

视觉识别模式适用于：

- AI 网页 DOM 结构复杂或频繁变化。
- 发送按钮难以通过 selector 定位。
- 回答内容无法稳定从 DOM 中提取。
- 需要基于截图判断品牌是否被提及。

限制：

- 需要配置支持图片理解的多模态模型。
- 不适合只支持文本的模型，例如不具备图片理解能力的普通文本模型。
- 回答很长时，需要配合完整回答截图、品牌提及定位截图和等待稳定检测。

## 内容与平台规则

内容生成会同时参考三类信息：

```text
GEO 问题逻辑
品牌事实库
平台发文规则
```

平台规则库位于：

```text
backend/app/data/platform_policies.json
```

平台规则接口位于：

```text
backend/app/api/v1/endpoints/platform_policies.py
```

规则检查分为：

- `block`：严重风险，建议阻止发布。
- `warning`：可能影响推荐或合规，需要确认。
- `suggestion`：优化建议，不影响保存。

已经真实发布的文章即使有 `warning`，也可以选择继续保存发布记录，并保留风险提示。

## 提示词模板库

GEO 提示词模板已从业务代码中抽离，便于后续优化。

目录：

```text
backend/app/prompts/geo/
```

当前模板：

- `question_bank_v1.md`
- `recommendation_logic_v1.md`
- `content_plan_v1.md`
- `article_writer_v1.md`
- `rewrite_with_memory_v1.md`

模板加载器：

```text
backend/app/prompts/templates.py
```

## 测试与验证

后端测试：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q
```

前端构建验证：

```powershell
npm --prefix frontend run build
```

最近一次验证结果：

```text
后端测试：34 passed
前端构建：Compiled successfully
```

## 打包 Windows 桌面应用

完整打包：

```powershell
npm run dist:win
```

只打安装目录：

```powershell
npm run dist:folder
```

只打便携版：

```powershell
npm run dist:portable
```

打包会依次执行：

```text
frontend build
QWebBridge build
backend PyInstaller bundle
electron-builder
```

产物输出到：

```text
release/
```

## GitHub 仓库说明

当前远程仓库：

```text
https://github.com/yishutian37-commits/geo-flow-agent-v3-current
```

默认不提交：

- `node_modules/`
- `.venv/`
- `release/`
- `frontend/build/`
- `backend/build/`
- `backend/dist/`
- 数据库文件
- 缓存目录
- 备份目录
- 运行时截图和临时文件

`_external/QWebBridge` 以普通源码目录上传，因为本项目对其做了本地改造；不是 submodule。

## 常见问题

### 系统设置加载用户失败

如果提示邮箱校验错误，通常是旧数据库里存在 `.local` 邮箱。当前版本启动时会自动修复为 `.app` 域名。

### WebBridge 返回 502

优先检查：

- 本地桥接服务是否启动；
- 浏览器扩展是否连接；
- 目标 AI 网页是否登录；
- selector 是否失效；
- 页面是否仍在加载或验证。

### 自动检测过快，抓不到完整回答

需要在检测平台中调整等待时间，或使用回答稳定检测。当前项目已支持更完整的回答文本保存、品牌提及位置截图和来源链接抓取。

### 视觉识别模型返回不可解析 JSON

常见原因：

- 当前模型没有图片理解能力。
- 模型虽然兼容 OpenAI 接口，但视觉输入格式不兼容。
- base URL 需要自动补齐 `/v1`。
- 模型输出不是 JSON，需要在提示词中强约束输出格式。

### 杀毒软件误报

Windows 桌面包使用 PyInstaller 和 Electron 打包，未签名时可能被部分杀毒软件误报。建议正式分发前增加代码签名。

## 相关文档

- `GEO-Flow-Agent-V2.3-详细使用说明.md`
- `GEO-Flow-Agent-V2.3-Agent介绍.md`
- `docs/DESKTOP_PACKAGING.md`
- `docs/QWEBBRIDGE_INTEGRATION.md`
- `skills/README.md`

## 最近重要更新

- 新增平台规则库和平台规则编辑能力。
- 新增 GEO 提示词模板库。
- 文章生成支持按平台规则生成草稿，并增强超时处理。
- 发布记录支持一文多平台，风险提示不再硬阻止真实发布记录。
- 问题库新增关键词拆解、问题公式、商业价值、证据支撑、推荐平台等字段。
- 监测明细新增补发建议，并可一键生成内容任务。
- 监测明细和检测记录删除接口已补充角色权限校验。
- AI 搜索详情支持原始回答、截图、信息来源和来源资产分析。
- 项目管理和项目详情中的检测记录支持更清晰的批量/单次、平台和样本信息展示。

## 许可与商业授权

本项目采用双授权模式：

- 社区授权：GNU Affero General Public License v3.0（AGPLv3），详见 `LICENSE`。
- 商业授权：如需闭源商用、企业生产环境闭源部署、客户交付、SaaS 化、白标、二次销售或集成进商业产品，请先获得书面商业授权，详见 `COMMERCIAL_LICENSE.md`。

简单理解：

- 个人学习、研究、非商业自用，可以在遵守 AGPLv3 的前提下免费使用。
- 如果修改本项目并通过网络向他人提供服务，需要按照 AGPLv3 向用户提供相应源代码。
- 如果不希望履行 AGPLv3 的开源义务，或计划将本项目用于闭源商业交付，需要购买或取得商业授权。

第三方依赖声明见 `THIRD_PARTY_NOTICES.md`。
