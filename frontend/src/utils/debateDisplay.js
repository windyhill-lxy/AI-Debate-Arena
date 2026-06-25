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

const POSITION_LABELS = ["一辩", "二辩", "三辩", "四辩"];

function positionLabel(side, position) {
  if (side === "judge") return "裁判";
  if (side === "assistant") return "系统";
  const sideText = side === "affirmative" ? "正方" : side === "negative" ? "反方" : "";
  const posText = POSITION_LABELS[position - 1] || "";
  return sideText && posText ? `${sideText}${posText}` : "";
}

function labelFromSpeakerId(speakerId) {
  const match = String(speakerId || "").match(/^(aff|neg)_(\d)$/);
  if (!match) return "";
  return positionLabel(match[1] === "aff" ? "affirmative" : "negative", Number(match[2]));
}

export function agentSeatLabel(agent) {
  if (!agent) return "";
  return positionLabel(agent.side, Number(agent.position || 0)) || (agent.side === "judge" ? "裁判" : "");
}

export function debaterPositionLabel(speakerId, agents = []) {
  const agent = agents.find((a) => a.id === speakerId);
  if (agent) return agentSeatLabel(agent);
  return labelFromSpeakerId(speakerId);
}

/** 队内讨论/公开发言统一显示赛位称谓，避免人格名和席位混淆。 */
export function displaySpeakerName(message, debate) {
  const seat = debaterPositionLabel(message?.speaker_id, debate?.agents || []);
  if (seat) return seat;
  if (message?.side === "judge" || /裁判/.test(message?.speaker_name || "")) return "裁判";
  if (message?.side === "assistant") return "系统";
  return message?.speaker_name || "系统";
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
  const scoreAff = Number(debate.score?.affirmative || 0);
  const scoreNeg = Number(debate.score?.negative || 0);
  const messages = debate.messages || [];
  const publicCount = messages.filter((m) => isPublicStageMessage(m)).length;
  const internalCount = messages.filter((m) => isTeamDiscussion(m)).length;
  const winner =
    scoreAff === scoreNeg
      ? "暂未分出优势方"
      : scoreAff > scoreNeg
        ? `正方暂时领先 ${(scoreAff - scoreNeg).toFixed(2)} 分`
        : `反方暂时领先 ${(scoreNeg - scoreAff).toFixed(2)} 分`;
  const lines = [
    "# AI辩论场复盘报告",
    "",
    `> 辩题：**${debate.topic || "未命名辩题"}**`,
    "",
    "## 一、报告摘要",
    "",
    `本报告整理了本场辩论的基础设置、阵容、关键比分与发言纪要，便于赛后阅读、复盘和归档。${winner}。`,
    "",
    "## 二、关键指标",
    "",
    "| 指标 | 内容 |",
    "| --- | --- |",
    `| 模式 | ${debate.mode || "未记录"} |`,
    `| 当前环节 | ${debate.phase || "未记录"} / ${debate.segment_label || "未记录"} |`,
    `| 赛制 | ${debate.schedule_template || "默认赛制"} |`,
    `| 比分 | 正方 ${scoreAff.toFixed(2)} · 反方 ${scoreNeg.toFixed(2)} |`,
    `| 发言统计 | 公开 ${publicCount} 条 · 队内 ${internalCount} 条 · 总计 ${messages.length} 条 |`,
    `| 导出时间 | ${new Date().toLocaleString("zh-CN", { hour12: false })} |`,
    "",
    "## 三、阵容",
    "",
    "| 席位 | 名称 | 模型 |",
    "| --- | --- | --- |",
  ];
  for (const agent of (debate.agents || []).filter((agent) => agent.side !== "assistant")) {
    lines.push(`| ${agentSeatLabel(agent) || agent.name || "未命名席位"} | ${agent.name || "未命名"} | ${agent.model || "未记录"} |`);
  }
  if (!(debate.agents || []).length) {
    lines.push("| 未记录 | 未记录 | 未记录 |");
  }
  lines.push("");

  if (debate.match_summary) {
    lines.push("## 四、全场总结", "", debate.match_summary.trim(), "");
  } else {
    lines.push("## 四、全场总结", "", "本场暂未生成全场总结。", "");
  }

  lines.push("## 五、发言纪要", "");
  if (!messages.length) {
    lines.push("本场暂未产生发言记录。", "");
  }
  messages.forEach((m, index) => {
    const scope = isTeamDiscussion(m) ? "队内讨论" : isJudgeThought(m) ? "裁判思考" : "公开发言";
    const speaker = displaySpeakerName(m, debate);
    lines.push(`### ${index + 1}. ${speaker}｜${m.segment_label || m.phase || "未命名环节"}`, "");
    lines.push(`范围：${scope} · 阵营：${m.side || "未记录"}${m.score_delta != null ? ` · 本轮得分 ${Number(m.score_delta).toFixed(2)}` : ""}`);
    lines.push("");
    lines.push((m.content || "").trim() || "（本条发言为空）");
    if (m.score_reason) {
      lines.push("", `> 评分理由：${m.score_reason}`);
    }
    if (m.sources?.length) {
      lines.push("", "**引用资料**");
      for (const source of m.sources) {
        lines.push(`- \`[${source.id || "source"}]\` ${source.title || "未命名资料"}：${source.excerpt || "无摘要"}`);
      }
    }
    lines.push("");
  });

  const verdicts = messages.filter((m) => m.side === "judge" && (m.segment_label || "").includes("输出裁判报告"));
  if (verdicts.length) {
    lines.push("## 六、裁判报告", "");
    for (const m of verdicts) {
      lines.push((m.content || "").trim(), "");
    }
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
