import assert from "node:assert/strict";
import { canResumeDebate, onlineRoomCanAutoStart } from "./progressControl.js";

const baseDebate = {
  mode: "online_match",
  phase: "opening_statement",
  segment_label: "正方一辩立论",
  active_speaker_id: "aff_1",
  auto_running: false,
  awaiting_user: true,
  online_ready: true,
  online_connected_debaters: 1,
  participants: [{ id: "p1", side: "affirmative", position: 1, connected: true }],
};

const participant = { id: "p1", side: "affirmative", position: 1, connected: true };

const speechState = { canSubmit: true, isYourTurn: true };

assert.equal(canResumeDebate({ debate: baseDebate, awaitingUser: true, speechInputState: speechState, isLocal: false }), false);

const waitingForGuest = {
  ...baseDebate,
  phase: "pre_match",
  segment_label: "赛前准备 · 主持开场",
  active_speaker_id: "judge",
  awaiting_user: false,
  online_connected_debaters: 1,
};

assert.equal(
  canResumeDebate({
    debate: waitingForGuest,
    awaitingUser: false,
    speechInputState: { canSubmit: false, isYourTurn: false },
    isLocal: false,
  }),
  false,
);
assert.equal(onlineRoomCanAutoStart(waitingForGuest), false);

const waitingForAi = {
  ...baseDebate,
  active_speaker_id: "judge",
  awaiting_user: false,
  online_connected_debaters: 2,
};

assert.equal(
  canResumeDebate({
    debate: waitingForAi,
    awaitingUser: false,
    speechInputState: { canSubmit: false, isYourTurn: false },
    isLocal: false,
  }),
  true,
);
