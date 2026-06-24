import { PHASE_NAMES, portraitById, demoAgents } from "../../data/agents";
import { MODE_LABELS } from "./constants.js";
import { agentSeatLabel, debaterPositionLabel } from "../../utils/debateDisplay.js";

export { MODE_LABELS };

export function sideName(side) {
  return { affirmative: "正方", negative: "反方", judge: "裁判" }[side] || side;
}

export function phaseName(phase) {
  return PHASE_NAMES[phase] || phase;
}

export function debaterLabel(agent) {
  const seat = agentSeatLabel(agent);
  if (seat) return seat;
  if (!agent?.position) return sideName(agent?.side);
  const side = agent.side === "affirmative" ? "正方" : "反方";
  return `${side}${["", "一", "二", "三", "四"][agent.position]}辩`;
}

export function resolveAvatar(agent) {
  return portraitById[agent?.id] || agent?.avatar;
}

export function userSideForMode(mode) {
  if (mode === "user_affirmative") return "affirmative";
  if (mode === "user_negative") return "negative";
  return null;
}

export function participantSpeakerId(participant) {
  if (!participant || participant.side === "spectator" || !participant.position) return null;
  return `${participant.side === "affirmative" ? "aff" : "neg"}_${participant.position}`;
}

export function userSpeakerId(debate) {
  const side = debate.user_side || userSideForMode(debate.mode);
  if (!side) return null;
  const position = debate.user_position || 1;
  return `${side === "affirmative" ? "aff" : "neg"}_${position}`;
}

function sideFromSpeakerId(speakerId) {
  if (!speakerId) return null;
  if (speakerId.startsWith("aff_")) return "affirmative";
  if (speakerId.startsWith("neg_")) return "negative";
  return null;
}

const INTERNAL_PREP_PHASES = ["opening_prep", "free_prep", "closing_prep"];

export function isInternalPrepPhase(debate) {
  return INTERNAL_PREP_PHASES.includes(debate?.phase);
}

export function isUserTaskAssignSegment(debate) {
  const label = debate?.segment_label || "";
  if (label.includes("任务分配")) return true;
  return /一辩任务分配/.test(label);
}

export function isTeamDiscussionSegment(debate) {
  const label = debate?.segment_label || "";
  return label.includes("队内讨论");
}

export function openingArgumentBankReady(debate) {
  if (typeof debate?.opening_argument_bank_ready === "boolean") {
    return debate.opening_argument_bank_ready;
  }
  const target = debate?.opening_argument_target_per_side || 10;
  return ["affirmative", "negative"].every(
    (side) => (debate?.argument_bank?.[side] || []).length >= target,
  );
}

export function openingEvidenceCompleted(debate) {
  if (typeof debate?.opening_evidence_completed === "boolean") {
    return debate.opening_evidence_completed;
  }
  return openingArgumentBankReady(debate);
}

export function openingArgumentBankStatus(debate) {
  const target = debate?.opening_argument_target_per_side || 10;
  const aff = (debate?.argument_bank?.affirmative || []).length;
  const neg = (debate?.argument_bank?.negative || []).length;
  return { target, aff, neg };
}

function userSpokeInCurrentSegment(debate) {
  const label = debate?.segment_label || "";
  return (debate?.messages || []).some(
    (m) => (m.speech_flag === "ok" || m.speech_flag === "inappropriate") && m.segment_label === label,
  );
}

function teamDiscussionSideFromLabel(debate) {
  const label = debate?.segment_label || "";
  if (label.includes("反方")) return "negative";
  if (label.includes("正方")) return "affirmative";
  return debate?.user_side || null;
}

export function needsUserTurn(debate, participant = null) {
  const internalTeamPhase = isInternalPrepPhase(debate);
  if (debate?.phase === "opening_prep" && isTeamDiscussionSegment(debate) && !openingEvidenceCompleted(debate)) {
    return false;
  }
  if (debate.mode === "online_match") {
    if (internalTeamPhase && !isUserTaskAssignSegment(debate) && !isTeamDiscussionSegment(debate)) return false;
    if (participant) return debate.active_speaker_id === participantSpeakerId(participant);
    return (debate.participants || []).some(
      (p) => p.connected && debate.active_speaker_id === participantSpeakerId(p),
    );
  }
  const userId = userSpeakerId(debate);
  if (!userId) return false;
  if (internalTeamPhase) {
    if (isUserTaskAssignSegment(debate)) {
      return debate.active_speaker_id === userId;
    }
    if (isTeamDiscussionSegment(debate)) {
      const teamSide = teamDiscussionSideFromLabel(debate);
      if (teamSide && debate.user_side !== teamSide) return false;
      return !userSpokeInCurrentSegment(debate);
    }
    return false;
  }
  return debate.active_speaker_id === userId;
}

export function getOnlineStatusMessage(debate, participant = null) {
  if (debate.phase === "finished") return "辩论已结束。";
  if (isInternalPrepPhase(debate) && isTeamDiscussionSegment(debate)) {
    return "队内讨论中，AI 队友正在协调，请等待公开发言环节。";
  }
  if (debate.mode === "online_match") {
    if (needsUserTurn(debate, participant)) {
      return "轮到您的联机席位发言，请在下方输入后提交。";
    }
    if (needsUserTurn(debate)) {
      return "正在等待对方辩手发言。";
    }
    if (debate.auto_running) return "AI 回合自动进行中…";
    return "待机中，等待下一环节。";
  }
  if (debate.awaiting_user || needsUserTurn(debate)) {
    return "轮到您发言，请在下方输入后提交。";
  }
  if (debate.auto_running) return "AI 回合自动进行中…";
  return "待机中，等待下一环节。";
}

