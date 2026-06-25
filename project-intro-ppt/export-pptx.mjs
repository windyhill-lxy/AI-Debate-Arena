import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const pptxgen = require("../.claude/skills/huashu-design/node_modules/pptxgenjs");

const deckDir = path.dirname(fileURLToPath(import.meta.url));
const outputDir = path.join(deckDir, "output");
fs.mkdirSync(outputDir, { recursive: true });
const screenshotDir = "F:\\Project\\截图";
const imageExts = new Set([".png", ".jpg", ".jpeg", ".webp", ".bmp"]);

function listImages(dir) {
  if (!fs.existsSync(dir)) return [];
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listImages(full));
    if (entry.isFile() && imageExts.has(path.extname(entry.name).toLowerCase())) out.push(full);
  }
  return out;
}

const screenshotImages = listImages(screenshotDir);

const pptx = new pptxgen();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "AI Debate Arena";
pptx.company = "AI 辩论场";
pptx.subject = "多智能体思辨训练系统项目介绍";
pptx.title = "AI 辩论场项目介绍";
pptx.lang = "zh-CN";
pptx.theme = {
  headFontFace: "Microsoft YaHei",
  bodyFontFace: "Microsoft YaHei",
  lang: "zh-CN",
};
pptx.defineLayout({ name: "LAYOUT_WIDE", width: 13.333, height: 7.5 });
pptx.layout = "LAYOUT_WIDE";

const C = {
  ink: "221B15",
  muted: "6E6256",
  paper: "F3EADB",
  paper2: "FFF8ED",
  red: "8F2F22",
  blue: "1F4869",
  gold: "D7A84B",
  dark: "1D1813",
  white: "FFFFFF",
  line: "D8CBB7",
  sage: "789383",
};

const W = 13.333;
const H = 7.5;
const M = 0.62;

const coverImage = path.join(outputDir, "cover.png");
const overviewImage = path.join(outputDir, "overview.png");
const pickImage = (idx, fallback) => screenshotImages[idx] || fallback;

function addBg(slide, dark = false) {
  slide.background = { color: dark ? C.dark : C.paper };
  slide.addShape(pptx.ShapeType.rect, {
    x: 0.18,
    y: 0.18,
    w: W - 0.36,
    h: H - 0.36,
    fill: { color: dark ? C.dark : C.paper, transparency: 100 },
    line: { color: dark ? "5A4B3E" : C.line, transparency: 20, width: 0.8 },
  });
}

function mast(slide, left, right, dark = false) {
  slide.addText(left, {
    x: M,
    y: 0.28,
    w: 5.4,
    h: 0.18,
    fontSize: 7.8,
    charSpacing: 1.6,
    color: dark ? "C8BBAA" : "8A7B6B",
    margin: 0,
  });
  slide.addText(right, {
    x: W - 5.9,
    y: 0.28,
    w: 5.3,
    h: 0.18,
    fontSize: 7.8,
    charSpacing: 1.6,
    color: dark ? "C8BBAA" : "8A7B6B",
    align: "right",
    margin: 0,
  });
}

function kicker(slide, text, y = 0.9) {
  slide.addShape(pptx.ShapeType.line, {
    x: M,
    y: y + 0.12,
    w: 0.48,
    h: 0,
    line: { color: C.red, width: 1.4 },
  });
  slide.addText(text, {
    x: M + 0.62,
    y,
    w: 4.6,
    h: 0.28,
    fontSize: 10.5,
    bold: true,
    charSpacing: 1.3,
    color: C.red,
    margin: 0,
  });
}

function title(slide, text, y = 1.18, w = 8.8, color = C.ink, size = 33) {
  slide.addText(text, {
    x: M,
    y,
    w,
    h: 1.2,
    fontFace: "Microsoft YaHei",
    fontSize: size,
    bold: true,
    color,
    breakLine: false,
    fit: "shrink",
    margin: 0,
  });
}

