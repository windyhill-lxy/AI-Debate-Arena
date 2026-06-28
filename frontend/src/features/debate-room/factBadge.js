export function factBadgeForMessage(message, debate) {
  const risk = message?.hallucination_risk;
  const srcCount = message?.sources?.length || 0;
  const isAI = message?.side === "affirmative" || message?.side === "negative" || message?.side === "judge";
  if (!isAI) return null;

  if (srcCount > 0) {
    return {
      tone: "low",
      title: "已通过RAG向量库检索核实",
      text: `已RAG核实 ${srcCount} 条`,
    };
  }

  const reviewMode = debate?.rag_review_mode || "essential";
  if (reviewMode !== "full" && !risk) {
    return null;
  }

  if (risk === "high") {
    return {
      tone: "high",
      title: "含数据或引用但无来源支撑，可能存在幻觉",
      text: "含数据待核实",
    };
  }

  if (risk === "medium") {
    return {
      tone: "medium",
      title: "含数字但无RAG来源支撑",
      text: "含数字未引用",
    };
  }

  if (reviewMode === "full") {
    return {
      tone: "none",
      title: "本轮完整复核未发现外部引用",
      text: "未引用资料",
    };
  }

  return null;
}
