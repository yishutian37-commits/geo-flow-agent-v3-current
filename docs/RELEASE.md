# GEO Flow Agent 发布说明

本文说明如何把本地桌面包发布到 GitHub Release，方便其他人下载试用。

## 1. 本地发布前检查

在项目根目录执行：

```powershell
python -m pytest backend/tests -q
npm --prefix frontend run build
npm run dist:win
```

生成的桌面包位于：

```text
release/GEO Flow Agent Setup 2.3.0.exe
release/GEO-Flow-Agent-2.3.0-Portable.exe
```

`release/` 默认被 `.gitignore` 忽略，不提交到代码仓库。

## 2. GitHub Actions 自动构建

仓库包含两个工作流：

- `.github/workflows/ci.yml`：每次 push 或 PR 时运行后端测试和前端构建。
- `.github/workflows/release.yml`：手动触发或推送 `v*` 标签时构建 Windows 桌面包。

手动触发方式：

1. 打开 GitHub 仓库。
2. 进入 `Actions`。
3. 选择 `Desktop Release`。
4. 点击 `Run workflow`。
5. 等待构建完成后，在 workflow artifacts 中下载安装包。

## 3. 正式 GitHub Release

推荐使用语义化标签：

```powershell
git tag v2.3.0
git push origin v2.3.0
```

推送标签后，`Desktop Release` 工作流会自动构建安装包，并把 `release/*.exe` 上传到对应 GitHub Release。

## 4. 发布说明建议

每次 Release 至少包含：

- 新增功能；
- 修复问题；
- 已知限制；
- 安装方式；
- 浏览器插件安装说明；
- 后端测试和前端构建状态；
- AGPLv3 + 商业授权双协议说明。

## 5. 注意事项

- 不要把 `.env`、API Key、浏览器登录态、数据库文件或本地打包缓存上传到 Release。
- 默认账号不再写死；首次启动时由用户初始化管理员账号。
- QWebBridge/Kimi WebBridge 依赖真实浏览器环境，用户仍需按说明安装浏览器插件并保持目标 AI 网站登录。
