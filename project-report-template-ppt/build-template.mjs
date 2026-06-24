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
const sharedDir = path.join(root, "shared");
const outputDir = path.join(root, "output");

fs.mkdirSync(slidesDir, { recursive: true });
fs.mkdirSync(sharedDir, { recursive: true });
fs.mkdirSync(outputDir, { recursive: true });

const deckTitle = "AI辩论场项目展示模板";
const slides = [
  {
    file: "01-title.html",
    label: "标题",
    section: "PROJECT TEMPLATE",
    title: "AI辩论场",
    subtitle: "项目展示模板",
    type: "cover",
  },
  {
    file: "02-origin.html",
    label: "项目制作缘由",
    section: "01",
    title: "项目制作缘由",
    type: "blank",
  },
  {
    file: "03-function.html",
    label: "功能基本介绍",
    section: "02",
    title: "功能基本介绍",
    type: "function",
    cards: [
      ["创建辩论房间", "输入辩题后选择 AI 自主、人机参与或多人联机模式，并锁定赛制、计时、可见性等比赛规则。"],
      ["标准 4v4 流程", "系统按立论、驳论、质辩、自由辩论、总结陈词和裁判报告推进，自动维护当前环节与发言人。"],
      ["论据库与检索", "赛前和赛中持续检索真实事实、案例和数据，形成正反方论据库，公开发言必须引用本方论据 ID。"],
      ["AI 辩手协作", "正反双方各 4 名 AI 辩手按席位分工发言，队内讨论只对本方可见，避免公开发言和内部策略混杂。"],
      ["用户/联机参与", "用户可加入指定辩位；联机模式下房主开启房间，宾客选座，轮到真人时系统暂停等待发言。"],
      ["复盘与导出", "系统保留发言记录、比分、裁判理由、工作流进度和论据来源，支持回放、分享与报告导出。"],
    ],
  },
  {
    file: "04-highlights.html",
    label: "项目亮点",
    section: "03",
    title: "项目亮点",
    type: "blank",
  },
  {
    file: "05-development.html",
    label: "开发历程",
    section: "04",
    title: "开发历程",
    type: "timeline",
  },
  {
    file: "06-interview.html",
    label: "辩论社员访谈",
    section: "05",
    title: "辩论社员访谈",
    type: "interview",
  },
  {
    file: "07-improve.html",
    label: "改进",
    section: "06",
    title: "改进",
    type: "blank",
  },
  {
    file: "08-closing.html",
    label: "结尾",
    section: "END",
    title: "结尾",
    type: "closing",
  },
];