function paragraph(slide, text, x, y, w, h, opts = {}) {
  slide.addText(text, {
    x,
    y,
    w,
    h,
    fontSize: opts.size || 15,
    color: opts.color || C.ink,
    breakLine: false,
    fit: "shrink",
    valign: "top",
    margin: opts.margin ?? 0.04,
    paraSpaceAfterPt: 8,
  });
}

function panel(slide, x, y, w, h, fill = C.paper2, line = C.line) {
  slide.addShape(pptx.ShapeType.rect, {
    x,
    y,
    w,
    h,
    fill: { color: fill },
    line: { color: line, transparency: 15, width: 0.7 },
    shadow: { type: "outer", color: "000000", opacity: 0.10, blur: 1.8, angle: 45, offset: 1.1 },
  });
}

function footer(slide, left = "AI Debate Arena", right = "Project Introduction") {
  slide.addText(left, {
    x: M,
    y: 7.08,
    w: 4.8,
    h: 0.18,
    fontSize: 7.8,
    charSpacing: 0.8,
    color: "978A7A",
    margin: 0,
  });
  slide.addText(right, {
    x: W - 5.4,
    y: 7.08,
    w: 4.8,
    h: 0.18,
    fontSize: 7.8,
    charSpacing: 0.8,
    color: "978A7A",
    align: "right",
    margin: 0,
  });
}

function addPlaceholder(slide, x, y, w, h, label, note) {
  slide.addShape(pptx.ShapeType.rect, {
    x,
    y,
    w,
    h,
    fill: { color: "FFFFFF", transparency: 12 },
    line: { color: C.red, width: 1.1, dash: "dash" },
  });
  slide.addText(label, {
    x: x + 0.22,
    y: y + 0.24,
    w: w - 0.44,
    h: 0.38,
    fontSize: 15,
    bold: true,
    color: C.red,
    margin: 0,
  });
  slide.addText(note, {
    x: x + 0.22,
    y: y + 0.78,
    w: w - 0.44,
    h: h - 1.0,
    fontSize: 11.2,
    color: C.muted,
    fit: "shrink",
    valign: "mid",
    margin: 0,
  });
}

function addImageIfExists(slide, imagePath, x, y, w, h, label, fallback) {
  if (imagePath && fs.existsSync(imagePath)) {
    slide.addImage({ path: imagePath, x, y, w, h, sizing: { type: "contain", x, y, w, h } });
    slide.addShape(pptx.ShapeType.rect, { x, y, w, h, fill: { color: "FFFFFF", transparency: 100 }, line: { color: C.line, transparency: 20, width: 0.7 } });
  } else {
    addPlaceholder(slide, x, y, w, h, label, fallback);
  }
}

function addPill(slide, text, x, y, w, fill = C.dark, color = C.white) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h: 0.36,
    rectRadius: 0.08,
    fill: { color: fill },
    line: { color: fill },
  });
  slide.addText(text, {
    x: x + 0.08,
    y: y + 0.08,
    w: w - 0.16,
    h: 0.12,
    fontSize: 7.8,
    bold: true,
    charSpacing: 0.6,
    color,
    align: "center",
    margin: 0,
  });
}

function addStat(slide, num, label, x, y, w, h) {
  panel(slide, x, y, w, h);
  slide.addText(num, { x: x + 0.22, y: y + 0.2, w: w - 0.44, h: 0.55, fontSize: 34, bold: true, color: C.blue, margin: 0 });
  slide.addText(label, { x: x + 0.22, y: y + 0.88, w: w - 0.44, h: h - 1.05, fontSize: 11.5, color: C.muted, fit: "shrink", margin: 0 });
}

