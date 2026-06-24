import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, FileCheck2, Loader2, Sparkles } from "lucide-react";
import { useErrorDialog } from "../components/ErrorDialogProvider.jsx";
import MarkdownBody from "../components/MarkdownBody.jsx";
import { API_BASE } from "../utils/apiBase.js";
import { errorDialogPayload, parseHttpErrorBody } from "../utils/httpError.js";
import blueAvatar from "../assets/agents/agent-blue.png";
import orangeAvatar from "../assets/agents/agent-orange.png";
import purpleAvatar from "../assets/agents/agent-purple.png";
import silverAvatar from "../assets/agents/agent-silver.png";
import "../styles/home.css";

async function analyzeOpening({ topic, side, draft }) {
  const response = await fetch(`${API_BASE}/api/debates/opening-training/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, side, draft }),
  });
  if (!response.ok) throw parseHttpErrorBody(await response.text(), response);
  return response.json();
}

async function polishOpening({ topic, side, draft, advice }) {
  const response = await fetch(`${API_BASE}/api/debates/opening-training/polish`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, side, draft, advice }),
  });
  if (!response.ok) throw parseHttpErrorBody(await response.text(), response);
  return response.json();
}

async function streamAutoImproveOpening({ topic, side, maxRounds }, onEvent) {
  const response = await fetch(`${API_BASE}/api/debates/opening-training/auto-improve/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, side, max_rounds: maxRounds }),
  });
  if (!response.ok) throw parseHttpErrorBody(await response.text(), response);
  const reader = response.body?.getReader();
  if (!reader) throw new Error("stream unavailable");
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  const dispatchFrame = async (frame) => {
    const line = frame.split(/\r?\n/).find((entry) => entry.startsWith("data: "));
    if (!line) return;
    onEvent(JSON.parse(line.slice(6)));
    await new Promise((resolve) => window.setTimeout(resolve, 0));
  };
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() || "";
    for (const frame of frames) {
      await dispatchFrame(frame);
    }
  }
  buffer += decoder.decode();
  if (buffer.trim()) {
    await dispatchFrame(buffer);
  }
}

function resolveTrainingAvatar(path, role, side) {
  if (path?.includes("agent-purple")) return purpleAvatar;
  if (path?.includes("agent-orange")) return orangeAvatar;
  if (path?.includes("agent-silver")) return silverAvatar;
  if (role === "user") return blueAvatar;
  return side === "negative" ? orangeAvatar : silverAvatar;
}

function conversationFromAnalyze(draft, data) {
  const summary = data.score_summary || {};
  return [
    {
      id: "user-draft",
      speaker_name: "我的立论稿",
      avatar: blueAvatar,
      role: "user",
      kind: "draft",
      content: draft,
    },
    {
      id: "ai-review",
      speaker_name: "AI教练",
      avatar: purpleAvatar,
      role: "reviewer",
      kind: "analysis",
      content: `本稿综合评分 ${summary.overall ?? data.score} 分。${summary.evaluation || ""} 定义和标准${
        data.structure.has_definition ? "已经出现" : "需要补充"
      }，三个分论点${data.structure.has_three_arguments ? "基本完整" : "还不够清楚"}，事实风险为 ${
        data.rag_checks?.hallucination_risk || "unknown"
      }。${(summary.improvement_suggestions || data.revision_advice || []).join(" ")}`,
    },
    {
      id: "ai-strategy",
      speaker_name: "AI裁判",
      avatar: purpleAvatar,
      role: "reviewer",
      kind: "strategy",
      content: data.suggested_revision_strategy,
    },
  ];
}

function scoreValue(result) {
  return result?.score_summary?.overall ?? result?.final_score ?? result?.score ?? "-";
}

function scoreDimensions(result) {
  const finalRound = result?.rounds?.[result.rounds.length - 1];
  return result?.dimensions || finalRound?.analysis?.dimensions || [];
}

