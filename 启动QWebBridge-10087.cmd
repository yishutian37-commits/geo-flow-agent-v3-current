@echo off
setlocal
cd /d "%~dp0_external\QWebBridge"
set QWEB_PORT=10087
set QWEB_HOME=%CD%\_runtime
if not exist "%QWEB_HOME%" mkdir "%QWEB_HOME%"
echo Starting QWebBridge on http://127.0.0.1:%QWEB_PORT%
echo WebSocket: ws://127.0.0.1:%QWEB_PORT%/selector/command
echo Keep this window open while GEO Flow Agent is running.
node packages\daemon\dist\cli.js run
pause
