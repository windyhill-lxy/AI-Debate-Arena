import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Copy, Globe, Link2, Loader2, Network, PlusCircle, Users, Wifi } from "lucide-react";
import { usePublicTunnel } from "../hooks/usePublicTunnel.js";
import { API_BASE, isTunnelHost } from "../utils/apiBase.js";
import OnlineNetworkDiag from "./OnlineNetworkDiag.jsx";
import TunnelProviderPanel from "./TunnelProviderPanel.jsx";
import {
  buildSessionInviteLink,
  inviteStatusLabel,
  isLoopbackHost,
  parseJoinTarget,
  resolveInviteBase,
} from "../utils/onlineInvite.js";
import { saveHostToken } from "../utils/hostToken.js";

function RoomRules({
  visibilityMode,
  setVisibilityMode,
  timingMode,
  setTimingMode,
  ttsEnabled,
  setTtsEnabled,
}) {
  return (
    <div className="online-simple__rules">
      <p className="online-simple__micro-hint">赛前规则会在房间开启后锁定。</p>
      <div className="segmented">
        <button
          type="button"
          className={visibilityMode === "all_visible" ? "active" : ""}
          onClick={() => setVisibilityMode("all_visible")}
        >
          全部可见
        </button>
        <button
          type="button"
          className={visibilityMode === "own_side_only" ? "active" : ""}
          onClick={() => setVisibilityMode("own_side_only")}
        >
          仅己方内容可见
        </button>
      </div>
      <div className="segmented">
        <button
          type="button"
          className={timingMode === "limited" ? "active" : ""}
          onClick={() => setTimingMode("limited")}
        >
          加入计时
        </button>
        <button
          type="button"
          className={timingMode === "unlimited" ? "active" : ""}
          onClick={() => setTimingMode("unlimited")}
        >
          不计时
        </button>
      </div>
      <label className="home-confidence__toggle">
        <input type="checkbox" checked={ttsEnabled} onChange={(event) => setTtsEnabled(event.target.checked)} />
        <span>启用 TTS 语音朗读</span>
      </label>
    </div>
  );
}

function TopicMaterialFields({ topic, onTopicChange, materialTitle, setMaterialTitle, materialText, setMaterialText }) {
  return (
    <div className="online-simple__step-fields">
      <textarea
        className="online-simple__topic"
        rows={2}
        value={topic}
        onChange={(e) => onTopicChange(e.target.value)}
        placeholder="输入辩题"
      />
      <input
        className="online-simple__topic"
        value={materialTitle}
        onChange={(e) => setMaterialTitle(e.target.value)}
        placeholder="资料标题"
      />
      <textarea
        className="online-simple__topic"
        rows={3}
        value={materialText}
        onChange={(e) => setMaterialText(e.target.value)}
        placeholder="辩题参考资料，可选"
      />
    </div>
  );
}

