import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, FileCheck2, Loader2, Sparkles } from "lucide-react";
import MarkdownBody from "../components/MarkdownBody.jsx";
import { API_BASE } from "../utils/apiBase.js";
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
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function autoImproveOpening({ topic, side, maxRounds }) {
  const response = await fetch(`${API_BASE}/api/debates/opening-training/auto-improve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, side, max_rounds: maxRounds }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function streamAutoImproveOpening({ topic, side, maxRounds }, onEvent) {
  const response = await fetch(`${API_BASE}/api/debates/opening-training/auto-improve/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, side, max_rounds: maxRounds }),
  });
  if (!response.ok) throw new Error(await response.text());
  const reader = response.body?.getReader();
  if (!reader) throw new Error("stream unavailable");
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const line = frame.split("\n").find((entry) => entry.startsWith("data: "));
      if (!line) continue;
      onEvent(JSON.parse(line.slice(6)));
    }
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
      content: `本稿综合评分 ${data.score} 分。定义和标准${data.structure.has_definition ? "已经出现" : "需要补充"}，三个分论点${data.structure.has_three_arguments ? "基本完整" : "还不够清楚"}，事实风险为 ${data.rag_checks?.hallucination_risk || "unknown"}。${data.revision_advice.join(" ")}`,
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

export default function OpeningTraining() {
  const [topic, setTopic] = useState("人工智能是否会提升青少年的综合学习能力");
  const [side, setSide] = useState("affirmative");
  const [trainingMode, setTrainingMode] = useState("human_draft");
  const [draft, setDraft] = useState("");
  const [maxRounds, setMaxRounds] = useState(6);
  const [result, setResult] = useState(null);
  const [conversation, setConversation] = useState([]);
  const [loading, setLoading] = useState(false);
  const [hint, setHint] = useState("");

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
    } finally {
      setLoading(false);
    }
  }

  async function onAutoImprove() {
    if (!topic.trim()) return;
    setLoading(true);
    setConversation([]);
    setResult(null);
    setHint("AI 一辩正在输出初稿…");
    try {
      await streamAutoImproveOpening({ topic, side, maxRounds }, (event) => {
        if (event.type === "draft_start") {
          const message = event.message;
          setConversation((current) => [
            ...current,
            {
              ...message,
              avatar: resolveTrainingAvatar(message.avatar, message.role, side),
            },
          ]);
          setHint("AI 一辩正在流式输出立论稿…");
        }
        if (event.type === "draft_delta") {
          const message = event.message;
          setConversation((current) => {
            const next = [...current];
            const index = next.findIndex((item) => item.id === message.id);
            const normalized = {
              ...message,
              avatar: resolveTrainingAvatar(message.avatar, message.role, side),
            };
            if (index >= 0) next[index] = normalized;
            else next.push(normalized);
            return next;
          });
        }
        if (event.type === "draft" || event.type === "review") {
          const message = event.message;
          setConversation((current) => {
            const normalized = {
              ...message,
              avatar: resolveTrainingAvatar(message.avatar, message.role, side),
            };
            const index = current.findIndex((item) => item.id === message.id);
            if (index >= 0) {
              const next = [...current];
              next[index] = normalized;
              return next;
            }
            return [...current, normalized];
          });
          setHint(event.type === "draft" ? "AI 裁判正在审阅这一版立论…" : "AI 一辩正在参考裁判意见继续修改…");
        }
        if (event.type === "done") {
          setResult(event.data);
          setDraft(event.data?.final_draft || "");
          setHint(event.data?.passed ? "已达到一辩立论标准。" : `已完成 ${event.data?.rounds?.length || 0} 轮，保留最后一版。`);
        }
        if (event.type === "error") {
          setHint(`训练失败：${event.message}`);
        }
      });
    } catch (error) {
      setHint(`训练失败：${error.message || "请确认后端已启动"}`);
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
            <div className="opening-score opening-score--compact">
              <span>{result?.passed === false ? "最后评分" : "评分"}</span>
              <strong>{result?.final_score ?? result?.score ?? "-"}</strong>
            </div>
          </div>
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