const css = `
* { box-sizing: border-box; }
html, body {
  width: 1920px;
  height: 1080px;
  margin: 0;
  overflow: hidden;
  background: #f0eadf;
  color: #211b16;
  font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
}
body {
  background:
    linear-gradient(90deg, rgba(33,83,87,.08) 1px, transparent 1px) 0 0 / 64px 64px,
    linear-gradient(0deg, rgba(33,83,87,.06) 1px, transparent 1px) 0 0 / 64px 64px,
    radial-gradient(circle at 18% 16%, rgba(141,51,40,.16), transparent 28%),
    radial-gradient(circle at 78% 72%, rgba(33,83,87,.14), transparent 30%),
    #f3ecdf;
}
.slide {
  position: relative;
  width: 1920px;
  height: 1080px;
  padding: 90px 118px 78px;
}
.slide::before {
  content: "";
  position: absolute;
  inset: 34px;
  border: 1px solid rgba(33,27,22,.16);
  pointer-events: none;
}
.masthead {
  position: absolute;
  top: 48px;
  left: 118px;
  right: 118px;
  display: flex;
  justify-content: space-between;
  color: rgba(33,27,22,.55);
  font-size: 18px;
  letter-spacing: .14em;
  text-transform: uppercase;
}
.footer {
  position: absolute;
  left: 118px;
  right: 118px;
  bottom: 42px;
  display: flex;
  justify-content: space-between;
  color: rgba(33,27,22,.46);
  font-size: 18px;
}
.section {
  margin-top: 66px;
  display: flex;
  align-items: center;
  gap: 18px;
  color: #8d3328;
  font-size: 24px;
  font-weight: 800;
  letter-spacing: .16em;
}
.section::before {
  content: "";
  width: 80px;
  height: 3px;
  background: #8d3328;
}
h1 {
  margin: 28px 0 0;
  max-width: 1360px;
  color: #211b16;
  font-family: "SimSun", "Songti SC", "Noto Serif CJK SC", serif;
  font-size: 96px;
  line-height: 1.08;
  letter-spacing: 0;
}
.cover h1 {
  margin-top: 160px;
  font-size: 170px;
}
.subtitle {
  margin-top: 28px;
  font-size: 42px;
  color: rgba(33,27,22,.76);
}
.blank-grid {
  margin-top: 72px;
  display: grid;
  grid-template-columns: 1.08fr .92fr;
  gap: 42px;
}
.blank-box {
  min-height: 470px;
  border: 2px dashed rgba(33,27,22,.24);
  background: rgba(255,250,240,.48);
  padding: 34px;
}
.blank-box.small { min-height: 220px; }
.blank-label {
  color: rgba(33,27,22,.42);
  font-size: 26px;
}
.function-grid {
  margin-top: 52px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
}
.card {
  min-height: 250px;
  padding: 30px 30px 26px;
  border: 1px solid rgba(33,27,22,.15);
  background: rgba(255,250,240,.64);
  box-shadow: 0 18px 42px rgba(54,42,28,.10);
}
.card h2 {
  margin: 0;
  color: #215357;
  font-size: 34px;
  line-height: 1.24;
}
.card p {
  margin: 18px 0 0;
  color: rgba(33,27,22,.78);
  font-size: 25px;
  line-height: 1.55;
}
.timeline {
  margin-top: 72px;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 24px;
}
.step {
  min-height: 410px;
  border: 2px dashed rgba(33,27,22,.22);
  background: rgba(255,250,240,.48);
  padding: 30px;
}
.step strong {
  display: block;
  color: #8d3328;
  font-size: 34px;
  margin-bottom: 26px;
}
.interview-layout {
  margin-top: 68px;
  display: grid;
  grid-template-columns: 360px 1fr;
  gap: 42px;
}
.portrait {
  min-height: 470px;
  border: 2px dashed rgba(33,27,22,.22);
  background: rgba(255,250,240,.48);
}
.quote-lines {
  display: grid;
  gap: 22px;
}
.quote-line {
  min-height: 134px;
  border: 2px dashed rgba(33,27,22,.22);
  background: rgba(255,250,240,.48);
  padding: 28px;
}
.closing {
  background: #211b16;
  color: #f8ead8;
}
.closing::before { border-color: rgba(248,234,216,.25); }
.closing .masthead, .closing .footer { color: rgba(248,234,216,.56); }
.closing h1 { color: #f8ead8; font-size: 130px; }
.closing .section { color: #d8ad58; }
.closing .section::before { background: #d8ad58; }
`;

fs.writeFileSync(path.join(sharedDir, "template.css"), css);

