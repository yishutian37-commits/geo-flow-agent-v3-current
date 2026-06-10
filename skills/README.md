# GEO Flow Agent Skills

这个目录用于沉淀本项目中高频、容易漏步骤、会影响交付质量的工作流。

## 通用版 Skills

通用版放在 `skills/common` 下，尽量不绑定具体项目路径、目录名、测试命令或业务名称，适合复制到其他项目中继续使用。

1. `common/project-release-qa`
   通用项目审查、逻辑链路检查、缺陷修复、测试、构建、打包、发版前检查。

2. `common/project-prd-gap-implementation`
   通用 PRD 对照、功能缺口识别、优先级排序、分批实现。

3. `common/browser-bridge-troubleshooter`
   通用浏览器桥接、浏览器插件、网页自动化、selector、发送和抓取故障诊断。

4. `common/project-github-sync`
   通用 GitHub 仓库同步、分支推送、PR 创建、冲突处理、WebBridge 兜底操作。

## GEO 专用 Skills

这些 skill 保留当前 GEO Flow Agent 的业务语境，适合本项目或同类 GEO / AIO / AI 搜索监测产品。

1. `geo-agent-release-qa`
   GEO Flow Agent 项目审查、测试、构建、桌面应用打包、GitHub 更新前后检查。

2. `geo-monitoring-evidence-chain`
   GEO 监测证据链、AI 搜索详情、检测明细、来源链接、截图、报告链路。

3. `webbridge-troubleshooter`
   本项目 Kimi WebBridge / QWebBridge 故障诊断。

4. `geo-content-fact-writing`
   事实库驱动的文章生成、反馈记忆、标题正文拆分、结构化验收。

5. `prd-gap-implementation`
   按本项目 PRD 对照未实现功能并分批补齐。

## 使用建议

- 做当前项目：优先使用 GEO 专用 skill。
- 做其他项目：优先复制 `skills/common` 下的通用 skill。
- 要让 Codex 自动长期识别调用，可把对应目录复制或安装到 Codex 的 skills 目录。
- 更新 skill 时要保持简洁，只沉淀可复用流程，不把一次性日志或聊天记录塞进去。

## 根据高频工作推荐的 3 个优先 Skill

1. `geo-agent-release-qa`
   适合“全面审查项目”“修复逻辑断链”“按 PRD 补齐”“重新打包”“最终质检”。它已经加入 GEO 主链路判断：事实库、问题库、检测证据、内容任务、发布记录和复测报告必须能连起来。

2. `common/project-github-sync`
   适合“同步 GitHub”“更新 README 后上传”“创建 PR”“WebBridge 打开 GitHub 兜底”。它明确规定 Git/GitHub API 是主通道，WebBridge 只做应急网页操作，避免把浏览器上传当成长期版本控制方案。

3. `geo-monitoring-evidence-chain`
   适合“AI 搜索详情”“信息来源抓取”“截图不完整”“品牌提及识别不到”“视觉识别模式失败”“检测明细删除”。它把检测结果从简单结论升级为可追溯证据链。

目前这 3 个方向已有对应 skill，不需要额外创建重复 skill。后续如果出现新的高频任务，例如“行业问题模板自动沉淀”或“平台发文规则适配”，再单独创建新 skill。
