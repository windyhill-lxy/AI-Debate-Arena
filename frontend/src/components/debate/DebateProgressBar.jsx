import { getDebateProgressHint } from "../../features/debate-room/utils.js";
import { agentSeatLabel, debaterPositionLabel } from "../../utils/debateDisplay.js";

const POSITION_LABELS = ["", "一辩", "二辩", "三辩", "四辩"];

function sideLabel(side) {
  return { affirmative: "正方", negative: "反方", judge: "裁判", assistant: "系统" }[side] || side || "系统";
}

function speakerLabel(debate, hint, streaming) {
  if (streaming?.speaker_id || streaming?.speaker_name) {
    return debaterPositionLabel(streaming.speaker_id, debate.agents || []) ||
      (streaming.side === "judge" ? "裁判" : streaming.speaker_name || "系统");
  }
  const hintName = hint && typeof hint === "object" ? hint.speakerName : "";
  const hintSide = hint && typeof hint === "object" ? hint.side : "";
  const hintPosition = hint && typeof hint === "object" ? hint.position : 0;
  if (hintName || hintSide || hintPosition) {
    const seat = hintSide && hintPosition ? `${sideLabel(hintSide)}${POSITION_LABELS[hintPosition] || ""}` : "";
    return seat || (hintSide === "judge" ? "裁判" : hintName || "系统");
  }
  const agent = debate.agents?.find((item) => item.id === debate.active_speaker_id);
  if (!agent) return debate.active_speaker_id || "系统";
  return agentSeatLabel(agent) || agent.name;
}

function currentNodeLabel(debate, hint) {
  if (hint && typeof hint === "object" && hint.nodeLabel) return hint.nodeLabel;
  const running = debate.workflow?.find((node) => node.status === "running");
  return running?.label || debate.segment_label || debate.phase;
}

function currentDetail(hint, fallback) {
  if (hint && typeof hint === "object") {
    if (hint.detail) return hint.detail;
    if (hint.type === "argument_bank_updated") {
      return `论据库已更新：正方 ${hint.affirmativeCount || 0} 条，反方 ${hint.negativeCount || 0} 条。`;
    }
    if (hint.type === "pipeline_prep" && hint.speakerName) {
      const seat = debaterPositionLabel(hint.speakerId, debate?.agents || []) || hint.speakerName;
      return `${seat} 预热 ${hint.sourcesCount || 0} 条资料，已读 ${hint.partialLength || 0} 字。`;
    }
    if (hint.nodeDetail) return hint.nodeDetail;
  }
  if (typeof hint === "string") return hint;
  return fallback;
}

export default function DebateProgressBar({ debate, pipelineHint, autoRunning, speechInputState, streaming }) {
  const schedule = debate.schedule || [];
  const total = schedule.length || 1;
  const currentIndex = debate.schedule_index ?? 0;
  const done = schedule.filter((item) => item.status === "done").length;
  const percent = Math.min(100, Math.max(2, Math.round(((done || currentIndex) / total) * 100)));
  const miniPercent = Math.min(100, Math.max(2, Math.round(((Math.min(currentIndex + 1, total)) / total) * 100)));
  const progressHint = getDebateProgressHint({ autoRunning, speechInputState, debate });
  const nodeLabel = currentNodeLabel(debate, pipelineHint);
  const callLabel = speechInputState?.isYourTurn ? "等待用户发言" : speakerLabel(debate, pipelineHint, streaming);
  const detail = currentDetail(pipelineHint, progressHint);

  return (
    <div className="debate-progress">
      <div className="debate-progress__head">
        <span>
          赛程进度 {Math.min(currentIndex + 1, total)} / {total}
        </span>
        <span>{debate.segment_label || debate.phase}</span>
      </div>
      <div className="debate-progress__track" aria-hidden>
        <div className="debate-progress__fill" style={{ width: `${percent}%` }} />
      </div>
      <div className="debate-progress__current" aria-live="polite">
        <span>当前节点：{nodeLabel}</span>
        <span>调用：{callLabel}</span>
      </div>
      <div className="debate-progress__mini-track" aria-hidden>
        <div className="debate-progress__mini-fill" style={{ width: `${miniPercent}%` }} />
      </div>
      <p className="debate-progress__hint">
        {detail}
      </p>
    </div>
  );
}
