import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "../../..");
const source = readFileSync(resolve(root, "src/features/debate-room/hooks/useDebateRoom.js"), "utf8");

assert.match(source, /sendMessage\s*=\s*useCallback\(async\s*\(\s*contentOverride/, "sendMessage should accept recognized speech text directly");
assert.match(source, /await\s+sendMessage\(nextDraft\)/, "speech recognition should submit immediately after ASR succeeds");
assert.match(source, /正在提交发言/, "speech input should tell the user that auto-submit is happening");
