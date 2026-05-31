# QWebBridge 集成说明

当前项目的网页自动检测已经支持两种浏览器桥接协议：

- `kimi`：官方 Kimi WebBridge，接口为 `GET /status` 与 `POST /command`
- `qweb`：开源 QWebBridge，接口为 `GET /health` 与 `POST /api/tool/<name>`

默认模式为 `auto`。后端会先探测 QWebBridge，再探测官方 Kimi WebBridge。这样在官方 Kimi WebBridge 出现 `502 Bad Gateway` 时，可以切换到开源 QWebBridge 路线。

桌面应用已内置 QWebBridge daemon。启动 GEO Flow Agent 时，主程序会自动尝试在 `10087` 端口启动 QWebBridge，并把后端检测地址指向：

```text
http://127.0.0.1:10087
```

浏览器扩展仍需在 Chrome/Edge 中加载一次，这是浏览器扩展安全机制决定的。

## 推荐切换方式

1. 启动 GEO Flow Agent，应用会自动启动 QWebBridge daemon。
2. 确保浏览器扩展连接地址为：

```text
ws://127.0.0.1:10087/selector/command
```

3. 在应用的“监测分析”里点击“开始自动检测”。进度日志会显示当前使用的桥接类型，例如：

```text
WebBridge 当前使用：QWebBridge
```

## 使用非默认端口

如果需要让 QWebBridge 跑在其他端口，例如 `10087`，启动后端或桌面应用前设置：

```cmd
set WEBBRIDGE_PROVIDER=qweb
set QWEBBRIDGE_BASE_URL=http://127.0.0.1:10087
```

浏览器扩展里的连接地址也要同步改成：

```text
ws://127.0.0.1:10087/selector/command
```

本项目已提供一个 Windows 启动脚本：

```text
启动QWebBridge-10087.cmd
```

双击后保持命令窗口不要关闭。脚本会把 QWebBridge 的运行文件写到 `_external/QWebBridge/_runtime`，避免写入用户目录时被权限或杀毒软件拦截。

## 排查顺序

先确认 daemon：

```text
http://127.0.0.1:10086/health
```

如果使用本项目脚本启动，请检查：

```text
http://127.0.0.1:10087/health
```

返回里需要看到：

```json
{
  "running": true,
  "extensions_connected": true
}
```

再回到应用检测。如果 `extensions_connected` 为 `false`，说明后台服务已启动，但浏览器扩展没有连上。
