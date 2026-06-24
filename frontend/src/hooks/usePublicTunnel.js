import { useCallback, useEffect, useState } from "react";
import { API_BASE } from "../utils/apiBase.js";
import { useErrorDialog } from "../components/ErrorDialogProvider.jsx";
import { parseHttpErrorBody } from "../utils/httpError.js";

const FETCH_TIMEOUT_MS = 30000;

async function fetchJson(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? FETCH_TIMEOUT_MS);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    if (!res.ok) throw parseHttpErrorBody(await res.text(), res);
    return res.json();
  } finally {
    clearTimeout(timer);
  }
}

export function usePublicTunnel(pollMs = 10000) {
  const [status, setStatus] = useState({
    running: false,
    url: null,
    error: null,
    provider: "cloudflare-quick",
    local_url: "http://127.0.0.1:5173",
    healthy: false,
    remote_reachable: false,
  });
  const [busy, setBusy] = useState(false);
  const { reportError } = useErrorDialog();

  const refresh = useCallback(async () => {
    try {
      const data = await fetchJson(`${API_BASE}/api/tunnel/status`, { timeoutMs: 5000 });
      setStatus(data);
      if (typeof window !== "undefined") {
        window.__DEBATE_TUNNEL_URL__ = data.running && data.url ? data.url : "";
        window.__DEBATE_UNIFIED_API__ = Boolean(data.running && data.url);
      }
    } catch (error) {
      reportError(
        {
          title: "公网隧道状态同步失败",
          message: error?.message || "无法连接后端",
          code: error?.code || error?.status,
          requestId: error?.requestId,
          details: error?.details || error?.stack || "",
          source: "usePublicTunnel.refresh",
        },
        { dedupeKey: "public-tunnel-refresh", throttleMs: 30000 },
      );
    }
  }, [reportError]);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, pollMs);
    return () => clearInterval(timer);
  }, [pollMs, refresh]);

  const verify = useCallback(async () => {
    try {
      const data = await fetchJson(`${API_BASE}/api/tunnel/verify`, { timeoutMs: 8000 });
      setStatus(data);
      if (typeof window !== "undefined") {
        window.__DEBATE_TUNNEL_URL__ = data.running && data.url ? data.url : "";
        window.__DEBATE_UNIFIED_API__ = Boolean(data.running && data.url);
      }
      return data;
    } catch (error) {
      reportError(
        {
          title: "公网隧道校验失败",
          message: error?.message || "无法校验公网隧道",
          code: error?.code || error?.status,
          requestId: error?.requestId,
          details: error?.details || error?.stack || "",
          source: "usePublicTunnel.verify",
        },
        { dedupeKey: "public-tunnel-verify", throttleMs: 30000 },
      );
      return null;
    }
  }, [reportError]);

  const start = useCallback(async ({ force = false } = {}) => {
    setBusy(true);
    try {
      const query = force ? "?force=true" : "";
      const data = await fetchJson(`${API_BASE}/api/tunnel/start${query}`, {
        method: "POST",
        timeoutMs: 35000,
      });
      setStatus(data);
      if (typeof window !== "undefined") {
        window.__DEBATE_TUNNEL_URL__ = data.running && data.url ? data.url : "";
        window.__DEBATE_UNIFIED_API__ = Boolean(data.running && data.url);
      }
      return data;
    } catch (error) {
      reportError(
        {
          title: "公网隧道启动失败",
          message: error?.message || "无法启动公网隧道",
          code: error?.code || error?.status,
          requestId: error?.requestId,
          details: error?.details || error?.stack || "",
          source: "usePublicTunnel.start",
        },
        { dedupeKey: `public-tunnel-start:${error?.message || ""}`, throttleMs: 10000 },
      );
      throw error;
    } finally {
      setBusy(false);
    }
  }, [reportError]);

  const stop = useCallback(async () => {
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/tunnel/stop`, { method: "POST" });
      if (!res.ok) throw parseHttpErrorBody(await res.text(), res);
      const data = await res.json();
      setStatus(data);
      if (typeof window !== "undefined") {
        window.__DEBATE_TUNNEL_URL__ = "";
        window.__DEBATE_UNIFIED_API__ = false;
      }
      return data;
    } catch (error) {
      reportError(
        {
          title: "公网隧道停止失败",
          message: error?.message || "无法停止公网隧道",
          details: error?.stack || "",
          source: "usePublicTunnel.stop",
        },
        { dedupeKey: `public-tunnel-stop:${error?.message || ""}`, throttleMs: 10000 },
      );
      throw error;
    } finally {
      setBusy(false);
    }
  }, [reportError]);

  return { status, busy, refresh, verify, start, stop };
}
