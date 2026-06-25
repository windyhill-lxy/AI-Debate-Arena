const { app, BrowserWindow, Menu, clipboard, dialog, shell } = require("electron");
const { execFile, spawn } = require("child_process");
const { promisify } = require("util");

const execFileAsync = promisify(execFile);
const path = require("path");
const fs = require("fs");
const http = require("http");
const os = require("os");

const BACKEND_PORT = 9000;
const FRONTEND_PORT = 5173;

const childProcs = [];
const logStreams = [];
let mainWindow = null;
let runtime = null;
let isQuitting = false;
let cleanupDone = false;

function getRuntime() {
  if (runtime) return runtime;

  const isPackaged = app.isPackaged;
  if (!isPackaged) {
    const packRoot = path.resolve(__dirname, "..");
    const projectRoot = path.resolve(packRoot, "..");
    const pythonDir = path.join(projectRoot, "tools", "python");
    runtime = {
      isPackaged: false,
      appCoreRoot: projectRoot,
      python: path.join(pythonDir, "python.exe"),
      pythonDir,
      scriptsDir: path.join(pythonDir, "Scripts"),
      nodeDir: path.join(projectRoot, "tools", "node"),
      backendCwd: path.join(projectRoot, "backend"),
      frontendDist: path.join(packRoot, "assets", "frontend-dist"),
      serveScript: path.join(packRoot, "scripts", "serve_unified.py"),
      configDir: projectRoot,
    };
    return runtime;
  }

  const appCoreRoot = path.join(process.resourcesPath, "app-core");
  const pythonDir = path.join(appCoreRoot, "python");
  const exeDir = path.dirname(process.execPath);
  runtime = {
    isPackaged: true,
    appCoreRoot,
    python: path.join(pythonDir, "python.exe"),
    pythonDir,
    scriptsDir: path.join(pythonDir, "Scripts"),
    nodeDir: null,
    backendCwd: path.join(appCoreRoot, "backend"),
    frontendDist: path.join(appCoreRoot, "frontend-dist"),
    serveScript: path.join(appCoreRoot, "scripts", "serve_unified.py"),
    configDir: exeDir,
    userDataDir: app.getPath("userData"),
  };
  return runtime;
}

function buildChildEnv(rt, extraEnv = {}) {
  const parts = [rt.pythonDir, rt.scriptsDir];
  if (rt.nodeDir) parts.push(rt.nodeDir);
  parts.push(process.env.PATH || "");
  const env = {
    ...process.env,
    PATH: parts.join(path.delimiter),
    NO_PROXY: "127.0.0.1,localhost",
    no_proxy: "127.0.0.1,localhost",
    ...extraEnv,
  };
  delete env.HTTP_PROXY;
  delete env.HTTPS_PROXY;
  delete env.http_proxy;
  delete env.https_proxy;
  delete env.ALL_PROXY;
  delete env.all_proxy;
  return env;
}

function ensurePackagedEnv(rt) {
  if (!rt.isPackaged) return;

  const target = path.join(rt.appCoreRoot, ".env");
  const candidates = [
    path.join(rt.configDir, ".env"),
    path.join(rt.userDataDir, ".env"),
    path.join(rt.appCoreRoot, ".env.example"),
  ];

  for (const src of candidates) {
    if (fs.existsSync(src)) {
      try {
        fs.mkdirSync(path.dirname(target), { recursive: true });
        fs.copyFileSync(src, target);
      } catch (err) {
        console.error("sync .env failed", err);
      }
      return;
    }
  }
}

function seedPortableEnv(rt) {
  if (!rt.isPackaged) return;

  const portableEnv = path.join(rt.configDir, ".env");
  const exampleInCore = path.join(rt.appCoreRoot, ".env.example");
  const exampleBesideExe = path.join(rt.configDir, ".env.example");

  if (fs.existsSync(portableEnv)) return;

  const example = fs.existsSync(exampleBesideExe)
    ? exampleBesideExe
    : fs.existsSync(exampleInCore)
      ? exampleInCore
      : null;

  if (example) {
    try {
      fs.copyFileSync(example, portableEnv);
    } catch (err) {
      console.error("seed .env failed", err);
    }
  }
}

function getLanIp() {
  const nets = os.networkInterfaces();
  for (const ifaces of Object.values(nets)) {
    for (const net of ifaces) {
      if (net.family === "IPv4" && !net.internal && !net.address.startsWith("169.254.")) {
        return net.address;
      }
    }
  }
  return null;
}

function getLogDir() {
  const rt = getRuntime();
  const logDir = path.join(rt.isPackaged ? rt.configDir : rt.appCoreRoot, "logs");
  fs.mkdirSync(logDir, { recursive: true });
  return logDir;
}

