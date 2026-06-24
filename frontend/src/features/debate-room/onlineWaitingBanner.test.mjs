import assert from "node:assert/strict";
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
