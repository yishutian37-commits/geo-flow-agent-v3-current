# GEO Flow Agent 桌面版打包说明

## 目标形态

桌面版由 Electron、React 静态资源、FastAPI 后端可执行文件和本地 SQLite 数据库组成。

```text
GEO Flow Agent.exe
|-- Electron 主进程
|-- frontend/build 静态前端
|-- backend/geo-flow-backend.exe
`-- 用户数据目录/geoflow.db
```

运行时数据不写入安装目录或便携包解压目录，而是写入 Electron 的 `userData` 目录：

```text
%APPDATA%/geo-flow-agent-desktop/
|-- geoflow.db
|-- logs/desktop.log
|-- logs/backend-boot.log
|-- logs/backend-runtime.log
`-- models/llm_registry.json
```

## 开发运行

1. 安装桌面壳依赖：

```bash
npm install
```

2. 安装后端依赖：

```bash
cd backend
pip install -r requirements.txt
```

3. 构建前端：

```bash
npm run frontend:build
```

4. 启动 Electron 桌面模式：

```bash
npm run desktop:dev
```

开发模式会优先使用 `backend/.venv` 里的 Python。若需要手动指定解释器：

```bash
set GEO_BACKEND_PYTHON=C:\path\to\python.exe
npm run desktop:dev
```

## 打包 Windows 应用

推荐生成文件夹版，误报概率低于单文件便携版：

```bash
npm run dist:folder
```

生成后从下面入口启动，整个 `win-unpacked` 文件夹需要一起保留：

```text
release/win-unpacked/GEO Flow Agent.exe
```

生成便携版：

```bash
npm run dist:portable
```

生成安装包和便携版：

```bash
npm run dist:win
```

打包流程会依次执行：

1. `npm --prefix frontend run build`
2. `cd backend && .venv\Scripts\pyinstaller.exe --clean --noconfirm geo-flow-backend.spec`
3. `electron-builder --win`

当前配置面向本地交付，Windows 包不做代码签名和 exe 资源改写，避免依赖系统签名缓存目录。
便携版是单文件自解压形态，部分杀毒软件更容易误报；正式交付优先使用文件夹版或代码签名后的安装包。

## 关键实现

- `desktop/main.js`：Electron 主进程，负责启动后端、等待健康检查、加载前端。
- `desktop/preload.js`：向前端注入 `window.geoDesktop.apiBaseUrl`。
- `backend/desktop_server.py`：桌面模式后端入口，自动配置 SQLite 数据库、模型配置路径和启动日志。
- `backend/geo-flow-backend.spec`：PyInstaller 打包配置。

## 注意事项

- 桌面版 MVP 使用 SQLite，不依赖 PostgreSQL、Redis、Docker 或 Celery。
- 当前异步任务应优先走 FastAPI 同步/短任务接口；后续需要定时任务时再增加内置 scheduler。
- 用户 API Key 保存到 `models/llm_registry.json`，正式交付前建议增加本机加密。