function slideCover() {
  const s = pptx.addSlide();
  addBg(s);
  mast(s, "AI DEBATE ARENA", "PROJECT INTRODUCTION");
  kicker(s, "多智能体思辨训练系统");
  s.addText("AI 辩论场", { x: M, y: 1.35, w: 6.2, h: 0.8, fontSize: 42, bold: true, color: C.ink, margin: 0 });
  paragraph(s, "一套把正规 4v4 辩论赛制、LangGraph 工作流、RAG 引用校验与人机协同整合起来的训练系统。它不是让 AI 替学生辩论，而是让学生在可信、可复盘、可联机的环境里练习论证、反驳和表达。", M, 2.25, 7.0, 1.35, { size: 17.5, color: C.ink });
  const xs = [0.75, 2.95, 5.15, 7.35, 9.55];
  const heads = ["输入辩题", "组建辩队", "工作流运行", "实时对抗", "赛后复盘"];
  const desc = ["设置持方、赛制、资料与参与模式", "正反各四辩与裁判智能体协同推进", "检索、判断、反思、生成、核查、评分", "WebSocket 流式同步，人机与联机模式共用", "裁判报告、逐字稿导出与回放分享"];
  xs.forEach((x, i) => {
    panel(s, x, 4.05, 1.95, 1.2, "FBF5EA");
    s.addText(heads[i], { x: x + 0.18, y: 4.22, w: 1.58, h: 0.22, fontSize: 12.8, bold: true, color: C.red, margin: 0 });
    s.addText(desc[i], { x: x + 0.18, y: 4.58, w: 1.58, h: 0.42, fontSize: 9.4, color: C.muted, fit: "shrink", margin: 0 });
  });
  addImageIfExists(s, pickImage(0, coverImage), 8.35, 1.1, 3.9, 2.2, "封面截图待补", "可替换为系统首页或辩论室主界面截图。");
  footer(s, "Reality Problem · System Result · Innovation", "PPTX Version");
}

function slideProblem() {
  const s = pptx.addSlide();
  addBg(s);
  mast(s, "PROBLEM", "从真实训练场景出发");
  kicker(s, "为什么需要它");
  title(s, "辩论训练最难的，不是写稿，而是反复经历完整对抗。", 1.18, 6.8, C.ink, 30);
  paragraph(s, "学生需要对手、裁判、资料、赛程和反馈同时在线；普通 AI 聊天容易给出没有来源的“漂亮话”。训练一旦缺少可信事实和结构化复盘，就会变成临场背稿。", M, 2.55, 5.95, 1.22, { size: 15.5 });
  panel(s, 7.25, 1.35, 4.75, 4.7);
  s.addText("五个被系统直接回应的痛点", { x: 7.55, y: 1.68, w: 4.1, h: 0.3, fontSize: 18, bold: true, color: C.red, margin: 0 });
  paragraph(s, "缺陪练：很难随时凑齐正反双方和裁判。\n缺流程：自由聊天无法模拟正式赛制压力。\n缺可信资料：大模型可能编造引用、数据和法规。\n缺复盘：一次练习后难以沉淀逐字稿与战场变化。\n缺部署条件：学校机房和比赛现场常常不能安装复杂环境。", 7.55, 2.22, 4.05, 2.85, { size: 13.2 });
  s.addShape(pptx.ShapeType.rect, { x: M, y: 4.88, w: 6.2, h: 0.75, fill: { color: C.dark }, line: { color: C.dark } });
  s.addText("核心判断：把 AI 辩论做成“可验证的训练场”，比做一个会说话的聊天机器人更有价值。", { x: 0.92, y: 5.06, w: 5.6, h: 0.25, fontSize: 13.6, bold: true, color: C.white, fit: "shrink", margin: 0 });
  footer(s);
}

