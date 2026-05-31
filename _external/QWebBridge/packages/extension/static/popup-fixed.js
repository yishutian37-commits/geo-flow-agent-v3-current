const DEFAULT_URL = "ws://127.0.0.1:10087/selector/command";
const POLL_INTERVAL_MS = 3000;

const $ = (id) => document.getElementById(id);

const el = {
  main: $("main-content"),
  settings: $("dev-settings"),
  statusIcon: $("status-icon"),
  statusText: $("status-text"),
  statusDesc: $("status-desc"),
  wsUrl: $("ws-url"),
  testBtn: $("dev-test-btn"),
  testResult: $("dev-test-result"),
};

const storage = typeof chrome !== "undefined" && chrome.storage && chrome.storage.local
  ? chrome.storage.local
  : { get: (_keys, cb) => cb({}), set: (_data, cb) => cb && cb() };

function setStatus(connected) {
  el.statusIcon.classList.toggle("connected", connected);
  el.statusIcon.textContent = connected ? "OK" : "x";
  el.statusText.textContent = connected ? "Browser helper is ready" : "Browser helper is not ready";
  el.statusDesc.textContent = connected
    ? "The extension is connected to the local QWebBridge service."
    : "Make sure GEO Flow Agent is running and port 10087 is available.";
}

function showSettings() {
  el.main.classList.add("hidden");
  el.settings.classList.remove("hidden");
  loadUrl();
}

function showMain() {
  el.settings.classList.add("hidden");
  el.main.classList.remove("hidden");
  checkStatus();
}

function loadUrl() {
  storage.get(["daemonUrl"], (data) => {
    el.wsUrl.value = data.daemonUrl || DEFAULT_URL;
  });
}

function saveUrl(url) {
  storage.set({ daemonUrl: url }, () => {
    try {
      chrome.runtime.sendMessage({ type: "SET_DAEMON_URL", url });
    } catch {}
  });
}

function checkStatus() {
  try {
    chrome.runtime.sendMessage({ type: "status" }, (response) => {
      setStatus(Boolean(response && response.connected));
    });
  } catch {
    setStatus(false);
  }
}

function showResult(text, ok) {
  el.testResult.textContent = text;
  el.testResult.className = `result ${ok ? "ok" : "fail"}`;
  el.testResult.classList.remove("hidden");
}

function testConnection(url) {
  el.testBtn.disabled = true;
  showResult("Testing...", true);
  return new Promise((resolve) => {
    let ws;
    const timer = setTimeout(() => {
      try { if (ws) ws.close(); } catch {}
      el.testBtn.disabled = false;
      showResult("Connection failed. Make sure the local app is running.", false);
      resolve(false);
    }, 5000);

    try {
      ws = new WebSocket(url);
    } catch {
      clearTimeout(timer);
      el.testBtn.disabled = false;
      showResult("Invalid WebSocket URL.", false);
      resolve(false);
      return;
    }

    ws.onopen = () => {
      clearTimeout(timer);
      try { ws.close(); } catch {}
      el.testBtn.disabled = false;
      showResult("Connection succeeded.", true);
      resolve(true);
    };
    ws.onerror = () => {
      clearTimeout(timer);
      el.testBtn.disabled = false;
      showResult("Connection failed. Make sure the local app is running.", false);
      resolve(false);
    };
  });
}

function on(id, event, handler) {
  const node = $(id);
  if (node) node.addEventListener(event, handler);
}

on("open-settings", "click", showSettings);
on("logo-area", "click", showSettings);
on("refresh-status", "click", checkStatus);
on("dev-exit", "click", showMain);
on("dev-reset", "click", () => {
  el.wsUrl.value = DEFAULT_URL;
  saveUrl(DEFAULT_URL);
  showResult("Default URL restored.", true);
});
on("dev-test-btn", "click", () => {
  const url = el.wsUrl.value.trim();
  if (!url.startsWith("ws://") && !url.startsWith("wss://")) {
    showResult("URL must start with ws:// or wss://.", false);
    return;
  }
  testConnection(url);
});
on("dev-save", "click", () => {
  const url = el.wsUrl.value.trim();
  if (!url.startsWith("ws://") && !url.startsWith("wss://")) {
    showResult("URL must start with ws:// or wss://.", false);
    return;
  }
  saveUrl(url);
  showResult("Saved. Reconnecting...", true);
  setTimeout(checkStatus, 1000);
});

loadUrl();
checkStatus();
setInterval(checkStatus, POLL_INTERVAL_MS);
