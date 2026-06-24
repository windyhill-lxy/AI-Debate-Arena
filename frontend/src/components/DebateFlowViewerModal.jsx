import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { LocateFixed, RotateCcw, X as XIcon, ZoomIn, ZoomOut } from "lucide-react";
import mermaid from "mermaid";
import projectFlowMmd from "../../../docs/ai-debate-project-flow.mmd?raw";

const INITIAL_VIEW = { x: 24, y: 24, scale: 1 };
const SCALE_LIMIT = { min: 0.035, max: 3.2 };

const LEGEND_ITEMS = [
  { kind: "main", label: "普通步骤" },
  { kind: "programDecision", label: "系统检查" },
  { kind: "aiDecision", label: "智能判断" },
  { kind: "data", label: "保存结果" },
  { kind: "error", label: "错误处理" },
];

const KIND_TEXT = {
  main: "普通步骤",
  programDecision: "系统检查",
  aiDecision: "智能判断",
  data: "保存结果",
  error: "错误处理",
};

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function cleanLabel(raw = "") {
  return raw.replace(/\\"/g, '"').replace(/<br\s*\/?>/gi, " ").trim();
}

function parseNodeExpression(expression) {
  const trimmed = expression.trim();
  const id = trimmed.match(/^([A-Za-z0-9_]+)/)?.[1];
  if (!id) return null;

  const normal = trimmed.match(/^[A-Za-z0-9_]+\["(.+)"\]$/);
  const diamond = trimmed.match(/^[A-Za-z0-9_]+\{"(.+)"\}$/);
  return {
    id,
    label: cleanLabel(normal?.[1] || diamond?.[1] || id),
    shape: diamond ? "diamond" : "normal",
  };
}

function parseProjectFlow(source) {
  const nodes = new Map();
  const edges = [];
  const sections = new Map();
  const classByNode = new Map();
  let currentSection = "";

  for (const rawLine of source.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("%%")) continue;

    const sectionMatch = line.match(/^subgraph\s+([A-Za-z0-9_]+)\["(.+)"\]$/);
    if (sectionMatch) {
      currentSection = sectionMatch[1];
      sections.set(currentSection, cleanLabel(sectionMatch[2]));
      continue;
    }

    if (line === "end") {
      currentSection = "";
      continue;
    }

    const classMatch = line.match(/^class\s+(.+?)\s+([A-Za-z0-9_]+);$/);
    if (classMatch) {
      for (const id of classMatch[1].split(",").map((item) => item.trim()).filter(Boolean)) {
        classByNode.set(id, classMatch[2]);
      }
      continue;
    }

    const edgeMatch = line.match(/^(.+?)\s*-->\s*(?:\|([^|]+)\|\s*)?(.+?)\s*$/);
    if (!edgeMatch) continue;

    const from = parseNodeExpression(edgeMatch[1]);
    const to = parseNodeExpression(edgeMatch[3]);
    if (!from || !to) continue;

    for (const node of [from, to]) {
      const existing = nodes.get(node.id);
      nodes.set(node.id, {
        id: node.id,
        label: existing?.label && existing.label !== existing.id ? existing.label : node.label,
        section: existing?.section || currentSection,
        shape: existing?.shape === "diamond" || node.shape === "diamond" ? "diamond" : "normal",
      });
    }

    edges.push({
      source: from.id,
      target: to.id,
      label: cleanLabel(edgeMatch[2] || ""),
      section: currentSection,
    });
  }

  for (const node of nodes.values()) {
    node.kind = classByNode.get(node.id) || (node.shape === "diamond" ? "programDecision" : "main");
  }

  return { nodes, edges, sections };
}

