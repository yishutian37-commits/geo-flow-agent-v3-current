# 第三方开源组件声明

GEO Flow Agent 使用了多个第三方开源组件。各第三方组件仍适用其原始许可证；本项目的 AGPLv3 或商业授权不改变第三方组件自身的授权条款。

本文件是高层级声明，实际依赖以 `package.json`、`frontend/package.json`、`backend/requirements.txt`、`_external/QWebBridge/` 及各依赖锁定文件为准。

## 主要前端与桌面依赖

- React
- React DOM
- React Router
- Ant Design
- Lucide React
- Axios
- Electron
- electron-builder

## 主要后端依赖

- FastAPI
- Starlette
- Uvicorn
- SQLAlchemy
- Pydantic
- Passlib
- Python JWT / JOSE 相关组件
- PyInstaller

## 浏览器桥接相关

- Kimi WebBridge：外部浏览器桥接工具，按其自身安装和使用条款执行。
- QWebBridge：项目中包含并改造的桥接组件源码位于 `_external/QWebBridge/`，请同时遵守其上游许可证及本项目对改造部分的授权说明。

## 使用方义务

使用、分发、商业部署或二次开发本项目时，使用方应自行核查：

- 第三方组件的许可证类型和兼容性。
- 是否需要保留版权声明、许可证文本或 NOTICE 文件。
- 是否涉及商标、平台账号、模型接口、浏览器插件或第三方服务的单独条款。

如果你计划进行商业分发、私有化交付或 SaaS 化部署，建议在交付前进行一次完整的开源合规审查。
