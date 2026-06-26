import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const projectRoot = process.cwd();
const frontendRoot = join(projectRoot, "frontend");
const fontDir = join(frontendRoot, "src", "assets", "fonts", "google-sans");
const weights = [300, 400, 500, 600, 700, 800];

function walk(dir, files = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const filePath = join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(filePath, files);
    } else if (/\.(jsx?|css|html|mjs)$/.test(entry.name)) {
      files.push(filePath);
    }
  }
  return files;
}

function collectChineseUiText() {
  const sourceFiles = walk(join(frontendRoot, "src"));
  const indexPath = join(frontendRoot, "index.html");
  if (existsSync(indexPath)) {
    sourceFiles.push(indexPath);
  }

  const characters = new Set();
  for (const filePath of sourceFiles) {
    const content = readFileSync(filePath, "utf8");
    for (const character of content) {
      const codePoint = character.codePointAt(0);
      if ((codePoint >= 0x3400 && codePoint <= 0x9fff) || (codePoint >= 0xf900 && codePoint <= 0xfaff)) {
        characters.add(character);
      }
    }
  }

  return [...characters].sort().join("");
}

async function download(url) {
  const response = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
  if (!response.ok) {
    throw new Error(`Failed to download ${url}: ${response.status} ${response.statusText}`);
  }
  return Buffer.from(await response.arrayBuffer());
}

async function getGoogleFontsFileUrl(cssUrl) {
  const css = (await download(cssUrl)).toString("utf8");
  const match = css.match(/url\((https:\/\/fonts\.gstatic\.com\/[^)]+)\)/);
  if (!match) {
    throw new Error(`No font file URL found in CSS from ${cssUrl}`);
  }
  return match[1];
}

mkdirSync(fontDir, { recursive: true });

const chineseUiText = collectChineseUiText();
if (!chineseUiText) {
  throw new Error("No Chinese UI text found to build the local subset");
}

for (const weight of weights) {
  const cssUrl =
    `https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@${weight}` +
    `&text=${encodeURIComponent(chineseUiText)}&display=swap`;
  const fontUrl = await getGoogleFontsFileUrl(cssUrl);
  const font = await download(fontUrl);
  const fileName = `NotoSansSCSubset-${weight}.ttf`;
  writeFileSync(join(fontDir, fileName), font);
  console.log(`${fileName}: ${font.length} bytes`);
}

writeFileSync(
  join(fontDir, "manifest.txt"),
  [
    "Google Sans Chinese local font bundle",
    "",
    "Latin: Google Sans Flex from Google Fonts CSS API.",
    "Chinese UI subset: Noto Sans SC from Google Fonts CSS API, generated from frontend source Chinese characters.",
    "Google Fonts FAQ states Google Sans and Google Sans Flex are available under the SIL Open Font License.",
    "Noto Sans SC is part of Google Fonts / Noto and is used here for Simplified Chinese coverage.",
    `Chinese subset glyph count: ${chineseUiText.length}`,
    "",
    "Downloaded on 2026-06-24.",
  ].join("\n"),
);
