import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Copy, Globe, Link2, Loader2, PlusCircle, Users, Wifi } from "lucide-react";
import { useErrorDialog } from "./ErrorDialogProvider.jsx";
import { usePublicTunnel } from "../hooks/usePublicTunnel.js";
import { API_BASE, isTunnelHost } from "../utils/apiBase.js";
import { errorDialogPayload, parseHttpErrorBody } from "../utils/httpError.js";
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

async function copyTextSafely(text) {
  if (!text) return false;
  try {
    if (document.hasFocus() && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall back to a temporary textarea when the browser denies clipboard access.
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch {
    copied = false;
  } finally {
    document.body.removeChild(textarea);
  }
  return copied;
}

function assertPublicTunnelReady(tunnelState) {
  if (!tunnelState?.running || !tunnelState?.url) {
    throw new Error(tunnelState?.error || "公网隧道未开启，请重新点击复制公网邀请链接。");
  }
  if (!tunnelState?.healthy) {
    throw new Error(
      tunnelState?.error ||
        "公网地址暂未连通，同学打开会显示离线。请稍后重试，或重启公网隧道/改用局域网联机。",
    );
  }
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
  const { reportError } = useErrorDialog();
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
    if (!response.ok) throw parseHttpErrorBody(await response.text(), response);
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
      tunnelState = await verify();
      assertPublicTunnelReady(tunnelState);
      const link = buildSessionInviteLink(sid, tunnelState.url);
      if (!link) throw new Error("无法生成公网邀请链接");
      if (!link.includes("/join/session/")) {
        throw new Error("邀请链接格式异常，请重试");
      }
      setLastInviteLink(link);
      setPublicReady(true);
      const copiedOk = await copyTextSafely(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      const via = tunnelState.provider === "ngrok" ? "ngrok" : "公网隧道";
      setHint(
        copiedOk
          ? `已复制完整邀请链接（${via}）。请把含 /join/session/ 的整段链接发给同学，不要只发 ngrok 域名。请保持程序窗口开着。`
          : `浏览器没有允许自动复制。完整邀请链接已显示在下方，请手动复制后发给同学。`,
      );
    } catch (error) {
      setHint(error.message || "公网邀请准备失败");
      reportError(errorDialogPayload(error, "公网邀请准备失败", "OnlineSimplePanel.publicLink"));
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
      if (!response.ok) throw parseHttpErrorBody(await response.text(), response);
      const debate = await response.json();
      if (debate.host_token) saveHostToken(debate.id, debate.host_token);
      navigate(`/join/${encodeURIComponent(debate.id)}`, {
        state: { topic: debate.topic, fromCreate: true, materials },
      });
    } catch (error) {
      setHint(error.message || "创建失败，请确认程序已启动");
      reportError(errorDialogPayload(error, "创建联机房间失败", "OnlineSimplePanel.createRoom", "请确认程序已启动"));
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
      let tunnelState = status;
      if (isLoopbackHost(hostname) && !tunnelUrl) {
        tunnelState = await start();
        tunnelUrl = tunnelState?.url || "";
      }
      if (tunnelUrl || isLoopbackHost(hostname)) {
        tunnelState = await verify();
        assertPublicTunnelReady(tunnelState);
        tunnelUrl = tunnelState.url || tunnelUrl;
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
      setLastInviteLink(finalLink);
      const copiedOk = await copyTextSafely(finalLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      if (!copiedOk) setHint("浏览器没有允许自动复制，邀请链接已显示，请手动复制。");
    } catch (error) {
      setHint(error.message || "复制失败，请检查浏览器权限");
      reportError(errorDialogPayload(error, "复制邀请链接失败", "OnlineSimplePanel.copyInvite", "请检查浏览器权限"));
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
          {lastInviteLink && (
            <p className="online-simple__micro-hint">
              邀请链接：<code>{lastInviteLink}</code>
            </p>
          )}
        </div>
      )}

      {showCreate && variant !== "room" && (
        <>
          <div className="online-simple__section online-simple__section--lan">
            <div className="online-simple__section-head">
              <Wifi size={18} />
              <div>
                <h3>局域网联机</h3>
                <p>同一 Wi-Fi 或教室网络内使用，延迟低、无需公网。</p>
              </div>
            </div>
            <div className="online-lan-wizard">
              <article>
                <strong>1 连接同一网络</strong>
                <span>房主和同学连接同一个 Wi-Fi、校园网或教室路由器。</span>
              </article>
              <article>
                <strong>2 房主启动局域网</strong>
                <span>房主运行项目根目录的 start-lan.bat，等待窗口显示局域网访问地址。</span>
              </article>
              <article>
                <strong>3 打开大厅</strong>
                <span>房主用浏览器打开局域网地址后进入联机大厅，在这里填写辩题和资料。</span>
              </article>
              <article>
                <strong>4 创建房间</strong>
                <span>点击创建局域网房间，进入席位选择，把浏览器地址栏里的房间链接发给同学。</span>
              </article>
              <article>
                <strong>5 同学加入</strong>
                <span>同学打开链接，选择席位并完成设备检查。打不开时先确认双方仍在同一网络。</span>
              </article>
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
