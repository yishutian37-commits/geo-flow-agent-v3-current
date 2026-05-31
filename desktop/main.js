const { app, BrowserWindow, dialog, net, protocol } = require('electron');
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const netNode = require('net');
const path = require('path');

let mainWindow = null;
let backendProcess = null;
let qwebBridgeProcess = null;
let backendPort = 0;
const qwebBridgePort = 10087;

app.setAppUserModelId('com.geoflow.agent');

protocol.registerSchemesAsPrivileged([
  {
    scheme: 'app',
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
      stream: true,
    },
  },
]);

function getProjectRoot() {
  return path.resolve(__dirname, '..');
}

function getAppIconPath() {
  return path.join(__dirname, 'assets', process.platform === 'win32' ? 'icon.ico' : 'icon.png');
}

function getFrontendRoot() {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'frontend')
    : path.join(getProjectRoot(), 'frontend', 'build');
}

function getBackendExecutablePath() {
  return path.join(process.resourcesPath, 'backend', process.platform === 'win32' ? 'geo-flow-backend.exe' : 'geo-flow-backend');
}

function getBackendSourcePath() {
  return path.join(getProjectRoot(), 'backend', 'desktop_server.py');
}

function getQWebBridgeRoot() {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'qwebbridge')
    : path.join(getProjectRoot(), '_external', 'QWebBridge');
}

function getQWebBridgeDaemonScript() {
  return app.isPackaged
    ? path.join(getQWebBridgeRoot(), 'daemon', 'cli.js')
    : path.join(getQWebBridgeRoot(), 'packages', 'daemon', 'dist', 'cli.js');
}

function getQWebBridgeExtensionPath() {
  return app.isPackaged
    ? path.join(getQWebBridgeRoot(), 'extension')
    : path.join(getQWebBridgeRoot(), 'packages', 'extension', 'dist');
}

function getDevPythonPath() {
  if (process.env.GEO_BACKEND_PYTHON) return process.env.GEO_BACKEND_PYTHON;

  const executable = process.platform === 'win32' ? 'python.exe' : 'python';
  const scriptsDir = process.platform === 'win32' ? 'Scripts' : 'bin';
  const venvPython = path.join(getProjectRoot(), 'backend', '.venv', scriptsDir, executable);
  return fs.existsSync(venvPython) ? venvPython : 'python';
}

function writeLog(...parts) {
  const line = `[${new Date().toISOString()}] ${parts.map((part) => String(part)).join(' ')}\n`;
  try {
    const logDir = path.join(app.getPath('userData'), 'logs');
    fs.mkdirSync(logDir, { recursive: true });
    fs.appendFileSync(path.join(logDir, 'desktop.log'), line, 'utf8');
  } catch {
    // Best-effort desktop logging.
  }
}

function findFreePort(host = '127.0.0.1') {
  return new Promise((resolve, reject) => {
    const server = netNode.createServer();
    server.on('error', reject);
    server.listen(0, host, () => {
      const address = server.address();
      const port = typeof address === 'object' && address ? address.port : 0;
      server.close(() => resolve(port));
    });
  });
}

function waitForBackend(apiBaseUrl, timeoutMs = 30000) {
  const startedAt = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      const req = http.get(`${apiBaseUrl}/health`, (res) => {
        res.resume();
        if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
          resolve();
          return;
        }
        retry();
      });
      req.on('error', retry);
      req.setTimeout(2000, () => {
        req.destroy();
        retry();
      });
    };

    const retry = () => {
      if (Date.now() - startedAt > timeoutMs) {
        reject(new Error(`Backend did not become ready within ${timeoutMs}ms`));
        return;
      }
      setTimeout(tick, 500);
    };

    tick();
  });
}

function waitForHttpOk(url, timeoutMs = 8000) {
  const startedAt = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      const req = http.get(url, (res) => {
        res.resume();
        if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
          resolve();
          return;
        }
        retry();
      });
      req.on('error', retry);
      req.setTimeout(1500, () => {
        req.destroy();
        retry();
      });
    };

    const retry = () => {
      if (Date.now() - startedAt > timeoutMs) {
        reject(new Error(`${url} did not become ready within ${timeoutMs}ms`));
        return;
      }
      setTimeout(tick, 300);
    };

    tick();
  });
}

