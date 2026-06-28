import { ApiError, parseHttpErrorBody } from "../utils/httpError.js";

export const DEFAULT_TUNNEL_TIMEOUT_MS = 30000;
export const TUNNEL_START_TIMEOUT_MS = 180000;

function timeoutMessage(action) {
  if (action === "start") {
    return "公网隧道启动超时。可能正在下载或连接 ngrok/Cloudflare，请稍后重试；若一直失败，请改用局域网联机或检查代理/VPN。";
  }
  if (action === "verify") {
    return "公网隧道校验超时。请稍后重试，或检查公网代理/VPN。";
  }
  return "公网隧道请求超时，请确认 AI辩论场后端仍在运行。";
}

export function normalizeTunnelFetchError(error, action = "request") {
  if (error?.name !== "AbortError") return error;
  return new ApiError(timeoutMessage(action), {
    code: "TUNNEL_REQUEST_TIMEOUT",
    details:
      "浏览器请求等待超过本地预算后主动取消。启动公网隧道时后端可能仍在尝试 ngrok、Cloudflare 或首次下载隧道程序。",
  });
}

export async function fetchTunnelJson(url, options = {}) {
  const { timeoutMs = DEFAULT_TUNNEL_TIMEOUT_MS, action = "request", ...fetchOptions } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...fetchOptions, signal: controller.signal });
    if (!res.ok) throw parseHttpErrorBody(await res.text(), res);
    return res.json();
  } catch (error) {
    throw normalizeTunnelFetchError(error, action);
  } finally {
    clearTimeout(timer);
  }
}
