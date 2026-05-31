import { existsSync, statSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const root = process.cwd();
const isWindows = process.platform === "win32";

function quoteForCmd(value) {
  const text = String(value);
  if (/^[A-Za-z0-9_./:@=+-]+$/.test(text)) return text;
  return `"${text.replace(/"/g, '\\"')}"`;
}

function run(command, args, options = {}) {
  const commandLine = [command, ...args].map(quoteForCmd).join(" ");
  const result = spawnSync(isWindows ? "cmd.exe" : command, isWindows ? ["/d", "/s", "/c", commandLine] : args, {
    cwd: root,
    stdio: "inherit",
    shell: false,
  });
  if (result.error) {
    console.error(result.error);
    process.exit(1);
  }
  const status = result.status ?? 1;
  if (status !== 0 && !options.allowNonZero) {
    process.exit(status);
  }
  return status;
}

function assertFile(relativePath) {
  const filePath = join(root, relativePath);
  if (!existsSync(filePath) || statSync(filePath).size === 0) {
    console.error(`Missing QWebBridge build artifact: ${relativePath}`);
    process.exit(1);
  }
}

run("npx.cmd", ["pnpm", "--dir", "_external/QWebBridge", "--filter", "@qweb/daemon", "build"]);
const extensionStatus = run(
  "npm.cmd",
  ["--prefix", "_external/QWebBridge/packages/extension", "run", "build"],
  { allowNonZero: true }
);

[
  "_external/QWebBridge/packages/daemon/dist/cli.js",
  "_external/QWebBridge/packages/extension/dist/background.js",
  "_external/QWebBridge/packages/extension/dist/manifest.json",
  "_external/QWebBridge/packages/extension/dist/popup-fixed.html",
  "_external/QWebBridge/packages/extension/dist/popup-fixed.js",
].forEach(assertFile);

if (extensionStatus !== 0) {
  console.warn("QWebBridge extension build returned a non-zero code after writing all required artifacts; continuing.");
}
