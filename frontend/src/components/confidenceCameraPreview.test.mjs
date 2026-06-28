import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const source = readFileSync(resolve(root, "src/components/ConfidenceCameraPreview.jsx"), "utf8");

assert.match(source, /confidence-camera__realtime-grid/, "camera preview should render a realtime multi-dimensional grid");
assert.match(source, /神态/, "camera preview should show expression/state data");
assert.match(source, /动作/, "camera preview should show gesture/action data");
assert.match(source, /计分预估/, "camera preview should show live scoring estimate");
assert.match(source, /发言结束后计入本轮分数/, "camera preview should explain that camera data is scored after speech");
assert.match(source, /confidence-camera__advice/, "camera preview should render realtime advice");
assert.match(source, /onStart/, "camera preview should expose a start action when the backend monitor is stopped");
assert.match(source, /启动摄像头/, "camera preview should label the start action clearly");
