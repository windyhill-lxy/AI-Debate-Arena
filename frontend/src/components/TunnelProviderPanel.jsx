import { useCallback, useEffect, useState } from "react";
import { KeyRound, Loader2, Save } from "lucide-react";
import { useErrorDialog } from "./ErrorDialogProvider.jsx";
import { API_BASE } from "../utils/apiBase.js";
import { errorDialogPayload, parseHttpErrorBody } from "../utils/httpError.js";

const TOKEN_STORAGE_KEY = "debate-ngrok-token-draft";

export default function TunnelProviderPanel({ onChanged }) {
  const { reportError } = useErrorDialog();
  const [providers, setProviders] = useState(null);
  const [provider, setProvider] = useState("auto");
  const [token, setToken] = useState(() => {
    if (typeof window === "undefined") return "";
    return window.localStorage.getItem(TOKEN_STORAGE_KEY) || "";
  });
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/tunnel/providers`);
      if (!res.ok) return;
      const data = await res.json();
      setProviders(data);
      setProvider(data.current || "auto");
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function saveProvider(next) {
    setBusy(true);
    setHint("");
    try {
      const res = await fetch(`${API_BASE}/api/tunnel/provider`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: next }),
      });
      if (!res.ok) throw parseHttpErrorBody(await res.text(), res);
      const data = await res.json();
      setProviders(data);
      setProvider(data.current || next);
      setHint("隧道方式已保存。推荐使用 ngrok。");
      onChanged?.();
    } catch (error) {
      setHint(error.message || "保存失败");
      reportError(errorDialogPayload(error, "保存隧道方式失败", "TunnelProviderPanel.saveProvider"));
    } finally {
      setBusy(false);
    }
  }

  async function saveToken() {
    setBusy(true);
    setHint("");
    try {
      const value = token.trim() || null;
      const res = await fetch(`${API_BASE}/api/tunnel/ngrok-token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ authtoken: value }),
      });
      if (!res.ok) throw parseHttpErrorBody(await res.text(), res);
      const data = await res.json();
      setProviders(data);
      if (value) window.localStorage.setItem(TOKEN_STORAGE_KEY, value);
      else window.localStorage.removeItem(TOKEN_STORAGE_KEY);
      setHint(value ? "ngrok Token 已保存。请重新复制公网链接。" : "已清除 ngrok Token。");
      onChanged?.();
    } catch (error) {
      setHint(error.message || "保存 Token 失败");
      reportError(errorDialogPayload(error, "保存 ngrok Token 失败", "TunnelProviderPanel.saveToken"));
    } finally {
      setBusy(false);
    }
  }

  const ngrokReady = providers?.ngrok_configured;

  return (
    <div className="tunnel-provider">
      <p className="online-simple__micro-hint">
        Cloudflare 临时链接易断开。推荐使用 <strong>ngrok</strong>（免费注册，连接更稳定）。
      </p>
      <label>
        公网隧道方式
        <select
          value={provider}
          disabled={busy}
          onChange={(e) => {
            const next = e.target.value;
            setProvider(next);
            saveProvider(next);
          }}
        >
          <option value="auto">自动（有 ngrok Token 优先用 ngrok）</option>
          <option value="ngrok">ngrok（推荐）</option>
          <option value="cloudflare">Cloudflare 临时（不稳定）</option>
        </select>
      </label>
      <div className="tunnel-provider__token">
        <label>
          ngrok Authtoken（免费）
          <input
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="在 ngrok 控制台复制，粘贴后保存"
            type="password"
            autoComplete="off"
          />
        </label>
        <button type="button" className="online-simple__secondary compact" disabled={busy} onClick={saveToken}>
          {busy ? <Loader2 size={14} className="spin" /> : <Save size={14} />}
          保存 Token
        </button>
      </div>
      <p className="online-simple__micro-hint">
        <KeyRound size={12} style={{ display: "inline", verticalAlign: "middle" }} />{" "}
        注册获取 Token：
        <a href="https://dashboard.ngrok.com/get-started/your-authtoken" target="_blank" rel="noreferrer">
          dashboard.ngrok.com/get-started/your-authtoken
        </a>
        {ngrokReady ? "（已配置）" : "（未配置时将回退到 Cloudflare）"}
      </p>
      {hint && <p className="online-simple__hint">{hint}</p>}
    </div>
  );
}