function describeNode(node, incoming, outgoing) {
  const section = node.section || "";
  const title = node.label;

  if (node.kind === "programDecision") {
    return `系统在这里按固定规则检查“${title.replace(/^程序判断：/, "")}”，根据检查结果进入不同分支。`;
  }
  if (node.kind === "aiDecision") {
    return `智能助手在这里理解上下文并判断“${title.replace(/^AI 判断：/, "")}”，用于决定内容质量、资料归属或下一步策略。`;
  }
  if (node.kind === "error") {
    return "这里负责把异常整理成用户能看懂的提示，并通过错误窗口明确告知用户。";
  }
  if (node.kind === "data") {
    return "这里产出、保存或刷新关键数据，供后续流程继续使用。";
  }
  if (section === "Match") {
    return "这是正式 4v4 赛制中的比赛步骤，用来标明当前发言主体、环节顺序和时间要求。";
  }
  if (section === "Training") {
    return "这是智能立论训练中的步骤，用来推进稿件生成、评审、打分和迭代改进。";
  }
  if (section === "Screen") {
    return "这是页面展示中的步骤，用来同步房间状态、消息、论据库、流程图和错误提示。";
  }
  if (incoming.length === 0) {
    return "这是该流程段的入口，表示用户或系统开始进入这一段业务流程。";
  }
  if (outgoing.length === 0) {
    return "这是该流程段的收尾，表示当前业务已经形成最终结果或报告。";
  }
  return "这是项目运行流程中的执行步骤，用来完成当前事项并把状态传递给后续步骤。";
}

function describeFunction(node, incoming, outgoing) {
  const nextCount = outgoing.length;
  if (node.kind === "programDecision" || node.kind === "aiDecision") {
    return nextCount > 1
      ? `分流控制：根据 ${nextCount} 个可能结果选择下一条路径。`
      : "判断控制：确认条件后继续推进下一步。";
  }
  if (node.kind === "error") return "异常反馈：阻止静默失败，让用户知道哪里出错以及需要如何处理。";
  if (node.kind === "data") return "数据承接：把资料、评分、编号或页面状态整理成后续节点可直接使用的形式。";
  if (node.section === "Match") return "赛程推进：约束发言顺序、对象关系和比赛时间。";
  if (node.section === "Training") return "训练迭代：帮助一辩稿在评分反馈中逐轮改进。";
  if (node.section === "Screen") return "界面同步：让用户看到当前房间、消息、论据和错误状态。";
  return incoming.length > 0 || outgoing.length > 0 ? "流程推进：承接上一步结果，并触发后续业务。" : "流程说明：标记项目中的关键环节。";
}

function buildNodeDetails(flow) {
  const byText = new Map();

  for (const node of flow.nodes.values()) {
    if (node.section === "Legend") continue;

    const incoming = flow.edges
      .filter((edge) => edge.target === node.id)
      .map((edge) => {
        const source = flow.nodes.get(edge.source);
        return `${source?.label || edge.source}${edge.label ? `（${edge.label}）` : ""}`;
      });

    const outgoing = flow.edges
      .filter((edge) => edge.source === node.id)
      .map((edge) => {
        const target = flow.nodes.get(edge.target);
        return `${edge.label ? `${edge.label}：` : ""}${target?.label || edge.target}`;
      });

    const details = {
      id: node.id,
      title: node.label,
      section: flow.sections.get(node.section) || "项目流程",
      incoming,
      outgoing,
      kind: node.kind,
      kindLabel: KIND_TEXT[node.kind] || "流程步骤",
      description: describeNode(node, incoming, outgoing),
      functionText: describeFunction(node, incoming, outgoing),
    };

    byText.set(node.label.replace(/\s+/g, ""), details);
  }

  return byText;
}

function extractViewBox(svg) {
  const match = svg.match(/viewBox="([^"]+)"/);
  if (!match) return null;
  const [minX, minY, width, height] = match[1].split(/\s+/).map(Number);
  if ([minX, minY, width, height].some((item) => !Number.isFinite(item))) return null;
  return { minX, minY, width, height };
}

function normalizeRenderedSvg(renderedSvg) {
  const box = extractViewBox(renderedSvg);
  if (!box) return { svg: renderedSvg, viewBox: null };

  const svg = renderedSvg.replace(/<svg\b([^>]*)>/, (match, attrs) => {
    const cleanedAttrs = attrs
      .replace(/\swidth="[^"]*"/i, "")
      .replace(/\sheight="[^"]*"/i, "")
      .replace(/\sstyle="[^"]*max-width:[^"]*"/i, "");
    return `<svg${cleanedAttrs} width="${box.width}" height="${box.height}">`;
  });

  return { svg, viewBox: box };
}