function slideInterview() {
  const s = pptx.addSlide();
  addBg(s);
  mast(s, "USER RESEARCH", "辩论社成员访谈");
  kicker(s, "需求调研补充");
  title(s, "我们把项目叙事从“技术炫技”改成“训练痛点驱动”。", 1.18, 8.7, C.ink, 30);
  paragraph(s, "面向辩论社成员的访谈应重点追问真实训练中的卡点：什么时候最缺人、什么时候最需要资料、赛后最希望看到什么反馈、AI 介入到什么程度才不破坏训练。以下为 PPT 中可展示的访谈洞察结构，具体姓名与原话可在正式提交前替换为真实记录。", M, 2.35, 7.15, 1.05, { size: 14.5 });

  const rows = [
    ["一辩/队长", "需要赛前快速拆题、分配论点，最好能看到资料来源。", "首页资料导入 + 立论前准备 + 论点分工确认"],
    ["二三辩", "最难的是临场追问和短兵相接，普通 AI 回答太长。", "盘问/自由辩短句模式 + 赛程计时 + 实时反驳检索"],
    ["四辩", "赛后想知道主战场在哪里，自己总结有没有覆盖关键争点。", "总结质量判断 + 终局裁判报告 + 逐字稿导出"],
    ["指导老师", "希望同学能练表达，但不能让 AI 直接代替发言。", "AI 教练给建议，用户保留最终提交权"]
  ];
  let y = 3.72;
  rows.forEach((r) => {
    panel(s, M, y, 11.8, 0.68, "FFF8ED");
    s.addText(r[0], { x: 0.86, y: y + 0.14, w: 1.35, h: 0.18, fontSize: 11.8, bold: true, color: C.red, margin: 0 });
    s.addText(r[1], { x: 2.25, y: y + 0.12, w: 4.15, h: 0.28, fontSize: 10.8, color: C.ink, fit: "shrink", margin: 0 });
    s.addText(r[2], { x: 6.85, y: y + 0.12, w: 4.95, h: 0.28, fontSize: 10.8, color: C.blue, fit: "shrink", margin: 0 });
    y += 0.82;
  });
  addPlaceholder(s, 10.15, 2.1, 2.25, 1.05, "访谈照片/记录待补", "建议插入辩论社访谈现场照片、问卷截图或匿名访谈摘录。");
  footer(s, "Interview Insight · Product Improvement", "用真实需求改进介绍");
}

function slideResult() {
  const s = pptx.addSlide();
  addBg(s);
  mast(s, "RESULT", "完整系统而非单点 Demo");
  kicker(s, "项目已经做成什么");
  title(s, "AI 辩论场把“辩题输入”到“裁判报告”的全链路跑通。", 1.18, 8.4, C.ink, 30);
  paragraph(s, "系统支持 AI 自主辩论、用户加入正方、用户加入反方和多人联机模式。每次发言经过 RAG 检索、策略规划、方向判断、反思生成、事实核查、发布和裁判评分，而不是一次普通的文本生成。", M, 2.38, 6.0, 1.3, { size: 14.8 });
  addStat(s, "9", "正反各四辩 + 紫苑裁判，形成完整辩论角色阵容。", 7.15, 2.0, 2.15, 1.25);
  addStat(s, "40", "前端展示工作流节点，覆盖准备、攻防、总结与裁决。", 9.55, 2.0, 2.15, 1.25);
  addStat(s, "9", "LangGraph 运行时节点，构成单回合智能体内核。", 7.15, 3.55, 2.15, 1.25);
  addStat(s, "4", "AI 自主、人机正方、人机反方、联机多人四类场景。", 9.55, 3.55, 2.15, 1.25);
  addImageIfExists(s, pickImage(1, overviewImage), M, 4.45, 5.9, 1.75, "项目概览截图待补", "可使用首页、辩论室或 PPT 概览截图。");
  footer(s);
}

