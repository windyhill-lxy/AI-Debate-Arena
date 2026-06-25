import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  BookOpen,
  Brain,
  Clock,
  Eye,
  EyeOff,
  FileUp,
  Lightbulb,
  Settings,
  Sparkles,
  TimerReset,
  Users,
  X,
} from "lucide-react";
import SystemConfigBanner from "../../../components/debate/SystemConfigBanner.jsx";
import DebateFlowViewer from "../../../components/DebateFlowViewer.jsx";
import { isHostDesktop } from "../../../utils/visitContext.js";
import { agentSeatLabel } from "../../../utils/debateDisplay.js";
import { MODE_LABELS, debaterLabel, resolveAvatar } from "../utils.js";
import { VISIBILITY_MODES } from "../visibilityModes.js";
import { resolveCurrentRoundSpeaker } from "../currentRoundSpeaker.js";

const VISIBILITY_ICONS = {
  all_visible: Brain,
  own_side_only: EyeOff,
  context: Eye,
  realistic: EyeOff,
  god: Brain,
};

function DockLabel({ icon, label }) {
  return (
    <>
      {icon}
      <span>{label}</span>
    </>
  );
}

export default function DebateLeftRail({
  debate,
  mode,
  isLocal,
  health,
  healthError,
  pipelineHint,
  timing,
  setTiming,
  visibility,
  setVisibility,
  awaitingUser,
  turnSecondsLeft,
  materialTitle,
  setMaterialTitle,
  materialDraft,
  setMaterialDraft,
  materialStatus,
  uploadMaterials,
  onMaterialFile,
  activeAgent,
  activeTab,
  setActiveTab,
  rightActiveTab,
  setRightActiveTab,
  showStrategyTab = false,
  onRequestLeave,
}) {
  const navigate = useNavigate();
  const visibleAgents = (debate.agents || []).filter((agent) => agent.side !== "assistant");
  const currentRoundSpeaker = resolveCurrentRoundSpeaker(debate, activeAgent);
  const currentRoundAvatar = resolveAvatar(currentRoundSpeaker);
  const currentRoundLabel = agentSeatLabel(currentRoundSpeaker) || currentRoundSpeaker?.name || "当前回合";

  const toggleTab = (tab) => {
    setRightActiveTab?.(null);
    setActiveTab(activeTab === tab ? null : tab);
  };

  const toggleRightTab = (tab) => {
    setActiveTab(null);
    setRightActiveTab?.(rightActiveTab === tab ? null : tab);
  };

  const handleLeaveHome = () => {
    if (onRequestLeave && onRequestLeave() === false) return;
    navigate(isHostDesktop() ? "/welcome" : "/");
  };

  return (
    <aside className={`sidebar-container left-sidebar ${activeTab ? "is-expanded" : ""}`}>
      <div className="sidebar-dock">
        <button type="button" className="dock-btn" title="返回首页" onClick={handleLeaveHome}>
          <DockLabel icon={<ArrowLeft size={18} />} label="返回" />
        </button>
        <button className={`dock-btn ${activeTab === "roster" ? "active" : ""}`} onClick={() => toggleTab("roster")} title="AI 成员">
          <DockLabel icon={<Users size={18} />} label="AI 成员" />
        </button>
        {!isLocal && debate.id && debate.id !== "demo-room" && (
          <button className={`dock-btn ${activeTab === "materials" ? "active" : ""}`} onClick={() => toggleTab("materials")} title="辩题资料入库">
            <DockLabel icon={<FileUp size={18} />} label="资料入库" />
          </button>
        )}
        <button className={`dock-btn ${activeTab === "settings" ? "active" : ""}`} onClick={() => toggleTab("settings")} title="设置">
          <DockLabel icon={<Settings size={18} />} label="系统设置" />
        </button>
        <DebateFlowViewer variant="dock" />
        <div className="dock-divider" aria-hidden="true" />
        <button
          className={`dock-btn dock-btn--round ${rightActiveTab === "turn" ? "active" : ""}`}
          onClick={() => toggleRightTab("turn")}
          title={`当前回合：${currentRoundLabel}`}
        >
          <DockLabel
            icon={
              currentRoundAvatar ? (
                <img className="dock-btn__avatar" src={currentRoundAvatar} alt="" />
              ) : (
                <span className="dock-btn__avatar dock-btn__avatar--fallback" aria-hidden="true">
                  回
                </span>
              )
            }
            label="回合"
          />
        </button>
        {showStrategyTab && (
          <button className={`dock-btn ${rightActiveTab === "strategy" ? "active" : ""}`} onClick={() => toggleRightTab("strategy")} title="AI 策略">
            <DockLabel icon={<Lightbulb size={18} />} label="策略" />
          </button>
        )}
        <button className={`dock-btn ${rightActiveTab === "team" ? "active" : ""}`} onClick={() => toggleRightTab("team")} title="队内讨论">
          <DockLabel icon={<Users size={18} />} label="队内讨论" />
        </button>
        <button className={`dock-btn ${rightActiveTab === "arguments" ? "active" : ""}`} onClick={() => toggleRightTab("arguments")} title="论据库">
          <DockLabel icon={<BookOpen size={18} />} label="论据库" />
        </button>
      </div>

      <div className="sidebar-panel-container">
        {activeTab && (
          <div className="sidebar-panel glass-panel">
            <div className="sidebar-header">
              <div className="brand-mark-row">
                <div className="brand-mark">
                  <Settings size={20} />
                </div>
                <div>
                  <p className="eyebrow">Agentic Debate</p>
                  <h3>{MODE_LABELS[debate.mode || mode]}</h3>
                </div>
              </div>
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
              {activeTab === "roster" && (
                <section className="panel roster roster--primary">
                  <div className="panel-title">
                    <Sparkles size={18} /> AI 成员
                    <span>{visibleAgents.length} 位</span>
                  </div>
                  {visibleAgents.length > 0 ? (
                    <div className="roster-grid">
                      {visibleAgents.map((agent) => (
                        <article key={agent.id} className={`agent-row ${agent.id === activeAgent?.id ? "current" : ""}`}>
                          <img src={resolveAvatar(agent)} alt={agentSeatLabel(agent) || agent.name} />
                          <div>
                            <strong>{agentSeatLabel(agent) || agent.name}</strong>
                            <span>
                              {debaterLabel(agent)} · {agent.model}
                            </span>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <p className="empty-note">正在等待后端下发 AI 成员信息。</p>
                  )}
                </section>
              )}

              {activeTab === "materials" && !isLocal && debate.id && debate.id !== "demo-room" && (
                <section className="panel materials-panel">
                  <div className="panel-title">
                    <FileUp size={18} /> 辩题资料入库
                  </div>
                  <input
                    className="materials-title-input"
                    value={materialTitle}
                    onChange={(e) => setMaterialTitle(e.target.value)}
                    placeholder="资料标题"
                  />
                  <textarea
                    rows={4}
                    value={materialDraft}
                    onChange={(e) => setMaterialDraft(e.target.value)}
                    placeholder="粘贴补充资料，将分块写入本场向量库…"
                  />
                  <div className="materials-actions">
                    <button type="button" onClick={() => uploadMaterials(false)} disabled={!materialDraft.trim()}>
                      追加入库
                    </button>
                    <label className="home-file-btn compact">
                      <FileUp size={14} /> 文件
                      <input type="file" accept=".txt,.md,text/plain" onChange={onMaterialFile} hidden />
                    </label>
                  </div>
                  {materialStatus && <p className="pipeline-hint">{materialStatus}</p>}
                </section>
              )}

              {activeTab === "settings" && (
                <>
                  <SystemConfigBanner health={health} healthError={healthError} />

                  <section className="panel panel--compact-hint">
                    {timing === "limited" && debate.auto_running && !awaitingUser && (
                      <p className="turn-timer">本环节剩余约 {turnSecondsLeft}s</p>
                    )}
                    <p className="keyboard-hint">底部固定栏：赛程进度、跳过朗读、继续推进、导出；Esc 跳过朗读</p>
                    {pipelineHint && <p className="pipeline-hint">{pipelineHint}</p>}
                  </section>

                  <section className="panel">
                    <p className="visibility-hint">赛前规则已锁定，赛中仅展示当前设置。</p>
                    <div className="segmented">
                      <button
                        className={timing === "limited" ? "active" : ""}
                        type="button"
                        disabled={debate.timing_locked}
                        onClick={() => !debate.timing_locked && setTiming("limited")}
                      >
                        <Clock size={14} /> 限时
                      </button>
                      <button
                        className={timing === "unlimited" ? "active" : ""}
                        type="button"
                        disabled={debate.timing_locked}
                        onClick={() => !debate.timing_locked && setTiming("unlimited")}
                      >
                        <TimerReset size={14} /> 不限时
                      </button>
                    </div>
                    <div className="visibility-list">
                      {VISIBILITY_MODES.map((modeOption) => {
                        const Icon = VISIBILITY_ICONS[modeOption.id] || Eye;
                        return (
                          <button
                            key={modeOption.id}
                            className={visibility === modeOption.id ? "active" : ""}
                            type="button"
                            title={modeOption.hint}
                            disabled={debate.visibility_locked}
                            onClick={() => !debate.visibility_locked && setVisibility(modeOption.id)}
                          >
                            <Icon size={15} /> {modeOption.label}
                          </button>
                        );
                      })}
                    </div>
                    <p className="visibility-hint">{VISIBILITY_MODES.find((m) => m.id === visibility)?.hint}</p>
                  </section>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
