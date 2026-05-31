# GEO Flow Agent Skills

这个目录用于沉淀本项目中高频、易漏步骤、对产品质量影响较大的工作流程。

## 通用版 Skills

通用版放在 `skills/common` 下，尽量不绑定具体项目路径、目录名、测试命令或业务名称，适合复制到其他项目中继续使用。

1. `common/project-release-qa`  
   通用项目审查、修复、测试、构建、打包、发版检查。

2. `common/project-prd-gap-implementation`  
   通用 PRD 对照、功能缺口识别、优先级排序、分批实现。

3. `common/browser-bridge-troubleshooter`  
   通用浏览器桥接、网页自动化、插件连接、selector、发送和抓取故障诊断。

## GEO 专用 Skills

这些 skill 保留当前 GEO Flow Agent 的业务语境，适合本项目或同类 GEO/AIO/AI 搜索监测产品。

1. `geo-agent-release-qa`  
   GEO Flow Agent 项目审查、测试、构建、桌面应用打包。

2. `geo-monitoring-evidence-chain`  
   GEO 监测证据链、AI 搜索详情、明细、来源、报告链路。

3. `webbridge-troubleshooter`  
   本项目 Kimi WebBridge / QWebBridge 故障诊断。

4. `geo-content-fact-writing`  
   事实库驱动的文章生成、反馈记忆、结构化验收。

5. `prd-gap-implementation`  
   按本项目 PRD 对照未实现功能并分批补齐。

## 使用建议

- 做当前项目：优先使用 GEO 专用 skill。
- 做其他项目：优先复制 `skills/common` 下的通用 skill。
- 如果要让 Codex 自动长期识别调用，可以把对应目录复制或安装到 Codex 的 skills 目录。

