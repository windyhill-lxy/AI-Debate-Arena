import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Brain,
  Download,
  Eye,
  FileText,
  Gavel,
  History,
  Mic,
  Network,
  PenLine,
  Loader2,
  Send,
  Sparkles,
  Volume2,
} from "lucide-react";
import CitationDetailPanel from "../../../components/CitationDetailPanel.jsx";
import MarkdownBody from "../../../components/MarkdownBody.jsx";
import { collectCitationSources } from "../../../utils/citationMap.jsx";
import { userSpeakerId } from "../utils.js";
import ResizableSplitPane from "../../../components/ResizableSplitPane.jsx";
import PublicMessageBoard from "./PublicMessageBoard.jsx";

export default function DebateCenterStage({
  debate,
  isLocal,
  status,
  speakingNow,
  ownSeatLabel,
  messageBoardRef,
  messageListScrollRef,
  visibleMessages,
  showStreamingPublic,
  streaming,
  audioByMessage,
  playMessageAudio,
  teamDiscussions,
  workflowColumns,
  exportFullHistory,
  exportPdf,
  speechFontPx,
  setSpeechFontPx,
  userInputEnabled,
  awaitingUser,
  speechInputState,
  draft,
  setDraft,
  askAssist,
  askDraft,
  assistLoading,
  draftLoading,
  showDraftPreview,
  setShowDraftPreview,
  sendMessage,
  messageSending = false,
  speechRecording,
  speechStatus,
  toggleSpeechInput,
  assist,
  autoScroll,
  setAutoScroll,
}) {
  const [selectedCitation, setSelectedCitation] = useState(null);
  const sourceMap = useMemo(
    () => collectCitationSources({ ...debate, messages: visibleMessages }, showStreamingPublic ? streaming?.sources : []),
    [debate, visibleMessages, showStreamingPublic, streaming?.sources],
  );
  const onCitationSelect = useCallback((citation) => setSelectedCitation(citation), []);
  const showMatchSummary = debate.phase === "finished" && Boolean(debate.match_summary);

  const composerPanel = userInputEnabled ? (
    <section className="panel composer composer--center" style={{ flexShrink: 0 }}>
      <div className="panel-title">
        <Send size={18} /> {debate.mode === "online_match" ? "联机发言" : "您的发言"}{" "}
        {awaitingUser && <span className="await-badge">轮到您</span>}
      </div>
      {speechInputState?.reason && !speechInputState.canSubmit && (
        <p className="composer-phase-hint" role="status">
          {speechInputState.reason}
          {speechInputState.phaseHint ? ` · ${speechInputState.phaseHint}` : ""}
        </p>
      )}
      <div className="composer-container">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          disabled={!speechInputState?.canSubmit || messageSending}
          placeholder={
            speechInputState?.canSubmit
              ? "支持 **Markdown** 格式。提交后 AI 将自动继续。"
              : speechInputState?.reason || "等待轮到您的发言环节…"
          }
        />
        <div className="composer-actions">
          <button type="button" onClick={() => setShowDraftPreview((v) => !v)}>
            <Eye size={16} /> {showDraftPreview ? "关闭预览" : "发言预览"}
          </button>
          <button type="button" onClick={askDraft} disabled={!speechInputState?.canSubmit || draftLoading}>
            <PenLine size={16} /> {draftLoading ? "生成中…" : "代拟草稿"}
          </button>
          <button type="button" onClick={askAssist} disabled={!speechInputState?.canSubmit || assistLoading}>
            <Sparkles size={16} /> {assistLoading ? "建议生成中…" : "发言建议"}
          </button>
          <button type="button" onClick={toggleSpeechInput} disabled={!speechInputState?.canSubmit}>
            <Mic size={16} /> {speechRecording ? "结束识别" : "语音录入"}
          </button>
          <button
            type="button"
            className={`primary ${messageSending ? "is-loading" : ""}`}
            onClick={sendMessage}
            disabled={!speechInputState?.canSubmit || messageSending}
          >
            {messageSending ? (
              <>
                <Loader2 size={16} className="spin" /> 提交中…
              </>
            ) : (
              <>
                <Send size={16} /> 提交发言
              </>
            )}
          </button>
        </div>
      </div>
      {speechStatus && <p className="speech-input-status">{speechStatus}</p>}
      {showDraftPreview && (
        <section className="draft-preview-panel" aria-label="发言预览">
          {draft?.trim() ? (
            <>
              <p className="assist-label">发言预览（提交前效果）</p>
              <MarkdownBody content={draft} />
            </>
          ) : (
            <p className="draft-preview-panel__empty">输入或代拟草稿后，此处显示 Markdown 预览</p>
          )}
        </section>
      )}
      {assist && (
        <section className="insight-panel-inline">
          <div className="panel-title">
            <Brain size={18} /> 发言建议
          </div>
          <MarkdownBody content={assist.suggestion} />
          {assist.counter_rebuttal && (
            <>
              <p className="assist-label">反驳切口</p>
              <MarkdownBody content={assist.counter_rebuttal} />
            </>
          )}
          {assist.possible_lines?.length > 0 && (
            <>
              <p className="assist-label">可追问句式</p>
              <ul className="assist-lines">
                {assist.possible_lines.map((line) => (
                  <li key={line}>
                    <MarkdownBody content={line} />
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      )}
    </section>
  ) : (
    <div className="composer composer--placeholder" aria-hidden="true" />
  );

  const matchSummaryPanel = (
    <section className="match-summary-panel match-summary-panel--split">
      <div className="panel-title">
        <Sparkles size={18} /> 全场总结
        <span>拖动上方分割条调整与主舞台的高度</span>
      </div>
      <div className="match-summary-panel__body">
        <MarkdownBody content={debate.match_summary} />
        <div className="match-summary-panel__scroll-spacer" aria-hidden="true" />
      </div>
    </section>
  );

  return (
    <section
      className={`center-stage center-stage--speech-first${showMatchSummary ? " center-stage--with-summary" : ""}`}
    >
      <header className="center-stage__meta">
        <div className="center-stage__topic">
          <p className="eyebrow">AI Debate Arena</p>
          <h2>{debate.topic}</h2>
          <p className="transcript-status">{status}</p>
          {ownSeatLabel && <p className="own-seat-badge">我的席位：{ownSeatLabel}</p>}
        </div>
        <div className="center-stage__tools">
          <div className="score-card score-card--prominent score-card--compact">
            <div className="score-side score-side--aff">
              <span className="score-label">正方</span>
              <strong className="score-value">{debate.score.affirmative.toFixed(1)}</strong>
            </div>
            <span className="score-vs">VS</span>
            <div className="score-side score-side--neg">
              <span className="score-label">反方</span>
              <strong className="score-value">{debate.score.negative.toFixed(1)}</strong>
            </div>
          </div>
          <div className="center-stage__exports">
            <button type="button" className="export-md-btn" onClick={exportFullHistory}>
              <Download size={14} /> 导出
            </button>
            {!isLocal && debate.id && debate.id !== "demo-room" && (
              <button type="button" className="export-md-btn" onClick={exportPdf}>
                <FileText size={14} /> PDF
              </button>
            )}
            {!isLocal && debate.id && debate.id !== "demo-room" && (
              <Link to={`/replay/${debate.id}`} className="export-md-btn replay-link-btn">
                <History size={14} /> 回放
              </Link>
            )}
          </div>
        </div>
      </header>

      {speakingNow && (
        <div className={`speaking-banner speaking-banner--compact ${speakingNow.side || ""}`}>
          <Volume2 size={16} />
          <strong>{speakingNow.name}</strong>
          <span>正在发言</span>
          <em>{speakingNow.segment}</em>
        </div>
      )}

      <CitationDetailPanel citation={selectedCitation} onClose={() => setSelectedCitation(null)} />

      <ResizableSplitPane
        className="center-stage__split"
        defaultRatio={showMatchSummary ? 0.5 : 0.62}
        minTopPx={showMatchSummary ? 120 : 80}
        minBottomPx={showMatchSummary ? 140 : 80}
        top={
          <PublicMessageBoard
            debate={debate}
            messageBoardRef={messageBoardRef}
            messageListScrollRef={messageListScrollRef}
            visibleMessages={visibleMessages}
            showStreamingPublic={showStreamingPublic}
            streaming={streaming}
            audioByMessage={audioByMessage}
            playMessageAudio={playMessageAudio}
            sourceMap={sourceMap}
            onCitationSelect={onCitationSelect}
            speechFontPx={speechFontPx}
            setSpeechFontPx={setSpeechFontPx}
            ownSpeakerId={userSpeakerId(debate)}
            autoScroll={autoScroll}
            setAutoScroll={setAutoScroll}
          />
        }
        bottom={showMatchSummary ? matchSummaryPanel : composerPanel}
      />

    </section>
  );
}