async function startQWebBridge() {
  if (process.env.DISABLE_QWEBBRIDGE === '1') {
    writeLog('qwebbridge disabled by env');
    return;
  }

  const healthUrl = `http://127.0.0.1:${qwebBridgePort}/health`;
  try {
    await waitForHttpOk(healthUrl, 1000);
    writeLog('qwebbridge already running', healthUrl);
    return;
  } catch {
    // Not running yet; start the bundled daemon.
  }

  const daemonScript = getQWebBridgeDaemonScript();
  if (!fs.existsSync(daemonScript)) {
    writeLog('qwebbridge daemon script missing', daemonScript);
    return;
  }

  const qwebHome = path.join(app.getPath('userData'), 'qwebbridge');
  fs.mkdirSync(qwebHome, { recursive: true });

  const env = {
    ...process.env,
    ELECTRON_RUN_AS_NODE: '1',
    QWEB_PORT: String(qwebBridgePort),
    QWEB_HOME: qwebHome,
  };

  const cwd = app.isPackaged
    ? path.dirname(daemonScript)
    : getQWebBridgeRoot();

  writeLog('starting qwebbridge', process.execPath, daemonScript);
  qwebBridgeProcess = spawn(process.execPath, [daemonScript, 'run'], {
    cwd,
    env,
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  qwebBridgeProcess.stdout.on('data', (chunk) => writeLog('[qwebbridge]', chunk.toString().trim()));
  qwebBridgeProcess.stderr.on('data', (chunk) => writeLog('[qwebbridge:error]', chunk.toString().trim()));
  qwebBridgeProcess.on('exit', (code, signal) => writeLog('qwebbridge exited', code, signal));

  try {
    await waitForHttpOk(healthUrl, 8000);
    writeLog('qwebbridge ready', healthUrl, 'extension', getQWebBridgeExtensionPath());
  } catch (error) {
    writeLog('qwebbridge startup check failed', error.message);
  }
}

function startBackend(port) {
  const userDataDir = app.getPath('userData');
  const dbPath = path.join(userDataDir, 'geoflow.db').replace(/\\/g, '/');
  const env = {
    ...process.env,
    GEO_DESKTOP_PORT: String(port),
    GEO_USER_DATA_DIR: userDataDir,
    DATABASE_URL: `sqlite+aiosqlite:///${dbPath}`,
    SYNC_DATABASE_URL: `sqlite:///${dbPath}`,
    GEO_LLM_REGISTRY_PATH: path.join(userDataDir, 'models', 'llm_registry.json'),
    CORS_ALLOW_ORIGIN_REGEX: '^(app://.*|file://.*|http://localhost:\\d+|http://127\\.0\\.0\\.1:\\d+)$',
    ENVIRONMENT: 'development',
    DEBUG: 'False',
    DESKTOP_MODE: '1',
    WEBBRIDGE_PROVIDER: 'auto',
    QWEBBRIDGE_BASE_URL: `http://127.0.0.1:${qwebBridgePort}`,
    QWEBBRIDGE_EXTENSION_PATH: getQWebBridgeExtensionPath(),
  };

  const packagedBackend = getBackendExecutablePath();
  let command;
  let args;
  let cwd;

  if (app.isPackaged && fs.existsSync(packagedBackend)) {
    command = packagedBackend;
    args = [];
    cwd = path.dirname(packagedBackend);
  } else {
    command = getDevPythonPath();
    args = [getBackendSourcePath()];
    cwd = path.join(getProjectRoot(), 'backend');
  }

  writeLog('starting backend', command, args.join(' '));
  backendProcess = spawn(command, args, {
    cwd,
    env,
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  backendProcess.stdout.on('data', (chunk) => writeLog('[backend]', chunk.toString().trim()));
  backendProcess.stderr.on('data', (chunk) => writeLog('[backend:error]', chunk.toString().trim()));
  backendProcess.on('exit', (code, signal) => writeLog('backend exited', code, signal));
}

function registerAppProtocol() {
  protocol.handle('app', (request) => {
    const frontendRoot = path.resolve(getFrontendRoot());
    const url = new URL(request.url);
    let pathname = decodeURIComponent(url.pathname || '');
    if (pathname.startsWith('/')) pathname = pathname.slice(1);
    if (!pathname) pathname = 'index.html';

    let target = path.resolve(frontendRoot, pathname);
    const relativePath = path.relative(frontendRoot, target);
    if (relativePath.startsWith('..') || path.isAbsolute(relativePath)) {
      return new Response('Forbidden', { status: 403 });
    }

    if (!fs.existsSync(target) || fs.statSync(target).isDirectory()) {
      target = path.join(frontendRoot, 'index.html');
    }

    return net.fetch(`file:///${target.replace(/\\/g, '/')}`);
  });
}

function createWindow(apiBaseUrl) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1100,
    minHeight: 720,
    title: 'GEO Flow Agent V2.3',
    icon: getAppIconPath(),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      additionalArguments: [`--geo-api-base=${apiBaseUrl}`],
    },
  });

  mainWindow.loadURL('app://./');
  if (!app.isPackaged || process.env.OPEN_DEVTOOLS === '1') {
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function stopBackend() {
  if (backendProcess && !backendProcess.killed) {
    writeLog('stopping backend');
    backendProcess.kill();
  }
  backendProcess = null;
}

function stopQWebBridge() {
  if (qwebBridgeProcess && !qwebBridgeProcess.killed) {
    writeLog('stopping qwebbridge');
    qwebBridgeProcess.kill();
  }
  qwebBridgeProcess = null;
}

function stopSidecars() {
  stopBackend();
  stopQWebBridge();
}

app.whenReady().then(async () => {
  try {
    registerAppProtocol();
    backendPort = await findFreePort();
    const apiBaseUrl = `http://127.0.0.1:${backendPort}`;
    await startQWebBridge();
    startBackend(backendPort);
    await waitForBackend(apiBaseUrl);
    createWindow(apiBaseUrl);
  } catch (error) {
    writeLog('desktop startup failed', error.stack || error.message);
    dialog.showErrorBox('GEO Flow Agent 启动失败', error.message || String(error));
    app.quit();
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow(`http://127.0.0.1:${backendPort}`);
    }
  });
});

app.on('before-quit', stopSidecars);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
