# GEO Flow Agent V2.3

通用 GEO 流程 Agent —— AI 品牌可见性、内容资产建设与复测闭环系统。

## 项目架构

```
geo-flow-agent-v2/
├── backend/          # FastAPI + PostgreSQL + Celery
├── frontend/         # React + Ant Design
├── docker-compose.yml
└── docs/
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI (Python 3.11) |
| 数据库 | PostgreSQL 16 + pgvector |
| 任务队列 | Celery + Redis |
| 前端 | React 18 + Ant Design 5 |
| 部署 | Docker Compose |

## 快速启动

### 1. 克隆并进入项目

```bash
cd geo-flow-agent-v2
```

### 2. 配置环境变量

```bash
cp backend/.env.example backend/.env
# 编辑 backend/.env，填写数据库和AI API配置
```

### 3. Docker 一键启动

```bash
docker-compose up -d
```

服务将启动在：
- 后端 API: http://localhost:8000
- 前端: http://localhost:3000
- API 文档: http://localhost:8000/docs

### 4. 数据库迁移（首次运行）

```bash
docker-compose exec backend alembic revision --autogenerate -m "init"
docker-compose exec backend alembic upgrade head
```

## 核心功能模块

### 五大核心 Agent

1. **项目与诊断 Agent**: 项目创建、资料缺口诊断、品牌事实库(brand_facts)构建
2. **诊断与意图 Agent**: 品牌AI体检、三层问题库、竞争差距分析、基线建立
3. **内容策略 Agent**: 内容矩阵生成、渠道组合、发布排期、预算估算
4. **内容生产 Agent**: 稿件生成、事实引用清单、合规检查、多平台适配
5. **监测与分析 Agent**: 复测任务、指标计算(Wilson置信区间)、舆情分类、优化建议

### 数据模型

严格按 PRD V2.3 第8章实现，核心表包括：
- `projects`, `brands`, `brand_facts` (Single Source of Truth)
- `corpus_items`, `source_assets`, `channel_accounts`
- `question_groups`, `questions`, `model_targets`, `baseline_runs`
- `content_tasks`, `content_drafts`, `compliance_checks`, `approvals`
- `publish_records`, `monitoring_runs`, `monitoring_samples`
- `sentiment_records`, `recommendations`

### 关键指标

- **Brand Mention Rate**: 品牌提及率 + Wilson 95% CI
- **Recommendation Rate**: 推荐率 + Wilson 95% CI
- **Position Score**: 平均推荐位置（列表型/散文化/无可识别候选）
- **Visibility Score**: 归一化可见性分数 (L-r+1)/L
- **Explicit Citation Rate** vs **Inferred Source Match Rate**: 严格拆分
- **Confidence Level**: 基于样本量、Wilson半宽、时间窗口的硬阈值

## 开发状态

| 阶段 | 状态 |
|------|------|
| Phase 1: 基础设施与数据模型 | ✅ 完成 |
| Phase 2: 项目与诊断 Agent | 🚧 进行中 |
| Phase 3: 诊断与意图 Agent + 问题库 | ⏳ 待开发 |
| Phase 4: 内容策略 Agent | ⏳ 待开发 |
| Phase 5: 内容生产 Agent | ⏳ 待开发 |
| Phase 6: 渠道账号与发布管理 | ⏳ 待开发 |
| Phase 7: 监测与分析 Agent | 🚧 Service层完成 |
| Phase 8: 报告系统 | ⏳ 待开发 |
| Phase 9: 整合与收尾 | ⏳ 待开发 |

## API 文档

启动服务后访问: http://localhost:8000/docs

## 与现有系统集成

- **geoflow-local**: 通过 REST API 推送内容任务，接收发布URL
- **geo_assistant**: 通过 Excel 导入导出交换诊断结论和复测数据

## 许可

内部项目
