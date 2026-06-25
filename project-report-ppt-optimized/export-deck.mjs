import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("../.claude/skills/huashu-design/node_modules/playwright");
const { PDFDocument } = require("../.claude/skills/huashu-design/node_modules/pdf-lib");
const pptxgen = require("../.claude/skills/huashu-design/node_modules/pptxgenjs");

const root = path.dirname(fileURLToPath(import.meta.url));
const slidesDir = path.join(root, "slides");
const outputDir = path.join(root, "output");
const manifest = JSON.parse(fs.readFileSync(path.join(root, "deck-manifest.json"), "utf8"));

fs.mkdirSync(outputDir, { recursive: true });

async function launchBrowser() {
  try {
    return await chromium.launch({ channel: "msedge" });
  } catch {
    return await chromium.launch();
  }
}

const browser = await launchBrowser();
const merged = await PDFDocument.create();
const screenshots = [];

for (let i = 0; i < manifest.length; i += 1) {
  const item = manifest[i];
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const fileUrl = pathToFileURL(path.join(slidesDir, item.file)).href;
  await page.goto(fileUrl, { waitUntil: "networkidle" });
  await page.emulateMedia({ media: "screen" });
  await page.waitForTimeout(250);

  const screenshotPath = path.join(outputDir, `slide-${String(i + 1).padStart(2, "0")}.png`);
  await page.screenshot({ path: screenshotPath, fullPage: false });
  screenshots.push(screenshotPath);

  const pdfBytes = await page.pdf({
    width: "1920px",
    height: "1080px",
    printBackground: true,
    margin: { top: 0, right: 0, bottom: 0, left: 0 },
  });
  const pdf = await PDFDocument.load(pdfBytes);
  const copied = await merged.copyPages(pdf, pdf.getPageIndices());
  copied.forEach((copiedPage) => merged.addPage(copiedPage));
  await page.close();
}

await browser.close();

const pdfOut = path.join(outputDir, "AI辩论场-项目报告-优化版.pdf");
fs.writeFileSync(pdfOut, await merged.save());

const pptx = new pptxgen();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "AI Debate Arena";
pptx.company = "江门市第一中学";
pptx.subject = "AI智能体开发专项赛项目报告";
pptx.title = "AI辩论场-项目报告-优化版";
pptx.lang = "zh-CN";
pptx.theme = {
  headFontFace: "Microsoft YaHei",
  bodyFontFace: "Microsoft YaHei",
  lang: "zh-CN",
};
pptx.defineLayout({ name: "LAYOUT_WIDE", width: 13.333, height: 7.5 });
pptx.layout = "LAYOUT_WIDE";

for (const screenshotPath of screenshots) {
  const slide = pptx.addSlide();
  slide.background = { color: "EEE4D2" };
  slide.addImage({ path: screenshotPath, x: 0, y: 0, w: 13.333, h: 7.5 });
}

const pptxOut = path.join(outputDir, "AI辩论场-项目报告-优化版.pptx");
await pptx.writeFile({ fileName: pptxOut });

console.log(JSON.stringify({ pdf: pdfOut, pptx: pptxOut, slides: screenshots.length }, null, 2));
