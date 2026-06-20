import { memo, useEffect, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlowProvider,
  Position,
  Handle,
  useReactFlow,
} from "@xyflow/react";
import dagre from "dagre";
import "@xyflow/react/dist/style.css";

const NODE_SIZE = {
  input: { width: 190, height: 78 },
  retrieval: { width: 190, height: 78 },
  llm: { width: 190, height: 78 },
  action: { width: 190, height: 78 },
  router: { width: 158, height: 118 },
  check: { width: 158, height: 118 },
  judge: { width: 158, height: 118 },
  terminal: { width: 180, height: 70 },
};

const DECISION_KINDS = new Set(["router", "check", "judge"]);

function isTerminal(node) {
  return /结束|输出裁判报告|赛制环节推进/.test(node?.label || "") || node?.id?.includes("end") || node?.id?.includes("final");
}

function flattenWorkflow(columns = []) {
  const items = [];
  for (const [stageIndex, column] of columns.entries()) {
    const stageNodes = [...(column.nodes || [])].sort((a, b) => (a.lane || 0) - (b.lane || 0));
    for (const [nodeIndex, node] of stageNodes.entries()) {
      const kind = isTerminal(node) ? "terminal" : node.kind || "action";
      items.push({
        ...node,
        kind,
        stage: column.stage,
        order: `${stageIndex + 1}.${nodeIndex + 1}`,
      });
    }
  }
  return items;
}

function edgeLabelFor(source, index) {
  if (!DECISION_KINDS.has(source.kind)) return "";
  return index % 2 === 0 ? "yes" : "no";
}

function layoutWorkflow(columns = []) {
  const flat = flattenWorkflow(columns);
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({
    rankdir: "TB",
    align: "DL",
    ranksep: 92,
    nodesep: 76,
    edgesep: 28,
    marginx: 36,
    marginy: 36,
  });
  graph.setDefaultEdgeLabel(() => ({}));

  for (const node of flat) {
    const size = NODE_SIZE[node.kind] || NODE_SIZE.action;
    graph.setNode(node.id, size);
  }

  for (let index = 0; index < flat.length - 1; index += 1) {
    graph.setEdge(flat[index].id, flat[index + 1].id);
  }

  dagre.layout(graph);

  const nodes = flat.map((node) => {
    const position = graph.node(node.id) || { x: 0, y: 0 };
    const size = NODE_SIZE[node.kind] || NODE_SIZE.action;
    return {
      id: node.id,
      type: "workflowNode",
      position: { x: position.x - size.width / 2, y: position.y - size.height / 2 },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      data: {
        label: node.label,
        detail: node.detail,
        kind: node.kind,
        order: node.order,
        stage: node.stage,
        status: node.status || "pending",
      },
      draggable: false,
      selectable: false,
      style: size,
    };
  });

  const edges = flat.slice(0, -1).map((node, index) => ({
    id: `edge-${node.id}-${flat[index + 1].id}`,
    source: node.id,
    target: flat[index + 1].id,
    type: "smoothstep",
    label: edgeLabelFor(node, index),
    animated: flat[index + 1].status === "running",
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    style: { strokeWidth: 2 },
  }));

  return { nodes, edges };
}

