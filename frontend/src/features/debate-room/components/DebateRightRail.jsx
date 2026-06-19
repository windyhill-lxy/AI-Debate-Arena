import { useRef, useState } from "react";
import { BookOpen, Brain, Download, Expand, Gavel, Globe, Lightbulb, Network, Users, X } from "lucide-react";
import MarkdownBody from "../../../components/MarkdownBody.jsx";
import OnlineSimplePanel from "../../../components/OnlineSimplePanel.jsx";
import {
  displaySpeakerName,
  isJudgeThought,
  isTeamDiscussion,
  teamDiscussionSide,
} from "../../../utils/debateDisplay.js";
import { debaterLabel, resolveAvatar } from "../utils.js";

const KIND_COLOR = {
  input: "#334a8a", retrieval: "#2f5f48", llm: "#7c4a8a",
  check: "#8a6a2f", action: "#4a6a8a", judge: "#8a2f2f", router: "#8a5a2f",
};

function escapeXml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function buildWorkflowLayout(columns) {
  const NODE_W = 230;
  const NODE_H = 78;
  const ROW_GAP = 22;
  const STAGE_GAP = 34;
  const PAD_X = 28;
  const PAD_Y = 36;
  const STAGE_W = 156;
  const NODE_X = PAD_X + STAGE_W + NODE_W / 2 + 30;
  const nodes = [];
  const stages = [];
  let y = PAD_Y + NODE_H / 2;
  for (const [stageIndex, column] of (columns || []).entries()) {
    const stageNodes = [...(column.nodes || [])].sort((a, b) => (a.lane || 0) - (b.lane || 0));
    if (!stageNodes.length) continue;
    const startY = y - NODE_H / 2;
    for (const [nodeIndex, node] of stageNodes.entries()) {
      nodes.push({
        ...node,
        stage: column.stage,
        x: NODE_X,
        y,
        order: `${stageIndex + 1}.${nodeIndex + 1}`,
      });
      y += NODE_H + ROW_GAP;
    }
    const endY = y - ROW_GAP - NODE_H / 2;
    stages.push({
      stage: column.stage,
      index: stageIndex + 1,
      x: PAD_X,
      y: (startY + endY) / 2,
      height: Math.max(NODE_H, endY - startY + NODE_H),
    });
    y += STAGE_GAP;
  }
  const width = 560;
  const height = Math.max(320, y + PAD_Y);
  return { nodes, stages, width, height, nodeWidth: NODE_W, nodeHeight: NODE_H };
}