function slideJourney() {
  const s = pptx.addSlide();
  addBg(s);
  mast(s, "USER JOURNEY", "一次训练如何发生");
  kicker(s, "使用路径");
  title(s, "从首页建房开始，系统把复杂辩论拆成可执行的训练流程。", 1.18, 8.9, C.ink, 30);
  const items = [
    ["1", "建立房间", "输入辩题，选择赛制、计时、可见性和参与身份。"],
    ["2", "导入资料", "上传参考材料，建立可引用的知识来源。"],
    ["3", "自动推进", "赛程状态机控制环节，AI 辩手按职责发言。"],
    ["4", "人类介入", "轮到用户时暂停，AI 教练给建议但不代发。"],
    ["5", "复盘输出", "裁判报告、逐字稿导出与回放分享。"],
  ];
  items.forEach((it, i) => {
    const x = 0.72 + i * 2.42;
    panel(s, x, 3.0, 2.0, 1.75);
    s.addText(it[0], { x: x + 0.18, y: 3.16, w: 0.38, h: 0.28, fontSize: 16, bold: true, color: C.red, margin: 0 });
    s.addText(it[1], { x: x + 0.62, y: 3.18, w: 1.12, h: 0.22, fontSize: 13.2, bold: true, color: C.blue, margin: 0 });
    s.addText(it[2], { x: x + 0.18, y: 3.68, w: 1.55, h: 0.58, fontSize: 9.7, color: C.muted, fit: "shrink", margin: 0 });
    if (i < items.length - 1) s.addText("→", { x: x + 2.05, y: 3.58, w: 0.3, h: 0.25, fontSize: 16, color: C.red, margin: 0 });
  });
  addImageIfExists(s, screenshotImages[2], 7.45, 5.25, 4.25, 0.82, "系统首页/建房流程截图待补", "建议插入首页配置、模式选择或资料上传截图。");
  footer(s);
}

function slideArchitecture() {
  const s = pptx.addSlide();
  addBg(s);
  mast(s, "ARCHITECTURE", "React · FastAPI · LangGraph");
  kicker(s, "系统设计");
  title(s, "架构支撑多人、实时、可复盘的辩论现场。", 1.18, 8.1, C.ink, 31);
  const blocks = [
    ["表现层", "React + Vite 构建首页、辩论室、联机大厅、回放页和管理页。同一套 Web UI 覆盖电脑、手机和 Electron 桌面壳。"],
    ["编排层", "FastAPI 提供 REST 与 WebSocket，LangGraph 负责单回合循环，YAML 赛程状态机负责正式 4v4 推进。"],
    ["能力层", "DeepSeek 作为默认 LLM 网关，RAG 与 SQLite 向量库提供资料检索，MongoDB/Redis 支撑持久化与实时缓存。"],
  ];
  blocks.forEach((b, i) => {
    const x = 0.75 + i * 4.1;
    panel(s, x, 2.65, 3.55, 2.75);
    s.addText(b[0], { x: x + 0.28, y: 2.98, w: 2.8, h: 0.28, fontSize: 18, bold: true, color: C.red, margin: 0 });
    paragraph(s, b[1], x + 0.28, 3.48, 2.92, 1.28, { size: 12.0, color: C.ink });
  });
  addPill(s, "可完整工程运行，也可内存降级先保证现场演示", 3.75, 5.95, 5.8, C.dark);
  footer(s);
}

function slideAgents() {
  const s = pptx.addSlide();
  addBg(s);
  mast(s, "MULTI-AGENT", "角色分工与信息边界");
  kicker(s, "多智能体协同");
  title(s, "系统把“一个 AI 发言”拆成一支辩队的协作。", 1.18, 8.5, C.ink, 31);
  panel(s, 0.78, 2.55, 3.55, 2.45);
  panel(s, 4.75, 2.35, 3.35, 2.85, C.dark, C.dark);
  panel(s, 8.55, 2.55, 3.55, 2.45);
  s.addText("正方辩队", { x: 1.08, y: 2.88, w: 2.2, h: 0.3, fontSize: 18, bold: true, color: C.red, margin: 0 });
  paragraph(s, "一辩立论，二辩驳论，三辩盘问与小结，四辩总结陈词。职责来自真实 4v4 辩论分工。", 1.08, 3.34, 2.72, 1.0, { size: 12 });
  s.addText("紫苑裁判", { x: 5.1, y: 2.78, w: 2.2, h: 0.3, fontSize: 19, bold: true, color: C.gold, margin: 0 });
  paragraph(s, "参与任务合理性、论点强度、事实风险、总结质量和最终胜负判断，让辩论过程具备可解释秩序。", 5.1, 3.25, 2.45, 1.1, { size: 12, color: "F7F0E4" });
  s.addText("反方辩队", { x: 8.85, y: 2.88, w: 2.2, h: 0.3, fontSize: 18, bold: true, color: C.red, margin: 0 });
  paragraph(s, "反方建立风险、边界和替代标准；队内讨论对对手不可见，用信息隔离模拟真实赛场。", 8.85, 3.34, 2.72, 1.0, { size: 12 });
  addImageIfExists(s, screenshotImages[3], 1.25, 5.45, 10.6, 0.68, "辩论室角色舞台截图待补", "建议插入 AI 角色舞台、正反双方对阵或裁判报告截图。");
  footer(s);
}

