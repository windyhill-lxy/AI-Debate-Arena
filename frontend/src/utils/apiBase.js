function isLoopbackHost(host) {
  if (!host) return true;
  const h = host.toLowerCase();
  return h === "localhost" || h === "127.0.0.1" || h === "[::1]";
}

const TUNNEL_HOST_SUFFIXES = [
  ".trycloudflare.com",
  ".ngrok-free.app",
  ".ngrok-free.dev",
  ".ngrok.io",
  ".loca.lt",
  ".serveo.net",
];

export function isTunnelHost(host) {
  if (!host) return false;
  const h = host.toLowerCase();
  return TUNNEL_HOST_SUFFIXES.some((suffix) => h.endsWith(suffix));
}

function usesSameOriginApi() {
  if (typeof window === "undefined") return false;
  const host = window.location.hostname || "";
  const port = window.location.port || "";
  if (isTunnelHost(host)) return true;
  if (window.__DEBATE_UNIFIED_API__ === true) return true;
  if (window.debateDesktop?.unifiedApi === true) return true;
  // Electron 统一服务与 Vite 开发服代理 /api 与 WebSocket（含常见 dev 端口）
  if (port === "5173" || port === "3000" || port === "4173") return true;
  return false;
}

export function toWebSocketBase(apiBase) {
  if (!apiBase) return "ws://127.0.0.1:9000";
  if (apiBase.startsWith("https://")) return `wss://${apiBase.slice("https://".length)}`;
  if (apiBase.startsWith("http://")) return `ws://${apiBase.slice("http://".length)}`;
  return apiBase.replace(/^http/i, "ws");
}

function defaultApiBase() {
  if (typeof window === "undefined") return "http://127.0.0.1:9000";
  if (usesSameOriginApi()) {
    return window.location.origin;
  }
  const protocol = window.location.protocol || "http:";
  const host = window.location.hostname || "127.0.0.1";
  return `${protocol}//${host}:9000`;
}

function resolveApiBase() {
  const envBase = import.meta.env.VITE_API_BASE?.trim();
  if (typeof window === "undefined") {
    return envBase || "http://127.0.0.1:9000";
  }
  const dynamic = defaultApiBase();
  if (!envBase) return dynamic;
  if (!isLoopbackHost(window.location.hostname) && /localhost|127\.0\.0\.1/i.test(envBase)) {
    return dynamic;
  }
  return envBase;
}

export function getPublicOrigin() {
  if (typeof window === "undefined") return "";
  const tunnel = window.__DEBATE_TUNNEL_URL__?.trim();
  if (tunnel) return tunnel.replace(/\/$/, "");
  if (isTunnelHost(window.location.hostname)) return window.location.origin;
  return window.location.origin;
}

export function buildJoinLink(debateId) {
  if (!debateId) return "";
  return `${getPublicOrigin()}/join/${debateId}`;
}

export const API_BASE = resolveApiBase();
