import assert from "node:assert/strict";
import { buildClientHistoryMarkdown } from "../../utils/debateDisplay.js";
import { resolveCurrentRoundSpeaker } from "./currentRoundSpeaker.js";
import {
  onlineMatchHasStarted,
  shouldShowOnlineWaitingBanner,
} from "./onlineWaitingBanner.js";

const waitingDebate = {
  mode: "online_match",
  online_ready: true,
  online_has_guest: false,
  phase: "pre_match",
  schedule_index: 0,
  turn_index: 0,
  messages: [],
};

assert.equal(onlineMatchHasStarted(waitingDebate), false);
assert.equal(shouldShowOnlineWaitingBanner(waitingDebate, 1), true);

assert.equal(
  shouldShowOnlineWaitingBanner(
    {
      ...waitingDebate,
      phase: "opening_prep",
      schedule_index: 3,
      turn_index: 3,
      messages: [{ side: "judge", content: "开场" }],
    },
    1,
  ),
  false,
);

const speakerDebate = {
  active_speaker_id: "neg_2",
  agents: [
    { id: "aff_1", side: "affirmative", position: 1, name: "云汐" },
    { id: "neg_2", side: "negative", position: 2, name: "砚秋" },
    { id: "judge", side: "judge", name: "裁判" },
  ],
};

assert.equal(resolveCurrentRoundSpeaker(speakerDebate)?.id, "neg_2");
assert.equal(
  resolveCurrentRoundSpeaker({ agents: speakerDebate.agents }, { id: "aff_1" })?.id,
  "aff_1",
);
assert.equal(resolveCurrentRoundSpeaker({ agents: speakerDebate.agents })?.id, "judge");

const report = buildClientHistoryMarkdown({
  topic: "人工智能是否应进入课堂",
  mode: "online_match",
  phase: "finished",
  segment_label: "赛后复盘",
  schedule_template: "standard",
  score: { affirmative: 3.5, negative: 2.25 },
  agents: speakerDebate.agents,
  messages: [
    {
      id: "m1",
      speaker_id: "aff_1",
      speaker_name: "云汐",
      side: "affirmative",
      phase: "opening_statement",
      segment_label: "正方一辩立论",
      content: "课堂需要更好的反馈。",
      score_delta: 0.5,
      score_reason: "引用清楚",
      sources: [{ id: "kb-class", title: "课堂研究", excerpt: "反馈有助于学习。" }],
    },
  ],
});

assert.match(report, /# AI辩论场复盘报告/);
assert.match(report, /## 一、报告摘要/);
assert.match(report, /## 五、发言纪要/);
assert.match(report, /正方一辩/);
assert.match(report, /\[kb-class\]/);

assert.equal(
  shouldShowOnlineWaitingBanner(
    {
      ...waitingDebate,
      online_has_guest: true,
    },
    2,
  ),
  false,
);
