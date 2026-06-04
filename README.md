# GEO Flow Agent V2.3

GEO Flow Agent V2.3 是一个本地运行的 GEO / AIO 工作台，用来把「品牌资料、品牌事实、问题库、AI 搜索监测、内容生产、发布记录、复测报告」串成一条可执行的优化链路。

它不是单纯的 AI 写作工具，而是围绕生成式搜索场景设计的项目操作系统：先沉淀可验证事实，再生成真实用户会问的问题，随后监测各 AI 产品的回答表现，并把未提及、未推荐、来源不足等问题回流为内容任务。

## 核心链路

```text
项目/品牌资料
  -> 品牌事实库
  -> GEO 问题库
  -> 多平台 AI 检测
  -> 原始回答、截图、信息来源
  -> 推荐率/提及率/来源覆盖分析
  -> 内容任务
  -> 平台化草稿
  -> 发布检查与发布记录
  -> 复测与报告
```

## 当前主要能力

- 项目管理：创建、编辑、删除项目，查看项目详情、内容任务、检测记录。
- 品牌事实库：支持一次性粘贴企业资料，由 AI 自动抽取候选事实，再人工确认。
- 资料缺口诊断：检查企业主体、资质、证书编号、地址、价格、案例、联系方式等缺口。
- 问题库：按曝光/推荐、验证/口碑、转化/承接、权威/对比等层级生成问题。
- 问题增强字段：问题关键词拆解、问题公式、商业价值、证据支撑、内容可执行性、推荐发布平台。
- 提示词模板库：问题生成、推荐逻辑、内容规划、文章生成、反馈改写记忆等 prompt 已从代码中抽离。
- 平台规则库：内置自媒体平台标题、字数、引流、AIGC 标识、风险表达等规则，并支持在系统设置中编辑。
- 内容管理：从问题矩阵生成内容任务，按平台生成草稿，支持平台化改写、发布检查、发布记录。
- 发布记录：支持一篇文章记录到多个平台；若已有真实发布但存在风险提示，可选择继续保存并留存风险。
- 记忆库：用户反馈会先由 AI 分析为可复用写作规则，再参与后续文章改写。
- 监测分析：通过 WebBridge/QWebBridge 操控真实浏览器访问 AI 网页，自动提问、等待回答、抓取回答、截图和来源链接。
- 文本/视觉识别：默认使用文本抓取模式，也可在检测平台中开启视觉识别模式。
- AI 搜索详情：查看问题、平台、原始回答、是否提及/推荐、判断依据、截图、信息来源。
- 检测明细：按「问题 × 平台」展示，可删除明细，并可把未提及/未推荐的检测短板一键生成内容任务。
- 报告中心：支持选择多组检测记录生成聚合报告。
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
│  │  ├─ data/              # 平台规则等结构化数据
│  │  ├─ models/            # SQLAlchemy 模型
│  │  ├─ prompts/geo/       # GEO 提示词模板库
│  │  └─ services/          # 业务服务
│  └─ tests/                # 后端测试
├─ frontend/                # React 前端
├─ desktop/                 # Electron 主进程、预加载脚本、图标
├─ _external/QWebBridge/    # 集成并改造过的 QWebBridge 源码
├─ docs/                    # 打包和桥接说明
├─ skills/                  # 项目沉淀的 Codex skills
├─ scripts/                 # 构建脚本
├─ release/                 # 本地打包产物，默认不提交 Git
└─ package.json             # 桌面端构建入口
```

## 桌面应用产物

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
npm --prefix frontend install
```

### 2. 安装 Python 依赖

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

### 3. 配置环境变量

```powershell
copy backend\.env.example backend\.env
```

常用配置包括：

- 数据库地址
- LLM API Base URL
- LLM API Key
- WebBridge / 截图存储目录
- 默认用户和权限配置

### 4. 启动开发环境

前端：

```powershell
npm --prefix frontend start
```

后端：

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

桌面壳：

```powershell
npm run desktop:dev
```

## 浏览器桥接

监测分析依赖浏览器桥接服务控制真实 AI 网页。

### Kimi WebBridge

默认端口：`10086`

健康检查：

```powershell
$exe=Join-Path $env:USERPROFILE '.kimi-webbridge\bin\kimi-webbridge.exe'
& $exe status
```

正常状态应包含：

```json
{
  "running": true,
  "extension_connected": true
}
```

### QWebBridge

默认端口：`10087`

启动脚本：

```powershell
.\启动QWebBridge-10087.cmd
```

健康检查：

```text
http://127.0.0.1:10087/health
```

浏览器扩展目录：

```text
_external/QWebBridge/packages/extension/dist
```

加载 Chrome/Edge 扩展时必须选择 `dist` 目录。

## 测试

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

## GitHub 仓库

当前远程仓库：

```text
https://github.com/yishutian37-commits/geo-flow-agent-v2
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
- 临时截图

## 最近重要更新

- 新增平台规则库和平台规则编辑能力。
- 新增 GEO 提示词模板库。
- 文章生成支持按平台规则生成草稿，并增强超时处理。
- 发布记录支持一文多平台，风险提示不再硬阻止真实发布记录。
- 问题库新增关键词拆解、问题公式、商业价值、证据支撑、推荐平台等字段。
- 监测明细新增补发建议，并可一键生成内容任务。
- 监测明细和检测记录删除接口已补充角色权限校验。
- AI 搜索详情支持原始回答、截图、信息来源和来源资产分析。
