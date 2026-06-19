import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import CopyShareLinkButton from "../components/CopyShareLinkButton.jsx";
import {
  Activity,
  ArrowLeft,
  BarChart2,
  ExternalLink,
  Pause,
  Play,
  QrCode,
  RefreshCw,
  RotateCcw,
  Save,
  Server,
  Settings2,
} from "lucide-react";
import RuntimeSettingsPanel from "../components/RuntimeSettingsPanel.jsx";
import SystemConfigBanner from "../components/debate/SystemConfigBanner.jsx";
import { useDebateHealth } from "../hooks/useDebateHealth.js";
import { API_BASE } from "../utils/apiBase.js";
import "../styles/admin.css";

async function adminFetch(path, options) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function StatusPill({ ok, label }) {
  return <span className={`admin-pill ${ok ? "ok" : "warn"}`}>{label}</span>;
}

const PHASE_LABELS = {
  opening_prep: "立论准备", opening_statement: "开篇立论", argument_review: "论点强度判断",
  rebuttal: "驳论", rebuttal_review: "驳论有效性", cross_examination: "盘问/质询",
  segment_summary: "攻辩小结", free_prep: "自由辩论准备", free_debate: "自由辩论",
  free_review: "自由辩论复盘", closing_prep: "总结准备", closing: "总结陈词",
  closing_review: "总结质量判断", pre_match: "赛前主持", post_match: "赛后裁决",
};

function PromptEditor() {
  const [phases, setPhases] = useState([]);
  const [selectedPhase, setSelectedPhase] = useState("free_debate");
  const [hintText, setHintText] = useState("");
  const [isCustom, setIsCustom] = useState(false);
  const [msg, setMsg] = useState("");
  const [saving, setSaving] = useState(false);

  const loadPrompts = useCallback(async () => {
    try {
      const data = await adminFetch("/api/admin/prompts");
      setPhases(data.phases || []);
      const cur = (data.phases || []).find((p) => p.phase === selectedPhase);
      if (cur) {
        const draft = window.localStorage.getItem(`promptDraft_${selectedPhase}`);
        setHintText(draft ?? cur.hint);
        setIsCustom(cur.is_custom);
      }
    } catch (e) {
      setMsg(`加载失败: ${e.message}`);
    }
  }, [selectedPhase]);

  useEffect(() => { loadPrompts(); }, [loadPrompts]);

  function selectPhase(phase) {
    setSelectedPhase(phase);
    const cur = phases.find((p) => p.phase === phase);
    if (cur) {
      const draft = window.localStorage.getItem(`promptDraft_${phase}`);
      setHintText(draft ?? cur.hint);
      setIsCustom(cur.is_custom);
    }
  }

  function onHintChange(val) {
    setHintText(val);
    window.localStorage.setItem(`promptDraft_${selectedPhase}`, val);
  }

  async function savePrompt() {
    setSaving(true); setMsg("");
    try {
      await adminFetch("/api/admin/prompts", {
        method: "PUT",
        body: JSON.stringify({ phase: selectedPhase, hint: hintText }),
      });
      window.localStorage.removeItem(`promptDraft_${selectedPhase}`);
      setMsg("已保存"); setIsCustom(true);
      await loadPrompts();
    } catch (e) { setMsg(`保存失败: ${e.message}`); }
    setSaving(false);
  }

  async function resetPrompt() {
    if (!window.confirm(`确定要重置"${PHASE_LABELS[selectedPhase] || selectedPhase}"到默认提示词吗？`)) return;
    try {
      await adminFetch(`/api/admin/prompts/${selectedPhase}`, { method: "DELETE" });
      window.localStorage.removeItem(`promptDraft_${selectedPhase}`);
      setMsg("已重置为默认"); setIsCustom(false);
      await loadPrompts();
    } catch (e) { setMsg(`重置失败: ${e.message}`); }
  }

  return (
    <section className="admin-panel admin-prompt-editor">
      <h2><Settings2 size={18} /> AI 提示词编辑</h2>
      <p className="admin-lead" style={{ fontSize: 13, marginBottom: 12 }}>
        修改各阶段 AI 发言指令，保存后立即生效（不影响已运行房间的当前发言）。
      </p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        {Object.entries(PHASE_LABELS).map(([phase, label]) => {
          const info = phases.find((p) => p.phase === phase);
          return (
            <button
              key={phase}
              type="button"
              className={`admin-phase-btn ${selectedPhase === phase ? "active" : ""} ${info?.is_custom ? "custom" : ""}`}
              onClick={() => selectPhase(phase)}
              title={info?.is_custom ? "已自定义" : "使用默认"}
            >
              {label}{info?.is_custom ? " ✎" : ""}
            </button>
          );
        })}
      </div>
      <label style={{ fontSize: 13, fontWeight: 600 }}>
        {PHASE_LABELS[selectedPhase] || selectedPhase}
        {isCustom && <span style={{ color: "#e67e22", marginLeft: 8 }}>（已自定义）</span>}
      </label>
      <textarea
        value={hintText}
        onChange={(e) => onHintChange(e.target.value)}
        rows={6}
        style={{ width: "100%", marginTop: 6, padding: 10, borderRadius: 8, fontSize: 13, fontFamily: "monospace", resize: "vertical", border: "1px solid #ddd" }}
        placeholder="输入该阶段的 AI 提示词…"
      />
      {msg && <p style={{ fontSize: 13, color: msg.includes("失败") ? "#c00" : "#2a7", marginTop: 4 }}>{msg}</p>}
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <button type="button" className="admin-btn" onClick={savePrompt} disabled={saving}>
          <Save size={14} /> {saving ? "保存中…" : "保存"}
        </button>
        {isCustom && (
          <button type="button" className="admin-btn secondary" onClick={resetPrompt}>
            <RotateCcw size={14} /> 重置为默认
          </button>
        )}
      </div>
    </section>
  );
}

