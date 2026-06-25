import { useCallback, useEffect, useRef } from "react";
import { ArrowDownToLine, MessageSquareText, Minus, Plus, Type } from "lucide-react";
import { SPEECH_FONT_SIZES } from "../constants.js";
import { phaseName } from "../utils.js";
import PublicMessage, { StreamingPublicMessage } from "./PublicMessage.jsx";

export default function PublicMessageBoard({
  debate,
  messageBoardRef,
  messageListScrollRef,
  visibleMessages,
  showStreamingPublic,
  streaming,
  audioByMessage,
  playMessageAudio,
  sourceMap,
  onCitationSelect,
  speechFontPx,
  setSpeechFontPx,
  ownSpeakerId,
  autoScroll,
  setAutoScroll,
}) {
  const fontIndex = SPEECH_FONT_SIZES.indexOf(speechFontPx);
  const canShrink = fontIndex > 0;
  const canGrow = fontIndex >= 0 && fontIndex < SPEECH_FONT_SIZES.length - 1;
  const ignoreScrollRef = useRef(false);

  function changeFont(delta) {
    const index = SPEECH_FONT_SIZES.indexOf(speechFontPx);
    const next = SPEECH_FONT_SIZES[index + delta];
    if (next) setSpeechFontPx(next);
  }

  const handleScroll = useCallback(() => {
    if (ignoreScrollRef.current) return;
    const el = messageListScrollRef.current;
    if (!el) return;
    const atBottom = el.scrollTop >= el.scrollHeight - el.clientHeight - 60;
    if (!atBottom && autoScroll) {
      setAutoScroll(false);
    }
  }, [autoScroll, messageListScrollRef, setAutoScroll]);

  useEffect(() => {
    const el = messageListScrollRef.current;
    if (!el) return;
    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, [handleScroll, messageListScrollRef]);

  const scrollToBottom = useCallback(() => {
    const el = messageListScrollRef.current;
    if (!el) return;
    ignoreScrollRef.current = true;
    el.scrollTop = el.scrollHeight;
    requestAnimationFrame(() => { ignoreScrollRef.current = false; });
    setAutoScroll(true);
  }, [messageListScrollRef, setAutoScroll]);

  return (
    <section
      className="message-board message-board--primary"
      ref={messageBoardRef}
      data-testid="debate-message-board"
      style={{
        "--speech-font-size": `${speechFontPx}px`,
        "--speech-line-height": speechFontPx >= 20 ? "1.72" : "1.8",
      }}
    >
      <div className="board-title board-title--primary">
        <div className="board-title__main">
          <MessageSquareText size={20} />
          <div>
            <strong>公开发言主舞台</strong>
            <span>
              {debate.segment_label || phaseName(debate.phase)} · 第 {debate.turn_index + 1} 步
            </span>
          </div>
        </div>
        <div className="board-title__actions">
          <button
            type="button"
            className={`autoscroll-toggle ${autoScroll ? "active" : ""}`}
            onClick={autoScroll ? () => setAutoScroll(false) : scrollToBottom}
            title={autoScroll ? "点击暂停自动滚动" : "点击恢复自动滚动到底部"}
            aria-label={autoScroll ? "暂停自动滚动" : "恢复自动滚动"}
          >
            <ArrowDownToLine size={14} />
            {autoScroll ? "自动滚动" : "已暂停"}
          </button>
        </div>
        <div className="speech-font-controls" aria-label="AI 发言字号">
          <span className="speech-font-controls__label">
            <Type size={14} /> 字号
          </span>
          <button
            type="button"
            className="speech-font-controls__btn"
            onClick={() => changeFont(-1)}
            disabled={!canShrink}
            title="缩小字号"
            aria-label="缩小 AI 发言字号"
          >
            <Minus size={14} />
          </button>
          <span className="speech-font-controls__value">{speechFontPx}px</span>
          <button
            type="button"
            className="speech-font-controls__btn"
            onClick={() => changeFont(1)}
            disabled={!canGrow}
            title="放大字号"
            aria-label="放大 AI 发言字号"
          >
            <Plus size={14} />
          </button>
          <div className="speech-font-controls__presets">
            {SPEECH_FONT_SIZES.map((size) => (
              <button
                key={size}
                type="button"
                className={size === speechFontPx ? "active" : ""}
                onClick={() => setSpeechFontPx(size)}
              >
                {size}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div ref={messageListScrollRef} className="message-list-scroll message-list-scroll--primary">
        {visibleMessages.map((message) => (
          <PublicMessage
            key={message.id}
            message={message}
            debate={debate}
            audioByMessage={audioByMessage}
            playMessageAudio={playMessageAudio}
            sourceMap={sourceMap}
            onCitationSelect={onCitationSelect}
            ownSpeakerId={ownSpeakerId}
          />
        ))}
        {visibleMessages.length === 0 && !showStreamingPublic && (
          <p className="empty-note">公开发言将显示在此处，请等待辩手发言。</p>
        )}
        {showStreamingPublic && (
          <div data-testid="debate-streaming">
            <StreamingPublicMessage
              streaming={streaming}
              debate={debate}
              sourceMap={sourceMap}
              onCitationSelect={onCitationSelect}
              ownSpeakerId={ownSpeakerId}
            />
          </div>
        )}
      </div>
    </section>
  );
}