function tailLogFile(logPath, maxLines = 8) {
  try {
    if (!fs.existsSync(logPath)) return "";
    const lines = fs.readFileSync(logPath, "utf8").split(/\r?\n/);
    return lines.slice(-maxLines).join("\n").trim();
  } catch {
    return "";
  }
}

function spawnProc(label, cmd, args, opts = {}) {
  const rt = getRuntime();
  const logDir = getLogDir();
  const logPath = path.join(logDir, `${label}.log`);
  const logStream = fs.openSync(logPath, "a");
  fs.writeSync(logStream, `\n--- ${label} start ${new Date().toISOString()} ---\n`);
  const proc = spawn(cmd, args, {
    cwd: opts.cwd,
    env: buildChildEnv(rt, opts.extraEnv),
    windowsHide: true,
    stdio: ["ignore", logStream, logStream],
  });
  proc.on("error", (err) => console.error(`[${label}]`, err));
  childProcs.push(proc);
  logStreams.push(logStream);
  return proc;
}

function closeLogStreams() {
  for (const fd of logStreams) {
    try {
      fs.closeSync(fd);
    } catch (_) {
      /* ignore */
    }
  }
  logStreams.length = 0;
}

async function killChildrenAsync() {
  const tasks = childProcs.map((proc) => {
    if (!proc.pid) return Promise.resolve();
    return execFileAsync("taskkill", ["/PID", String(proc.pid), "/T", "/F"], {
      windowsHide: true,
    }).catch(() => {});
  });
  await Promise.all(tasks);
  childProcs.length = 0;
}

async function shutdownChildren() {
  if (cleanupDone) return;
  await killChildrenAsync();
  closeLogStreams();
  cleanupDone = true;
}