function QrCodeCard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  async function load() {
    setLoading(true); setErr("");
    try {
      const port = window.location.port || "5173";
      const res = await adminFetch(`/api/admin/qrcode?frontend_port=${port}`);
      setData(res);
    } catch (e) {
      setErr(e.message);
    }
    setLoading(false);
  }

  return (
    <section className="admin-panel" style={{ marginTop: 24 }}>
      <h2><QrCode size={18} /> 手机扫码访问（局域网）</h2>
      <p className="admin-lead" style={{ fontSize: 13, marginBottom: 12 }}>
        在同一局域网内，用手机扫描二维码即可访问辩论系统。
      </p>
      {!data && !loading && (
        <button type="button" className="admin-btn" onClick={load}>生成二维码</button>
      )}
      {loading && <p style={{ fontSize: 13 }}>生成中…</p>}
      {err && <p style={{ fontSize: 13, color: "#c00" }}>{err}</p>}
      {data && (
        <div style={{ display: "flex", gap: 20, alignItems: "flex-start", flexWrap: "wrap" }}>
          <div className="admin-qr-card">
            <img src={`data:image/png;base64,${data.qrcode_b64}`} alt="QR码" />
            <p>扫码访问局域网辩论系统</p>
            <a href={data.url} target="_blank" rel="noreferrer" style={{ fontSize: 12, color: "#334a8a" }}>{data.url}</a>
          </div>
          <div style={{ fontSize: 13, color: "#6b5a48", marginTop: 8 }}>
            <p>局域网 IP：<code>{data.lan_ip}</code></p>
            <p>确保设备与本机在同一 WiFi 网络下。</p>
            <button type="button" className="admin-btn secondary" style={{ marginTop: 8 }} onClick={load}>刷新二维码</button>
          </div>
        </div>
      )}
    </section>
  );
}

