# 第三方开源组件声明

GEO Flow Agent 使用了多个第三方开源组件。各第三方组件仍适用其原始许可证；本项目的 AGPLv3 或商业授权不改变第三方组件自身的授权条款。

本文件列出当前项目的主要直接依赖、关键运行依赖和打包依赖。实际完整依赖以 `package.json`、`frontend/package.json`、`backend/requirements.txt`、`package-lock.json`、`frontend/package-lock.json`、`_external/QWebBridge/pnpm-lock.yaml` 以及各依赖包自身的许可证文件为准。

## 1. 项目自身授权

| 组件 | 版本 | 许可证 | 用途 |
|---|---:|---|---|
| GEO Flow Agent | 2.3.0 | AGPL-3.0-or-later / 商业授权双协议 | 本项目主程序、后端、前端、桌面壳、业务逻辑、提示词模板和文档 |

## 2. 桌面端与构建依赖

来源：`package.json`

| 组件 | 当前声明版本 | 上游许可证 | 用途 |
|---|---:|---|---|
| Electron | ^28.3.3 | MIT | Windows 桌面应用运行壳 |
| electron-builder | ^24.13.3 | MIT | 桌面安装包、便携包构建 |

## 3. 前端直接依赖

来源：`frontend/package.json`

| 组件 | 当前声明版本 | 上游许可证 | 用途 |
|---|---:|---|---|
| React | ^18.3.1 | MIT | 前端 UI 框架 |
| React DOM | ^18.3.1 | MIT | React 浏览器渲染 |
| React Router DOM | ^6.23.1 | MIT | 前端路由 |
| Ant Design | ^5.17.0 | MIT | 前端组件库 |
| @ant-design/icons | ^5.3.7 | MIT | Ant Design 图标 |
| Axios | ^1.6.8 | MIT | HTTP 请求客户端 |
| react-scripts | 5.0.1 | MIT | Create React App 构建脚本 |

## 4. 后端直接依赖

来源：`backend/requirements.txt`

| 组件 | 当前锁定版本 | 上游许可证 | 用途 |
|---|---:|---|---|
| FastAPI | 0.111.0 | MIT | 后端 Web API 框架 |
| Uvicorn | 0.30.0 | BSD-3-Clause | ASGI 服务运行 |
| SQLAlchemy | 2.0.30 | MIT | ORM 与数据库访问 |
| aiosqlite | 0.20.0 | MIT | SQLite 异步访问 |
| asyncpg | 0.29.0 | Apache-2.0 | PostgreSQL 异步访问 |
| psycopg2-binary | 2.9.9 | LGPL with exceptions | PostgreSQL 驱动 |
| Alembic | 1.13.1 | MIT | 数据库迁移 |
| Pydantic | 2.7.1 | MIT | 数据校验和模型定义 |
| pydantic-settings | 2.2.1 | MIT | 配置管理 |
| Celery | 5.4.0 | BSD-3-Clause | 后台任务队列 |
| redis | 5.0.4 | MIT | Redis 客户端 |
| python-jose | 3.3.0 | MIT | JWT / JOSE 认证相关 |
| passlib | 1.7.4 | BSD | 密码哈希 |
| bcrypt | 由 `passlib[bcrypt]` 引入 | Apache-2.0 | bcrypt 哈希实现 |
| python-multipart | 0.0.9 | Apache-2.0 | 表单与文件上传解析 |
| HTTPX | 0.27.0 | BSD-3-Clause | HTTP 客户端与测试客户端 |
| aiohttp | 3.9.5 | Apache-2.0 | 异步 HTTP 客户端 |
| OpenAI Python SDK | 1.30.0 | Apache-2.0 | OpenAI 兼容模型接口调用 |
| python-dotenv | 1.0.1 | BSD-3-Clause | 环境变量加载 |
| orjson | 3.10.3 | Apache-2.0 / MIT | 高性能 JSON 序列化 |
| structlog | 24.1.0 | MIT | 结构化日志 |
| SciPy | 1.13.1 | BSD-3-Clause | 统计计算 |
| NumPy | 1.26.4 | BSD-3-Clause | 数值计算 |
| openpyxl | 3.1.2 | MIT | Excel 文件读写 |
| XlsxWriter | 3.2.0 | BSD-2-Clause | Excel 报表写入 |
| python-dateutil | 2.9.0 | Apache-2.0 / BSD | 日期时间处理 |
| pytz | 2024.1 | MIT | 时区处理 |
| pytest | 8.2.1 | MIT | 后端测试 |
| pytest-asyncio | 0.23.7 | Apache-2.0 | 异步测试支持 |
| PyInstaller | 6.8.0 | GPL-2.0-or-later with bootloader exception | 后端可执行文件打包 |

