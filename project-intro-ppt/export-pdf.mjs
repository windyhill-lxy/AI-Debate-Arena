import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { writeFile } from "node:fs/promises";

const require = createRequire(import.meta.url);
const { chromium } = require("../.claude/skills/huashu-design/node_modules/playwright");
const { PDFDocument } = require("../.claude/skills/huashu-design/node_modules/pdf-lib");

const slides = [
  "01-cover.html",
  "02-real-problem.html",
  "03-result-overview.html",
  "04-user-journey.html",
  "05-architecture.html",
  "06-agents.html",
  "07-workflow.html",
  "08-kernel-loop.html",
  "09-anti-hallucination.html",
  "10-human-ai.html",
  "11-deployment.html",
  "12-engineering.html",
  "13-value.html",
];

const deckDir = path.dirname(fileURLToPath(import.meta.url));

const browser = await chromium.launch({ channel: "msedge" });
const merged = await PDFDocument.create();

for (const slide of slides) {
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  const fileUrl = pathToFileURL(path.join(deckDir, "slides", slide)).href;
  await page.goto(fileUrl, { waitUntil: "networkidle" });
  await page.emulateMedia({ media: "screen" });
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

const output = path.join(deckDir, "output", "AI辩论场项目介绍.pdf");
await writeFile(output, await merged.save());
console.log(output);