function httpGet(url) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: 4000 }, (res) => {
      res.resume();
      resolve(res.statusCode >= 200 && res.statusCode < 500);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitReady(maxMs = 120000) {
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    const fe = await httpGet(`http://127.0.0.1:${FRONTEND_PORT}/`);
    const be = await httpGet(`http://127.0.0.1:${BACKEND_PORT}/health`);
    const proxyApi = await httpGet(`http://127.0.0.1:${FRONTEND_PORT}/health`);
    const lobby = await httpGet(`http://127.0.0.1:${FRONTEND_PORT}/api/debates/online-lobby`);
    if (fe && be && proxyApi && lobby) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

function preflight() {
  const rt = getRuntime();
  if (!fs.existsSync(rt.python)) {
    dialog.showErrorBox(
      "缺少 Python 运行时",
      rt.isPackaged
        ? `打包资源不完整，请重新运行「打包发布.bat」。\n\n${rt.python}`
        : `请先运行项目根目录 bootstrap.bat 安装便携环境。\n\n${rt.python}`,
    );
    return false;
  }
  if (!fs.existsSync(path.join(rt.frontendDist, "index.html"))) {
    dialog.showErrorBox(
      "缺少前端资源",
      rt.isPackaged
        ? "打包资源不完整，请重新运行「打包发布.bat」。"
        : "请先运行「准备程序.bat」构建并复制前端页面。",
    );
    return false;
  }
  return true;
}

function startServices() {
  const rt = getRuntime();
  if (rt.isPackaged) {
    seedPortableEnv(rt);
    ensurePackagedEnv(rt);
  }

  spawnProc(
    "backend",
    rt.python,
    ["-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", String(BACKEND_PORT)],
    {
      cwd: rt.backendCwd,
      extraEnv: rt.isPackaged ? { DEBATE_PROJECT_ROOT: rt.appCoreRoot } : {},
    },
  );

  spawnProc(
    "frontend",
    rt.python,
    [rt.serveScript, "--host", "0.0.0.0", "--port", String(FRONTEND_PORT), "--root", rt.frontendDist],
    { cwd: rt.appCoreRoot },
  );
}

function killChildren() {
  void shutdownChildren();
}

function buildMenu() {
  const rt = getRuntime();
  const lanIp = getLanIp();
  const lanUrl = lanIp ? `http://${lanIp}:${FRONTEND_PORT}` : null;

  const fileSubmenu = [
    {
      label: "复制本机地址",
      click: () => {
        clipboard.writeText(`http://127.0.0.1:${FRONTEND_PORT}`);
      },
    },
    {
      label: lanUrl ? "复制联机地址（局域网）" : "复制联机地址（未检测到局域网 IP）",
      enabled: Boolean(lanUrl),
      click: () => {
        if (lanUrl) clipboard.writeText(lanUrl);
      },
    },
    { type: "separator" },
    {
      label: "在浏览器中打开",
      click: () => shell.openExternal(`http://127.0.0.1:${FRONTEND_PORT}/`),
    },
  ];

  if (rt.isPackaged) {
    fileSubmenu.push(
      { type: "separator" },
      {
        label: "打开配置目录（编辑 .env）",
        click: () => shell.openPath(rt.configDir),
      },
    );
  }

  fileSubmenu.push({ type: "separator" }, { role: "quit", label: "退出" });

  const template = [
    { label: "文件", submenu: fileSubmenu },
    {
      label: "联机",
      submenu: [
        {
          label: "进入联机大厅",
          click: () => {
            if (mainWindow) mainWindow.loadURL(`http://127.0.0.1:${FRONTEND_PORT}/welcome`);
          },
        },
        {
          label: lanUrl ? `局域网地址：${lanUrl}` : "未检测到局域网 IP",
          enabled: false,
        },
        {
          label: "联机说明",
          click: () => {
            const lines = [
              "本程序已内置局域网联机，无需单独 LAN 启动脚本。",
              "",
              "主持步骤：",
              "1. 在本机创建联机房间",
              "2. 菜单 → 复制联机地址，发给同学",
              "3. 同学用浏览器打开该地址，选席位加入",
              "",
              lanUrl ? `当前联机地址：${lanUrl}` : "请确认电脑已连接 Wi‑Fi / 有线网。",
              "",
              "防火墙需允许端口 5173（页面与联机 API/WebSocket）。",
            ];
            dialog.showMessageBox({
              type: "info",
              title: "联机说明",
              message: "多人联机（内置）",
              detail: lines.join("\n"),
            });
          },
        },
      ],
    },
    {
      label: "视图",
      submenu: [
        { role: "reload", label: "刷新" },
        { role: "forceReload", label: "强制刷新" },
        { type: "separator" },
        { role: "resetZoom", label: "重置缩放" },
        { role: "zoomIn", label: "放大" },
        { role: "zoomOut", label: "缩小" },
        { type: "separator" },
        { role: "togglefullscreen", label: "全屏" },
        { type: "separator" },
        { role: "toggleDevTools", label: "开发者工具" },
      ],
    },
    {
      label: "帮助",
      submenu: [
        {
          label: "关于",
          click: () => {
            dialog.showMessageBox({
              type: "info",
              title: "AI 辩论场",
              message: rt.isPackaged ? "AI 辩论场 · 独立发行版" : "AI 辩论场 · 桌面版",
              detail: [
                "界面与网页端一致，后端与联机能力已内置。",
                rt.isPackaged ? "API 密钥请编辑程序目录下的 .env 文件。" : "",
                "",
                `本机：http://127.0.0.1:${FRONTEND_PORT}`,
                lanUrl ? `联机：${lanUrl}` : "",
              ]
                .filter(Boolean)
                .join("\n"),
            });
          },
        },
      ],
    },
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

async function createWindow() {
  const logDir = getLogDir();
  process.env.DEBATE_LOG_DIR = logDir;
  const ready = await waitReady();

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 640,
    title: "AI 辩论场",
    show: false,
    autoHideMenuBar: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });

  mainWindow.webContents.on("will-prevent-unload", (event) => {
    // 桌面端强制允许关闭，避免渲染进程 beforeunload 拦截窗口 ×
    event.preventDefault();
  });

  mainWindow.on("close", (event) => {
    if (isQuitting) return;
    event.preventDefault();
    isQuitting = true;
    shutdownChildren()
      .then(() => {
        mainWindow.removeAllListeners("close");
        mainWindow.destroy();
        app.quit();
      })
      .catch(() => {
        mainWindow.destroy();
        app.quit();
      });
  });

  if (ready) {
    mainWindow.loadURL(`http://127.0.0.1:${FRONTEND_PORT}/welcome`);
  } else {
    const backendTail = tailLogFile(path.join(logDir, "backend.log"));
    const frontendTail = tailLogFile(path.join(logDir, "frontend.log"));
    const errorPage = path.join(__dirname, "loading-error.html");
    const query = new URLSearchParams({
      failed: "1",
      logDir,
    }).toString();
    if (fs.existsSync(errorPage)) {
      mainWindow.loadFile(errorPage, { query });
    } else {
      mainWindow.loadURL(`http://127.0.0.1:${FRONTEND_PORT}/welcome`);
    }
    dialog.showErrorBox(
      "启动超时",
      [
        "后端或统一服务未能就绪，已显示错误页而非空白界面。",
        "",
        "请确认端口 5173、9000 未被占用后重试。",
        `日志目录：${logDir}`,
        backendTail ? `\n[backend 最近日志]\n${backendTail}` : "",
        frontendTail ? `\n[frontend 最近日志]\n${frontendTail}` : "",
      ].join("\n"),
    );
  }

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    if (!preflight()) {
      app.quit();
      return;
    }
    buildMenu();
    startServices();
    await createWindow();
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
  });

  app.on("before-quit", () => {
    isQuitting = true;
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
}

process.on("exit", killChildren);