export default function OnlineSimplePanel({
  variant = "standalone",
  debateId = "",
  topic: topicProp,
  onTopicChange,
  rooms = [],
  onCreateStart,
  onCreateEnd,
}) {
  const navigate = useNavigate();
  const { status, busy, start, stop, refresh, verify } = usePublicTunnel();
  const [joinInput, setJoinInput] = useState("");
  const [topic, setTopic] = useState(
    topicProp || "人工智能是否会提升青少年的综合学习能力",
  );
  const [materialText, setMaterialText] = useState("");
  const [materialTitle, setMaterialTitle] = useState("辩题参考资料");
  const [visibilityMode, setVisibilityMode] = useState("own_side_only");
  const [timingMode, setTimingMode] = useState("limited");
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [creating, setCreating] = useState(false);
  const [copying, setCopying] = useState(false);
  const [hint, setHint] = useState("");
  const [copied, setCopied] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [publicReady, setPublicReady] = useState(false);
  const [lastInviteLink, setLastInviteLink] = useState("");

  const hostname = typeof window !== "undefined" ? window.location.hostname : "";
  const statusLabel = inviteStatusLabel(status.running, hostname);
  const effectiveTopic = topicProp ?? topic;
  const onLan = !isLoopbackHost(hostname) && !isTunnelHost(hostname);

  function handleTopicChange(value) {
    if (onTopicChange) onTopicChange(value);
    else setTopic(value);
  }

  function goJoin(raw) {
    const target = parseJoinTarget(raw);
    if (!target?.id) return;
    if (target.kind === "session") navigate(`/join/session/${encodeURIComponent(target.id)}`);
    else navigate(`/join/${encodeURIComponent(target.id)}`);
  }

  async function ensureSession() {
    if (sessionId) return sessionId;
    const response = await fetch(`${API_BASE}/api/debates/online-session`, { method: "POST" });
    if (!response.ok) throw new Error(await response.text());
    const data = await response.json();
    setSessionId(data.session_id);
    return data.session_id;
  }

  async function preparePublicLink() {
    setCopying(true);
    setHint("");
    try {
      const sid = await ensureSession();
      let tunnelState = status;
      if (!tunnelState?.running || !tunnelState?.url) {
        tunnelState = await start({ force: false });
      }
      if (!tunnelState?.url || !tunnelState?.running) {
        tunnelState = await start({ force: true });
      }
      if (!tunnelState?.url || !tunnelState?.running) {
        throw new Error(
          tunnelState?.error ||
            "公网隧道不可用。请先配置 ngrok Token 并保持程序窗口开启；否则请改用局域网联机。",
        );
      }
      const link = buildSessionInviteLink(sid, tunnelState.url);
      if (!link) throw new Error("无法生成公网邀请链接");
      if (!link.includes("/join/session/")) {
        throw new Error("邀请链接格式异常，请重试");
      }
      await navigator.clipboard.writeText(link);
      setLastInviteLink(link);
      setPublicReady(true);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      const via = tunnelState.provider === "ngrok" ? "ngrok" : "公网隧道";
      setHint(
        `已复制完整邀请链接（${via}）。请把含 /join/session/ 的整段链接发给同学，不要只发 ngrok 域名。请保持程序窗口开着。`,
      );
    } catch (error) {
      setHint(error.message || "公网邀请准备失败");
    } finally {
      setCopying(false);
    }
  }

  async function createRoom(network) {
    if (!effectiveTopic.trim()) return;
    setCreating(true);
    setHint("");
    onCreateStart?.();
    try {
      let sid = sessionId;
      if (network === "public" && !sid) {
        sid = await ensureSession();
      }
      const materials = materialText.trim()
        ? [{ title: materialTitle, content: materialText }]
        : [];
      const response = await fetch(`${API_BASE}/api/debates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: effectiveTopic.trim(),
          mode: "online_match",
          visibility: visibilityMode,
          timing: timingMode,
          tts_enabled: ttsEnabled,
          human_timeout_penalty_enabled: timingMode === "limited",
          format: "formal",
          schedule_template: "formal_4v4",
          materials,
          session_id: network === "public" ? sid : null,
        }),
      });
      if (!response.ok) throw new Error(await response.text());
      const debate = await response.json();
      if (debate.host_token) saveHostToken(debate.id, debate.host_token);
      navigate(`/join/${encodeURIComponent(debate.id)}`, {
        state: { topic: debate.topic, fromCreate: true, materials },
      });
    } catch (error) {
      setHint(error.message || "创建失败，请确认程序已启动");
    } finally {
      setCreating(false);
      onCreateEnd?.();
    }
  }

  async function copyInviteLink() {
    setCopying(true);
    setHint("");
    try {
      let tunnelUrl = status.url || "";
      if (isLoopbackHost(hostname) && !tunnelUrl) {
        const data = await start();
        tunnelUrl = data?.url || "";
      }
      const base =
        resolveInviteBase(tunnelUrl) ||
        (isLoopbackHost(hostname) ? "" : window.location.origin);
      const finalLink = sessionId
        ? buildSessionInviteLink(sessionId, tunnelUrl)
        : debateId
          ? `${base.replace(/\/$/, "")}/join/${debateId}`
          : base;
      if (!finalLink) {
        setHint("暂时无法生成可分享链接，请先开启公网隧道或使用局域网地址");
        return;
      }
      await navigator.clipboard.writeText(finalLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setHint("复制失败，请检查浏览器权限");
    } finally {
      setCopying(false);
    }
  }

  const showCreate = variant === "lobby" || variant === "standalone";
  const showRoomList = variant === "lobby" && rooms.length > 0;

  return (
    <section className="online-simple" aria-label="联机">
      <div className="online-simple__head">
        <Users size={22} />
        <div>
          <h2 className="online-simple__title">联机对战</h2>
          <p className="online-simple__subtitle">
            选一种连接方式，创建房间后发链接。
            <span
              className={`online-simple__badge online-simple__badge--${status.running ? "remote" : onLan ? "lan" : "local"}`}
            >
              {statusLabel}
            </span>
          </p>
        </div>
      </div>

      {variant === "room" && debateId && (
        <div className="online-simple__host-actions">
          <button
            type="button"
            className="online-simple__primary"
            disabled={copying || busy}
            onClick={copyInviteLink}
          >
            {copying || busy ? <Loader2 size={18} className="spin" /> : <Copy size={18} />}
            {copied ? "已复制邀请链接" : copying ? "正在准备链接…" : "复制邀请链接，发给同学"}
          </button>
          <p className="online-simple__micro-hint">同学打开链接后，将看到辩题资料、选席位与摄像头调试流程。</p>
        </div>
      )}

      {showCreate && variant !== "room" && (
        <>
          <div className="online-simple__section online-simple__section--lan">
            <div className="online-simple__section-head">
              <Wifi size={18} />
              <div>
                <h3>局域网联机</h3>
                <p>同一 Wi‑Fi 或教室网络内使用，延迟低、无需公网。</p>
              </div>
            </div>
            <div className="online-steps">
              <span>1 同一 Wi-Fi</span>
              <span>2 填辩题</span>
              <span>3 创建并发链接</span>
            </div>
            {onLan && (
              <p className="online-simple__micro-hint">
                当前局域网地址：<code>{typeof window !== "undefined" ? window.location.origin : ""}</code>
              </p>
            )}
            {!onLan && (
              <p className="online-simple__micro-hint">
                你正在本机访问（localhost）。如需局域网联机，请用局域网 IP 打开本页面。
              </p>
            )}
            {variant === "lobby" && (
              <>
                <TopicMaterialFields
                  topic={effectiveTopic}
                  onTopicChange={handleTopicChange}
                  materialTitle={materialTitle}
                  setMaterialTitle={setMaterialTitle}
                  materialText={materialText}
                  setMaterialText={setMaterialText}
                />
                <RoomRules
                  visibilityMode={visibilityMode}
                  setVisibilityMode={setVisibilityMode}
                  timingMode={timingMode}
                  setTimingMode={setTimingMode}
                  ttsEnabled={ttsEnabled}
                  setTtsEnabled={setTtsEnabled}
                />
              </>
            )}
            <button
              type="button"
              className="online-simple__primary"
              disabled={creating || !effectiveTopic.trim()}
              onClick={() => (variant === "lobby" ? createRoom("lan") : navigate("/lobby"))}
            >
              {creating ? <Loader2 size={18} className="spin" /> : <PlusCircle size={18} />}
              {creating ? "创建中…" : variant === "lobby" ? "创建局域网房间" : "进入联机大厅"}
            </button>
          </div>

          <div className="online-simple__section online-simple__section--radmin">
            <div className="online-simple__section-head">
              <Network size={18} />
              <div>
                <h3>Radmin LAN</h3>
                <p>不在同一 Wi-Fi 时，用虚拟局域网连接。</p>
              </div>
            </div>
            <ol className="online-radmin-guide">
              <li>房主和同学都安装 Radmin VPN，并打开软件。</li>
              <li>房主点击“网络”，选择“创建网络”，填写网络名和密码。</li>
              <li>同学点击“网络”，选择“加入网络”，输入房主给的网络名和密码。</li>
              <li>所有人进入同一个房间后，房主在 Radmin 主界面复制自己的 26.x.x.x 地址。</li>
              <li>房主运行本项目的“局域网启动”或 start-lan.bat，并用浏览器打开 <code>http://房主26IP:5173/lobby</code>。</li>
              <li>房主在这里创建 Radmin 房间，再把生成的邀请链接发给同学。</li>
              <li>同学打不开时，先确认 Radmin 里双方在线，再检查防火墙是否允许 Node 和 Python 通过专用网络。</li>
            </ol>
            {variant === "lobby" && (
              <>
                <TopicMaterialFields
                  topic={effectiveTopic}
                  onTopicChange={handleTopicChange}
                  materialTitle={materialTitle}
                  setMaterialTitle={setMaterialTitle}
                  materialText={materialText}
                  setMaterialText={setMaterialText}
                />
                <RoomRules
                  visibilityMode={visibilityMode}
                  setVisibilityMode={setVisibilityMode}
                  timingMode={timingMode}
                  setTimingMode={setTimingMode}
                  ttsEnabled={ttsEnabled}
                  setTtsEnabled={setTtsEnabled}
                />
              </>
            )}
            <button
              type="button"
              className="online-simple__primary"
              disabled={creating || !effectiveTopic.trim()}
              onClick={() => (variant === "lobby" ? createRoom("radmin") : navigate("/lobby"))}
            >
              {creating ? <Loader2 size={18} className="spin" /> : <PlusCircle size={18} />}
              {creating ? "创建中…" : variant === "lobby" ? "创建 Radmin 房间" : "进入联机大厅"}
            </button>
          </div>

          <div className="online-simple__section online-simple__section--public">
            <div className="online-simple__section-head">
              <Globe size={18} />
              <div>
                <h3>公网联机</h3>
                <p>不在同一网络时使用。</p>
              </div>
            </div>
            <TunnelProviderPanel onChanged={refresh} />
            {status.running && status.url ? (
              <p className="online-simple__tunnel-live">
                公网已连接：<code>{status.url}</code>
                {status.provider === "ngrok" ? "（关闭程序即失效）" : ""}
              </p>
            ) : status.error ? (
              <p className="online-simple__tunnel-offline">{status.error}</p>
            ) : null}
            <div className="online-steps">
              <span>1 选择隧道</span>
              <span>2 复制邀请链接</span>
              <span>3 创建房间</span>
            </div>
            <OnlineNetworkDiag />
            {variant === "lobby" && (
              <>
                <button
                  type="button"
                  className="online-simple__secondary"
                  disabled={copying || busy}
                  onClick={preparePublicLink}
                >
                  {copying || busy ? <Loader2 size={16} className="spin" /> : <Copy size={16} />}
                  {copied ? "公网链接已复制" : "复制公网邀请链接"}
                </button>
                {lastInviteLink && (
                  <p className="online-simple__micro-hint">
                    发给同学的完整链接：
                    <code>{lastInviteLink}</code>
                  </p>
                )}
                {publicReady && (
                  <>
                    <TopicMaterialFields
                      topic={effectiveTopic}
                      onTopicChange={handleTopicChange}
                      materialTitle={materialTitle}
                      setMaterialTitle={setMaterialTitle}
                      materialText={materialText}
                      setMaterialText={setMaterialText}
                    />
                    <RoomRules
                      visibilityMode={visibilityMode}
                      setVisibilityMode={setVisibilityMode}
                      timingMode={timingMode}
                      setTimingMode={setTimingMode}
                      ttsEnabled={ttsEnabled}
                      setTtsEnabled={setTtsEnabled}
                    />
                    <button
                      type="button"
                      className="online-simple__primary"
                      disabled={creating || !effectiveTopic.trim()}
                      onClick={() => createRoom("public")}
                    >
                      {creating ? <Loader2 size={18} className="spin" /> : <PlusCircle size={18} />}
                      {creating ? "创建中…" : "创建公网房间并选席位"}
                    </button>
                  </>
                )}
              </>
            )}
            {variant !== "lobby" && (
              <button type="button" className="online-simple__secondary" onClick={() => navigate("/lobby")}>
                前往联机大厅设置公网房间
              </button>
            )}
            {status.url && <code className="online-simple__url">{status.url}</code>}
            {status.error && <p className="online-simple__hint online-simple__hint--error">{status.error}</p>}
            {status.running && !status.healthy && !status.error && (
              <p className="online-simple__hint">公网隧道连接中，请稍候再复制链接…</p>
            )}
            {status.running && (
              <button type="button" className="online-simple__secondary compact" disabled={busy} onClick={() => stop()}>
                关闭公网隧道
              </button>
            )}
          </div>
        </>
      )}

      {variant !== "room" && (
        <>
          <div className="online-simple__divider">或加入已有房间</div>
          <form
            className="online-simple__join"
            onSubmit={(event) => {
              event.preventDefault();
              goJoin(joinInput);
            }}
          >
            <input
              value={joinInput}
              onChange={(e) => setJoinInput(e.target.value)}
              placeholder="粘贴同学发来的链接"
            />
            <button type="submit" className="online-simple__secondary" disabled={!joinInput.trim()}>
              <Link2 size={16} /> 加入
            </button>
          </form>
        </>
      )}

      {hint && <p className="online-simple__hint">{hint}</p>}

      {showRoomList && (
        <details className="online-simple__rooms">
          <summary>浏览大厅中的 {rooms.length} 个房间</summary>
          <ul>
            {rooms.map((room) => (
              <li key={room.id}>
                <div>
                  <strong>{room.topic || room.id}</strong>
                  <span>{room.online_count || 0} 人在线</span>
                </div>
                <Link to={`/join/${room.id}`} className="online-simple__secondary compact">
                  加入
                </Link>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
