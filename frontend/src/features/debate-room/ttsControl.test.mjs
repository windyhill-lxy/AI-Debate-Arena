import assert from "node:assert/strict";
import { effectiveTtsEnabled, shouldAcceptIncomingTts } from "./ttsControl.js";

assert.equal(effectiveTtsEnabled(true, false), true, "remote enabled should allow TTS");
assert.equal(effectiveTtsEnabled(false, false), false, "remote disabled should stop TTS");
assert.equal(effectiveTtsEnabled(true, true), false, "local stop should override stale remote enabled snapshots");

assert.equal(
  shouldAcceptIncomingTts({ remoteTtsEnabled: true, locallyStopped: true, audioUrl: "data:audio/wav;base64,AA==" }),
  false,
  "late realtime audio deltas must be ignored after local stop",
);

assert.equal(
  shouldAcceptIncomingTts({ remoteTtsEnabled: true, locallyStopped: false, audioUrl: "" }),
  false,
  "empty audio payload should not enter the queue",
);

assert.equal(
  shouldAcceptIncomingTts({ remoteTtsEnabled: true, locallyStopped: false, audioUrl: "data:audio/wav;base64,AA==" }),
  true,
  "valid audio should play while TTS is enabled",
);

console.log("ttsControl tests passed");