function escapeXml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function exportWorkflowSVG(columns, topic) {
  const { nodes, edges } = layoutWorkflow(columns);
  if (!nodes.length) return;
  const minX = Math.min(...nodes.map((node) => node.position.x));
  const minY = Math.min(...nodes.map((node) => node.position.y));
  const maxX = Math.max(...nodes.map((node) => node.position.x + (node.style?.width || 190)));
  const maxY = Math.max(...nodes.map((node) => node.position.y + (node.style?.height || 78)));
  const pad = 64;
  const width = maxX - minX + pad * 2;
  const height = maxY - minY + pad * 2;
  const translate = (point) => ({ x: point.x - minX + pad, y: point.y - minY + pad });

  const edgeSvg = edges.map((edge) => {
    const source = nodes.find((node) => node.id === edge.source);
    const target = nodes.find((node) => node.id === edge.target);
    if (!source || !target) return "";
    const s = translate({
      x: source.position.x + (source.style?.width || 190) / 2,
      y: source.position.y + (source.style?.height || 78),
    });
    const t = translate({
      x: target.position.x + (target.style?.width || 190) / 2,
      y: target.position.y,
    });
    const midY = (s.y + t.y) / 2;
    return `<path d="M${s.x},${s.y} V${midY} H${t.x} V${t.y}" fill="none" stroke="#433a32" stroke-width="1.6" marker-end="url(#arrow)"/>${
      edge.label ? `<text x="${(s.x + t.x) / 2 + 8}" y="${midY - 6}" font-size="12" fill="#433a32" font-family="sans-serif">${edge.label}</text>` : ""
    }`;
  });

  const nodeSvg = nodes.map((node) => {
    const size = node.style || NODE_SIZE.action;
    const p = translate(node.position);
    const isDiamond = DECISION_KINDS.has(node.data.kind);
    const isEnd = node.data.kind === "terminal";
    const fill = `var(--${node.data.kind})`;
    if (isDiamond) {
      const cx = p.x + size.width / 2;
      const cy = p.y + size.height / 2;
      const points = `${cx},${p.y} ${p.x + size.width},${cy} ${cx},${p.y + size.height} ${p.x},${cy}`;
      return `<polygon points="${points}" fill="#4b93df" stroke="#24364f"/><text x="${cx}" y="${cy - 4}" font-size="13" font-weight="700" text-anchor="middle" fill="#fff" font-family="sans-serif">${escapeXml(node.data.label)}</text>`;
    }
    return `<rect x="${p.x}" y="${p.y}" width="${size.width}" height="${size.height}" rx="${isEnd ? 32 : 10}" fill="${fill}" stroke="#433a32" stroke-width="1.2"/><text x="${p.x + size.width / 2}" y="${p.y + 34}" font-size="13" font-weight="700" text-anchor="middle" fill="#2c241f" font-family="sans-serif">${escapeXml(node.data.label)}</text><text x="${p.x + size.width / 2}" y="${p.y + 54}" font-size="11" text-anchor="middle" fill="#6b5a48" font-family="sans-serif">${escapeXml(node.data.stage)}</text>`;
  });

  const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">
  <defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#433a32"/></marker></defs>
  <style>:root{--input:#dbe8ff;--retrieval:#dff5ea;--llm:#efe2ff;--action:#ffe1a8;--terminal:#f8b03b;}</style>
  <rect width="${width}" height="${height}" fill="#fbf7ef"/>
  <text x="24" y="30" font-size="15" fill="#2c241f" font-weight="700" font-family="sans-serif">LangGraph 赛程流程 · ${escapeXml(topic || "")}</text>
  ${edgeSvg.join("")}
  ${nodeSvg.join("")}
</svg>`;

  const blob = new Blob([svg], { type: "image/svg+xml" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `debate-workflow-${(topic || "export").slice(0, 20).replace(/\s/g, "-")}.svg`;
  a.click();
  URL.revokeObjectURL(url);
}

const WorkflowNode = memo(function WorkflowNode({ data }) {
  return (
    <div className={`workflow-flow-node workflow-flow-node--${data.kind} ${data.status || ""}`}>
      <Handle type="target" position={Position.Top} isConnectable={false} />
      <div className="workflow-flow-node__inner">
        <span>{data.order}</span>
        <strong>{data.label}</strong>
        <small>{data.stage}</small>
      </div>
      <Handle type="source" position={Position.Bottom} isConnectable={false} />
    </div>
  );
});

const nodeTypes = { workflowNode: WorkflowNode };

function WorkflowGraphCanvas({ columns, interactive = false }) {
  const { nodes, edges } = useMemo(() => layoutWorkflow(columns), [columns]);
  const flow = useReactFlow();
  const focusNodes = useMemo(() => {
    const runningIndex = nodes.findIndex((node) => node.data.status === "running");
    if (runningIndex < 0) return nodes.slice(0, interactive ? 6 : 4);
    return nodes.slice(Math.max(0, runningIndex - 2), Math.min(nodes.length, runningIndex + 4));
  }, [interactive, nodes]);

  useEffect(() => {
    window.requestAnimationFrame(() => {
      flow.fitView({
        nodes: interactive ? nodes : focusNodes,
        padding: interactive ? 0.18 : 0.24,
        duration: 240,
        maxZoom: interactive ? 0.95 : 0.78,
      });
    });
  }, [flow, focusNodes, interactive, nodes]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      defaultViewport={{ x: 120, y: 80, zoom: interactive ? 0.9 : 0.68 }}
      minZoom={0.18}
      maxZoom={2.2}
      panOnDrag
      panOnScroll={interactive}
      zoomOnScroll={interactive}
      zoomOnPinch
      zoomOnDoubleClick={false}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable={false}
      proOptions={{ hideAttribution: true }}
    >
      <Background color="#e8ddcf" gap={24} size={1} />
      {interactive && <MiniMap pannable zoomable nodeStrokeWidth={2} />}
      {interactive && <Controls showInteractive={false} />}
    </ReactFlow>
  );
}

export default function WorkflowGraph({ columns, interactive = false }) {
  return (
    <div className={`workflow-flow ${interactive ? "workflow-flow--interactive" : ""}`}>
      <ReactFlowProvider>
        <WorkflowGraphCanvas columns={columns} interactive={interactive} />
      </ReactFlowProvider>
    </div>
  );
}
