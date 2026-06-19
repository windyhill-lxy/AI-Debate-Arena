import { Download, Pause, Play, SkipForward, Square, Volume2, Zap } from "lucide-react";
import DebateProgressBar from "../../../components/debate/DebateProgressBar.jsx";

export default function DebateRoomDock({
  debate,
  pipelineHint,
  status,
  awaitingUser,
  speechInputState,
  isLocal,
  roomNav,
  wsConnected,
  wsReconnecting,
  wsConnectionState = "idle",
  ttsStatus,
  currentAudio,
  audioQueueLength,
  audioPaused,
  audioDisabled,
  pauseAudio,
  resumeAudio,
  skipCurrentAudio,
  stopTtsSession,
  resumeDebate,
  exportFullHistory,
  streaming,
}) {
  const showResume =
    !isLocal &&
    debate.phase !== "finished" &&
    !debate.auto_running &&
    (!awaitingUser || (speechInputState && !speechInputState.canSubmit));
  const showAudioControls = !audioDisabled || currentAudio || audioQueueLength > 0 || audioPaused;

  return (
    <footer className="debate-dock" aria-label="赛程与常用操作">
      <div className="debate-dock__progress">
        <DebateProgressBar
          debate={debate}
          pipelineHint={pipelineHint}
          autoRunning={debate.auto_running}
          speechInputState={speechInputState}
        />
        {streaming?.content && (
          <p className="debate-dock__streaming" aria-live="polite">
            流式输出中 · {streaming.speaker_name}（{streaming.content.length} 字）
          </p>
        )}
      </div>
      <div className="debate-dock__actions">
        {roomNav}
        <span className="debate-dock__status" title={status}>
          {!isLocal && (
            <em
              className={`ws-pill ${
                wsConnected ? "ok" : wsReconnecting || wsConnectionState === "degraded" ? "warn" : ""
              }`}
            >
              {wsConnected
                ? "已连接"
                : wsConnectionState === "connecting"
                  ? "连接中"
                  : wsConnectionState === "degraded" || wsReconnecting
                    ? "恢复中"
                    : wsConnectionState === "reconnecting"
                      ? "重连"
                      : "未连接"}
            </em>
          )}
          {debate.auto_running ? "AI 进行中" : awaitingUser ? "轮到您" : "待机"}
        </span>

        {showAudioControls && (
          <div className="debate-dock__audio-group" aria-label="语音朗读控制">
            {!audioDisabled && (
              <>
                <button
                  type="button"
                  className="debate-dock__btn"
                  onClick={pauseAudio}
                  disabled={!currentAudio || audioPaused}
                  title="暂停朗读（空格）"
                >
                  <Pause size={15} /> 暂停
                </button>
                <button
                  type="button"
                  className="debate-dock__btn"
                  onClick={resumeAudio}
                  disabled={!audioPaused}
                  title="继续朗读（空格）"
                >
                  <Play size={15} /> 继续
                </button>
                <button
                  type="button"
                  className="debate-dock__btn"
                  onClick={skipCurrentAudio}
                  disabled={!currentAudio && audioQueueLength <= 0}
                  title="跳过当前朗读（Esc）"
                >
                  <SkipForward size={15} /> 跳过
                  {audioQueueLength > 0 ? ` (${audioQueueLength})` : ""}
                </button>
                <button
                  type="button"
                  className="debate-dock__btn debate-dock__btn--danger"
                  onClick={stopTtsSession}
                  title="停止本场语音：不再请求 TTS，不影响 AI 发言"
                >
                  <Square size={15} /> 停止
                </button>
              </>
            )}
            {audioDisabled && (
              <span className="debate-dock__tts debate-dock__tts--muted" title="本场辩论已关闭语音">
                <Volume2 size={14} /> 语音已停止
              </span>
            )}
          </div>
        )}

        {showResume && (
          <button type="button" className="debate-dock__btn debate-dock__btn--primary" onClick={resumeDebate}>
            <Zap size={15} /> 继续推进
          </button>
        )}
        <button type="button" className="debate-dock__btn" onClick={exportFullHistory}>
          <Download size={15} /> 导出
        </button>
        {ttsStatus && !audioDisabled && (
          <span className="debate-dock__tts" title={ttsStatus}>
            <Volume2 size={14} />
            {ttsStatus.length > 28 ? `${ttsStatus.slice(0, 28)}…` : ttsStatus}
          </span>
        )}
      </div>
    </footer>
  );
}
