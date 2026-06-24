import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Download, Pause, Play, SkipForward, Volume2 } from "lucide-react";
import MarkdownBody from "../components/MarkdownBody.jsx";
import { buildShareUrl } from "../utils/shareLink.js";
import { useAudioQueue } from "../hooks/useAudioQueue.js";
import {
  buildClientHistoryMarkdown,
  displaySpeakerName,
  downloadTextFile,
  stripMarkdownForSubtitle,
} from "../utils/debateDisplay.js";
import { demoAgents, PHASE_NAMES, portraitById } from "../data/agents";
import { API_BASE } from "../utils/apiBase.js";
import { useErrorDialog } from "../components/ErrorDialogProvider.jsx";
import { errorDialogPayload, throwHttpError } from "../utils/httpError.js";

function phaseName(phase) {
  return PHASE_NAMES[phase] || phase;
}

function resolveAvatar(agentId) {
  return portraitById[agentId] || demoAgents.find((a) => a.id === agentId)?.avatar;
}

function audioUrlsForMessage(message) {
  if (message.audio_urls?.length) return message.audio_urls;
  if (message.audio_url) return [message.audio_url];
  return [];
}

export default function Replay({ shareMode = false }) {
  const { id } = useParams();
  const [debate, setDebate] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const [autoPlayOnSelect, setAutoPlayOnSelect] = useState(true);
  const [playFromHere, setPlayFromHere] = useState(false);
  const [error, setError] = useState("");

  const { playMessage, enqueue, skipCurrent, setReplayMode, subtitle, queueLength, current } = useAudioQueue();
  const { reportError } = useErrorDialog();

  useEffect(() => {
    setReplayMode(true);
    return () => setReplayMode(false);
  }, [setReplayMode]);

  useEffect(() => {
    fetch(`${API_BASE}/api/debates/${id}`)
      .then((r) => {
        if (!r.ok) return throwHttpError(r);
        return r.json();
      })
      .then((data) => {
        setDebate(data);
        setActiveId(data.messages?.[0]?.id || null);
      })
      .catch((e) => {
        setError(e.message || "无法加载回放");
        reportError(errorDialogPayload(e, "加载回放失败", "Replay.load", "无法加载回放"));
      });
  }, [id, reportError]);

  const activeMessage = useMemo(
    () => debate?.messages?.find((m) => m.id === activeId) || debate?.messages?.[0],
    [debate, activeId],
  );

  const messagesWithAudio = useMemo(
    () => (debate?.messages || []).filter((m) => audioUrlsForMessage(m).length > 0),
    [debate],
  );

  const playOne = useCallback(
    (message) => {
      const urls = audioUrlsForMessage(message);
      if (!urls.length) return;
      playMessage(urls, {
        messageId: message.id,
        text: message.content,
        speakerName: displaySpeakerName(message, debate),
      });
    },
    [debate, playMessage],
  );

  const playFromActive = useCallback(() => {
    if (!debate?.messages?.length || !activeId) return;
    const startIndex = debate.messages.findIndex((m) => m.id === activeId);
    const slice = debate.messages.slice(startIndex >= 0 ? startIndex : 0);
    const withAudio = slice.filter((m) => audioUrlsForMessage(m).length > 0);
    if (!withAudio.length) return;
    for (const msg of withAudio) {
      enqueue(audioUrlsForMessage(msg), {
        messageId: msg.id,
        text: msg.content,
        speakerName: displaySpeakerName(msg, debate),
      }, { replay: true });
    }
  }, [debate, activeId, enqueue]);

  useEffect(() => {
    if (playFromHere) {
      setPlayFromHere(false);
      playFromActive();
    }
  }, [playFromHere, playFromActive]);

  function selectMessage(message) {
    setActiveId(message.id);
    if (autoPlayOnSelect) playOne(message);
  }

  if (error) {
    return (
      <main className="replay-page">
        <p>{error}</p>
        <Link to="/">返回首页</Link>
      </main>
    );
  }

  if (!debate) {
    return (
      <main className="replay-page">
        <p>加载回放中…</p>
      </main>
    );
  }

  const subtitlePlain = subtitle.text || (activeMessage ? stripMarkdownForSubtitle(activeMessage.content) : "");
  const visibleText = subtitlePlain.slice(0, subtitle.visibleChars || subtitlePlain.length);
  const activeSpeakerLabel = activeMessage ? displaySpeakerName(activeMessage, debate) : "";

  return (
    <main className="replay-page">
      <header className="replay-header">
        {shareMode ? (
          <Link to="/" className="back-home">
            <ArrowLeft size={16} /> 返回首页
          </Link>
        ) : (
          <Link to={`/room/${id}`} className="back-home">
            <ArrowLeft size={16} /> 返回辩论室
          </Link>
        )}
        <div>
          <p className="eyebrow">{shareMode ? "只读分享回放" : "Replay Mode"}</p>
          <h1>{debate.topic}</h1>
          <p>
            正方 {Number(debate.score?.affirmative || 0).toFixed(1)} · 反方{" "}
            {Number(debate.score?.negative || 0).toFixed(1)} · {debate.phase === "finished" ? "已结束" : "进行中"}
            {debate.schedule_template && ` · 赛制 ${debate.schedule_template}`}
          </p>
        </div>
        <div className="replay-header__actions">
          <button
            type="button"
            className="export-md-btn"
            onClick={() => downloadTextFile(`debate-${id}-replay.md`, buildClientHistoryMarkdown(debate))}
          >
            <Download size={14} /> 导出回放
          </button>
        </div>
      </header>

      {shareMode && (
        <p className="replay-share-hint">
          此为只读回放链接，观看者无法进入辩论室修改赛程或发言。链接：
          <code>{buildShareUrl(id)}</code>
        </p>
      )}

      <section className="replay-controls">
        <label className="replay-toggle">
          <input
            type="checkbox"
            checked={autoPlayOnSelect}
            onChange={(e) => setAutoPlayOnSelect(e.target.checked)}
          />
          选中发言时自动播放语音
        </label>
        <button type="button" className="export-md-btn" onClick={() => setPlayFromHere(true)} disabled={!messagesWithAudio.length}>
          <Play size={14} /> 从当前起连续播放
        </button>
        <button type="button" className="export-md-btn" onClick={() => activeMessage && playOne(activeMessage)}>
          <Volume2 size={14} /> 播放当前
        </button>
        <button type="button" className="export-md-btn" onClick={skipCurrent}>
          <SkipForward size={14} /> 跳过
          {queueLength > 0 ? ` (${queueLength})` : ""}
        </button>
        {current && (
          <span className="replay-now-playing">
            <Pause size={14} /> 正在播放…
          </span>
        )}
      </section>

      {(subtitle.text || visibleText) && (
        <section className="audio-subtitle-bar replay-subtitle-bar" aria-live="polite">
          <span className="audio-subtitle-bar__speaker">{subtitle.speakerName || activeSpeakerLabel}</span>
          <p className="audio-subtitle-bar__text">
            {visibleText}
            <span className="audio-subtitle-bar__caret">|</span>
          </p>
          <div
            className="audio-subtitle-bar__progress"
            style={{ width: `${Math.round((subtitle.progress || 0) * 100)}%` }}
          />
        </section>
      )}

      {debate.match_summary && (
        <section className="replay-summary">
          <h2>全场总结</h2>
          <MarkdownBody content={debate.match_summary} />
        </section>
      )}

      <div className="replay-layout">
        <aside className="replay-timeline" aria-label="辩论进程">
          <h2>
            <Play size={16} /> 进程 ({debate.messages.length})
          </h2>
          <p className="replay-audio-hint">带 🔊 的环节可同步 TTS 字幕</p>
          <ol>
            {debate.messages.map((message, index) => {
              const hasAudio = audioUrlsForMessage(message).length > 0;
              const isPlaying = subtitle.messageId === message.id || current?.messageId === message.id;
              return (
                <li key={message.id}>
                  <button
                    type="button"
                    className={`${message.id === activeId ? "active" : ""} ${isPlaying ? "playing" : ""}`}
                    onClick={() => selectMessage(message)}
                  >
                    <span className="replay-timeline__index">{index + 1}</span>
                    <span>
                      <strong>
                        {displaySpeakerName(message, debate)}
                        {hasAudio ? " 🔊" : ""}
                      </strong>
                      <em>{message.segment_label || PHASE_NAMES[message.phase] || message.phase}</em>
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </aside>

        <section className="replay-detail" aria-live="polite">
          {activeMessage && (
            <>
              <div className="replay-detail__head">
                <img src={resolveAvatar(activeMessage.speaker_id)} alt="" />
                <div>
                  <h3>{activeSpeakerLabel}</h3>
                  <p>{activeMessage.segment_label || phaseName(activeMessage.phase)}</p>
                  {activeMessage.score_delta != null && (
                    <p className="score-reason">
                      本轮 {activeMessage.score_delta > 0 ? "+" : ""}
                      {activeMessage.score_delta}
                      {activeMessage.score_reason ? ` · ${activeMessage.score_reason}` : ""}
                    </p>
                  )}
                </div>
              </div>
              <MarkdownBody content={activeMessage.content} />
            </>
          )}
        </section>
      </div>
    </main>
  );
}