function slideWorkflow() {
  const s = pptx.addSlide();
  addBg(s);
  mast(s, "WORKFLOW", "展示工作流与运行时内核");
  kicker(s, "核心工作流");
  title(s, "前端看见 40 个节点，后端真正执行 9 个节点；两层共同解释系统如何思考。", 1.18, 9.5, C.ink, 28);
  const rows = [
    ["展示层：40 节点", "工作流树把赛前准备、立论前准备、驳论检索、自由辩策略、总结陈词和终局裁决展开。"],
    ["执行层：LangGraph 9 节点", "RAG 检索、策略规划、方向判断、反思、发言生成、事实核查、发布消息、裁判评分、回合路由。"],
    ["赛程层：正式 4v4", "YAML 模板定义立论、攻辩、盘问、自由辩、总结与裁判终局，让 AI 按真实辩论节奏推进。"],
  ];
  rows.forEach((r, i) => {
    panel(s, 0.82, 2.5 + i * 1.12, 10.95, 0.86);
    s.addText(r[0], { x: 1.12, y: 2.72 + i * 1.12, w: 2.65, h: 0.2, fontSize: 14.2, bold: true, color: C.red, margin: 0 });
    s.addText(r[1], { x: 4.0, y: 2.65 + i * 1.12, w: 7.2, h: 0.28, fontSize: 11.2, color: C.ink, fit: "shrink", margin: 0 });
  });
  addImageIfExists(s, screenshotImages[4], 7.55, 5.95, 4.2, 0.62, "工作流树截图待补", "建议插入底部工作流树或当前节点高亮截图。");
  footer(s);
}

function slideHallucination() {
  const s = pptx.addSlide();
  addBg(s);
  mast(s, "TRUST", "让论证可验证");
  kicker(s, "创新点之一");
  title(s, "AI 辩论最危险的地方，是“听起来很有道理”。", 1.18, 7.4, C.ink, 31);
  paragraph(s, "系统不把流畅文本当作最终答案，而是把事实来源、引用编号、核查结果和裁判扣分放进同一条链路。目标不是让模型永不出错，而是让错误在训练流程里被发现、被标记、被复盘。", M, 2.55, 6.1, 1.25, { size: 14.2 });
  const steps = [
    ["资料入库", "上传材料形成可检索来源，发言引用绑定为可追踪编号。"],
    ["发言前", "RAG 根据环节、持方和历史战场检索资料。"],
    ["发言后", "事实核查失败会触发重写，避免风险直接公开。"],
    ["发布前", "移除未入库引用，让伪造编号不能伪装成来源。"],
    ["赛后", "裁判报告记录主战场、失误与幻觉风险。"],
  ];
  steps.forEach((st, i) => {
    panel(s, 7.35, 1.45 + i * 0.85, 4.55, 0.62);
    s.addText(st[0], { x: 7.58, y: 1.62 + i * 0.85, w: 1.0, h: 0.16, fontSize: 10.8, bold: true, color: C.red, margin: 0 });
    s.addText(st[1], { x: 8.75, y: 1.58 + i * 0.85, w: 2.85, h: 0.22, fontSize: 9.6, color: C.muted, fit: "shrink", margin: 0 });
  });
  addImageIfExists(s, screenshotImages[5], 0.9, 5.2, 5.3, 0.86, "引用详情/资料面板截图待补", "建议插入点击 [kb-x] 后出现的引用详情面板。");
  footer(s);
}

