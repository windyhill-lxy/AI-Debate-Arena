import fs from "node:fs/promises";
import path from "node:path";

const OUT_DIR = path.resolve("docs/ppt-effective-flow/pages");
const W = 1280;
const H = 900;

const colors = {
  bg: "#fbf7ef",
  grid: "rgba(104,86,64,0.075)",
  ink: "#211b12",
  muted: "#6f5a47",
  mainFill: "#f5efe2",
  mainStroke: "#8a7b5a",
  decisionFill: "#e7f0ff",
  decisionStroke: "#5477a6",
  aiFill: "#f0e7ff",
  aiStroke: "#7c5fb3",
  dataFill: "#eef5ec",
  dataStroke: "#557a55",
  errorFill: "#fde7e5",
  errorStroke: "#b45b55",
  line: "#5a5148",
};

function esc(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function wrap(text, max = 15) {
  const input = String(text);
  const lines = [];
  let line = "";
  for (const ch of input) {
    if (ch === "\n") {
      if (line) lines.push(line);
      line = "";
      continue;
    }
    const len = [...line].length;
    if (len >= max && /[，。；、：,;:]/.test(ch) === false) {
      lines.push(line);
      line = ch;
    } else {
      line += ch;
    }
  }
  if (line) lines.push(line);
  return lines.slice(0, 5);
}

function nodeColor(kind) {
  if (kind === "programDecision") return [colors.decisionFill, colors.decisionStroke];
  if (kind === "aiDecision") return [colors.aiFill, colors.aiStroke];
  if (kind === "data") return [colors.dataFill, colors.dataStroke];
  if (kind === "error") return [colors.errorFill, colors.errorStroke];
  return [colors.mainFill, colors.mainStroke];
}

function shape(node) {
  const [fill, stroke] = nodeColor(node.kind);
  const x = node.x;
  const y = node.y;
  const w = node.w || 190;
  const h = node.h || 88;
  const labelLines = wrap(node.label, node.kind === "data" ? 13 : 14);
  const detail = node.detail ? `<div class="detail">${esc(node.detail)}</div>` : "";
  const label = `<div class="label">${labelLines.map(esc).join("<br/>")}</div>${detail}`;
  const cx = x + w / 2;
  const cy = y + h / 2;

  if (node.kind === "programDecision" || node.kind === "aiDecision") {
    return `
      <g class="node ${node.kind}" id="${node.id}">
        <polygon points="${cx},${y} ${x + w},${cy} ${cx},${y + h} ${x},${cy}" fill="${fill}" stroke="${stroke}" stroke-width="2"/>
        <foreignObject x="${x + 26}" y="${y + 22}" width="${w - 52}" height="${h - 44}">
          <div xmlns="http://www.w3.org/1999/xhtml" class="nodeText">${label}</div>
        </foreignObject>
      </g>`;
  }

  if (node.kind === "data") {
    const ry = 14;
    return `
      <g class="node data" id="${node.id}">
        <path d="M${x},${y + ry} C${x},${y - ry / 2} ${x + w},${y - ry / 2} ${x + w},${y + ry} V${y + h - ry} C${x + w},${y + h + ry / 2} ${x},${y + h + ry / 2} ${x},${y + h - ry} Z" fill="${fill}" stroke="${stroke}" stroke-width="2"/>
        <ellipse cx="${cx}" cy="${y + ry}" rx="${w / 2}" ry="${ry}" fill="${fill}" stroke="${stroke}" stroke-width="2"/>
        <foreignObject x="${x + 16}" y="${y + 24}" width="${w - 32}" height="${h - 34}">
          <div xmlns="http://www.w3.org/1999/xhtml" class="nodeText">${label}</div>
        </foreignObject>
      </g>`;
  }

  const rx = node.kind === "error" ? 6 : 10;
  return `
    <g class="node ${node.kind || "main"}" id="${node.id}">
      <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" fill="${fill}" stroke="${stroke}" stroke-width="2"/>
      <foreignObject x="${x + 16}" y="${y + 17}" width="${w - 32}" height="${h - 28}">
        <div xmlns="http://www.w3.org/1999/xhtml" class="nodeText">${label}</div>
      </foreignObject>
    </g>`;
}

function anchor(node, side) {
  const w = node.w || 190;
  const h = node.h || 88;
  if (side === "left") return [node.x, node.y + h / 2];
  if (side === "right") return [node.x + w, node.y + h / 2];
  if (side === "top") return [node.x + w / 2, node.y];
  return [node.x + w / 2, node.y + h];
}

function edge(nodesById, edge) {
  const source = nodesById.get(edge.from);
  const target = nodesById.get(edge.to);
  const fromSide = edge.fromSide || "right";
  const toSide = edge.toSide || "left";
  const [x1, y1] = anchor(source, fromSide);
  const [x2, y2] = anchor(target, toSide);
  const points = edge.points || [];
  const d = [`M${x1} ${y1}`, ...points.map(([x, y]) => `L${x} ${y}`), `L${x2} ${y2}`].join(" ");
  const label = edge.label
    ? `<text x="${edge.labelX ?? (x1 + x2) / 2}" y="${edge.labelY ?? (y1 + y2) / 2 - 8}" class="edgeLabel">${esc(edge.label)}</text>`
    : "";
  return `<path d="${d}" fill="none" stroke="${colors.line}" stroke-width="2.3" marker-end="url(#arrow)"/>${label}`;
}

function legend() {
  const y0 = 138;
  const items = [
    ["普通步骤", colors.mainFill, colors.mainStroke, "rect"],
    ["系统检查", colors.decisionFill, colors.decisionStroke, "diamond"],
    ["AI判断", colors.aiFill, colors.aiStroke, "diamond"],
    ["保存/数据库", colors.dataFill, colors.dataStroke, "data"],
    ["错误处理", colors.errorFill, colors.errorStroke, "rect"],
  ];
  return items
    .map((item, index) => {
      const x = 56 + index * 154;
      const [label, fill, stroke, kind] = item;
      const icon =
        kind === "diamond"
          ? `<polygon points="${x + 16},${y0} ${x + 32},${y0 + 16} ${x + 16},${y0 + 32} ${x},${y0 + 16}" fill="${fill}" stroke="${stroke}" stroke-width="1.6"/>`
          : kind === "data"
            ? `<path d="M${x},${y0 + 6} C${x},${y0 - 4} ${x + 34},${y0 - 4} ${x + 34},${y0 + 6} V${y0 + 26} C${x + 34},${y0 + 36} ${x},${y0 + 36} ${x},${y0 + 26} Z" fill="${fill}" stroke="${stroke}" stroke-width="1.6"/><ellipse cx="${x + 17}" cy="${y0 + 6}" rx="17" ry="6" fill="${fill}" stroke="${stroke}" stroke-width="1.6"/>`
            : `<rect x="${x}" y="${y0 + 2}" width="34" height="28" rx="5" fill="${fill}" stroke="${stroke}" stroke-width="1.6"/>`;
      return `<g>${icon}<text x="${x + 43}" y="${y0 + 22}" class="legendText">${label}</text></g>`;
    })
    .join("\n");
}

function render(def) {
  const nodesById = new Map(def.nodes.map((node) => [node.id, node]));
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(def.title)}">
  <defs>
    <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
      <path d="M32 0H0V32" fill="none" stroke="${colors.grid}" stroke-width="1"/>
    </pattern>
    <marker id="arrow" viewBox="0 0 18 18" refX="15" refY="9" markerWidth="10" markerHeight="10" orient="auto">
      <path d="M2 2 L16 9 L2 16 Z" fill="${colors.line}"/>
    </marker>
    <filter id="shadow" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#32261c" flood-opacity="0.1"/>
    </filter>
    <style>
      svg { background: ${colors.bg}; font-family: "Microsoft YaHei", "Noto Sans SC", "PingFang SC", Arial, sans-serif; }
      .title { fill: ${colors.ink}; font-size: 34px; font-weight: 850; letter-spacing: 0; }
      .subtitle { fill: ${colors.muted}; font-size: 17px; font-weight: 650; letter-spacing: 0; }
      .legendText { fill: ${colors.ink}; font-size: 15px; font-weight: 800; }
      .node { filter: url(#shadow); }
      .nodeText { box-sizing: border-box; width: 100%; height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; color: #5c4d3d; line-height: 1.25; overflow-wrap: anywhere; word-break: break-word; }
      .nodeText .label { font-size: 17px; font-weight: 850; }
      .nodeText .detail { margin-top: 4px; font-size: 12px; font-weight: 700; color: #7c6752; line-height: 1.2; }
      .programDecision .nodeText { color: #345f9c; }
      .aiDecision .nodeText { color: #7654b3; }
      .data .nodeText { color: #446f48; }
      .error .nodeText { color: #ad4e49; }
      .edgeLabel { fill: #4f463d; paint-order: stroke; stroke: ${colors.bg}; stroke-width: 7px; stroke-linejoin: round; font-size: 14px; font-weight: 800; }
      .code { fill: ${colors.muted}; font-family: Consolas, "Courier New", monospace; font-size: 13px; }
    </style>
  </defs>
  <rect x="0" y="0" width="${W}" height="${H}" fill="url(#grid)"/>
  <rect x="32" y="24" width="1216" height="98" rx="16" fill="#f7efe2" stroke="rgba(124,101,78,0.22)"/>
  <text x="56" y="67" class="title">${esc(def.title)}</text>
  <text x="58" y="99" class="subtitle">${esc(def.subtitle)}</text>
  ${legend()}
  <g>${def.edges.map((item) => edge(nodesById, item)).join("\n")}</g>
  <g>${def.nodes.map(shape).join("\n")}</g>
  <text x="46" y="858" class="code">${esc(def.code)}</text>
  <text x="46" y="882" class="subtitle">来源：PPT有效信息页内容 + docs/ai-debate-project-flow.mmd + 项目实际后端/前端文件。</text>
</svg>`;
}

const x = { a: 70, b: 315, c: 560, d: 805, e: 1050 };
const y = { top: 185, mid: 365, low: 545, bottom: 695 };

const pages = [
  {
    file: "slide-07-system-overview",
    title: "PPT 7｜AI辩论场完整训练闭环",
    subtitle: "把“真实赛程、论据库、多模态、导出复盘”串成一场可运行的辩论。",
    code: "api/debates.py · workflow/debate_graph.py · services/rag.py · services/judge_report.py · services/export_pdf.py",
    nodes: [
      { id: "start", x: x.a, y: y.mid, label: "选择训练模式", detail: "AI自主/用户加入/多人联机" },
      { id: "room", x: x.b, y: y.mid, label: "创建正式房间", detail: "辩题、席位、赛程" },
      { id: "data", kind: "data", x: x.c, y: y.top, label: "资料与论据库", detail: "RAG + argument bank" },
      { id: "ready", kind: "programDecision", x: x.c, y: y.mid, w: 205, h: 118, label: "论据和赛程是否就绪" },
      { id: "debate", x: x.d, y: y.mid, label: "按4v4流程辩论", detail: "队内讨论/公开发言/裁判" },
      { id: "multi", x: x.d, y: y.low, label: "多模态训练", detail: "TTS/ASR/摄像头" },
      { id: "report", kind: "data", x: x.e, y: y.mid, label: "赛后复盘报告", detail: "Markdown/PDF/回放" },
    ],
    edges: [
      { from: "start", to: "room" },
      { from: "room", to: "ready" },
      { from: "data", to: "ready", fromSide: "bottom", toSide: "top" },
      { from: "ready", to: "debate", label: "是" },
      { from: "ready", to: "data", label: "否，继续补充", fromSide: "top", toSide: "bottom" },
      { from: "debate", to: "multi", fromSide: "bottom", toSide: "top", label: "真人发言时" },
      { from: "multi", to: "debate", fromSide: "top", toSide: "bottom" },
      { from: "debate", to: "report" },
    ],
  },
  {
    file: "slide-08-architecture-workflow",
    title: "PPT 8｜前后端、工作流与数据层协同",
    subtitle: "React 页面发起操作，FastAPI 管状态，LangGraph 风格节点推进辩论，数据层保存结果。",
    code: "frontend debate-room · api/debates.py · workflow/debate_graph.py · services/ai_context_manager.py",
    nodes: [
      { id: "ui", x: x.a, y: y.mid, label: "前端辩论室", detail: "赛程/消息/右侧栏" },
      { id: "api", x: x.b, y: y.mid, label: "FastAPI服务层", detail: "房间、发言、WebSocket" },
      { id: "state", kind: "data", x: x.c, y: y.top, label: "房间状态库", detail: "消息/席位/报告" },
      { id: "graph", x: x.c, y: y.mid, label: "工作流编排", detail: "检索→生成→评分→推进" },
      { id: "ctx", kind: "programDecision", x: x.d, y: y.mid, w: 205, h: 118, label: "角色是否有权限看到信息" },
      { id: "llm", kind: "aiDecision", x: x.e, y: y.mid, w: 190, h: 112, label: "模型生成或判断" },
      { id: "deny", kind: "error", x: x.d, y: y.low, label: "隐藏越权内容", detail: "只返回可见上下文" },
    ],
    edges: [
      { from: "ui", to: "api" },
      { from: "api", to: "state", fromSide: "top", toSide: "left" },
      { from: "api", to: "graph" },
      { from: "graph", to: "ctx" },
      { from: "ctx", to: "llm", label: "允许" },
      { from: "ctx", to: "deny", label: "不允许", fromSide: "bottom", toSide: "top" },
      { from: "llm", to: "state", fromSide: "top", toSide: "right", points: [[1145, 205], [660, 205]] },
      { from: "state", to: "ui", fromSide: "left", toSide: "top", points: [[120, 229]] },
    ],
  },
  {
    file: "slide-10-formal-langgraph-schedule",
    title: "PPT 10｜正规赛程驱动的 LangGraph 流程",
    subtitle: "每轮发言不是聊天接龙，而是由赛程、当前角色和节点结果共同决定下一步。",
    code: "workflow/debate_graph.py · config/schedules/formal_4v4.yaml · services/debate_schedule.py",
    nodes: [
      { id: "schedule", kind: "data", x: x.a, y: y.mid, label: "formal_4v4赛程", detail: "阶段、发言人、时长" },
      { id: "turn", x: x.b, y: y.mid, label: "读取当前轮次", detail: "谁该发言/做什么" },
      { id: "human", kind: "programDecision", x: x.c, y: y.mid, w: 205, h: 118, label: "当前席位是真人吗" },
      { id: "wait", x: x.c, y: y.low, label: "等待用户输入", detail: "暂停自动推进" },
      { id: "graph", x: x.d, y: y.mid, label: "AI节点执行", detail: "检索/策略/生成/核查" },
      { id: "score", x: x.e, y: y.mid, label: "发布并评分", detail: "裁判记录得分" },
      { id: "end", kind: "programDecision", x: x.e, y: y.low, w: 190, h: 112, label: "比赛是否结束" },
    ],
    edges: [
      { from: "schedule", to: "turn" },
      { from: "turn", to: "human" },
      { from: "human", to: "wait", label: "是", fromSide: "bottom", toSide: "top" },
      { from: "wait", to: "score", fromSide: "right", toSide: "bottom" },
      { from: "human", to: "graph", label: "否" },
      { from: "graph", to: "score" },
      { from: "score", to: "end", fromSide: "bottom", toSide: "top" },
      { from: "end", to: "turn", label: "否", fromSide: "left", toSide: "bottom", points: [[900, 755], [410, 755]] },
    ],
  },
  {
    file: "slide-11-team-discussion",
    title: "PPT 11｜原创队内讨论环节",
    subtitle: "让同一方先围绕论据和攻防沟通，再进入公开发言，形成团队连续性。",
    code: "services/team_discussion.py · services/argument_bank.py · services/debate_schedule.py",
    nodes: [
      { id: "ready", kind: "programDecision", x: x.a, y: y.mid, w: 205, h: 118, label: "本方论据是否就绪" },
      { id: "bank", kind: "data", x: x.a, y: y.top, label: "本方论据库", detail: "AFF/NEG编号" },
      { id: "assign", x: x.b, y: y.mid, label: "一辩分配任务", detail: "主论点/引用论据" },
      { id: "seat", kind: "programDecision", x: x.c, y: y.mid, w: 205, h: 118, label: "该席位是否真人占用" },
      { id: "wait", x: x.c, y: y.low, label: "等待真人队内发言" },
      { id: "ai", kind: "aiDecision", x: x.d, y: y.mid, w: 205, h: 118, label: "AI队友生成建议" },
      { id: "log", kind: "data", x: x.e, y: y.mid, label: "记录队内讨论", detail: "供公开发言使用" },
    ],
    edges: [
      { from: "bank", to: "ready", fromSide: "bottom", toSide: "top" },
      { from: "ready", to: "assign", label: "是" },
      { from: "ready", to: "bank", label: "否，继续搜集", fromSide: "top", toSide: "bottom" },
      { from: "assign", to: "seat" },
      { from: "seat", to: "wait", label: "是", fromSide: "bottom", toSide: "top" },
      { from: "seat", to: "ai", label: "否" },
      { from: "wait", to: "log", fromSide: "right", toSide: "bottom" },
      { from: "ai", to: "log" },
    ],
  },
  {
    file: "slide-12-camera-recognition",
    title: "PPT 12｜摄像头识别与表达表现评分",
    subtitle: "用户选择使用摄像头时，系统把姿态、眼神、手势、自信度纳入训练反馈。",
    code: "api/confidence_monitor.py · services/confidence_monitor.py · services/camera_speech_scoring.py",
    nodes: [
      { id: "choice", kind: "programDecision", x: x.a, y: y.mid, w: 205, h: 118, label: "用户是否启用摄像头" },
      { id: "skip", x: x.a, y: y.low, label: "不打开摄像头", detail: "不弹设备错误" },
      { id: "open", x: x.b, y: y.mid, label: "请求摄像头权限" },
      { id: "ok", kind: "programDecision", x: x.c, y: y.mid, w: 205, h: 118, label: "设备是否可用" },
      { id: "error", kind: "error", x: x.c, y: y.low, label: "弹出摄像头提示", detail: "后续降级显示" },
      { id: "monitor", x: x.d, y: y.mid, label: "实时识别表现", detail: "眼神/姿态/手势/自信度" },
      { id: "score", kind: "data", x: x.e, y: y.mid, label: "写入表达评分", detail: "合并到发言反馈" },
    ],
    edges: [
      { from: "choice", to: "skip", label: "否", fromSide: "bottom", toSide: "top" },
      { from: "choice", to: "open", label: "是" },
      { from: "open", to: "ok" },
      { from: "ok", to: "error", label: "否", fromSide: "bottom", toSide: "top" },
      { from: "ok", to: "monitor", label: "是" },
      { from: "monitor", to: "score" },
    ],
  },
  {
    file: "slide-13-asr-tts",
    title: "PPT 13｜语音识别与 TTS 朗读",
    subtitle: "用户可以开口发言，AI 也能朗读输出，让训练更接近现场辩论压力。",
    code: "services/asr.py · services/tts.py · services/tts_policy.py · hooks/useAudioQueue.js",
    nodes: [
      { id: "mode", kind: "programDecision", x: x.a, y: y.mid, w: 205, h: 118, label: "当前是用户说话还是AI发言" },
      { id: "record", x: x.b, y: y.low, label: "录音上传" },
      { id: "asr", x: x.c, y: y.low, label: "ASR转文字" },
      { id: "validate", kind: "programDecision", x: x.d, y: y.low, w: 205, h: 118, label: "是否轮到该用户" },
      { id: "ttsPolicy", kind: "programDecision", x: x.b, y: y.top, w: 205, h: 118, label: "是否允许朗读" },
      { id: "tts", x: x.c, y: y.top, label: "生成TTS音频" },
      { id: "queue", x: x.d, y: y.top, label: "顺序播放音频", detail: "避免重叠" },
      { id: "speech", kind: "data", x: x.e, y: y.mid, label: "进入发言文本", detail: "评分/发布/推进" },
    ],
    edges: [
      { from: "mode", to: "ttsPolicy", label: "AI发言", fromSide: "top", toSide: "left" },
      { from: "ttsPolicy", to: "tts", label: "允许", labelX: 548, labelY: 230 },
      { from: "tts", to: "queue" },
      { from: "queue", to: "speech", fromSide: "right", toSide: "top" },
      { from: "mode", to: "record", label: "用户说话", fromSide: "bottom", toSide: "left" },
      { from: "record", to: "asr" },
      { from: "asr", to: "validate" },
      { from: "validate", to: "speech", label: "是" },
    ],
  },
  {
    file: "slide-14-rag-anti-hallucination",
    title: "PPT 14｜RAG 防 AI 幻觉",
    subtitle: "AI 发言前先检索资料和论据库，尽量围绕可查来源组织观点。",
    code: "services/rag.py · workflow/debate_graph.py · services/opening_evidence.py",
    nodes: [
      { id: "topic", x: x.a, y: y.mid, label: "收到辩题与当前任务" },
      { id: "index", kind: "data", x: x.b, y: y.top, label: "资料索引", detail: "上传文本/网页/历史资料" },
      { id: "retrieve", x: x.b, y: y.mid, label: "检索相关材料" },
      { id: "hit", kind: "programDecision", x: x.c, y: y.mid, w: 205, h: 118, label: "是否检索到可用依据" },
      { id: "draft", kind: "aiDecision", x: x.d, y: y.mid, w: 205, h: 118, label: "基于材料生成发言" },
      { id: "fallback", kind: "error", x: x.c, y: y.low, label: "降低断言强度", detail: "不编造数据来源" },
      { id: "publish", kind: "data", x: x.e, y: y.mid, label: "带引用发布", detail: "供后续核查" },
    ],
    edges: [
      { from: "topic", to: "retrieve" },
      { from: "index", to: "retrieve", fromSide: "bottom", toSide: "top" },
      { from: "retrieve", to: "hit" },
      { from: "hit", to: "draft", label: "是" },
      { from: "hit", to: "fallback", label: "否", fromSide: "bottom", toSide: "top" },
      { from: "fallback", to: "draft", fromSide: "right", toSide: "bottom" },
      { from: "draft", to: "publish" },
    ],
  },
  {
    file: "slide-15-argument-system",
    title: "PPT 15｜多轮审查后的论据系统",
    subtitle: "论据先入库、审查、编号，AI 正式发言时引用清晰来源。",
    code: "services/argument_bank.py · services/opening_evidence.py · backend/tests/test_argument_bank.py",
    nodes: [
      { id: "raw", x: x.a, y: y.mid, label: "候选事实/案例/数据" },
      { id: "review1", kind: "aiDecision", x: x.b, y: y.mid, w: 205, h: 118, label: "来源是否清楚可信" },
      { id: "review2", kind: "aiDecision", x: x.c, y: y.mid, w: 205, h: 118, label: "是否能支撑当前观点" },
      { id: "drop", kind: "error", x: x.c, y: y.low, label: "丢弃或降级", detail: "避免断章取义" },
      { id: "number", x: x.d, y: y.mid, label: "分配稳定编号", detail: "AFF/NEG" },
      { id: "bank", kind: "data", x: x.e, y: y.mid, label: "正式论据库", detail: "供发言引用" },
    ],
    edges: [
      { from: "raw", to: "review1" },
      { from: "review1", to: "review2", label: "通过" },
      { from: "review1", to: "drop", label: "失败", fromSide: "bottom", toSide: "left" },
      { from: "review2", to: "drop", label: "不支撑", fromSide: "bottom", toSide: "top" },
      { from: "review2", to: "number", label: "通过" },
      { from: "number", to: "bank" },
    ],
  },
  {
    file: "slide-16-ai-context-permissions",
    title: "PPT 16｜AI 上下文管理与信息权限",
    subtitle: "不同角色只拿到自己应该看到的信息，防止立场混乱和提前越权。",
    code: "services/ai_context_manager.py · services/message_visibility.py · services/viewer_payload.py",
    nodes: [
      { id: "role", x: x.a, y: y.mid, label: "识别当前角色", detail: "正方/反方/裁判/观众" },
      { id: "public", kind: "data", x: x.b, y: y.top, label: "公开发言记录" },
      { id: "private", kind: "data", x: x.b, y: y.low, label: "本方队内信息" },
      { id: "policy", kind: "programDecision", x: x.c, y: y.mid, w: 215, h: 126, label: "请求内容是否在权限范围内" },
      { id: "ctx", x: x.d, y: y.mid, label: "组装可见上下文" },
      { id: "deny", kind: "error", x: x.d, y: y.low, label: "隐藏越权内容" },
      { id: "llm", kind: "aiDecision", x: x.e, y: y.mid, w: 190, h: 112, label: "角色内思考发言" },
    ],
    edges: [
      { from: "role", to: "policy" },
      { from: "public", to: "policy", fromSide: "right", toSide: "top" },
      { from: "private", to: "policy", fromSide: "right", toSide: "bottom" },
      { from: "policy", to: "ctx", label: "允许" },
      { from: "policy", to: "deny", label: "拒绝", fromSide: "bottom", toSide: "left" },
      { from: "ctx", to: "llm" },
    ],
  },
  {
    file: "slide-17-realtime-scoring",
    title: "PPT 17｜无来源、灌水、虚假发言识别并扣分",
    subtitle: "发言发布前后都会检查引用、论证质量和事实风险，把问题写入评分。",
    code: "services/user_message_scoring.py · services/user_speech_judge.py · workflow/debate_graph.py",
    nodes: [
      { id: "speech", x: x.a, y: y.mid, label: "收到发言文本" },
      { id: "cite", kind: "programDecision", x: x.b, y: y.mid, w: 205, h: 118, label: "是否引用有效论据" },
      { id: "quality", kind: "aiDecision", x: x.c, y: y.mid, w: 205, h: 118, label: "是否空泛重复或逻辑跳跃" },
      { id: "fact", kind: "aiDecision", x: x.d, y: y.mid, w: 205, h: 118, label: "是否存在虚假或高风险断言" },
      { id: "penalty", kind: "data", x: x.e, y: y.top, label: "记录扣分原因", detail: "无来源/灌水/幻觉" },
      { id: "score", kind: "data", x: x.e, y: y.low, label: "生成裁判评分", detail: "进入赛后报告" },
    ],
    edges: [
      { from: "speech", to: "cite" },
      { from: "cite", to: "quality", label: "有或可解释" },
      { from: "cite", to: "penalty", label: "无来源", fromSide: "top", toSide: "left" },
      { from: "quality", to: "fact" },
      { from: "quality", to: "penalty", label: "质量低", fromSide: "top", toSide: "left" },
      { from: "fact", to: "penalty", label: "有风险", fromSide: "top", toSide: "bottom" },
      { from: "fact", to: "score", label: "通过", fromSide: "bottom", toSide: "left" },
      { from: "penalty", to: "score", fromSide: "bottom", toSide: "top" },
    ],
  },
  {
    file: "slide-18-error-dialogs",
    title: "PPT 18｜错误弹窗而不是程序崩溃",
    subtitle: "摄像头、网络、API Key、语音和实时连接失败时，统一整理成用户可读提示。",
    code: "frontend/src/components/ErrorDialogProvider.jsx · hooks/useDebateSocket.js · api health/tunnel/asr",
    nodes: [
      { id: "action", x: x.a, y: y.mid, label: "用户或系统发起操作" },
      { id: "module", x: x.b, y: y.mid, label: "调用设备/网络/模型接口" },
      { id: "ok", kind: "programDecision", x: x.c, y: y.mid, w: 205, h: 118, label: "调用是否成功" },
      { id: "continue", x: x.d, y: y.top, label: "继续当前流程" },
      { id: "normalize", kind: "error", x: x.d, y: y.low, label: "整理错误原因", detail: "设备/网络/API Key" },
      { id: "dialog", kind: "error", x: x.e, y: y.low, label: "弹出错误窗口", detail: "告诉用户如何处理" },
      { id: "state", kind: "data", x: x.e, y: y.top, label: "保留当前房间状态", detail: "避免崩溃丢进度" },
    ],
    edges: [
      { from: "action", to: "module" },
      { from: "module", to: "ok" },
      { from: "ok", to: "continue", label: "成功", fromSide: "top", toSide: "left" },
      { from: "continue", to: "state" },
      { from: "ok", to: "normalize", label: "失败", fromSide: "bottom", toSide: "left" },
      { from: "normalize", to: "dialog" },
      { from: "dialog", to: "state", fromSide: "top", toSide: "bottom" },
    ],
  },
  {
    file: "slide-19-online-and-user-join",
    title: "PPT 19｜AI自主、用户加入与多人联机",
    subtitle: "同一套房间状态和赛程，可以支持 AI 全自动、单人训练和多人共同参与。",
    code: "api/debates.py · services/presence.py · services/tunnel_service.py · OnlineSimplePanel.jsx",
    nodes: [
      { id: "create", x: x.a, y: y.mid, label: "房主创建房间" },
      { id: "mode", kind: "programDecision", x: x.b, y: y.mid, w: 205, h: 118, label: "选择哪种参与模式" },
      { id: "auto", x: x.c, y: y.top, label: "AI自主辩论", detail: "无人类席位" },
      { id: "single", x: x.c, y: y.mid, label: "用户加入一方", detail: "选择正方/反方" },
      { id: "online", x: x.c, y: y.low, label: "多人联机邀请", detail: "公网链接/局域网" },
      { id: "seats", kind: "data", x: x.d, y: y.mid, label: "席位与在线状态", detail: "presence/session" },
      { id: "run", x: x.e, y: y.mid, label: "进入同一赛程推进", detail: "轮到真人则等待" },
    ],
    edges: [
      { from: "create", to: "mode" },
      { from: "mode", to: "auto", label: "AI自主", fromSide: "top", toSide: "left" },
      { from: "mode", to: "single", label: "单人训练" },
      { from: "mode", to: "online", label: "多人", fromSide: "bottom", toSide: "left" },
      { from: "auto", to: "seats", fromSide: "right", toSide: "top" },
      { from: "single", to: "seats" },
      { from: "online", to: "seats", fromSide: "right", toSide: "bottom" },
      { from: "seats", to: "run" },
    ],
  },
  {
    file: "slide-20-opening-draft-polish",
    title: "PPT 20｜一辩立论修改润色与循环迭代",
    subtitle: "用户稿件进入 AI 教练流程，围绕结构、论据、表达和时间反复改进。",
    code: "api/debates.py assist/draft endpoints · services/rag.py · services/user_speech_judge.py",
    nodes: [
      { id: "draft", x: x.a, y: y.mid, label: "用户输入一辩稿" },
      { id: "rubric", kind: "data", x: x.b, y: y.top, label: "赛制与评分要求", detail: "论点/论据/时长" },
      { id: "evidence", kind: "data", x: x.b, y: y.low, label: "可用论据库", detail: "具体数据与来源" },
      { id: "review", kind: "aiDecision", x: x.c, y: y.mid, w: 205, h: 118, label: "AI评审稿件问题" },
      { id: "rewrite", x: x.d, y: y.mid, label: "生成修改建议与润色稿" },
      { id: "accept", kind: "programDecision", x: x.e, y: y.mid, w: 190, h: 112, label: "用户是否继续迭代" },
      { id: "final", kind: "data", x: x.e, y: y.low, label: "定稿进入训练", detail: "可用于正式发言" },
    ],
    edges: [
      { from: "draft", to: "review" },
      { from: "rubric", to: "review", fromSide: "right", toSide: "top" },
      { from: "evidence", to: "review", fromSide: "right", toSide: "bottom" },
      { from: "review", to: "rewrite" },
      { from: "rewrite", to: "accept" },
      { from: "accept", to: "review", label: "继续改", fromSide: "top", toSide: "top", points: [[1145, 205], [660, 205]] },
      { from: "accept", to: "final", label: "完成", fromSide: "bottom", toSide: "top" },
    ],
  },
  {
    file: "slide-22-interview-needs",
    title: "PPT 22｜访谈需求落到训练流程",
    subtitle: "现场抓关键词、自由辩全队参与、具体论据和评委反馈，分别落到实时发言、队内讨论和评分报告。",
    code: "team_discussion.py · ai_context_manager.py · user_turn_flow.py · user_message_scoring.py · judge_report.py",
    nodes: [
      { id: "listen", x: x.a, y: y.mid, label: "接收对方发言", detail: "现场材料" },
      { id: "keyword", kind: "aiDecision", x: x.b, y: y.mid, w: 205, h: 118, label: "抓取关键词和漏洞" },
      { id: "team", x: x.c, y: y.top, label: "队内策略讨论", detail: "不是一个人撑全场" },
      { id: "evidence", kind: "data", x: x.c, y: y.low, label: "检索具体数据", detail: "支撑反驳" },
      { id: "reply", x: x.d, y: y.mid, label: "组织现场反驳" },
      { id: "score", kind: "aiDecision", x: x.e, y: y.mid, w: 190, h: 112, label: "评委指出漏洞与优点" },
      { id: "report", kind: "data", x: x.e, y: y.low, label: "写入训练反馈", detail: "下一轮改进" },
    ],
    edges: [
      { from: "listen", to: "keyword" },
      { from: "keyword", to: "team", fromSide: "top", toSide: "left" },
      { from: "keyword", to: "evidence", fromSide: "bottom", toSide: "left" },
      { from: "team", to: "reply", fromSide: "right", toSide: "top" },
      { from: "evidence", to: "reply", fromSide: "right", toSide: "bottom" },
      { from: "reply", to: "score" },
      { from: "score", to: "report", fromSide: "bottom", toSide: "top" },
    ],
  },
  {
    file: "slide-23-summary-training-platform",
    title: "PPT 23｜真实、严谨、实用的训练闭环",
    subtitle: "反复模拟、具体反馈、防幻觉和团队协作，最终形成可持续训练平台。",
    code: "debate_graph.py · rag.py · team_discussion.py · user_message_scoring.py · judge_report.py · export_pdf.py",
    nodes: [
      { id: "simulate", x: x.a, y: y.mid, label: "启动一轮模拟辩论" },
      { id: "real", kind: "programDecision", x: x.b, y: y.mid, w: 205, h: 118, label: "是否贴近真实赛程" },
      { id: "rigor", kind: "aiDecision", x: x.c, y: y.mid, w: 205, h: 118, label: "内容是否严谨有来源" },
      { id: "useful", kind: "aiDecision", x: x.d, y: y.mid, w: 205, h: 118, label: "反馈是否具体可改" },
      { id: "fix", kind: "error", x: x.c, y: y.low, label: "标出问题", detail: "赛程/来源/逻辑漏洞" },
      { id: "report", kind: "data", x: x.e, y: y.mid, label: "生成复盘报告", detail: "下一轮继续训练" },
      { id: "export", kind: "data", x: x.e, y: y.low, label: "导出PDF/报告" },
    ],
    edges: [
      { from: "simulate", to: "real" },
      { from: "real", to: "rigor", label: "是" },
      { from: "real", to: "fix", label: "否", fromSide: "bottom", toSide: "left" },
      { from: "rigor", to: "useful" },
      { from: "rigor", to: "fix", label: "无来源", fromSide: "bottom", toSide: "top" },
      { from: "useful", to: "report", label: "是" },
      { from: "useful", to: "fix", label: "否", fromSide: "bottom", toSide: "right" },
      { from: "fix", to: "report", fromSide: "right", toSide: "bottom" },
      { from: "report", to: "export", fromSide: "bottom", toSide: "top" },
    ],
  },
];

await fs.mkdir(OUT_DIR, { recursive: true });

const rows = [];
for (const page of pages) {
  const svg = render(page);
  const filename = `${page.file}.svg`;
  await fs.writeFile(path.join(OUT_DIR, filename), svg, "utf8");
  rows.push(`| ${page.title.split("｜")[0].replace("PPT ", "")} | ${page.title.replace(/^PPT \d+｜/, "")} | [SVG](pages/${filename}) | PNG: \`pages/${page.file}.png\` |`);
}

const index = `# PPT有效信息页逐页程序流程图

这些图按 PPT 的有效信息页逐页生成，样式贴近项目程序里的流程图展示：

- 圆角矩形：普通流程步骤
- 蓝色菱形：系统检查
- 紫色菱形：AI 判断
- 绿色圆柱：数据库、状态保存或资料库
- 红色节点：错误处理或风险提示

| PPT页 | 内容 | SVG | PNG |
|---|---|---|---|
${rows.join("\n")}

总览图仍保留在上一层目录：

- \`docs/ppt-effective-flow/ppt-effective-implementation-flow.svg\`
- \`docs/ppt-effective-flow/ppt-effective-implementation-flow.png\`
`;

await fs.writeFile(path.resolve("docs/ppt-effective-flow/page-flow-index.md"), index, "utf8");
console.log(`Generated ${pages.length} SVG files in ${OUT_DIR}`);