function scoreSummary(result) {
  const finalRound = result?.rounds?.[result.rounds.length - 1];
  return result?.score_summary || finalRound?.analysis?.score_summary || {};
}

function OpeningScorePanel({ result, loading }) {
  const summary = scoreSummary(result);
  const dimensions = scoreDimensions(result);
  const suggestions = summary.improvement_suggestions || result?.revision_advice || [];
  return (
    <div className="opening-score-panel">
      <div className="opening-score-panel__main">
        <div>
          <span>{loading ? "正在评分" : result?.passed === false ? "最后评分" : "评分"}</span>
          <strong>{scoreValue(result)}</strong>
        </div>
        <small>综合分</small>
      </div>
      {dimensions.length > 0 && (
        <div className="opening-score-panel__dimensions">
          {dimensions.map((item) => {
            const percent = Math.max(0, Math.min(100, Math.round((Number(item.score || 0) / Number(item.max_score || 1)) * 100)));
            return (
              <article key={item.key || item.label}>
                <div>
                  <span>{item.label}</span>
                  <strong>
                    {item.score}/{item.max_score}
                  </strong>
                </div>
                <i style={{ "--score-width": `${percent}%` }} />
              </article>
            );
          })}
        </div>
      )}
      {(summary.evaluation || suggestions.length > 0) && (
        <div className="opening-score-panel__notes">
          {summary.evaluation && <p>{summary.evaluation}</p>}
          {suggestions.length > 0 && (
            <ul>
              {suggestions.slice(0, 3).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export default function OpeningTraining() {
  const { reportError } = useErrorDialog();
  const [topic, setTopic] = useState("人工智能是否会提升青少年的综合学习能力");
  const [side, setSide] = useState("affirmative");
  const [trainingMode, setTrainingMode] = useState("human_draft");
  const [draft, setDraft] = useState("");
  const [maxRounds, setMaxRounds] = useState(6);
  const [result, setResult] = useState(null);
  const [conversation, setConversation] = useState([]);
  const [loading, setLoading] = useState(false);
  const [hint, setHint] = useState("");
  const visibleContentRef = useRef({});
  const targetContentRef = useRef({});
  const revealTimersRef = useRef({});

  function upsertConversationMessage(message) {
    setConversation((current) => {
      const index = current.findIndex((item) => item.id === message.id);
      if (index >= 0) {
        const next = [...current];
        next[index] = { ...next[index], ...message };
        return next;
      }
      return [...current, message];
    });
  }

  function revealMessage(message) {
    const id = message.id;
    const target = message.content || "";
    targetContentRef.current[id] = target;
    if (visibleContentRef.current[id] == null) {
      visibleContentRef.current[id] = "";
      upsertConversationMessage({ ...message, content: "" });
    }
    if (revealTimersRef.current[id]) return;
    const tick = () => {
      const visible = visibleContentRef.current[id] || "";
      const nextTarget = targetContentRef.current[id] || "";
      if (visible.length >= nextTarget.length) {
        revealTimersRef.current[id] = null;
        upsertConversationMessage({ ...message, content: nextTarget });
        return;
      }
      const nextVisible = nextTarget.slice(0, Math.min(nextTarget.length, visible.length + 28));
      visibleContentRef.current[id] = nextVisible;
      upsertConversationMessage({ ...message, content: nextVisible });
      revealTimersRef.current[id] = window.setTimeout(tick, 16);
    };
    revealTimersRef.current[id] = window.setTimeout(tick, 0);
  }

  async function onAnalyze() {
    if (!topic.trim() || !draft.trim()) return;
    setLoading(true);
    setHint("正在分析立论结构、论据风险和修改方向…");
    try {
      const data = await analyzeOpening({ topic, side, draft });
      setResult(data);
      setConversation(conversationFromAnalyze(draft, data));
      setHint("分析完成。");
    } catch (error) {
      setHint(`分析失败：${error.message || "请确认后端已启动"}`);
      reportError(errorDialogPayload(error, "立论分析失败", "OpeningTraining.analyze", "请确认后端已启动"));
    } finally {
      setLoading(false);
    }
  }

  async function onPolish() {
    if (!topic.trim() || !draft.trim() || !result?.revision_advice) return;
    setLoading(true);
    setHint("AI 正在依据评审意见润色立论稿…");
    try {
      const data = await polishOpening({ topic, side, draft, advice: result.revision_advice || [] });
      const polished = data.polished_draft || "";
      setDraft(polished);
      setResult(data.analysis || result);
      setConversation((current) => [
        ...current,
        {
          id: `polish-${Date.now()}`,
          speaker_name: "AI一辩润色稿",
          avatar: resolveTrainingAvatar("", "writer", side),
          role: "writer",
          kind: "polish",
          content: polished,
        },
      ]);
      setHint("润色完成，已回填到左侧立论稿。");
    } catch (error) {
      setHint(`润色失败：${error.message || "请确认后端已启动"}`);
      reportError(errorDialogPayload(error, "立论润色失败", "OpeningTraining.polish", "请确认后端已启动"));
    } finally {
      setLoading(false);
    }
  }

  async function onAutoImprove() {
    if (!topic.trim()) return;
    setLoading(true);
    setConversation([]);
    visibleContentRef.current = {};
    targetContentRef.current = {};
    revealTimersRef.current = {};
    setResult(null);
    setHint("AI 一辩正在输出初稿…");
    try {
      await streamAutoImproveOpening({ topic, side, maxRounds }, (event) => {
        if (event.type === "draft_start" || event.type === "review_start") {
          const message = event.message;
          const normalized = {
            ...message,
            avatar: resolveTrainingAvatar(message.avatar, message.role, side),
          };
          visibleContentRef.current[message.id] = "";
          targetContentRef.current[message.id] = "";
          upsertConversationMessage(normalized);
          if (event.analysis) {
            setResult({ ...event.analysis, passed: event.passed });
          }
          setHint(event.type === "draft_start" ? "AI 一辩正在流式输出立论稿…" : "AI 裁判正在逐段审核这一版立论…");
        }
        if (event.type === "draft_delta" || event.type === "review_delta") {
          const message = event.message;
          revealMessage({
            ...message,
            avatar: resolveTrainingAvatar(message.avatar, message.role, side),
          });
        }
        if (event.type === "draft" || event.type === "review") {
          const message = event.message;
          revealMessage({
            ...message,
            avatar: resolveTrainingAvatar(message.avatar, message.role, side),
          });
          if (event.analysis) {
            setResult({ ...event.analysis, passed: event.passed });
          }
          setHint(event.type === "draft" ? "AI 裁判正在审阅这一版立论…" : "AI 一辩正在参考裁判意见继续修改…");
        }
        if (event.type === "done") {
          setResult(event.data);
          setDraft(event.data?.final_draft || "");
          setHint(event.data?.passed ? "已达到一辩立论标准。" : `已完成 ${event.data?.rounds?.length || 0} 轮，保留最后一版。`);
        }
        if (event.type === "error") {
          setHint(`训练失败：${event.message}`);
          reportError({
            title: "自动训练失败",
            message: event.message || "请检查后端和模型配置",
            source: "OpeningTraining.autoImprove.stream",
          });
        }
      });
    } catch (error) {
      setHint(`训练失败：${error.message || "请确认后端已启动"}`);
      reportError(errorDialogPayload(error, "自动训练失败", "OpeningTraining.autoImprove", "请确认后端已启动"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="home-page opening-training-page">
      <header className="home-nav">
        <div className="home-logo">
          <FileCheck2 size={20} />
          <span>一辩立论训练</span>
        </div>
        <Link to="/welcome" className="home-admin-link">
          <ArrowLeft size={16} /> 返回模式选择
        </Link>
      </header>

      <section className="home-hero opening-training-hero">
        <h1>一辩立论训练</h1>
      </section>

      <main className="opening-training-grid">
        <section className="setup-panel setup-panel--active opening-training-form">
          <label htmlFor="opening-topic">辩题</label>
          <textarea id="opening-topic" rows={3} value={topic} onChange={(event) => setTopic(event.target.value)} />

          <div className="opening-mode-windows">
            <button type="button" className={trainingMode === "human_draft" ? "active" : ""} onClick={() => setTrainingMode("human_draft")}>
              <strong>人工立论智能评审</strong>
              <span>提交自己的立论稿，由 AI 裁判评分并给出修改意见。</span>
            </button>
            <button type="button" className={trainingMode === "ai_loop" ? "active" : ""} onClick={() => setTrainingMode("ai_loop")}>
              <strong>AI 立论迭代训练</strong>
              <span>AI 一辩先写稿，AI 裁判逐轮审稿，直到达标或达到轮数上限。</span>
            </button>
          </div>

          <div className="segmented opening-side-tabs">
            <button type="button" className={side === "affirmative" ? "active" : ""} onClick={() => setSide("affirmative")}>
              正方一辩
            </button>
            <button type="button" className={side === "negative" ? "active" : ""} onClick={() => setSide("negative")}>
              反方一辩
            </button>
          </div>

          {trainingMode === "human_draft" ? (
            <>
              <label htmlFor="opening-draft">人工立论稿</label>
              <textarea
                id="opening-draft"
                rows={14}
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="粘贴或撰写你的开篇立论。建议包含定义、判断标准、三个分论点和结尾收束。"
              />
              <button type="button" className="home-cta opening-analyze-btn" disabled={loading || !topic.trim() || !draft.trim()} onClick={onAnalyze}>
                {loading ? (
                  <>
                    正在分析 <Loader2 size={18} className="spin" />
                  </>
                ) : (
                  <>
                    开始智能评审 <Sparkles size={18} />
                  </>
                )}
              </button>
              <button
                type="button"
                className="home-cta opening-polish-btn"
                disabled={loading || !topic.trim() || !draft.trim() || !result?.revision_advice}
                onClick={onPolish}
              >
                AI 一键润色 <Sparkles size={18} />
              </button>
            </>
          ) : (
            <>
              <label htmlFor="opening-rounds">最多迭代轮数</label>
              <input
                id="opening-rounds"
                className="opening-rounds-input"
                type="number"
                min={1}
                max={12}
                value={maxRounds}
                onChange={(event) => setMaxRounds(Math.max(1, Math.min(12, Number(event.target.value) || 1)))}
              />
              <button type="button" className="home-cta opening-analyze-btn" disabled={loading || !topic.trim()} onClick={onAutoImprove}>
                {loading ? (
                  <>
                    循环改稿中 <Loader2 size={18} className="spin" />
                  </>
                ) : (
                  <>
                    开始迭代训练 <Sparkles size={18} />
                  </>
                )}
              </button>
            </>
          )}
          {hint && <p className="home-hint">{hint}</p>}
        </section>

        <section className="setup-panel setup-panel--active opening-training-result opening-training-chat-panel">
          <div className="opening-chat-panel-head">
            <div>
              <strong>训练对话</strong>
              <span>{trainingMode === "ai_loop" ? "AI 一辩输出后，AI 裁判单独审核" : "人工稿件提交后，AI 裁判给出评审"}</span>
            </div>
          </div>
          <OpeningScorePanel result={result} loading={loading && trainingMode === "ai_loop"} />
          <div className={`opening-chat ${conversation.length ? "" : "opening-chat--empty"}`}>
            {!conversation.length && <p className="home-hint">开始训练后，对话会按生成顺序逐条显示。</p>}
            {conversation.map((message) => (
              <article key={message.id} className={`opening-chat-message opening-chat-message--${message.role || "ai"}`}>
                <img src={message.avatar} alt="" />
                <div>
                  <strong>{message.speaker_name}</strong>
                  {message.round && <span>第 {message.round} 轮</span>}
                  <MarkdownBody content={message.content} />
                </div>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