export function getDebateProgressHint({ autoRunning, speechInputState, debate }) {
  if (autoRunning) return "AI 回合进行中";
  if (speechInputState?.isYourTurn) return "等待您的发言";
  if (speechInputState?.reason) {
    if (speechInputState.reason.includes("队内讨论")) return "AI 队友发言中";
    if (speechInputState.reason.includes("准备环节")) return "准备环节进行中";
    if (speechInputState.reason.includes("连接") || speechInputState.reason.includes("重连")) {
      return speechInputState.reason;
    }
    if (speechInputState.reason.includes("等待轮到")) return "等待轮到您的席位发言";
    if (speechInputState.reason.includes("辩论已结束")) return "辩论已结束";
    return speechInputState.reason;
  }
  return debate?.awaiting_user ? "等待您的发言" : "待机";
}

export function formatPipelineHint(hint) {
  if (!hint) return "";
  if (typeof hint === "string") return hint;
  if (hint.type === "argument_bank_updated") {
    return hint.detail || `论据库已更新：正方 ${hint.affirmativeCount || 0} 条，反方 ${hint.negativeCount || 0} 条。`;
  }
  if (hint.type === "workflow_progress") {
    const seat = debaterPositionLabel(hint.speakerId, demoAgents) || (hint.side === "judge" ? "裁判" : hint.speakerName);
    return `当前节点：${hint.nodeLabel || "流程节点"}；调用：${seat || "系统"}`;
  }
  if (hint.type === "pipeline_prep") {
    const seat = debaterPositionLabel(hint.speakerId, demoAgents) || hint.speakerName || "下一位 AI";
    return hint.detail || `${seat} 正在预热 ${hint.sourcesCount || 0} 条资料。`;
  }
  if (hint.type === "reflection_done") {
    return hint.detail || "反思定稿完成。";
  }
  return hint.detail || hint.nodeLabel || "";
}

export function getSpeechInputState({
  debate,
  participant,
  mode,
  userInputEnabled,
  wsConnected,
  wsReconnecting,
  wsEverConnected = false,
  wsConnectionState = "idle",
  isLocal,
}) {
  const phaseHint = debate.segment_label || "";
  if (!userInputEnabled) {
    return { canSubmit: false, reason: "", phaseHint, isYourTurn: false };
  }
  if (debate.phase === "finished") {
    return { canSubmit: false, reason: "辩论已结束", phaseHint, isYourTurn: false };
  }
  if (!isLocal && !wsConnected) {
    let reason = "正在连接服务器…";
    if (wsConnectionState === "degraded" || wsConnectionState === "reconnecting") {
      reason = "正在恢复实时连接，席位已保留…";
    } else if (wsReconnecting || wsEverConnected) {
      reason = "连接断开，正在重连…";
    }
    return { canSubmit: false, reason, phaseHint, isYourTurn: false };
  }
  const serverAllowed = debate.user_turn_allowed;
  const isYourTurn =
    typeof serverAllowed === "boolean"
      ? serverAllowed
      : mode === "online_match"
        ? Boolean(
            participant &&
              debate.active_speaker_id === participantSpeakerId(participant) &&
              (debate.awaiting_user || needsUserTurn(debate, participant)),
          )
        : Boolean(debate.awaiting_user || needsUserTurn(debate));
  if (isInternalPrepPhase(debate) && isTeamDiscussionSegment(debate) && !isYourTurn) {
    if (debate.phase === "opening_prep" && !openingEvidenceCompleted(debate)) {
      const { target, aff, neg } = openingArgumentBankStatus(debate);
      return {
        canSubmit: false,
        reason: `正在搜集论据库：正方 ${aff}/${target}，反方 ${neg}/${target}，完成后进入队内讨论`,
        phaseHint,
        isYourTurn: false,
      };
    }
    return {
      canSubmit: false,
      reason: "队内讨论中，请等待轮到您在本方队内窗口发言",
      phaseHint,
      isYourTurn: false,
    };
  }
  if (isInternalPrepPhase(debate) && !isUserTaskAssignSegment(debate) && !isTeamDiscussionSegment(debate)) {
    return {
      canSubmit: false,
      reason: "准备环节中，请等待轮到您的任务分配回合",
      phaseHint,
      isYourTurn: false,
    };
  }
  if (!isYourTurn) {
    const reason =
      mode === "online_match"
        ? "等待轮到您的席位发言"
        : "等待轮到您的发言环节";
    return { canSubmit: false, reason, phaseHint, isYourTurn: false };
  }
  return {
    canSubmit: true,
    reason: "",
    phaseHint,
    isYourTurn: true,
  };
}

export function getAgent(debate, speakerId) {
  return debate.agents.find((a) => a.id === speakerId) || demoAgents.find((a) => a.id === speakerId);
}

export function localDemoMarkdown(agent, debate) {
  if (agent.side === "judge") {
    return `**裁判提示**：当前进入「${debate.segment_label}」，请双方围绕辩题标准推进。`;
  }
  const aff =
    "**主席、各位评委**，我方认为：在合理使用下，AI 的即时反馈能帮助学生发现盲区。\n\n- 定位薄弱点\n- 追问与修正\n- 迁移到真实问题";
  const neg =
    "**主席、各位评委**，对方把「完成任务」偷换成「能力提升」。\n\n> 若学生绕过思考直接拿答案，训练反而减少。";
  return agent.side === "affirmative" ? aff : neg;
}
