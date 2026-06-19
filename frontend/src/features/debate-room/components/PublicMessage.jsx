import { Volume2 } from "lucide-react";
import CitationMarkdownBody from "../../../components/CitationMarkdownBody.jsx";
import { getAgent, phaseName, resolveAvatar, sideName } from "../utils.js";

function FactCheckBadge({ message }) {
  const risk = message.hallucination_risk;
  const srcCount = message.sources?.length || 0;
  const isAI = message.side === "affirmative" || message.side === "negative" || message.side === "judge";
  if (!isAI || (!risk && srcCount === 0)) return null;

  if (srcCount > 0) {
    return (
      <div className="fact-badge fact-badge--low" title="已通过RAG向量库检索核实">
        已RAG核实 {srcCount} 条
      </div>
    );
  }
  if (risk === "high") {
    return (
      <div className="fact-badge fact-badge--high" title="含数据或引用但无来源支撑，可能存在幻觉">
        含数据待核实
      </div>
    );
  }
  if (risk === "medium") {
    return (
      <div className="fact-badge fact-badge--medium" title="含数字但无RAG来源支撑">
        含数字未引用
      </div>
    );
  }
  return (
    <div className="fact-badge fact-badge--none" title="发言未引用外部资料">
      未引用资料
    </div>
  );
}

export default function PublicMessage({ message, debate, audioByMessage, playMessageAudio, sourceMap, onCitationSelect, ownSpeakerId }) {
  const agent = getAgent(debate, message.speaker_id);
  const isOwn = ownSpeakerId && message.speaker_id === ownSpeakerId;
  const audio = audioByMessage[message.id];
  const audioUrls = audio?.audio_urls?.length ? audio.audio_urls : audio?.audio_url ? [audio.audio_url] : [];
  const replayAudio = () => {
    if (!audioUrls.length) return;
    playMessageAudio?.(audioUrls, {
      messageId: message.id,
      speakerName: message.speaker_name,
      text: message.content,
      voice: audio?.voice,
    });
  };
  return (
    <article className={`message ${message.side} ${isOwn ? "message--own" : ""}`}>
      <img className="message-avatar" src={resolveAvatar(agent)} alt={message.speaker_name} />
      <div className="message-body">
        <div className="message-head">
          <strong>{message.speaker_name}</strong>
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
        <FactCheckBadge message={message} />
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
  return (
    <article className={`message ${streaming.side} ${isOwn ? "message--own" : ""} streaming-message`}>
      <img className="message-avatar" src={resolveAvatar(agent)} alt={streaming.speaker_name} />
      <div className="message-body">
        <div className="message-head">
          <strong>{streaming.speaker_name}</strong>
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
