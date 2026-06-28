import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "../");
const useLocalCamera = readFileSync(resolve(root, "src/hooks/useLocalCamera.js"), "utf8");
const confidencePreview = readFileSync(resolve(root, "src/components/ConfidenceCameraPreview.jsx"), "utf8");
const home = readFileSync(resolve(root, "src/pages/Home.jsx"), "utf8");
const floating = readFileSync(resolve(root, "src/components/FloatingConfidenceCamera.jsx"), "utf8");

assert.match(useLocalCamera, /width:\s*\{\s*ideal:\s*320\s*\}/, "local camera should default to 320px width");
assert.match(useLocalCamera, /height:\s*\{\s*ideal:\s*240\s*\}/, "local camera should default to 240px height");
assert.match(useLocalCamera, /frameRate:\s*\{\s*ideal:\s*15,\s*max:\s*15\s*\}/, "local camera should cap frame rate at 15fps");

assert.match(confidencePreview, /PREVIEW_REFRESH_MS\s*=\s*2200/, "confidence preview should refresh below 0.5fps");
assert.match(confidencePreview, /STATUS_REFRESH_MS\s*=\s*3500/, "confidence status polling should be throttled");
assert.match(confidencePreview, /document\.hidden/, "confidence preview should pause while page is hidden");
assert.match(
  confidencePreview,
  /confidence-camera__readout/,
  "multidimensional scores should render below the video viewport",
);
const viewportStart = confidencePreview.indexOf('className="confidence-camera__viewport"');
const readoutStart = confidencePreview.indexOf('className="confidence-camera__readout"');
assert.ok(viewportStart > 0 && readoutStart > viewportStart, "readout should render after the video viewport");
const viewportMarkup = confidencePreview.slice(viewportStart, readoutStart);
assert.doesNotMatch(viewportMarkup, /计分预估|综合|眼神|手势/, "scores should not be part of the in-video markup");

assert.match(home, /useState\(true\)/, "home camera low performance mode should default on");
assert.match(floating, /low_performance:\s*true/, "floating camera toggle should keep classroom mode on");
