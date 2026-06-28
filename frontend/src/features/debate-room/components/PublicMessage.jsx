import { Volume2 } from "lucide-react";
import CitationMarkdownBody from "../../../components/CitationMarkdownBody.jsx";
import { displaySpeakerName } from "../../../utils/debateDisplay.js";
import { getAgent, phaseName, resolveAvatar, sideName } from "../utils.js";
import { factBadgeForMessage } from "../factBadge.js";

function FactCheckBadge({ message, debate }) {
  const badge = factBadgeForMessage(message, debate);
  if (!badge) return null;
  return (
    <div className={`fact-badge fact-badge--${badge.tone}`} title={badge.title}>
      {badge.text}
    </div>
  );
}

export default function PublicMessage({ message, debate, audioByMessage, playMessageAudio, sourceMap, onCitationSelect, ownSpeakerId }) {
  const agent = getAgent(debate, message.speaker_id);
  const isOwn = ownSpeakerId && message.speaker_id === ownSpeakerId;
  const speakerLabel = displaySpeakerName(message, debate);
  const audio = audioByMessage[message.id];
  const audioUrls = audio?.audio_urls?.length ? audio.audio_urls : audio?.audio_url ? [audio.audio_url] : [];
  const replayAudio = () => {
    if (!audioUrls.length) return;
    playMessageAudio?.(audioUrls, {
      messageId: message.id,
      speakerName: speakerLabel,
      text: message.content,
      voice: audio?.voice,
    });
  };
  return (
    <article className={`message ${message.side} ${isOwn ? "message--own" : ""}`}>
      <img className="message-avatar" src={resolveAvatar(agent)} alt={speakerLabel} />
      <div className="message-body">
        <div className="message-head">
          <strong>{speakerLabel}</strong>
          <span>
            {sideName(message.side)} · {message.segment_label || phaseName(message.phase)}
          </span>
          {message.score_delta != null && (
            <em className="score-delta" title={message.score_reason || ""}>
              {message.score_delta > 0 ? "+" : ""}
              {message.score_delta}
            </em>
          )}
        </div>
        <CitationMarkdownBody
          content={message.content}
          sourceMap={sourceMap}
          onCitationSelect={onCitationSelect}
        />
        <FactCheckBadge message={message} debate={debate} />
        {audioUrls.length > 0 && (
          <button type="button" className="message-audio message-audio--queued" onClick={replayAudio}>
            <Volume2 size={14} />
            <span>播放语音（{audio?.voice || "TTS"}）</span>
          </button>
        )}
      </div>
    </article>
  );
}

export function StreamingPublicMessage({ streaming, debate, sourceMap, onCitationSelect, ownSpeakerId }) {
  const agent = getAgent(debate, streaming.speaker_id);
  const isOwn = ownSpeakerId && streaming.speaker_id === ownSpeakerId;
  const speakerLabel = displaySpeakerName(streaming, debate);
  return (
    <article className={`message ${streaming.side} ${isOwn ? "message--own" : ""} streaming-message`}>
      <img className="message-avatar" src={resolveAvatar(agent)} alt={speakerLabel} />
      <div className="message-body">
        <div className="message-head">
          <strong>{speakerLabel}</strong>
          <span>{sideName(streaming.side)} · 流式输出中</span>
        </div>
        <CitationMarkdownBody
          content={streaming.content}
          streaming
          sourceMap={sourceMap}
          onCitationSelect={onCitationSelect}
        />
      </div>
    </article>
  );
}