## 5. QWebBridge 集成组件

来源：`_external/QWebBridge/`

本项目包含并改造了 QWebBridge 相关源码，用于本地浏览器自动化桥接。该目录中的本项目改造部分按本项目授权执行；其上游代码、第三方依赖和浏览器平台能力仍受各自许可证或服务条款约束。

### 5.1 QWebBridge 工作区包

| 组件 | 当前声明版本 | 许可证 | 用途 |
|---|---:|---|---|
| qweb-bridge | private | 项目内集成组件 | QWebBridge 工作区根包 |
| @qweb/daemon | 1.0.0 | 项目内集成组件 | 本地桥接守护进程 |
| @qweb/extension | 1.0.0 | 项目内集成组件 | 浏览器扩展 |
| @qweb/protocol | 1.0.0 | 项目内集成组件 | 桥接协议定义 |

### 5.2 QWebBridge 关键运行与构建依赖

| 组件 | 当前声明版本 | 上游许可证 | 用途 |
|---|---:|---|---|
| ws | ^8.18.0 | MIT | WebSocket 通信 |
| TypeScript | ^5.5.0 | Apache-2.0 | TypeScript 编译 |
| Vite | ^5.4.0 | MIT | 浏览器扩展构建 |
| tsup | ^8.2.0 | MIT | daemon 构建 |
| Vitest | ^1.6.0 | MIT | QWebBridge 测试 |
| ESLint | ^10.4.0 | MIT | 代码检查 |
| Prettier | ^3.8.3 | MIT | 代码格式化 |
| @types/chrome | ^0.0.268 | MIT | Chrome 扩展类型定义 |
| @types/ws | ^8.5.12 | MIT | ws 类型定义 |

## 6. 外部服务与平台

以下外部服务或平台不是本项目的一部分，但应用功能可能会调用或依赖它们。使用方应自行遵守对应平台的服务条款、账号规则和 API 计费规则。

| 服务 / 平台 | 用途 | 说明 |
|---|---|---|
| OpenAI 兼容模型服务 | 文章生成、事实抽取、视觉识别、规则总结 | 包括用户自行配置的模型服务 |
| Mimo / 小米 TokenPlan 等模型服务 | 模型调用 | 按服务商自身条款和计费规则执行 |
| Kimi WebBridge | 控制用户真实浏览器 | 按 Kimi WebBridge 自身安装与使用条款执行 |
| GitHub | 代码托管 | 按 GitHub 服务条款执行 |
| 目标 AI 网页平台 | GEO 监测与网页自动提问 | 如 Kimi、豆包、文心一言、DeepSeek 等，需遵守各平台规则 |

## 7. 传递依赖说明

本文件优先列出直接依赖和关键打包依赖。前端、后端和 QWebBridge 的构建链会引入大量传递依赖，例如 Babel、Webpack、Rollup、ESBuild、PostCSS、testing-library、anyio、starlette、cryptography 等。

正式商业分发、客户交付或上架前，建议额外执行一次完整依赖许可证审计，并生成机器可读的完整清单，例如：

```powershell
npm ls --all
npm --prefix frontend ls --all
pip-licenses --from=mixed --format=markdown
pnpm --dir _external/QWebBridge licenses list
```

如果审计结果与本文件存在差异，应以上游依赖包实际发布的许可证文件和锁定版本为准。

## 8. 使用方义务

使用、分发、商业部署或二次开发本项目时，使用方应自行核查：

- 第三方组件的许可证类型和兼容性。
- 是否需要保留版权声明、许可证文本或 NOTICE 文件。
- 是否涉及商标、平台账号、模型接口、浏览器插件或第三方服务的单独条款。
- 是否需要向客户提供完整许可证清单、源码链接或开源合规报告。

如果你计划进行商业分发、私有化交付或 SaaS 化部署，建议在交付前进行一次完整的开源合规审查。