function slideHumanAI() {
  const s = pptx.addSlide();
  addBg(s);
  mast(s, "HUMAN + AI", "辅助而不是代替");
  kicker(s, "创新点之二");
  title(s, "系统刻意保留学生的发言权，让 AI 做陪练、资料官和教练。", 1.18, 9.2, C.ink, 29);
  paragraph(s, "在人机模式中，轮到用户时自动暂停。学生可以查看当前战场、资料引用和 AI 教练建议，也可以让系统代拟草稿，但最终提交仍由学生决定。", M, 2.35, 6.0, 1.05, { size: 14.8 });
  panel(s, 7.25, 1.65, 4.75, 3.25);
  s.addText("三种训练视角", { x: 7.55, y: 1.95, w: 3.6, h: 0.28, fontSize: 18, bold: true, color: C.red, margin: 0 });
  paragraph(s, "上下文模式：适合学习，能看到更多推理和队内准备。\n真实辩论模式：适合实战，只看到自己应当看到的信息。\n上帝视角：适合老师和复盘，观察双方策略如何变化。", 7.55, 2.55, 3.9, 1.35, { size: 12.4 });
  addImageIfExists(s, screenshotImages[6], 0.9, 4.85, 5.6, 0.92, "AI 教练/用户输入截图待补", "建议插入等待用户发言、AI 教练建议或发言草稿面板。");
  footer(s);
}

function slideScreenshots() {
  const s = pptx.addSlide();
  addBg(s);
  mast(s, "SCREENSHOTS", "可选择性插入项目截图");
  kicker(s, "视觉证据页");
  title(s, "真实界面截图应服务叙事：证明系统已经跑通，而不是堆图。", 1.18, 9.2, C.ink, 29);
  addImageIfExists(s, pickImage(7, overviewImage), 0.82, 2.25, 5.35, 3.02, "截图 A 待补", "优先选择辩论室主界面：三栏布局、角色舞台、发言流。");
  addImageIfExists(s, screenshotImages[8], 6.55, 2.25, 5.15, 1.35, "截图 B 待补", "建议插入：工作流树高亮、赛程进度条或裁判报告。");
  addImageIfExists(s, screenshotImages[9], 6.55, 3.92, 5.15, 1.35, "截图 C 待补", "建议插入：联机大厅、手机加入页面、引用详情面板或 AI 教练。");
  s.addText("截图选择原则：只放能证明系统结果的界面，不用装饰性图片。真实项目截图缺位处已用虚线框标记。", { x: 0.95, y: 5.65, w: 10.6, h: 0.32, fontSize: 11.5, color: C.red, fit: "shrink", margin: 0 });
  footer(s, "Screenshot Curation", "保留空位，等待真实截图");
}

function slideDeployment() {
  const s = pptx.addSlide();
  addBg(s);
  mast(s, "DEPLOYMENT", "比赛现场与学校机房可运行");
  kicker(s, "跨端运行");
  title(s, "同一套系统覆盖电脑主持、手机加入、桌面发行和弱环境演示。", 1.18, 9.0, C.ink, 29);
  const blocks = [
    ["电脑端", "浏览器访问本机前端与后端；主持人可创建房间、管理赛程、观察进度，并在管理页诊断状态。"],
    ["手机端", "响应式 Web 布局支持同 WiFi 加入，联机席位、在线状态和发言同步由 WebSocket 维护。"],
    ["发行版", "Electron 桌面壳复用 Web UI；便携 Python/Node 与启动脚本支持 U 盘部署。"],
  ];
  blocks.forEach((b, i) => {
    const x = 0.8 + i * 4.1;
    panel(s, x, 2.55, 3.55, 2.25);
    s.addText(b[0], { x: x + 0.3, y: 2.85, w: 2.4, h: 0.25, fontSize: 17, bold: true, color: C.red, margin: 0 });
    paragraph(s, b[1], x + 0.3, 3.28, 2.9, 0.95, { size: 11.8 });
  });
  addImageIfExists(s, screenshotImages[10], 2.2, 5.42, 8.6, 0.74, "联机/手机端截图待补", "建议插入手机加入链接、在线大厅或 Electron 桌面启动界面。");
  footer(s);
}

