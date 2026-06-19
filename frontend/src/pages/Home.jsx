import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bot, Camera, FileUp, MessageCircle, Scale, Sparkles, Users } from "lucide-react";
import ConfidenceCameraPreview from "../components/ConfidenceCameraPreview.jsx";
import SystemConfigBanner from "../components/debate/SystemConfigBanner.jsx";
import { useDebateHealth } from "../hooks/useDebateHealth.js";
import { API_BASE } from "../utils/apiBase.js";
import "../styles/home.css";
const MODES = [
  {
    id: "ai_autonomous",
    title: "AI 自主辩论",
    desc: "正反双方由 AI 完成。",
    icon: Bot,
    accent: "mode-auto",
  },
  {
    id: "user_affirmative",
    title: "加入正方",
    desc: "作为正方辩手参赛。",
    icon: Users,
    accent: "mode-aff",
  },
  {
    id: "user_negative",
    title: "加入反方",
    desc: "作为反方辩手参赛。",
    icon: Scale,
    accent: "mode-neg",
  },
];

const FALLBACK_SCHEDULES = [
  {
    id: "formal_4v4",
    title: "标准 4v4 完整赛制",
    description: "立论、盘问、自由辩、总结与裁判终局",
    segments_count: 80,
  },
];

const WIZARD_STEPS = ["辩题资料", "参赛席位", "赛程设置", "摄像头", "确认进入"];
const DEBATER_POSITIONS = [1, 2, 3, 4];

