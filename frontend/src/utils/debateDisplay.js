const INTERNAL_PREP_PHASES = new Set(["opening_prep", "free_prep", "closing_prep"]);
const INTERNAL_PREP_LABEL =
  /立论前准备|自由辩论前准备|总结陈词前准备|队内讨论|任务分配|论点分工|论据分配|策略锁定|攻防策略|角色临时分工|总结框架确认|四辩接收汇总/;

const PUBLIC_DEBATE_PHASES = new Set([
  "opening_statement",
  "rebuttal",
  "cross_examination",
  "segment_summary",
  "free_debate",
  "closing",
]);

export function isTeamDiscussion(message) {
  if (!message?.side || !["affirmative", "negative"].includes(message.side)) return false;
  if (message.phase && INTERNAL_PREP_PHASES.has(message.phase)) return true;
  return INTERNAL_PREP_LABEL.test(message.segment_label || "");
}

/** 队内讨论归属：优先按环节标签，避免流式阶段 speaker 与窗口错位 */
export function teamDiscussionSide(message, agents = []) {
  const label = message?.segment_label || "";
  if (/反方.*(队内|讨论|任务分配|汇总|准备)/.test(label)) return "negative";
  if (/正方.*(队内|讨论|任务分配|汇总|准备)/.test(label)) return "affirmative";
  const agent = agents.find((a) => a.id === message?.speaker_id);
  if (agent?.side === "affirmative" || agent?.side === "negative") return agent.side;
  return message?.side;
}

export function isJudgeThought(message) {
  return (
    message?.side === "judge" &&
    message?.phase === "post_match" &&
    !(message?.segment_label || "").includes("输出裁判报告")
  );
}

export function isPublicStageMessage(message) {
  if (!message) return false;
  if (isTeamDiscussion(message) || isJudgeThought(message)) return false;

  const label = message.segment_label || "";

  if (message.side === "judge") {
    if (message.phase === "post_match") return label.includes("输出裁判报告");
    if (message.phase === "pre_match") return true;
    return label.includes("准备就绪") || label.includes("结束自由辩论") || label.includes("暂停计时");
  }

  if (["affirmative", "negative"].includes(message.side)) {
    if (message.phase) return PUBLIC_DEBATE_PHASES.has(message.phase);
    return !INTERNAL_PREP_LABEL.test(label);
  }

  return false;
}

export function debaterPositionLabel(speakerId, agents = []) {
  const agent = agents.find((a) => a.id === speakerId);
  if (!agent) return "";
  const side = agent.side === "affirmative" ? "正方" : agent.side === "negative" ? "反方" : "";
  const pos = ["一辩", "二辩", "三辩", "四辩"][agent.position - 1] || "";
  return side && pos ? `${side}${pos}` : "";
}

/** 队内讨论/公开发言：用户席位显示 user_name，AI 显示角色名 + 席位标签 */
export function displaySpeakerName(message, debate) {
  const name = message?.speaker_name || "";
  const seat = debaterPositionLabel(message?.speaker_id, debate?.agents || []);
  const userSeat = debate?.user_side && debate?.user_position
    ? `${debate.user_side === "affirmative" ? "aff" : "neg"}_${debate.user_position}`
    : null;
  const isUserSeat =
    message?.speech_flag != null ||
    (userSeat && message?.speaker_id === userSeat) ||
    name === (debate?.user_name || "用户辩手");
  if (isUserSeat && debate?.user_name) {
    return seat ? `${debate.user_name}（${seat}）` : debate.user_name;
  }
  return seat ? `${name}（${seat}）` : name;
}

export function stripMarkdownForSubtitle(text) {
  if (!text) return "";
  return text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[[^\]]*]\([^)]+\)/g, "")
    .replace(/\[([^\]]+)]\([^)]+\)/g, "$1")
    .replace(/[#>*_~\-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function buildClientHistoryMarkdown(debate) {
  const lines = [
    `# ${debate.topic}`,
    "",
    `- 模式: ${debate.mode}`,
    `- 环节: ${debate.phase} / ${debate.segment_label}`,
    `- 比分: 正方 ${Number(debate.score?.affirmative || 0).toFixed(2)} · 反方 ${Number(debate.score?.negative || 0).toFixed(2)}`,
    "",
  ];
  if (debate.match_summary) {
    lines.push("## 全场总结", "", debate.match_summary, "");
  }
  lines.push("## 完整记录", "");
  for (const m of debate.messages || []) {
    lines.push(`### ${m.speaker_name} · ${m.segment_label || m.phase}`, "", m.content || "", "");
  }
  return lines.join("\n").trim() + "\n";
}

export function downloadTextFile(filename, content, mime = "text/markdown;charset=utf-8") {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
