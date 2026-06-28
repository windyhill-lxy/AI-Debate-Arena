import fs from "node:fs/promises";
import path from "node:path";
import playwright from "../frontend/node_modules/playwright/index.js";

const { chromium } = playwright;

const [, , svgPath, pngPath, widthArg = "1120", heightArg = "310"] = process.argv;

if (!svgPath || !pngPath) {
  console.error("Usage: node tools/render_svg_png.mjs <svg> <png> [width] [height]");
  process.exit(2);
}

const width = Number(widthArg);
const height = Number(heightArg);
const svg = await fs.readFile(svgPath, "utf8");
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
await page.setContent(
  `<!doctype html><html><head><meta charset="utf-8"><style>
  html, body { margin: 0; width: ${width}px; height: ${height}px; overflow: hidden; background: transparent; }
  svg { display: block; width: ${width}px; height: ${height}px; }
  </style></head><body>${svg}</body></html>`,
);
await page.screenshot({ path: pngPath, omitBackground: true });
await browser.close();
console.log(path.resolve(pngPath));
