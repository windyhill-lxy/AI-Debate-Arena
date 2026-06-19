import { useCallback, useEffect, useState } from "react";
import { API_BASE } from "../utils/apiBase.js";

const FETCH_TIMEOUT_MS = 30000;

async function fetchJson(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? FETCH_TIMEOUT_MS);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    if (!res.ok) throw new Error(await res.text());
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

  const refresh = useCallback(async () => {
    try {
      const data = await fetchJson(`${API_BASE}/api/tunnel/status`, { timeoutMs: 5000 });
      setStatus(data);
      if (typeof window !== "undefined") {
        window.__DEBATE_TUNNEL_URL__ = data.running && data.url ? data.url : "";
        window.__DEBATE_UNIFIED_API__ = Boolean(data.running && data.url);
      }
    } catch {
      /* backend offline */
    }
  }, []);

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
    } catch {
      return null;
    }
  }, []);

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
    } finally {
      setBusy(false);
    }
  }, []);

  const stop = useCallback(async () => {
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/tunnel/stop`, { method: "POST" });
      const data = await res.json();
      setStatus(data);
      if (typeof window !== "undefined") {
        window.__DEBATE_TUNNEL_URL__ = "";
        window.__DEBATE_UNIFIED_API__ = false;
      }
      return data;
    } finally {
      setBusy(false);
    }
  }, []);

  return { status, busy, refresh, verify, start, stop };
}
