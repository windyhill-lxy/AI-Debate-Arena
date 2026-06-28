import assert from "node:assert/strict";
import { canStartQueuedAudio } from "./audioQueueControl.js";

assert.equal(
  canStartQueuedAudio({ playing: false, disabled: false, paused: false, hasActiveAudio: false }),
  true,
  "idle queue should be allowed to start",
);

assert.equal(
  canStartQueuedAudio({ playing: true, disabled: false, paused: false, hasActiveAudio: true }),
  false,
  "new TTS must not start while another audio is playing",
);

assert.equal(
  canStartQueuedAudio({ playing: false, disabled: false, paused: false, hasActiveAudio: true }),
  false,
  "active Audio object should lock playback even if playing flag is briefly stale",
);

assert.equal(
  canStartQueuedAudio({ playing: false, disabled: true, paused: false, hasActiveAudio: false }),
  false,
  "disabled queue should not start",
);

assert.equal(
  canStartQueuedAudio({ playing: false, disabled: false, paused: true, hasActiveAudio: false }),
  false,
  "paused queue should not start new audio",
);

console.log("audioQueueControl tests passed");
