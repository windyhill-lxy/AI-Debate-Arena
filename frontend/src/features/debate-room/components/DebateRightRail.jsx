import { useState } from "react";
import { BookOpen, Download, Expand, Gavel, Globe, Lightbulb, Network, Users, X } from "lucide-react";
import MarkdownBody from "../../../components/MarkdownBody.jsx";
import OnlineSimplePanel from "../../../components/OnlineSimplePanel.jsx";
import WorkflowGraph, { exportWorkflowSVG } from "./WorkflowGraph.jsx";
import {
  displaySpeakerName,
  isTeamDiscussion,
  teamDiscussionSide,
} from "../../../utils/debateDisplay.js";
import { debaterLabel, resolveAvatar } from "../utils.js";

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
      <WorkflowGraph columns={columns} interactive />
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
                  <WorkflowGraph columns={workflowColumns} />
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
