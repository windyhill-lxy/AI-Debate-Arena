import { useEffect, useState } from "react";
import { Copy, Globe, Loader2, Power, PowerOff } from "lucide-react";
import { usePublicTunnel } from "../hooks/usePublicTunnel.js";

export default function PublicTunnelPanel({ compact = false }) {
  const { status, busy, start, stop } = usePublicTunnel();
  const [copied, setCopied] = useState("");

  async function copyText(label, text) {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(label);
      setTimeout(() => setCopied(""), 2000);
    } catch {
      setCopied("");
    }
  }

  const joinBase = status.url || "";
  const joinExample = joinBase ? `${joinBase.replace(/\/$/, "")}/join/房间ID` : "";

  return (
    <section className={`tunnel-panel ${compact ? "tunnel-panel--compact" : ""}`} aria-label="公网联机（内网穿透）">
      <div className="tunnel-panel__head">
        <Globe size={20} />
        <div>
          <h2 className="home-section-title">公网联机（内网穿透）</h2>
          <p className="home-hint">
            通过 Cloudflare 临时隧道，让不在同一 Wi‑Fi 的同学也能加入。首次启动会自动下载 cloudflared（约 30MB）。
          </p>
        </div>
      </div>

      <div className="tunnel-panel__actions">
        {!status.running ? (
          <button type="button" className="home-file-btn" disabled={busy} onClick={() => start()}>
            {busy ? <Loader2 size={16} className="spin" /> : <Power size={16} />}
            {busy ? "正在建立隧道…" : "开启公网穿透"}
          </button>
        ) : (
          <button type="button" className="home-file-btn secondary" disabled={busy} onClick={() => stop()}>
            {busy ? <Loader2 size={16} className="spin" /> : <PowerOff size={16} />}
            关闭公网穿透
          </button>
        )}
      </div>

      {status.running && status.url && (
        <div className="tunnel-panel__url">
          <p className="home-hint">公网访问地址（发给远程同学）：</p>
          <code>{status.url}</code>
          <div className="tunnel-panel__copy-row">
            <button type="button" className="home-file-btn compact" onClick={() => copyText("url", status.url)}>
              <Copy size={14} />
              {copied === "url" ? "已复制" : "复制公网地址"}
            </button>
            {joinExample && (
              <button type="button" className="home-file-btn compact" onClick={() => copyText("join", joinExample)}>
                <Copy size={14} />
                {copied === "join" ? "已复制" : "复制加入链接示例"}
              </button>
            )}
          </div>
        </div>
      )}

      {status.error && <p className="tunnel-panel__error">{status.error}</p>}

      <ol className="tunnel-panel__steps">
        <li>点击「开启公网穿透」，等待出现 https://…trycloudflare.com 地址</li>
        <li>在本机创建联机房间，进入房间后复制「加入链接」发给同学</li>
        <li>同学用浏览器打开链接（无需在同一局域网）</li>
        <li>临时隧道在关闭程序或点击「关闭公网穿透」后失效，需重新分享新地址</li>
      </ol>
    </section>
  );
}
