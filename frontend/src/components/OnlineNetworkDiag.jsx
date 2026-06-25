import { useCallback, useEffect, useState } from "react";
import { Activity, Loader2, Save, Shield } from "lucide-react";
import { useErrorDialog } from "./ErrorDialogProvider.jsx";
import { API_BASE, toWebSocketBase } from "../utils/apiBase.js";
import { errorDialogPayload, parseHttpErrorBody } from "../utils/httpError.js";

const PROXY_STORAGE_KEY = "debate-tunnel-proxy-draft";

export default function OnlineNetworkDiag() {
  const { reportError } = useErrorDialog();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [proxy, setProxy] = useState(() => {
    if (typeof window === "undefined") return "";
    return window.localStorage.getItem(PROXY_STORAGE_KEY) || "";
  });
  const [report, setReport] = useState(null);
  const [hint, setHint] = useState("");

  const loadProxy = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/tunnel/proxy`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.proxy) {
        setProxy(data.proxy);
        window.localStorage.setItem(PROXY_STORAGE_KEY, data.proxy);
      }
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (open) loadProxy();
  }, [loadProxy, open]);

  async function runDiagnose() {
    setBusy(true);
    setHint("");
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 10000);
      const res = await fetch(`${API_BASE}/api/tunnel/diagnose?quick=1`, {
        signal: controller.signal,
      });
      clearTimeout(timer);
      if (!res.ok) throw parseHttpErrorBody(await res.text(), res);
      setReport(await res.json());
    } catch (error) {
      const msg =
        error.name === "AbortError"
          ? "诊断超时（10 秒）。可先配置代理后再试，或改用局域网联机。"
          : error.message || "诊断失败，请确认程序已启动";
      setHint(msg);
      reportError({
        ...errorDialogPayload(error, "联机网络诊断失败", "OnlineNetworkDiag.run", msg),
        message: msg,
      });
    } finally {
      setBusy(false);
    }
  }

  async function saveProxy() {
    setSaving(true);
    setHint("");
    try {
      const value = proxy.trim() || null;
      const res = await fetch(`${API_BASE}/api/tunnel/proxy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proxy: value }),
      });
      if (!res.ok) throw parseHttpErrorBody(await res.text(), res);
      const data = await res.json();
      const saved = data.proxy || "";
      setProxy(saved);
      if (saved) window.localStorage.setItem(PROXY_STORAGE_KEY, saved);
      else window.localStorage.removeItem(PROXY_STORAGE_KEY);
      setHint(saved ? `已保存代理：${saved}。请重新点击「检测联机网络」或开启公网隧道。` : "已清除代理，将使用直连。");
      await runDiagnose();
    } catch (error) {
      setHint(error.message || "保存失败");
      reportError(errorDialogPayload(error, "保存代理失败", "OnlineNetworkDiag.saveProxy"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="online-network-diag">
      <button
        type="button"
        className="online-simple__secondary"
        onClick={() => setOpen((v) => !v)}
      >
        <Activity size={16} />
        {open ? "收起网络诊断" : "联机网络诊断与代理"}
      </button>

      {open && (
        <div className="online-network-diag__panel">
          <p className="online-simple__micro-hint">
            若公网出现 Cloudflare 1033，先运行项目根目录的 <strong>配置联机网络.bat</strong>（管理员），再配置代理并检测。
          </p>
          <ul className="online-network-diag__checks">
            <li className="is-ok">
              <strong>页面地址</strong>
              <span>{typeof window !== "undefined" ? window.location.origin : ""}</span>
            </li>
            <li className="is-ok">
              <strong>API 基址</strong>
              <span>{API_BASE}</span>
            </li>
            <li className="is-ok">
              <strong>WebSocket 基址</strong>
              <span>{toWebSocketBase(API_BASE)}</span>
            </li>
            {typeof window !== "undefined" && window.debateDesktop?.logDir && (
              <li className="is-ok">
                <strong>桌面日志目录</strong>
                <span>{window.debateDesktop.logDir}</span>
              </li>
            )}
          </ul>

          <div className="online-network-diag__proxy">
            <label>
              HTTP 代理（可选，如 Clash/V2Ray 本地端口）
              <input
                value={proxy}
                onChange={(e) => setProxy(e.target.value)}
                placeholder="http://127.0.0.1:7890"
              />
            </label>
            <button type="button" className="online-simple__secondary compact" disabled={saving} onClick={saveProxy}>
              {saving ? <Loader2 size={14} className="spin" /> : <Save size={14} />}
              保存代理
            </button>
          </div>

          <div className="online-network-diag__actions">
            <button type="button" className="online-simple__secondary compact" disabled={busy} onClick={runDiagnose}>
              {busy ? <Loader2 size={14} className="spin" /> : <Shield size={14} />}
              检测联机网络
            </button>
          </div>

          {hint && <p className="online-simple__hint">{hint}</p>}

          {report?.checks && (
            <ul className="online-network-diag__checks">
              {report.checks.map((item) => (
                <li key={item.name} className={item.ok ? "is-ok" : "is-fail"}>
                  <strong>{item.name}</strong>
                  <span>{item.detail}</span>
                  {!item.ok && item.fix && <em>{item.fix}</em>}
                </li>
              ))}
            </ul>
          )}

          {report?.suggestions?.length > 0 && (
            <div className="online-network-diag__tips">
              <strong>建议</strong>
              <ul>
                {report.suggestions.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
          )}

          {report?.log_tail && (
            <details className="online-network-diag__log">
              <summary>隧道最近日志</summary>
              <pre>{report.log_tail}</pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