function shell(item, index, inner, extraClass = "") {
  return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>${item.label}</title>
<link rel="stylesheet" href="../shared/template.css" />
</head>
<body>
<main class="slide ${extraClass}">
  <div class="masthead"><span>${deckTitle}</span><span>${item.section}</span></div>
  ${inner}
  <div class="footer"><span>${item.label}</span><span>${String(index + 1).padStart(2, "0")} / ${String(slides.length).padStart(2, "0")}</span></div>
</main>
</body>
</html>`;
}

function renderSlide(item, index) {
  if (item.type === "cover") {
    return shell(
      item,
      index,
      `<div class="section">${item.section}</div><h1>${item.title}</h1><div class="subtitle">${item.subtitle}</div>`,
      "cover",
    );
  }
  if (item.type === "function") {
    return shell(
      item,
      index,
      `<div class="section">${item.section}</div><h1>${item.title}</h1><div class="function-grid">${item.cards
        .map(([title, body]) => `<section class="card"><h2>${title}</h2><p>${body}</p></section>`)
        .join("")}</div>`,
    );
  }
  if (item.type === "timeline") {
    return shell(
      item,
      index,
      `<div class="section">${item.section}</div><h1>${item.title}</h1><div class="timeline">
        ${["阶段一", "阶段二", "阶段三", "阶段四"].map((label) => `<div class="step"><strong>${label}</strong><div class="blank-label">填写开发节点、问题、解决方式</div></div>`).join("")}
      </div>`,
    );
  }
  if (item.type === "interview") {
    return shell(
      item,
      index,
      `<div class="section">${item.section}</div><h1>${item.title}</h1><div class="interview-layout">
        <div class="portrait"></div>
        <div class="quote-lines">
          <div class="quote-line"><div class="blank-label">访谈对象 / 背景</div></div>
          <div class="quote-line"><div class="blank-label">核心反馈</div></div>
          <div class="quote-line"><div class="blank-label">对项目的启发</div></div>
        </div>
      </div>`,
    );
  }
  if (item.type === "closing") {
    return shell(
      item,
      index,
      `<div class="section">${item.section}</div><h1>${item.title}</h1><div class="subtitle">填写感谢语 / 联系方式 / 结束语</div>`,
      "closing",
    );
  }
  return shell(
    item,
    index,
    `<div class="section">${item.section}</div><h1>${item.title}</h1><div class="blank-grid">
      <div class="blank-box"><div class="blank-label">填写主要内容</div></div>
      <div>
        <div class="blank-box small"><div class="blank-label">图片 / 截图 / 证据</div></div>
        <div class="blank-box small" style="margin-top:30px"><div class="blank-label">补充要点</div></div>
      </div>
    </div>`,
  );
}

for (const [index, item] of slides.entries()) {
  fs.writeFileSync(path.join(slidesDir, item.file), renderSlide(item, index));
}

fs.writeFileSync(
  path.join(root, "deck-manifest.json"),
  JSON.stringify(slides.map(({ file, label, section, title }) => ({ file, label, section, title })), null, 2),
);

fs.writeFileSync(
  path.join(root, "index.html"),
  `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>${deckTitle}</title>
<style>
html, body { margin: 0; min-height: 100%; background: #211b16; font-family: Microsoft YaHei, sans-serif; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 22px; padding: 36px; }
iframe { width: 100%; aspect-ratio: 16 / 9; border: 0; background: #f3ecdf; transform-origin: top left; }
.card { background: #2d251d; padding: 12px; color: #f8ead8; }
.label { padding: 8px 2px 0; font-size: 15px; color: rgba(248,234,216,.72); }
</style>
</head>
<body>
<div class="grid">
${slides.map((s, i) => `<div class="card"><iframe src="slides/${s.file}"></iframe><div class="label">${i + 1}. ${s.label}</div></div>`).join("\n")}
</div>
</body>
</html>`,
);

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

for (let i = 0; i < slides.length; i += 1) {
  const item = slides[i];
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  await page.goto(pathToFileURL(path.join(slidesDir, item.file)).href, { waitUntil: "networkidle" });
  await page.waitForTimeout(150);
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

const pdfOut = path.join(outputDir, "AI辩论场-项目报告-模板版.pdf");
fs.writeFileSync(pdfOut, await merged.save());

const pptx = new pptxgen();
pptx.defineLayout({ name: "LAYOUT_WIDE", width: 13.333, height: 7.5 });
pptx.layout = "LAYOUT_WIDE";
pptx.author = "AI Debate Arena";
pptx.company = "江门市第一中学";
pptx.subject = "AI辩论场项目展示模板";
pptx.title = "AI辩论场-项目报告-模板版";
pptx.lang = "zh-CN";
pptx.theme = {
  headFontFace: "Microsoft YaHei",
  bodyFontFace: "Microsoft YaHei",
  lang: "zh-CN",
};

for (const screenshotPath of screenshots) {
  const slide = pptx.addSlide();
  slide.background = { color: "F3ECDF" };
  slide.addImage({ path: screenshotPath, x: 0, y: 0, w: 13.333, h: 7.5 });
}

const pptxOut = path.join(outputDir, "AI辩论场-项目报告-模板版.pptx");
await pptx.writeFile({ fileName: pptxOut });

fs.writeFileSync(
  path.join(root, "README.md"),
  `# AI辩论场项目报告模板版

- HTML 演示入口：index.html
- PPTX：output/AI辩论场-项目报告-模板版.pptx
- PDF：output/AI辩论场-项目报告-模板版.pdf

本模板共 8 页：标题、项目制作缘由、功能基本介绍、项目亮点、开发历程、辩论社员访谈、改进、结尾。除“功能基本介绍”页外，其余页面只保留标题和空白版式。
`,
);

console.log(JSON.stringify({ slides: slides.length, pdf: pdfOut, pptx: pptxOut }, null, 2));
