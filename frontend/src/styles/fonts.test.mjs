import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const stylesDir = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(stylesDir, "../..");
const fontsCssPath = resolve(stylesDir, "fonts.css");
const fontAssetDir = resolve(frontendDir, "src/assets/fonts/google-sans");

const css = readFileSync(fontsCssPath, "utf8");

assert.ok(existsSync(fontAssetDir), "expected local google-sans font asset directory");

for (const fileName of [
  "GoogleSansChinese-300.ttf",
  "GoogleSansChinese-400.ttf",
  "GoogleSansChinese-500.ttf",
  "GoogleSansChinese-600.ttf",
  "GoogleSansChinese-700.ttf",
  "GoogleSansChinese-800.ttf",
]) {
  assert.ok(existsSync(resolve(fontAssetDir, fileName)), `expected local font file ${fileName}`);
  assert.match(css, new RegExp(`\\.\\./assets/fonts/google-sans/${fileName}`));
}

for (const fileName of [
  "NotoSansSCSubset-300.ttf",
  "NotoSansSCSubset-400.ttf",
  "NotoSansSCSubset-500.ttf",
  "NotoSansSCSubset-600.ttf",
  "NotoSansSCSubset-700.ttf",
  "NotoSansSCSubset-800.ttf",
]) {
  assert.ok(existsSync(resolve(fontAssetDir, fileName)), `expected local Chinese subset file ${fileName}`);
  assert.match(css, new RegExp(`\\.\\./assets/fonts/google-sans/${fileName}`));
}

assert.match(css, /font-family:\s*"Google Sans Chinese"/);
assert.match(css, /--font-ui-sans:\s*"Google Sans Chinese"/);
assert.match(css, /--font-reading-serif:\s*"Google Sans Chinese"/);
assert.match(css, /--font-code-mono:\s*"Google Sans Chinese"/);
assert.doesNotMatch(css, /Anthropic|PingFang|Microsoft YaHei|Songti|Georgia|Noto Serif/);