function getSvgNodeFromEvent(target, container) {
  if (!(target instanceof Element)) return null;
  const node = target.closest(".node");
  return node && container.contains(node) ? node : null;
}

export default function DebateFlowViewerModal({ onClose }) {
  const [svg, setSvg] = useState("");
  const [renderError, setRenderError] = useState("");
  const [viewBox, setViewBox] = useState(null);
  const [view, setView] = useState(INITIAL_VIEW);
  const [tooltip, setTooltip] = useState(null);
  const canvasRef = useRef(null);
  const dragRef = useRef(null);
  const didFitRef = useRef(false);
  const diagramIdRef = useRef(`project-flow-${Date.now().toString(36)}`);

  const nodeDetails = useMemo(() => buildNodeDetails(parseProjectFlow(projectFlowMmd)), []);

  const fitToScreen = useCallback(
    (mode = "contain") => {
      const canvas = canvasRef.current;
      if (!canvas || !viewBox) return;

      const rect = canvas.getBoundingClientRect();
      const padding = mode === "reset" ? 42 : 28;
      const nextScale = clamp(
        Math.min((rect.width - padding * 2) / viewBox.width, (rect.height - padding * 2) / viewBox.height),
        SCALE_LIMIT.min,
        SCALE_LIMIT.max,
      );

      setView({
        x: (rect.width - viewBox.width * nextScale) / 2 - viewBox.minX * nextScale,
        y: (rect.height - viewBox.height * nextScale) / 2 - viewBox.minY * nextScale,
        scale: nextScale,
      });
    },
    [viewBox],
  );

  useEffect(() => {
    let cancelled = false;

    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "loose",
      theme: "base",
      themeVariables: {
        background: "#fbf7ef",
        primaryColor: "#f5efe2",
        primaryBorderColor: "#8a7b5a",
        primaryTextColor: "#211b12",
        lineColor: "#5a5148",
        secondaryColor: "#eef5ec",
        tertiaryColor: "#f7efe2",
        fontFamily: "Microsoft YaHei, PingFang SC, Arial, sans-serif",
        fontSize: "19px",
      },
      flowchart: {
        htmlLabels: true,
        nodeSpacing: 120,
        rankSpacing: 150,
        padding: 34,
        curve: "basis",
      },
    });

    async function renderDiagram() {
      try {
        const { svg: renderedSvg } = await mermaid.render(diagramIdRef.current, projectFlowMmd);
        if (cancelled) return;
        const normalized = normalizeRenderedSvg(renderedSvg);
        setSvg(normalized.svg);
        setViewBox(normalized.viewBox);
        setRenderError("");
      } catch (error) {
        if (cancelled) return;
        setRenderError(error instanceof Error ? error.message : "流程图渲染失败");
      }
    }

    renderDiagram();

    return () => {
      cancelled = true;
    };
  }, []);

  useLayoutEffect(() => {
    if (!viewBox || didFitRef.current) return;
    didFitRef.current = true;
    fitToScreen();
  }, [fitToScreen, viewBox]);

  const zoomAt = useCallback((clientX, clientY, factor) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const px = clientX - rect.left;
    const py = clientY - rect.top;

    setView((current) => {
      const nextScale = clamp(current.scale * factor, SCALE_LIMIT.min, SCALE_LIMIT.max);
      const worldX = (px - current.x) / current.scale;
      const worldY = (py - current.y) / current.scale;
      return {
        scale: nextScale,
        x: px - worldX * nextScale,
        y: py - worldY * nextScale,
      };
    });
  }, []);

  const zoomFromCenter = useCallback(
    (factor) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, factor);
    },
    [zoomAt],
  );

  const onWheel = useCallback(
    (event) => {
      event.preventDefault();
      zoomAt(event.clientX, event.clientY, event.deltaY > 0 ? 0.88 : 1.14);
    },
    [zoomAt],
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;

    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, [onWheel]);

  const onPointerDown = useCallback((event) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { id: event.pointerId, x: event.clientX, y: event.clientY };
  }, []);

  const onPointerMove = useCallback(
    (event) => {
      const drag = dragRef.current;
      if (drag && drag.id === event.pointerId) {
        const dx = event.clientX - drag.x;
        const dy = event.clientY - drag.y;
        dragRef.current = { id: drag.id, x: event.clientX, y: event.clientY };
        setView((current) => ({ ...current, x: current.x + dx, y: current.y + dy }));
      }

      const svgNode = getSvgNodeFromEvent(event.target, event.currentTarget);
      if (!svgNode) {
        setTooltip(null);
        return;
      }

      const title = (svgNode.textContent || "").replace(/\s+/g, "");
      const details = nodeDetails.get(title);
      if (!details) {
        setTooltip(null);
        return;
      }

      const rect = event.currentTarget.getBoundingClientRect();
      setTooltip({
        x: event.clientX - rect.left + 14,
        y: event.clientY - rect.top + 14,
        details,
      });
    },
    [nodeDetails],
  );

  const onPointerUp = useCallback((event) => {
    if (dragRef.current?.id === event.pointerId) dragRef.current = null;
  }, []);

  return (
    <div className="flow-viewer-modal" role="dialog" aria-modal="true" aria-label="项目流程图">
      <div className="flow-viewer-modal__bar">
        <div>
          <strong>项目流程图</strong>
          <span>来源：项目当前真实流程说明。滚轮缩放，按住拖动，悬停步骤查看详细介绍。</span>
        </div>
        <div className="flow-viewer-modal__actions">
          <button type="button" onClick={() => zoomFromCenter(1.18)} title="放大">
            <ZoomIn size={16} /> 放大
          </button>
          <button type="button" onClick={() => zoomFromCenter(0.84)} title="缩小">
            <ZoomOut size={16} /> 缩小
          </button>
          <button type="button" onClick={() => fitToScreen("reset")} title="适配窗口">
            <LocateFixed size={16} /> 适配
          </button>
          <button type="button" onClick={() => setView(INITIAL_VIEW)} title="重置视图">
            <RotateCcw size={16} /> 重置
          </button>
          <button type="button" onClick={onClose} title="关闭">
            <XIcon size={17} /> 关闭
          </button>
        </div>
      </div>
      <div className="flow-viewer-modal__legend" aria-label="流程图图例">
        {LEGEND_ITEMS.map((item) => (
          <span key={item.kind} className={`flow-viewer-modal__legend-item flow-viewer-modal__legend-item--${item.kind}`}>
            {item.label}
          </span>
        ))}
      </div>
      <div
        ref={canvasRef}
        className="flow-viewer-modal__canvas flow-svg-canvas"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onPointerLeave={() => setTooltip(null)}
      >
        {renderError ? (
          <div className="flow-viewer-modal__error" role="alert">
            <strong>流程图渲染失败</strong>
            <span>{renderError}</span>
          </div>
        ) : svg ? (
          <div
            className="flow-svg-shell"
            style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` }}
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        ) : (
          <div className="flow-viewer-modal__loading">加载流程图中…</div>
        )}
        {tooltip && (
          <div className="flow-viewer-tooltip" style={{ left: tooltip.x, top: tooltip.y }}>
            <strong>{tooltip.details.title}</strong>
            <span>
              {tooltip.details.section} · {tooltip.details.kindLabel}
            </span>
            <p>详细介绍：{tooltip.details.description}</p>
            <p>功能：{tooltip.details.functionText}</p>
            {tooltip.details.incoming.length > 0 && <p>来自：{tooltip.details.incoming.slice(0, 3).join("；")}</p>}
            {tooltip.details.outgoing.length > 0 && <p>下一步：{tooltip.details.outgoing.slice(0, 3).join("；")}</p>}
          </div>
        )}
      </div>
    </div>
  );
}