function slideEngineering() {
  const s = pptx.addSlide();
  addBg(s);
  mast(s, "ENGINEERING", "从原型到可维护系统");
  kicker(s, "工程结果");
  title(s, "项目不只完成演示界面，也补齐了测试、导出、回放和运维入口。", 1.18, 9.2, C.ink, 29);
  const rows = [
    ["代码结构", "后端按 API、服务、工作流、数据库、配置拆分；前端按页面、辩论室特性组件和通用 hooks 拆分。"],
    ["实时能力", "WebSocket 事件覆盖 snapshot、speech_chunk、awaiting_user、debate_stepped、debate_finished 等状态。"],
    ["质量保障", "测试覆盖引用校验、消息可见性、工作流推进、WebSocket、联机流程和用户发言评审。"],
    ["输出沉淀", "全场发言可以导出 Markdown/PDF；回放页和分享链接让一次训练变成可复盘材料。"],
  ];
  rows.forEach((r, i) => {
    panel(s, 0.9, 2.45 + i * 0.92, 10.9, 0.7);
    s.addText(r[0], { x: 1.16, y: 2.64 + i * 0.92, w: 1.55, h: 0.18, fontSize: 12.2, bold: true, color: C.red, margin: 0 });
    s.addText(r[1], { x: 3.05, y: 2.58 + i * 0.92, w: 8.1, h: 0.24, fontSize: 10.8, color: C.ink, fit: "shrink", margin: 0 });
  });
  addPill(s, "从“现场跑一次”升级为“可反复训练、诊断问题、留下记录”的工程系统", 2.7, 6.2, 7.8, C.blue);
  footer(s);
}

function slideValue() {
  const s = pptx.addSlide();
  addBg(s, true);
  mast(s, "VALUE", "教育与推广价值", true);
  kicker(s, "应用价值");
  title(s, "把 AI 素养训练落到一次具体、可复盘的辩论里。", 1.18, 8.8, "F7F0E4", 32);
  paragraph(s, "学生在使用系统时，会自然接触工作流、提示词、RAG、输出校验、多智能体协同和实时通信。这些技术不再停留在概念层，而是在一场辩论中变成可观察、可解释的系统行为。", M, 2.6, 6.25, 1.3, { size: 15.2, color: "EADFCC" });
  panel(s, 7.15, 1.65, 4.75, 3.9, "F7F0E4", "F7F0E4");
  s.addText("面向四类场景", { x: 7.48, y: 2.0, w: 3.4, h: 0.3, fontSize: 18, bold: true, color: C.red, margin: 0 });
  paragraph(s, "课堂：演示如何建立论证与反驳。\n社团：同学加入正反方，AI 补位降低组局成本。\n竞赛：讲清楚从需求分析到系统实现的完整过程。\n个人训练：导出逐字稿与裁判报告，追踪表达改进。", 7.48, 2.55, 3.8, 1.65, { size: 12.4, color: C.ink });
  s.addShape(pptx.ShapeType.rect, { x: M, y: 5.3, w: 6.2, h: 0.78, fill: { color: C.gold }, line: { color: C.gold } });
  s.addText("最终目标不是证明 AI 比人会辩论，而是让人更会提出问题、核验证据、组织表达。", { x: 0.9, y: 5.5, w: 5.65, h: 0.2, fontSize: 12.5, bold: true, color: C.dark, fit: "shrink", margin: 0 });
}

[
  slideCover,
  slideProblem,
  slideInterview,
  slideResult,
  slideJourney,
  slideArchitecture,
  slideAgents,
  slideWorkflow,
  slideHallucination,
  slideHumanAI,
  slideScreenshots,
  slideDeployment,
  slideEngineering,
  slideValue,
].forEach((fn) => fn());

const out = path.join(outputDir, "AI辩论场项目介绍-访谈改进版.pptx");
await pptx.writeFile({ fileName: out });
console.log(out);
