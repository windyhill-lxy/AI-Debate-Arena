const { contextBridge } = require("electron");

// Sandboxed preload cannot require Node built-ins (path/fs). Main sets DEBATE_LOG_DIR.
contextBridge.exposeInMainWorld("debateDesktop", {
  isDesktop: true,
  unifiedApi: true,
  logDir: process.env.DEBATE_LOG_DIR || "",
});