async function createDebate(topic, mode, scheduleTemplate, materials, userSeat, rules) {
  const response = await fetch(`${API_BASE}/api/debates`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      topic,
      mode,
      user_side: userSeat?.side || null,
      user_position: userSeat?.position || 1,
      user_name: userSeat?.name || "用户辩手",
      visibility: rules.visibility,
      timing: rules.timing,
      tts_enabled: rules.ttsEnabled,
      human_timeout_penalty_enabled: rules.timing === "limited",
      format: "formal",
      schedule_template: scheduleTemplate,
      materials: materials.filter((m) => m.content?.trim()),
    }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function toggleConfidenceMonitor(enabled, { showLandmarks = false, cameraIndex = 0, lowPerformance = false } = {}) {
  const response = await fetch(`${API_BASE}/api/confidence-monitor/toggle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      enabled,
      show_landmarks: showLandmarks,
      camera_index: cameraIndex,
      low_performance: lowPerformance,
    }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function fetchConfidenceStatus() {
  const response = await fetch(`${API_BASE}/api/confidence-monitor/status`);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function fetchConfidenceReport() {
  const response = await fetch(`${API_BASE}/api/confidence-monitor/report`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ max_samples: 1000 }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export default function Home() {
  const navigate = useNavigate();
  const { health, error: healthError, apiBase } = useDebateHealth();
  const initialMode = "ai_autonomous";
  const [topic, setTopic] = useState("人工智能是否会提升青少年的综合学习能力");
  const [mode, setMode] = useState(initialMode);
  const [setupStep, setSetupStep] = useState(0);
  const [userSide, setUserSide] = useState("affirmative");
  const [userPosition, setUserPosition] = useState(1);
  const [userName, setUserName] = useState("用户辩手");
  const [scheduleTemplate, setScheduleTemplate] = useState("formal_4v4");
  const [visibilityMode, setVisibilityMode] = useState("own_side_only");
  const [timingMode, setTimingMode] = useState("limited");
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [schedules, setSchedules] = useState(FALLBACK_SCHEDULES);
  const [materialTitle, setMaterialTitle] = useState("辩题参考资料");
  const [materialText, setMaterialText] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploadHint, setUploadHint] = useState("");
  const [importHint, setImportHint] = useState("");
  const [importing, setImporting] = useState(false);
  const [confidenceEnabled, setConfidenceEnabled] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem("confidence-monitor-enabled") === "1";
  });
  const [showLandmarks, setShowLandmarks] = useState(true);
  const [lowPerformance, setLowPerformance] = useState(false);
  const [confidenceHint, setConfidenceHint] = useState("");
  const [confidenceStatus, setConfidenceStatus] = useState(null);
  const [confidenceReport, setConfidenceReport] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [cameraDiag, setCameraDiag] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/api/debates/schedules`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data?.templates?.length) setSchedules(data.templates);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("confidence-monitor-enabled", confidenceEnabled ? "1" : "0");
  }, [confidenceEnabled]);

  useEffect(() => {
    let stopped = false;
    async function sync() {
      try {
        const status = await fetchConfidenceStatus();
        if (!stopped) setConfidenceStatus(status);
      } catch {
        if (!stopped) setConfidenceStatus(null);
      }
    }
    sync();
    const timer = setInterval(sync, 3000);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, []);

  async function onMaterialFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      setMaterialText((prev) => (prev ? `${prev}\n\n${text}` : text));
      setMaterialTitle(file.name.replace(/\.[^.]+$/, "") || "上传文件");
      setUploadHint(`已读取 ${file.name}（${text.length} 字），创建房间时将写入向量库。`);
    } catch {
      setUploadHint("文件读取失败，请使用 UTF-8 编码的 .txt / .md");
    }
    event.target.value = "";
  }

  async function enterRoom() {
    setLoading(true);
    try {
      const humanMode = mode === "user_affirmative" || mode === "user_negative";
      const modeForCreate = humanMode
        ? userSide === "negative"
          ? "user_negative"
          : "user_affirmative"
        : mode;
      const userSeat = humanMode
        ? { side: userSide, position: userPosition, name: userName.trim() || "用户辩手" }
        : null;
      const shouldEnableMonitor = modeForCreate !== "ai_autonomous" && confidenceEnabled;
      try {
        const monitor = await toggleConfidenceMonitor(shouldEnableMonitor, { showLandmarks, lowPerformance });
        if (shouldEnableMonitor && !monitor.running && monitor.last_error) {
          setConfidenceHint(`启动失败：${monitor.last_error}`);
          const confirmEnter = window.confirm(`自信度摄像头训练启动失败：\n${monitor.last_error}\n\n是否不开启摄像头继续进入房间？`);
          if (!confirmEnter) {
            setLoading(false);
            return;
          }
        } else if (shouldEnableMonitor && monitor.running) {
          setConfidenceHint("自信度训练已启动，摄像头窗口会在桌面弹出。");
        } else if (modeForCreate === "ai_autonomous" && confidenceEnabled) {
          setConfidenceHint("当前是 AI 自主模式，已自动关闭自信度训练。");
        } else if (confidenceEnabled && !monitor.available) {
          setConfidenceHint(
            `自信度训练未启动：缺少依赖 ${monitor.missing_dependencies?.join(", ") || "未知"}。`,
          );
        } else {
          setConfidenceHint("自信度训练处于关闭状态。");
        }
      } catch (error) {
        setConfidenceHint(`自信度训练开关失败：${error.message || "请确认后端已启动"}`);
      }

      const materials = materialText.trim()
        ? [{ title: materialTitle, content: materialText }]
        : [];
      const rules = {
        visibility: modeForCreate === "ai_autonomous" ? "all_visible" : visibilityMode,
        timing: modeForCreate === "ai_autonomous" ? "unlimited" : timingMode,
        ttsEnabled,
      };
      const debate = await createDebate(topic, modeForCreate, scheduleTemplate, materials, userSeat, rules);
      if (modeForCreate === "online_match") {
        navigate(`/join/${debate.id}`, {
          state: { topic, fromCreate: true, scheduleTemplate, materialChunks: materials.length },
        });
      } else {
        navigate(`/room/${debate.id}`, {
          state: { debate, mode: modeForCreate, topic, scheduleTemplate, materialChunks: materials.length },
        });
      }
    } catch (error) {
      alert(`创建房间失败：${error.message || "请确认后端已启动并填写 API Key"}`);
    } finally {
      setLoading(false);
    }
  }

  async function runCameraDiagnostics() {
    if (!navigator.mediaDevices?.enumerateDevices) {
      setCameraDiag("当前浏览器不支持摄像头诊断。");
      return;
    }
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const videos = devices.filter((d) => d.kind === "videoinput");
      const status = await fetchConfidenceStatus().catch(() => null);
      setCameraDiag(
        `检测到 ${videos.length} 个摄像头设备；训练状态：${status?.running ? "运行中" : "未运行"}；` +
          `可信度：${status?.confidence_reliability || "unknown"}`,
      );
    } catch (error) {
      setCameraDiag(`诊断失败：${error.message || "请检查浏览器权限"}`);
    }
  }

  async function onHistoryFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setImportHint(`正在导入 ${file.name}…`);
    try {
      const content = await file.text();
      const response = await fetch(`${API_BASE}/api/debates/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: file.name, content }),
      });
      if (!response.ok) throw new Error(await response.text());
      const debate = await response.json();
      navigate(`/replay/${debate.id}`, {
        state: { debate, mode: debate.mode, topic: debate.topic },
      });
    } catch (error) {
      setImportHint(`导入失败：${error.message || "请确认是本项目导出的 Markdown 历史记录"}`);
    } finally {
      setImporting(false);
      event.target.value = "";
    }
  }

  async function onGenerateConfidenceReport() {
    setReportLoading(true);
    try {
      const data = await fetchConfidenceReport();
      setConfidenceReport(data);
    } catch (error) {
      setConfidenceReport({
        llm_report: `生成失败：${error.message || "请确认后端与模型配置正常"}`,
        metrics: null,
      });
    } finally {
      setReportLoading(false);
    }
  }

  return (
    <div className="home-page">
      <header className="home-nav">
        <div className="home-logo">
          <Sparkles size={20} />
          <span>AI Debate Arena</span>
        </div>
        <Link to="/welcome" className="home-admin-link">
          返回模式选择
        </Link>
      </header>

      <SystemConfigBanner health={health} healthError={healthError} apiBase={apiBase} />

      <section className="home-hero">
        <h1>设置辩题与参赛方式</h1>
      </section>

      <nav className="setup-steps" aria-label="进入房间设置步骤">
        {WIZARD_STEPS.map((label, index) => (
          <button
            key={label}
            type="button"
            className={`setup-step ${index === setupStep ? "active" : ""} ${index < setupStep ? "done" : ""}`}
            onClick={() => setSetupStep(index)}
          >
            <span>{index + 1}</span>
            <strong>{label}</strong>
          </button>
        ))}
      </nav>

      {setupStep === 0 && (
        <div className="setup-panel setup-panel--active">
      <section className="home-topic">
        <label htmlFor="topic">辩题</label>
        <textarea
          id="topic"
          rows={3}
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="输入本场辩论辩题…"
        />
      </section>

      <section className="home-materials">
        <div className="home-materials__head">
          <label htmlFor="materials">辩题参考资料（可选）</label>
          <label className="home-file-btn">
            <FileUp size={16} /> 上传 .txt / .md
            <input type="file" accept=".txt,.md,text/plain,text/markdown" onChange={onMaterialFile} hidden />
          </label>
        </div>
        <input
          className="home-materials__title"
          value={materialTitle}
          onChange={(e) => setMaterialTitle(e.target.value)}
          placeholder="资料标题"
        />
        <textarea
          id="materials"
          rows={5}
          value={materialText}
          onChange={(e) => setMaterialText(e.target.value)}
          placeholder="粘贴论文摘要、新闻、数据说明等… 将自动分块写入轻量向量库（无需 Ollama）。"
        />
        {uploadHint && <p className="home-hint">{uploadHint}</p>}
      </section>

      <section className="home-import">
        <div>
          <h2 className="home-section-title">导入历史记录</h2>
          <p className="home-hint">支持导入之前导出的 Markdown 历史记录，导入后直接进入回放页。</p>
        </div>
        <label className={`home-file-btn ${importing ? "disabled" : ""}`}>
          <FileUp size={16} /> {importing ? "导入中…" : "导入 .md 历史"}
          <input type="file" accept=".md,text/markdown,text/plain" onChange={onHistoryFile} disabled={importing} hidden />
        </label>
        {importHint && <p className="home-hint home-import__hint">{importHint}</p>}
      </section>

        </div>
      )}

      {setupStep === 3 && (
        <section className="home-confidence setup-panel setup-panel--active">
        <div>
          <h2 className="home-section-title">自信度摄像头训练（可选）</h2>
          <p className="home-hint">
            摄像头画面会直接显示在网页内，用于训练眼神、手势和姿态表达；不会再要求你切换到额外弹窗。
          </p>
        </div>
        <label className="home-confidence__toggle">
          <input
            type="checkbox"
            checked={confidenceEnabled}
            disabled={mode === "ai_autonomous"}
            onChange={(e) => setConfidenceEnabled(e.target.checked)}
          />
          <span>
            <Camera size={15} /> 进入辩论室时启用自信度训练
          </span>
        </label>
        <label className="home-confidence__toggle">
          <input
            type="checkbox"
            checked={lowPerformance}
            onChange={(e) => setLowPerformance(e.target.checked)}
            disabled={!confidenceEnabled || mode === "ai_autonomous"}
          />
          <span>低性能模式（低分辨率/低帧率，适合机房设备）</span>
        </label>
        <label className="home-confidence__toggle">
          <input
            type="checkbox"
            checked={showLandmarks}
            onChange={(e) => setShowLandmarks(e.target.checked)}
            disabled={!confidenceEnabled || mode === "ai_autonomous"}
          />
          <span>默认显示关键点（鼻子/肩膀/手腕）</span>
        </label>
        {mode === "ai_autonomous" && (
          <p className="home-hint home-confidence__hint">AI 自主辩论没有人类发言，摄像头训练不可启用，也不会影响计分。</p>
        )}
        {confidenceEnabled && mode !== "ai_autonomous" && (
          <ConfidenceCameraPreview />
        )}
        <p className="home-hint">进入房间后，右侧栏会继续显示网页内摄像头预览和训练参数。</p>
        {confidenceStatus?.fixed_realtime_hint && (
          <p className="home-hint home-confidence__hint">实时提示：{confidenceStatus.fixed_realtime_hint}</p>
        )}
        {confidenceStatus?.confidence_reliability_hint && (
          <p className="home-hint home-confidence__hint">评分可信度：{confidenceStatus.confidence_reliability_hint}</p>
        )}
        {confidenceStatus?.last_error && (
          <p className="home-hint system-banner--error" style={{ padding: '8px 12px', borderRadius: '8px', marginTop: '8px' }}>
            系统异常：{confidenceStatus.last_error}
          </p>
        )}
        {confidenceStatus?.latest_sample && (
          <p className="home-hint">
            实时参数：眼神 {Math.round((confidenceStatus.latest_sample.eye || 0) * 100)}% / 手势{" "}
            {Math.round((confidenceStatus.latest_sample.gesture || 0) * 100)}% / 姿态{" "}
            {Math.round((confidenceStatus.latest_sample.posture || 0) * 100)}%
          </p>
        )}
        <div className="home-confidence__actions">
          <button type="button" className="home-file-btn" onClick={onGenerateConfidenceReport} disabled={reportLoading}>
            {reportLoading ? "生成中…" : "生成训练总结"}
          </button>
          <button type="button" className="home-file-btn" onClick={runCameraDiagnostics}>
            摄像头一键诊断
          </button>
        </div>
        {cameraDiag && <p className="home-hint">{cameraDiag}</p>}
        {confidenceReport?.metrics?.fixed_feedback && (
          <p className="home-hint">{confidenceReport.metrics.fixed_feedback}</p>
        )}
        {confidenceReport?.compare?.available && (
          <p className="home-hint">
            与上次对比：自信度 {Math.round((confidenceReport.compare.delta.confidence || 0) * 100)}%，眼神{" "}
            {Math.round((confidenceReport.compare.delta.eye || 0) * 100)}%，手势{" "}
            {Math.round((confidenceReport.compare.delta.gesture || 0) * 100)}%，姿态{" "}
            {Math.round((confidenceReport.compare.delta.posture || 0) * 100)}%。
          </p>
        )}
        {confidenceReport?.llm_report && (
          <pre className="home-confidence__report">{confidenceReport.llm_report}</pre>
        )}
        {confidenceHint && <p className="home-hint home-confidence__hint">{confidenceHint}</p>}
      </section>
      )}

      {setupStep === 2 && (
        <section className="home-schedules setup-panel setup-panel--active">
        <h2 className="home-section-title">赛程模板</h2>
        <div className="schedule-template-grid">
          {schedules.map((item) => {
            const active = scheduleTemplate === item.id;
            return (
              <button
                key={item.id}
                type="button"
                data-testid={`schedule-${item.id}`}
                className={`schedule-template-card ${active ? "active" : ""}`}
                onClick={() => setScheduleTemplate(item.id)}
              >
                <strong>{item.title || item.id}</strong>
                <p>{item.description || "自定义 YAML 赛程"}</p>
                <span>{item.segments_count ?? "?"} 个环节</span>
                {active && <em>已选择</em>}
              </button>
            );
          })}
        </div>
        <section className="seat-config-card">
          <div>
            <h2 className="home-section-title">赛前规则</h2>
            <p className="home-hint">人类训练规则会在进入房间后锁定，赛中不能再改。</p>
          </div>
          {mode !== "ai_autonomous" && (
            <div className="segmented">
              <button
                type="button"
                className={visibilityMode === "all_visible" ? "active" : ""}
                onClick={() => setVisibilityMode("all_visible")}
              >
                全部可见
              </button>
              <button
                type="button"
                className={visibilityMode === "own_side_only" ? "active" : ""}
                onClick={() => setVisibilityMode("own_side_only")}
              >
                仅己方内容可见
              </button>
            </div>
          )}
          {mode === "ai_autonomous" && <p className="home-hint">AI 自主辩论自动使用“全部可见”。</p>}
          <div className={`segmented ${mode === "ai_autonomous" ? "is-disabled" : ""}`}>
            <button
              type="button"
              className={timingMode === "limited" ? "active" : ""}
              disabled={mode === "ai_autonomous"}
              onClick={() => setTimingMode("limited")}
            >
              加入计时
            </button>
            <button
              type="button"
              className={timingMode === "unlimited" ? "active" : ""}
              disabled={mode === "ai_autonomous"}
              onClick={() => setTimingMode("unlimited")}
            >
              不计时
            </button>
          </div>
          {mode === "ai_autonomous" && <p className="home-hint">AI 自主辩论按 TTS 朗读预计时长推进，不启用人类计时扣分。</p>}
          <label className="home-confidence__toggle">
            <input type="checkbox" checked={ttsEnabled} onChange={(event) => setTtsEnabled(event.target.checked)} />
            <span>开赛后启用 TTS 语音朗读</span>
          </label>
        </section>
      </section>
      )}

      {setupStep === 1 && (
        <div className="setup-panel setup-panel--active">
      <section className="mode-grid">
        {MODES.map((item) => {
          const Icon = item.icon;
          const active = mode === item.id;
          return (
            <button
              key={item.id}
              type="button"
              className={`mode-card ${item.accent} ${active ? "active" : ""}`}
              onClick={() => {
                setMode(item.id);
                if (item.id === "user_affirmative") setUserSide("affirmative");
                if (item.id === "user_negative") setUserSide("negative");
              }}
            >
              <div className="mode-icon">
                <Icon size={22} />
              </div>
              <h3>{item.title}</h3>
              <p>{item.desc}</p>
              {active && <span className="mode-check">已选择</span>}
            </button>
          );
        })}
      </section>
          {(mode === "user_affirmative" || mode === "user_negative") && (
            <section className="seat-config-card">
              <div>
                <h2 className="home-section-title">选择你的辩手席位</h2>
              </div>
              <div className="seat-config-grid">
                <label>
                  阵营
                  <select
                    value={userSide}
                    onChange={(event) => {
                      const side = event.target.value;
                      setUserSide(side);
                      setMode(side === "negative" ? "user_negative" : "user_affirmative");
                    }}
                  >
                    <option value="affirmative">正方</option>
                    <option value="negative">反方</option>
                  </select>
                </label>
                <label>
                  席位
                  <select value={userPosition} onChange={(event) => setUserPosition(Number(event.target.value))}>
                    {DEBATER_POSITIONS.map((position) => (
                      <option key={position} value={position}>
                        {position} 辩
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  显示名称
                  <input value={userName} onChange={(event) => setUserName(event.target.value)} maxLength={24} />
                </label>
              </div>
            </section>
          )}
        </div>
      )}

      <footer className="home-footer">
        <div className="setup-footer-actions">
          <button
            type="button"
            className="home-file-btn"
            disabled={setupStep === 0}
            onClick={() => setSetupStep((step) => Math.max(0, step - 1))}
          >
            上一步
          </button>
          {setupStep < WIZARD_STEPS.length - 1 && (
            <button
              type="button"
              className="home-file-btn setup-next-btn"
              disabled={setupStep === 0 && !topic.trim()}
              onClick={() => setSetupStep((step) => Math.min(WIZARD_STEPS.length - 1, step + 1))}
            >
              下一步：{WIZARD_STEPS[setupStep + 1]}
            </button>
          )}
        </div>
        <button
          type="button"
          className="home-cta"
          data-testid="home-enter-room"
          disabled={loading || !topic.trim() || setupStep !== WIZARD_STEPS.length - 1}
          onClick={enterRoom}
        >
          {loading ? "正在创建房间…" : "进入辩论室"}
          <MessageCircle size={18} />
        </button>
        <p className="home-hint">规则会在进入房间时锁定；如创建失败，请检查后端与系统管理中的 API Key 配置。</p>
      </footer>
    </div>
  );
}