function exportWorkflowSVG(columns, topic) {
  const layout = buildWorkflowLayout(columns);
  const { nodes, stages, width, height, nodeWidth, nodeHeight } = layout;

  const paths = nodes.slice(1).map((n, i) => {
    const prev = nodes[i];
    return `<path d="M${prev.x},${prev.y + nodeHeight / 2} C${prev.x},${prev.y + nodeHeight / 2 + 12} ${n.x},${n.y - nodeHeight / 2 - 12} ${n.x},${n.y - nodeHeight / 2}" fill="none" stroke="#c9b9a5" stroke-width="2"/>`;
  });

  const stageLabels = stages.map((stage) => `
    <g transform="translate(${stage.x},${stage.y - stage.height / 2})">
      <rect width="148" height="${stage.height}" rx="12" fill="#f3eadf" stroke="#dcc9b5"/>
      <text x="14" y="28" font-size="12" fill="#8b6848" font-weight="700" font-family="sans-serif">${String(stage.index).padStart(2, "0")}</text>
      <text x="14" y="50" font-size="13" fill="#2c241f" font-weight="700" font-family="sans-serif">${escapeXml(stage.stage)}</text>
    </g>`);

  const rects = nodes.map((n) => {
    const color = KIND_COLOR[n.kind] || "#555";
    const status = n.status === "done" ? "opacity:0.5" : n.status === "running" ? "filter:drop-shadow(0 0 4px #334a8a)" : "";
    return `
    <g transform="translate(${n.x - nodeWidth / 2},${n.y - nodeHeight / 2})" style="${status}">
      <rect width="${nodeWidth}" height="${nodeHeight}" rx="10" fill="${color}18" stroke="${color}" stroke-width="1.5"/>
      <text x="8" y="20" font-size="10" fill="${color}" font-weight="600" font-family="sans-serif">${n.kind?.toUpperCase()}</text>
      <text x="${nodeWidth / 2}" y="44" font-size="13" fill="#2c241f" font-weight="700" text-anchor="middle" font-family="sans-serif">${escapeXml(n.label)}</text>
      <text x="${nodeWidth / 2}" y="62" font-size="10" fill="#6b5a48" text-anchor="middle" font-family="sans-serif">${escapeXml(n.stage)}</text>
    </g>`;
  });

  const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">
  <rect width="${width}" height="${height}" fill="#faf6ef"/>
  <text x="28" y="24" font-size="14" fill="#2c241f" font-weight="700" font-family="sans-serif">LangGraph 赛程流程 · ${escapeXml(topic || '')}</text>
  ${stageLabels.join("")}
  ${paths.join("")}
  ${rects.join("")}
</svg>`;

  const blob = new Blob([svg], { type: "image/svg+xml" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `debate-workflow-${(topic || "export").slice(0, 20).replace(/\s/g, "-")}.svg`;
  a.click();
  URL.revokeObjectURL(url);
}

function WorkflowMindMap({ columns, interactive = false }) {
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const dragRef = useRef(null);
  const { nodes, stages, width, height } = buildWorkflowLayout(columns);
  const onWheel = (event) => {
    if (!interactive) return;
    event.preventDefault();
    const next = Math.max(0.45, Math.min(2.4, scale + (event.deltaY > 0 ? -0.08 : 0.08)));
    setScale(next);
  };
  const onPointerDown = (event) => {
    if (!interactive || event.button !== 0) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    dragRef.current = { x: event.clientX, y: event.clientY, start: offset };
  };
  const onPointerMove = (event) => {
    if (!dragRef.current) return;
    const dx = event.clientX - dragRef.current.x;
    const dy = event.clientY - dragRef.current.y;
    setOffset({ x: dragRef.current.start.x + dx, y: dragRef.current.start.y + dy });
  };
  const stopDrag = () => {
    dragRef.current = null;
  };

  return (
    <div
      className={`workflow-mindmap-shell ${interactive ? "workflow-mindmap-shell--interactive" : ""}`}
      onWheel={onWheel}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={stopDrag}
      onPointerCancel={stopDrag}
    >
      <div
        className="workflow-mindmap"
        style={{
          "--workflow-width": `${width}px`,
          transform: interactive ? `translate(${offset.x}px, ${offset.y}px) scale(${scale})` : undefined,
          transformOrigin: "center center",
        }}
      >
      <svg className="workflow-mindmap__links" viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
        {nodes.slice(1).map((node, index) => {
          const prev = nodes[index];
          return (
            <path
              key={`${prev.id}-${node.id}`}
              d={`M ${prev.x} ${prev.y + 40} C ${prev.x} ${prev.y + 58}, ${node.x} ${node.y - 58}, ${node.x} ${node.y - 40}`}
            />
          );
        })}
      </svg>
      <div className="workflow-mindmap__nodes" style={{ width, height }}>
        {stages.map((stage) => (
          <aside
            key={stage.stage}
            className="workflow-stage-label"
            style={{ left: stage.x, top: stage.y, height: stage.height }}
          >
            <span>{String(stage.index).padStart(2, "0")}</span>
            <strong>{stage.stage}</strong>
          </aside>
        ))}
        {nodes.map((node) => (
          <article
            key={node.id}
            className={`mind-node ${node.status} ${node.kind || ""}`}
            style={{ left: node.x, top: node.y }}
          >
            <span>{node.order}</span>
            <strong>{node.label}</strong>
            <p>{node.stage}</p>
          </article>
        ))}
      </div>
      </div>
    </div>
  );
}

function WorkflowGraphModal({ columns, topic, onClose }) {
  return (
    <div className="workflow-modal" role="dialog" aria-modal="true" aria-label="LangGraph 流程图大图">
      <div className="workflow-modal__bar">
        <div>
          <strong>LangGraph 流程图</strong>
          <span>{topic || "当前辩论"} · 滚轮缩放，按住拖动查看</span>
        </div>
        <button type="button" className="workflow-modal__close" onClick={onClose}>
          <X size={18} /> 关闭
        </button>
      </div>
      <WorkflowMindMap columns={columns} interactive />
    </div>
  );
}

function DockLabel({ icon, label }) {
  return (
    <>
      {icon}
      <span>{label}</span>
    </>
  );
}

export default function DebateRightRail({
  debate,
  activeAgent,
  judgeThoughts,
  aiStrategyNotes = [],
  streaming,
  participant,
  teamDiscussions,
  workflowColumns,
  activeTab,
  setActiveTab,
  visibility = "context",
  userSide = null,
}) {
  const displayAgent = activeAgent || debate.agents?.[0] || {
    id: "pending",
    name: "等待辩手",
    side: "assistant",
    position: 0,
    model: "pending",
    avatar: "",
  };
  const [graphOpen, setGraphOpen] = useState(false);

  const toggleTab = (tab) => {
    setActiveTab(activeTab === tab ? null : tab);
  };

  const teamEmptyNote = (side, messages, live) => {
    if (messages.length > 0 || live) return null;
    const viewerTeam = userSide && userSide !== "spectator" && visibility !== "god" ? userSide : null;
    if (viewerTeam && side !== viewerTeam) {
      return <p className="empty-note empty-note--denied">没有权限查看对方队内讨论。</p>;
    }
    return <p className="empty-note">等待本方讨论节点开始。</p>;
  };

  return (
    <aside
      className={`sidebar-container right-sidebar ${activeTab ? "is-expanded" : ""} ${
        activeTab === "graph" ? "is-graph-panel" : ""
      } ${activeTab === "team" ? "is-team-panel" : ""} ${activeTab === "arguments" ? "is-arguments-panel" : ""}`}
    >
      <div className="sidebar-dock">
        <button className={`dock-btn ${activeTab === "turn" ? "active" : ""}`} onClick={() => toggleTab("turn")} title="当前回合">
          <DockLabel icon={<Gavel size={18} />} label="回合" />
        </button>
        {debate.mode === "online_match" && (
          <button className={`dock-btn ${activeTab === "online" ? "active" : ""}`} onClick={() => toggleTab("online")} title="邀请同学">
            <DockLabel icon={<Globe size={18} />} label="联机" />
          </button>
        )}
        <button className={`dock-btn ${activeTab === "judge" ? "active" : ""}`} onClick={() => toggleTab("judge")} title="裁判思路">
          <DockLabel icon={<Brain size={18} />} label="裁判" />
        </button>
        {visibility === "context" && (
          <button className={`dock-btn ${activeTab === "strategy" ? "active" : ""}`} onClick={() => toggleTab("strategy")} title="AI 策略">
            <DockLabel icon={<Lightbulb size={18} />} label="策略" />
          </button>
        )}
        <button className={`dock-btn ${activeTab === "team" ? "active" : ""}`} onClick={() => toggleTab("team")} title="队内讨论">
            <DockLabel icon={<Users size={18} />} label="队内讨论" />
          </button>
        <button className={`dock-btn ${activeTab === "arguments" ? "active" : ""}`} onClick={() => toggleTab("arguments")} title="论据库">
          <DockLabel icon={<BookOpen size={18} />} label="论据库" />
        </button>
        <button className={`dock-btn ${activeTab === "graph" ? "active" : ""}`} onClick={() => toggleTab("graph")} title="LangGraph 工作流">
          <DockLabel icon={<Network size={18} />} label="流程图" />
        </button>
      </div>

      <div className="sidebar-panel-container">
        {activeTab && (
          <div className="sidebar-panel glass-panel">
            <div className="sidebar-header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <h3>
                {activeTab === "turn" && "当前回合"}
                {activeTab === "online" && "邀请同学"}
                {activeTab === "judge" && "裁判思路"}
                {activeTab === "strategy" && "AI 策略"}
                {activeTab === "team" && "队内讨论"}
                {activeTab === "arguments" && "论据库"}
                {activeTab === "graph" && "LangGraph 工作流"}
              </h3>
              {activeTab === "graph" && (
                <div className="graph-header-actions">
                  <button type="button" className="dock-btn" title="打开大图" onClick={() => setGraphOpen(true)}>
                    <Expand size={13} /> 大图
                  </button>
                  <button
                    type="button"
                    className="dock-btn"
                    title="导出工作流图 SVG"
                    onClick={() => exportWorkflowSVG(workflowColumns, debate?.topic)}
                  >
                    <Download size={13} /> 导出
                  </button>
                </div>
              )}
            </div>

            <div className={`sidebar-content ${activeTab === "graph" ? "sidebar-content--graph" : ""}`}>
              {activeTab === "turn" && (
                <section className="panel active-turn">
                  <div className="active-agent">
                    <img src={resolveAvatar(displayAgent)} alt={displayAgent.name} />
                    <div>
                      <h3>{displayAgent.name}</h3>
                      <p>
                        {debaterLabel(displayAgent)} · {displayAgent.model}
                      </p>
                      <p className="segment-info">{debate.segment_label}</p>
                    </div>
                  </div>
                </section>
              )}

              {activeTab === "online" && debate.mode === "online_match" && (
                <section className="panel online-panel online-panel--simple">
                  <OnlineSimplePanel variant="room" debateId={debate.id} />
                  <details className="online-panel__details">
                    <summary>在线辩手</summary>
                    <p className="empty-note">
                      当前身份：
                      {participant
                        ? `${participant.side === "affirmative" ? "正方" : "反方"}${participant.position} 辩 · ${participant.name}`
                        : "未加入席位"}
                    </p>
                    <div className="online-seat-list">
                      {(debate.participants || []).filter((item) => item.side !== "spectator").length === 0 && (
                        <p className="empty-note">等待同学选席加入。</p>
                      )}
                      {(debate.participants || [])
                        .filter((item) => item.side !== "spectator")
                        .map((item) => (
                          <div key={item.id} className={`online-seat ${item.side}`}>
                            <span>
                              {`${item.side === "affirmative" ? "正" : "反"}${item.position} · ${item.name}`}
                            </span>
                          </div>
                        ))}
                    </div>
                  </details>
                </section>
              )}

              {activeTab === "judge" && (
                <section className="panel judge-thought-panel">
                  <div className="judge-thought-list">
                    {visibility === "realistic" && (
                      <p className="empty-note">赛场视角不展示裁判内部思路。</p>
                    )}
                    {visibility !== "realistic" && judgeThoughts.length === 0 && !(streaming && isJudgeThought(streaming)) && (
                      <p className="empty-note">等待裁判进入最终裁决分析阶段。</p>
                    )}
                    {visibility !== "realistic" && judgeThoughts.map((message) => (
                      <article key={message.id} className="judge-thought-item">
                        <strong>{message.segment_label}</strong>
                        <MarkdownBody content={message.content} />
                      </article>
                    ))}
                    {visibility !== "realistic" && streaming && isJudgeThought(streaming) && (
                      <article className="judge-thought-item streaming-message">
                        <strong>{streaming.segment_label || "裁判分析"}</strong>
                        <MarkdownBody content={streaming.content} streaming />
                      </article>
                    )}
                  </div>
                </section>
              )}

              {activeTab === "strategy" && visibility === "context" && (
                <section className="panel strategy-panel">
                  <p className="empty-note">复盘视角：展示 AI 辩手的内部策略与反思草稿（不进入主舞台）。</p>
                  <div className="strategy-note-list">
                    {aiStrategyNotes.length === 0 && (
                      <p className="empty-note">暂无策略备注，等待 AI 发言后生成。</p>
                    )}
                    {aiStrategyNotes.map((message) => (
                      <article key={message.id} className="strategy-note-item">
                        <strong>{message.speaker_name}</strong>
                        <span>{message.segment_label}</span>
                        {message.private_thought && (
                          <div className="strategy-block">
                            <em>内部思路</em>
                            <MarkdownBody content={message.private_thought} />
                          </div>
                        )}
                        {message.strategy && (
                          <div className="strategy-block">
                            <em>策略路线</em>
                            <MarkdownBody content={message.strategy} />
                          </div>
                        )}
                      </article>
                    ))}
                  </div>
                </section>
              )}

              {activeTab === "team" && (
                <section className="panel team-discussion-panel">
                  <p className="empty-note">内部讨论不调用 TTS</p>
                  <div className="team-discussion-grid">
                    {["affirmative", "negative"].map((side) => {
                      const messages = teamDiscussions?.[side] || [];
                      const live =
                        streaming && isTeamDiscussion(streaming) && teamDiscussionSide(streaming, debate.agents) === side
                          ? streaming
                          : null;
                      return (
                        <article key={side} className={`team-window ${side}`}>
                          <h3>{side === "affirmative" ? "正方" : "反方"}</h3>
                          <div className="team-window-body">
                            {teamEmptyNote(side, messages, live)}
                            {messages.map((message) => (
                              <div key={message.id} className="team-note">
                                <strong>{displaySpeakerName(message, debate)}</strong>
                                <span>{message.segment_label}</span>
                                <MarkdownBody content={message.content} />
                              </div>
                            ))}
                            {live && (
                              <div className="team-note streaming-message">
                                <strong>{live.speaker_name}</strong>
                                <span>{live.segment_label || "队内讨论"}</span>
                                <MarkdownBody content={live.content} streaming />
                              </div>
                            )}
                          </div>
                        </article>
                      );
                    })}
                  </div>
                </section>
              )}

              {activeTab === "arguments" && (
                <section className="panel argument-bank-panel">
                  {["affirmative", "negative"].map((side) => {
                    const items = debate.argument_bank?.[side] || [];
                    return (
                      <div key={side} className={`argument-bank-side ${side}`}>
                        <h4>{side === "affirmative" ? "正方论据" : "反方论据"}</h4>
                        {items.length === 0 && <p className="empty-note">队内讨论或训练准备结束后将显示本方入库论据。</p>}
                        {items.map((item) => (
                          <article key={item.id} className="argument-bank-item">
                            <div className="argument-bank-item__head">
                              <strong>{item.title || item.claim?.slice(0, 14) || item.id}</strong>
                              <span>{item.id}</span>
                            </div>
                            <MarkdownBody content={item.claim} />
                            {item.source && <small>{item.source}</small>}
                          </article>
                        ))}
                      </div>
                    );
                  })}
                </section>
              )}

              {activeTab === "graph" && (
                <section className="panel graph-panel">
                  <WorkflowMindMap columns={workflowColumns} />
                </section>
              )}
            </div>
          </div>
        )}
      </div>
      {graphOpen && <WorkflowGraphModal columns={workflowColumns} topic={debate?.topic} onClose={() => setGraphOpen(false)} />}
    </aside>
  );
}
