# Release Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐 GEO Flow Agent 对外展示和发版前最关键的工程化短板。

**Architecture:** 优先补齐 P0 层：账号初始化安全、CI、Release 指引、架构说明。随后补齐 P1 中风险最低、收益最高的 Orchestrator 轻量预检编排；平台化重写和强事实校验继续单独推进，避免一次性大改影响当前可用主流程。

**Tech Stack:** FastAPI、SQLAlchemy Async、pytest、React、GitHub Actions、Electron/electron-builder、PyInstaller。

---

### Task 1: 默认账号安全

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_auth_bootstrap_security.py`
- Modify: `README.md`
- Modify: `GEO-Flow-Agent-V2.3-详细使用说明.md`

- [x] **Step 1: 写默认种子关闭测试**

```python
@pytest.mark.asyncio
async def test_default_project_owner_seed_is_opt_in(monkeypatch):
    class FailingSessionFactory:
        def __call__(self):
            raise AssertionError("database should not be opened when default seed is disabled")

    monkeypatch.setattr(main, "SEED_DEFAULT_PROJECT_OWNER", False)
    monkeypatch.setattr(main, "AsyncSessionLocal", FailingSessionFactory())

    await main.ensure_default_project_owner()
```

- [x] **Step 2: 修改启动逻辑**

`ensure_default_project_owner()` 只有在 `GEO_SEED_DEFAULT_PROJECT_OWNER=1` 且设置密码时才创建项目负责人。

- [x] **Step 3: 文档改为首次启动初始化**

删除公开固定密码，改为用户首次启动自行设置管理员账号。

- [x] **Step 4: 验证**

Run: `python -m pytest backend/tests/test_auth_bootstrap_security.py -q`

Expected: PASS。

### Task 2: CI 与 Release 工程化

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/release.yml`
- Create: `docs/RELEASE.md`
- Modify: `README.md`

- [x] **Step 1: 新增 CI**

CI 运行后端 pytest 和前端 build。

- [x] **Step 2: 新增 Release workflow**

支持手动触发和 `v*` tag 自动构建 Windows 桌面包。

- [x] **Step 3: 新增 Release 文档**

说明本地打包、Actions 手动触发、tag 发版、注意事项。

- [x] **Step 4: 验证 YAML 文件存在**

Run: `Get-ChildItem .github/workflows`

Expected: `ci.yml` 和 `release.yml` 存在。

### Task 3: 架构说明

**Files:**
- Create: `architecture.md`
- Modify: `README.md`

- [x] **Step 1: 新增架构文档**

覆盖系统定位、核心闭环、数据对象、Agent 分工、事实约束、监测链路和已知边界。

- [x] **Step 2: README 链接架构文档**

README 中加入 `architecture.md` 和 `docs/RELEASE.md` 入口。

- [x] **Step 3: 验证文档入口**

Run: `Select-String -Path README.md -Pattern "architecture.md|docs/RELEASE.md"`

Expected: 两个入口都存在。

### Task 4: Orchestrator 轻量预检编排

**Files:**
- Modify: `backend/app/agents/orchestrator.py`
- Test: `backend/tests/test_orchestrator_workflows.py`
- Modify: `architecture.md`

- [x] **Step 1: 诊断工作流补齐真实前置检查**

检查项目是否已有企业资料/确认事实、启用问题和检测平台；缺失时返回 `blocked`、阻断原因和下一步。

- [x] **Step 2: 内容生产工作流补齐事实/草稿状态分支**

没有已确认公开事实时阻断；有事实无草稿时返回可生成；已有草稿时返回待审核。

- [x] **Step 3: 监测工作流补齐问题/平台前置检查**

缺问题或缺检测平台时阻断；条件齐全时返回可开始采样。

- [x] **Step 4: 验证**

Run: `python -m pytest backend/tests/test_orchestrator_workflows.py backend/tests/test_auth_bootstrap_security.py -q`

Expected: PASS。

### Task 5: 代码审查

**Files:**
- Review: changed files

- [ ] **Step 1: 执行 project-release-qa-tiered 审查**

按阶段检查：现状保护、技术栈识别、修改范围、测试、构建、剩余风险。

- [ ] **Step 2: 输出风险清单**

只报告有证据的问题，不把未验证项说成完成。
