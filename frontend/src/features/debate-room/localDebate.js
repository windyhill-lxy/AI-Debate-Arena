import { demoAgents, formalSchedulePreview, workflow } from "../../data/agents";
import { INITIAL_DEMO_MESSAGES } from "./constants.js";

export function createLocalDebate(topic, mode) {
  return {
    id: "demo-room",
    topic,
    mode: mode || "ai_autonomous",
    visibility: "context",
    timing: "limited",
    awaiting_user: false,
    auto_running: false,
    phase: "pre_match",
    segment_label: "赛前介绍",
    segment_rules: "主席介绍辩题、双方、评委与规则。",
    segment_seconds: 60,
    schedule_index: 0,
    turn_index: 0,
    active_speaker_id: "judge",
    schedule: formalSchedulePreview.map((item, index) => ({
      index,
      id: `preview_${index}`,
      label: item.label,
      phase: item.phase,
      seconds: item.seconds,
      speakerId: item.speakerId,
      status: index === 0 ? "current" : "pending",
    })),
    agents: demoAgents,
    messages: INITIAL_DEMO_MESSAGES,
    score: { affirmative: 0, negative: 0 },
    workflow: workflow.map(([id, label, detail, stage, kind], index) => ({
      id,
      label,
      detail,
      stage,
      kind: kind || (index % 3 === 0 ? "llm" : index % 3 === 1 ? "action" : "retrieval"),
      status: index < 2 ? "done" : index === 2 ? "running" : "pending",
    })),
  };
}
