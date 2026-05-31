# GEO Flow Agent V2.3

GEO Flow Agent V2.3 是一个面向本地交付的 GEO / AIO 工作台，用于管理品牌事实库、生成问题库、执行 AI 搜索监测、沉淀信息来源、生成内容任务、记录发布结果，并通过复测形成优化闭环。

当前仓库包含完整的前端、后端、桌面壳和 QWebBridge 集成源码，可开发运行，也可打包成 Windows 桌面应用。

## 当前定位

这个项目不是单纯的 AI 写作工具，而是一个围绕“可信证据链”的 GEO 决策系统。

核心链路：

```text
项目/品牌资料
  -> 品牌事实库
  -> 问题库
  -> 多平台 AI 检测
  -> 原始回答与截图证据
  -> 信息来源分析
  -> 内容任务与文章生成
  -> 发布记录
  -> 复测与报告
```

## 主要功能

- 项目管理：创建、编辑、删除项目，查看项目详情与检测记录。
- 品牌事实库：统一上传企业资料，由 AI 抽取候选事实，再人工确认。
- 问题库：围绕曝光、验证、转化等层级生成和管理检测问题。
- 监测分析：通过 WebBridge / QWebBridge 打开 AI 网页，自动提问、等待回答、抓取原始回答、截图和信息来源。
- 监测明细：按“问题 × 平台”查看每条检测结果，支持查看 AI 搜索详情和删除明细。
- 内容管理：根据事实库和问题库生成内容任务、草稿、发布检查和发布记录。
- 记忆库：沉淀用户反馈，由 AI 总结成可复用写作规则。
- 报告中心：支持选择多组检测记录生成聚合报告。
- AI 模型管理：配置 OpenAI 兼容模型、Mimo、小米 TokenPlan 等模型服务。
- 系统设置：管理用户、角色、账号状态和密码。

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
├── backend/                 # FastAPI 后端
│   ├── app/                 # API、模型、服务、Agent、LLM 客户端
│   ├── tests/               # 后端测试
│   └── geo-flow-backend.spec
├── frontend/                # React 前端
│   └── src/
├── desktop/                 # Electron 主进程、预加载脚本、图标
├── _external/QWebBridge/    # 本项目集成并改造过的 QWebBridge 源码
├── docs/                    # 打包和 QWebBridge 集成说明
├── skills/                  # 本项目沉淀的 Codex skill 流程文档
├── scripts/                 # 构建脚本
├── release/                 # 打包产物，已被 .gitignore 忽略
└── package.json             # 桌面端构建入口
```

## 快速使用桌面版

如果只是使用应用，不需要安装开发环境。

打包后的文件位于本地：

```text
release/GEO Flow Agent Setup 2.3.0.exe
release/GEO-Flow-Agent-2.3.0-Portable.exe
```

说明：

- `Setup` 是安装版。
- `Portable` 是便携版。
- `release/` 不会上传到 GitHub，需要本地重新打包生成。

## 默认账号

项目会在本地开发/桌面环境中自动创建项目负责人账号：

```text
用户名：pm01
密码：Pm@20260529
角色：项目负责人
```

默认邮箱已修正为：

```text
pm01@geoflow.app
```

说明：旧版本曾使用 `.local` 邮箱，Pydantic 会把 `.local` 判定为保留域名并导致系统设置加载用户失败。当前版本启动时会自动修复历史 `.local` 用户邮箱。

## 本地开发

### 1. 安装 Node 依赖

```powershell
npm install
npm --prefix frontend install
```

QWebBridge 依赖位于 `_external/QWebBridge`，如需单独开发桥接能力，再进入该目录安装依赖。

### 2. 安装 Python 依赖

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

### 3. 配置后端环境变量

复制配置模板：

```powershell
copy backend\.env.example backend\.env
```

常用配置包括：

- 数据库地址。
- LLM API Base URL。
- LLM API Key。
- 默认项目负责人账号。
- WebBridge / 截图存储目录。

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

## 浏览器桥接说明

监测分析依赖浏览器桥接来控制真实浏览器页面。

当前项目支持两类桥接：

1. Kimi WebBridge  
   默认端口：`10086`

2. QWebBridge  
   默认端口：`10087`

### Kimi WebBridge

安装和使用参考：

```text
https://www.kimi.com/zh-cn/features/webbridge
```

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

本项目内置了改造过的 QWebBridge 源码，主要用于网页自动提问、发送、等待、截图和信息来源抓取。

启动脚本：

```powershell
.\启动QWebBridge-10087.cmd
```

健康检查：

```text
http://127.0.0.1:10087/health
```

浏览器插件目录：

```text
_external/QWebBridge/packages/extension/dist
```

如果浏览器提示插件未就绪，需要确认：

- QWebBridge 服务已启动；
- 浏览器扩展已加载；
- 目标 AI 网页已登录；
- 检测平台配置了正确的输入框、发送按钮和回答容器 selector。

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

当前最近一次验证结果：

```text
后端测试：31 passed
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

当前项目已上传到 GitHub 私密仓库：

```text
https://github.com/yishutian37-commits/geo-flow-agent-v2
```

上传时已排除：

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

### 杀毒软件误报

Windows 桌面包使用 PyInstaller 和 Electron 打包，未签名时可能被部分杀毒软件误报。建议后续正式分发前增加代码签名。

## 相关文档

- `GEO-Flow-Agent-V2.3-详细使用说明.md`
- `GEO-Flow-Agent-V2.3-Agent介绍.md`
- `docs/DESKTOP_PACKAGING.md`
- `docs/QWEBBRIDGE_INTEGRATION.md`
- `skills/README.md`

## 许可

内部私有项目。未经授权不得公开分发。

