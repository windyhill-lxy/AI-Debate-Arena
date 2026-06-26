import { BookOpen, Gavel, Lightbulb, Users, X } from "lucide-react";
import { useState } from "react";
import { Check, Copy } from "lucide-react";
import CitationMarkdownBody from "../../../components/CitationMarkdownBody.jsx";
import MarkdownBody from "../../../components/MarkdownBody.jsx";
import {
  agentSeatLabel,
  displaySpeakerName,
  isTeamDiscussion,
  teamDiscussionSide,
} from "../../../utils/debateDisplay.js";
import { citationTokenForArgumentId, copyTextToClipboard } from "../argumentCitation.js";
import { debaterLabel, resolveAvatar } from "../utils.js";

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
  teamDiscussions,
  activeTab,
  setActiveTab,
  visibility = "context",
  userSide = null,
  hideDock = false,
  sourceMap,
  onCitationSelect,
}) {
  const [copiedArgumentId, setCopiedArgumentId] = useState(null);
  const displayAgent = activeAgent || debate.agents?.[0] || {
    id: "pending",
    name: "等待辩手",
    side: "assistant",
    position: 0,
    model: "pending",
    avatar: "",
  };
  const displayAgentLabel = agentSeatLabel(displayAgent) || displayAgent.name;

  const toggleTab = (tab) => {
    setActiveTab(activeTab === tab ? null : tab);
  };

  const copyArgumentCitation = async (id) => {
    const token = citationTokenForArgumentId(id);
    if (!token) return;
    await copyTextToClipboard(token);
    setCopiedArgumentId(id);
    window.setTimeout(() => {
      setCopiedArgumentId((current) => (current === id ? null : current));
    }, 1200);
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
        activeTab === "team" ? "is-team-panel" : ""
      } ${activeTab === "arguments" ? "is-arguments-panel" : ""} ${
        hideDock ? "is-dockless" : ""
      }`}
    >
      {!hideDock && (
        <div className="sidebar-dock">
          <button className={`dock-btn ${activeTab === "turn" ? "active" : ""}`} onClick={() => toggleTab("turn")} title="当前回合">
            <DockLabel icon={<Gavel size={18} />} label="回合" />
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
        </div>
      )}

      <div className="sidebar-panel-container">
        {activeTab && (
          <div className="sidebar-panel glass-panel">
            <div className="sidebar-header">
              <h3>
                {activeTab === "turn" && "当前回合"}
                {activeTab === "strategy" && "AI 策略"}
                {activeTab === "team" && "队内讨论"}
                {activeTab === "arguments" && "论据库"}
              </h3>
              <button
                type="button"
                className="sidebar-close-btn"
                onClick={() => setActiveTab(null)}
                title="关闭"
                aria-label="关闭面板"
              >
                <X size={16} />
              </button>
            </div>

            <div className="sidebar-content">
              {activeTab === "turn" && (
                <section className="panel active-turn">
                  <div className="active-agent">
                    <img src={resolveAvatar(displayAgent)} alt={displayAgent.name} />
                    <div>
                      <h3>{displayAgentLabel}</h3>
                      <p>
                        {displayAgent.side === "judge" ? "裁判" : debaterLabel(displayAgent)} · {displayAgent.model}
                      </p>
                      <p className="segment-info">{debate.segment_label}</p>
                    </div>
                  </div>
                </section>
              )}
              {activeTab === "strategy" && visibility === "context" && (
                <section className="panel strategy-panel">
                  <p className="empty-note">复盘视角：展示 AI 辩手的内部策略与反思草稿，不进入主舞台。</p>
                  <div className="strategy-note-list">
                    {aiStrategyNotes.length === 0 && (
                      <p className="empty-note">暂无策略备注，等待 AI 发言后生成。</p>
                    )}
                    {aiStrategyNotes.map((message) => (
                      <article key={message.id} className="strategy-note-item">
                        <strong>{displaySpeakerName(message, debate)}</strong>
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
                                <CitationMarkdownBody
                                  content={message.content}
                                  sourceMap={sourceMap}
                                  onCitationSelect={onCitationSelect}
                                />
                              </div>
                            ))}
                            {live && (
                              <div className="team-note streaming-message">
                                <strong>{displaySpeakerName(live, debate)}</strong>
                                <span>{live.segment_label || "队内讨论"}</span>
                                <CitationMarkdownBody
                                  content={live.content}
                                  streaming
                                  sourceMap={sourceMap}
                                  onCitationSelect={onCitationSelect}
                                />
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
                        {items.length === 0 && (
                          <p className="empty-note">
                            {debate.argument_bank_locked
                              ? `${side === "affirmative" ? "正方" : "反方"}论据尚未入库，正在等待检索结果同步。`
                              : `${side === "affirmative" ? "正方" : "反方"}论据检索即将开始，双方论据会公开显示在这里。`}
                          </p>
                        )}
                        {items.length > 0 && <span className="argument-bank-count">{items.length} 条</span>}
                        {items.map((item) => (
                          <article key={item.id} className="argument-bank-item">
                            <div className="argument-bank-item__head">
                              <div className="argument-bank-item__id-wrap">
                                <span className="argument-bank-item__id">{item.id}</span>
                                <button
                                  type="button"
                                  className="argument-bank-item__copy"
                                  title={`复制引用 ${citationTokenForArgumentId(item.id)}`}
                                  aria-label={`复制论据引用 ${citationTokenForArgumentId(item.id)}`}
                                  onClick={() => copyArgumentCitation(item.id)}
                                >
                                  {copiedArgumentId === item.id ? <Check size={13} /> : <Copy size={13} />}
                                </button>
                              </div>
                              <strong className="argument-bank-item__title">{item.title || "标题生成中"}</strong>
                            </div>
                            <div className="argument-bank-item__content" aria-label="论据内容">
                              <MarkdownBody content={item.claim || "暂无论据内容"} />
                            </div>
                            {item.source && <small className="argument-bank-item__source">来源：{item.source}</small>}
                          </article>
                        ))}
                      </div>
                    );
                  })}
                </section>
              )}

            </div>
          </div>
        )}
      </div>
    </aside>
  );
}

