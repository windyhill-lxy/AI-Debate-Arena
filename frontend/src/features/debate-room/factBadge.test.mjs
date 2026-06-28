import assert from "node:assert/strict";
import { factBadgeForMessage } from "./factBadge.js";

const aiMessage = {
  side: "affirmative",
  content: "这里有 3 个理由。",
  sources: [],
};

assert.equal(
  factBadgeForMessage(aiMessage, { rag_review_mode: "essential" }),
  null,
  "essential RAG mode should not mark every sourceless numeric message as unverified",
);

assert.equal(
  factBadgeForMessage({ ...aiMessage, hallucination_risk: "high" }, { rag_review_mode: "essential" })?.text,
  "含数据待核实",
  "explicit high risk should still be visible",
);

assert.equal(
  factBadgeForMessage({ ...aiMessage, hallucination_risk: "medium" }, { rag_review_mode: "full" })?.text,
  "含数字未引用",
  "full review mode should show medium risk",
);

assert.equal(
  factBadgeForMessage({ ...aiMessage, sources: [{ id: "AFF1" }, { id: "AFF2" }] }, { rag_review_mode: "essential" })?.text,
  "已RAG核实 2 条",
  "messages with sources should show verified source count",
);

assert.equal(
  factBadgeForMessage({ side: "user", sources: [], hallucination_risk: "high" }, { rag_review_mode: "full" }),
  null,
  "user messages should not receive AI fact badges",
);

console.log("factBadge tests passed");