function UsageStats() {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    adminFetch("/api/admin/usage-log")
      .then((d) => { setLogs(d.recent || []); setTotal(d.total || 0); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const modeLabel = (m) => ({ ai_autonomous: "全AI", user_affirmative: "加入正方", user_negative: "加入反方", online_match: "联机" }[m] || m);

  return (
    <section className="admin-panel" style={{ marginTop: 24 }}>
      <h2><BarChart2 size={18} /> 使用记录</h2>
      {loading && <p style={{ fontSize: 13 }}>加载中…</p>}
      {!loading && (
        <>
          <p style={{ fontSize: 13, color: "#6b5a48", margin: "0 0 8px" }}>
            累计运行 <strong>{total}</strong> 场辩论
          </p>
          {logs.length === 0 && <p className="admin-empty">暂无使用记录，运行一场辩论后自动记录。</p>}
          <div className="usage-log-list">
            {logs.map((row, i) => (
              <div key={i} className="usage-log-row">
                <time>{row.ts ? new Date(row.ts).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "-"}</time>
                <span className="usage-topic" title={row.topic}>{row.topic || "-"}</span>
                <span className="usage-mode">{modeLabel(row.mode)}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

export default function Admin() {
  const { health, error: healthError } = useDebateHealth();
  const [overview, setOverview] = useState(null);
  const [items, setItems] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [actionMsg, setActionMsg] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setActionMsg("");
    try {
      const [ov, list] = await Promise.all([
        adminFetch("/api/admin/overview"),
        adminFetch("/api/admin/debates?limit=40"),
      ]);
      setOverview(ov);
      setItems(list.items || []);
      if (selectedId) {
        const d = await adminFetch(`/api/admin/debates/${selectedId}`);
        setDetail(d);
      }
    } catch (e) {
      setActionMsg(`加载失败：${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    load();
  }, [load]);

  const selectDebate = async (id) => {
    setSelectedId(id);
    try {
      const d = await adminFetch(`/api/admin/debates/${id}`);
      setDetail(d);
    } catch (e) {
      setActionMsg(`详情加载失败：${e.message}`);
    }
  };

  const runControl = async (id, action) => {
    try {
      await adminFetch(`/api/admin/debates/${id}/${action}`, { method: "POST" });
      setActionMsg(action === "stop-auto" ? "已停止自动推进" : "已请求恢复推进");
      await load();
      if (selectedId === id) await selectDebate(id);
    } catch (e) {
      setActionMsg(`操作失败：${e.message}`);
    }
  };

  const counts = overview?.debate_counts || {};

  return (
    <div className="admin-page">
      <header className="admin-header">
        <Link to="/" className="admin-back">
          <ArrowLeft size={16} /> 返回首页
        </Link>
        <div>
          <p className="admin-eyebrow">Operations</p>
          <h1>
            <Server size={28} /> 辩论场管理
          </h1>
          <p className="admin-lead">查看房间状态、诊断卡住的任务，并手动停止/恢复自动推进。</p>
        </div>
        <button type="button" className="admin-refresh" onClick={load} disabled={loading}>
          <RefreshCw size={16} className={loading ? "spin" : ""} /> 刷新
        </button>
      </header>

      <SystemConfigBanner health={health} healthError={healthError} />

      <RuntimeSettingsPanel />

      {actionMsg && <p className="admin-action-msg">{actionMsg}</p>}

      {overview && (
        <section className="admin-overview">
          <div className="admin-stat-card">
            <span>存储</span>
            <strong>{overview.storage}</strong>
            <StatusPill ok={overview.mongo_connected} label={overview.mongo_connected ? "Mongo 已连" : "内存模式"} />
          </div>
          <div className="admin-stat-card">
            <span>房间总数</span>
            <strong>{counts.total ?? 0}</strong>
            <em>进行中 {counts.in_progress ?? 0} · 已结束 {counts.finished ?? 0}</em>
          </div>
          <div className="admin-stat-card">
            <span>自动推进</span>
            <strong>{counts.auto_running ?? 0}</strong>
            <em>等待用户 {counts.awaiting_user ?? 0}</em>
          </div>
          <div className="admin-stat-card">
            <span>内存任务</span>
            <strong>{Object.keys(overview.active_runners || {}).length}</strong>
            <StatusPill ok={overview.deepseek_configured} label={overview.deepseek_configured ? "LLM 已配置" : "LLM 未配置"} />
          </div>
        </section>
      )}
      {overview?.ops_events?.length > 0 && (
        <section className="admin-panel">
          <h2>运行事件（最近）</h2>
          <ul className="admin-diag-list">
            {overview.ops_events.slice(-8).reverse().map((evt, idx) => (
              <li key={`${evt.ts || idx}-${idx}`}>
                [{evt.event_type || "event"}] {evt.message}
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="admin-grid">
        <section className="admin-panel">
          <h2>
            <Activity size={18} /> 房间列表
          </h2>
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>辩题</th>
                  <th>模式</th>
                  <th>环节</th>
                  <th>消息</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {items.length === 0 && (
                  <tr>
                    <td colSpan={6} className="admin-empty">
                      暂无房间，请先在首页创建辩论。
                    </td>
                  </tr>
                )}
                {items.map((row) => (
                  <tr
                    key={row.id}
                    className={selectedId === row.id ? "selected" : ""}
                    onClick={() => selectDebate(row.id)}
                  >
                    <td title={row.topic}>{row.topic?.slice(0, 28) || row.id}</td>
                    <td>{row.mode}</td>
                    <td title={row.segment_label}>{row.segment_label?.slice(0, 16) || row.phase}</td>
                    <td>{row.message_count}</td>
                    <td>
                      {row.auto_running && <span className="tag tag-run">推进中</span>}
                      {row.awaiting_user && <span className="tag tag-wait">等用户</span>}
                      {row.phase === "finished" && <span className="tag tag-done">已结束</span>}
                      {detail?.diagnostics?.stale_auto_flag && selectedId === row.id && (
                        <span className="tag tag-warn">可能卡住</span>
                      )}
                    </td>
                    <td className="admin-row-actions" onClick={(e) => e.stopPropagation()}>
                      <Link to={`/room/${row.id}`} title="进入辩论室">
                        <ExternalLink size={14} />
                      </Link>
                      <button type="button" title="停止" onClick={() => runControl(row.id, "stop-auto")}>
                        <Pause size={14} />
                      </button>
                      <button type="button" title="恢复" onClick={() => runControl(row.id, "resume-auto")}>
                        <Play size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="admin-panel admin-detail">
          <h2>房间诊断</h2>
          {!detail && <p className="admin-empty">点击左侧一行查看 LLM 统计与诊断信息。</p>}
          {detail && (
            <>
              <p className="admin-detail-topic">{detail.summary?.topic}</p>
              <p className="admin-detail-meta">
                ID: <code>{detail.summary?.id}</code>
              </p>
              <ul className="admin-diag-list">
                <li>
                  Runner 存活：
                  {detail.diagnostics?.runner_alive ? "是" : "否"}
                </li>
                <li>
                  auto_running 悬空：
                  {detail.diagnostics?.stale_auto_flag ? "是（建议点恢复或停止）" : "否"}
                </li>
                <li>LLM 调用：{detail.llm_stats?.total_calls ?? 0} 次</li>
                <li>
                  Token：{detail.llm_stats?.prompt_tokens ?? 0} + {detail.llm_stats?.completion_tokens ?? 0}
                </li>
                <li>失败：{detail.llm_stats?.failed_calls ?? 0}</li>
              </ul>
              {detail.last_message_preview && (
                <blockquote className="admin-preview">{detail.last_message_preview}</blockquote>
              )}
              <div className="admin-detail-actions">
                <Link to={`/room/${detail.summary?.id}`} className="admin-btn">
                  进入辩论室
                </Link>
                <Link to={`/replay/${detail.summary?.id}`} className="admin-btn secondary">
                  回放
                </Link>
                <Link to={`/share/${detail.summary?.id}`} className="admin-btn secondary" target="_blank" rel="noreferrer">
                  只读分享页
                </Link>
                <CopyShareLinkButton debateId={detail.summary?.id} className="admin-btn secondary" />
              </div>
            </>
          )}
        </section>
      </div>

      <PromptEditor />
      <QrCodeCard />
      <UsageStats />
    </div>
  );
}
