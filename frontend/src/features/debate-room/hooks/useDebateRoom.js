import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import {
  debaterPositionLabel,
  buildClientHistoryMarkdown,
  downloadTextFile,
  isPublicStageMessage,
  isTeamDiscussion,
  teamDiscussionSide,
} from "../../../utils/debateDisplay.js";
import { useAudioQueue } from "../../../hooks/useAudioQueue.js";
import { useDebateHealth } from "../../../hooks/useDebateHealth.js";
import { useTurnTimer } from "../../../hooks/useTurnTimer.js";
import { useErrorDialog } from "../../../components/ErrorDialogProvider.jsx";
import { errorDialogPayload, parseHttpErrorBody } from "../../../utils/httpError.js";
import { API_BASE, SPEECH_FONT_SIZES, SPEECH_FONT_STORAGE_KEY } from "../constants.js";
import { debateRequest } from "../api.js";
import { createLocalDebate } from "../localDebate.js";
import { encodeChunksAsWav } from "../speechRecorder.js";
import {
  getSpeechInputState,
  formatPipelineHint,
  localDemoMarkdown,
  needsUserTurn,
  participantSpeakerId,
  phaseName,
  userSideForMode,
  userSpeakerId,
} from "../utils.js";
import { useDebateRoomSocket } from "./useDebateRoomSocket.js";
import { buildViewerQuery } from "../visibilityModes.js";
import { loadStoredParticipant } from "../../../utils/participantStorage.js";

function isDebateSnapshotStale(prev, next) {
  if (!prev || !next) return false;
  const prevIdx = prev.schedule_index ?? 0;
  const nextIdx = next.schedule_index ?? 0;
  const prevTurn = prev.turn_index ?? 0;
  const nextTurn = next.turn_index ?? 0;
  if (nextIdx > prevIdx || nextTurn > prevTurn) return false;
  const prevTs = Date.parse(prev.updated_at || 0);
  const nextTs = Date.parse(next.updated_at || 0);
  if (prevTs && nextTs && nextTs < prevTs) return true;
  if (nextIdx < prevIdx) return true;
  if (nextTurn < prevTurn) return true;
  return false;
}

function mergeArgumentItems(currentItems = [], incomingItems = []) {
  const byId = new Map();
  for (const item of currentItems || []) {
    if (item?.id) byId.set(item.id, item);
  }
  for (const item of incomingItems || []) {
    if (item?.id) byId.set(item.id, { ...(byId.get(item.id) || {}), ...item });
  }
  return Array.from(byId.values());
}

function mergeArgumentBank(current = {}, incoming = {}) {
  return {
    affirmative: mergeArgumentItems(current?.affirmative, incoming?.affirmative),
    negative: mergeArgumentItems(current?.negative, incoming?.negative),
  };
}

async function streamSseJson(path, body, onEvent) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw parseHttpErrorBody(await response.text(), response);
  if (!response.body) throw new Error("stream unavailable");

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const line = frame
        .split("\n")
        .find((entry) => entry.startsWith("data: "));
      if (!line) continue;
      const payload = line.slice(6).trim();
      if (!payload) continue;
      try {
        onEvent?.(JSON.parse(payload));
      } catch {
        // ignore malformed stream frame
      }
    }
  }
}

export function useDebateRoom() {
  const { id: routeId } = useParams();
  const location = useLocation();
  const init = location.state || {};
  const isLocal = init.local || routeId === "demo";
  const { reportError } = useErrorDialog();

  const [debate, setDebate] = useState(() => init.debate || createLocalDebate(init.topic, init.mode || "ai_autonomous"));
  const mode = debate.mode || init.mode || "ai_autonomous";
  const [participant, setParticipant] = useState(() => init.participant || loadStoredParticipant(routeId));
  const [streaming, setStreaming] = useState(null);
  const [pipelineHint, setPipelineHint] = useState("");
  const [draft, setDraft] = useState("");
  const [visibility, setVisibility] = useState(() => debate.visibility || "own_side_only");
  const [timing, setTiming] = useState(() => debate.timing || "limited");
  const { health, error: healthError } = useDebateHealth();
  const [assist, setAssist] = useState(null);
  const [assistLoading, setAssistLoading] = useState(false);
  const [showDraftPreview, setShowDraftPreview] = useState(true);
  const [draftLoading, setDraftLoading] = useState(false);
  const [messageSending, setMessageSending] = useState(false);
  const [status, setStatus] = useState("AI 回合自动进行中…");
  const [materialDraft, setMaterialDraft] = useState("");
  const [materialTitle, setMaterialTitle] = useState("补充资料");
  const [materialStatus, setMaterialStatus] = useState("");
  const [audioByMessage, setAudioByMessage] = useState({});
  const [ttsStatus, setTtsStatus] = useState("");
  const [speechStatus, setSpeechStatus] = useState("");
  const [speechRecording, setSpeechRecording] = useState(false);
  const [hydrating, setHydrating] = useState(
    () => !isLocal && Boolean(routeId) && routeId !== "demo" && !init.debate,
  );
  const [speechFontPx, setSpeechFontPx] = useState(() => {
    if (typeof window === "undefined") return 16;
    const stored = Number(window.localStorage.getItem(SPEECH_FONT_STORAGE_KEY));
    return SPEECH_FONT_SIZES.includes(stored) ? stored : 16;
  });
  const [autoScroll, setAutoScroll] = useState(true);

  const streamStaleRef = useRef(null);
  const ttsTimeoutRef = useRef(null);
  const ttsEnabledRef = useRef(debate.tts_enabled !== false);
  const speechRecorderRef = useRef(null);
  const localTimer = useRef(null);
  const localRunning = useRef(false);
  const messageBoardRef = useRef(null);
  const messageListScrollRef = useRef(null);
  const debateRef = useRef(debate);
  const streamingRef = useRef(null);

  useEffect(() => {
    debateRef.current = debate;
  }, [debate]);

  useEffect(() => {
    if (debate.visibility) setVisibility(debate.visibility);
    if (debate.timing) setTiming(debate.timing);
  }, [debate.visibility, debate.timing]);

  useEffect(() => {
    streamingRef.current = streaming;
  }, [streaming]);

  const onlineSpeakerId = participantSpeakerId(participant);
  const isOnlineDebater =
    participant && (participant.side === "affirmative" || participant.side === "negative") && participant.position;
  const userInputEnabled = mode === "online_match" ? Boolean(isOnlineDebater) : mode !== "ai_autonomous";
  const userSide = mode === "online_match" ? participant?.side || null : userSideForMode(mode);
  const userPosition = mode === "online_match" ? participant?.position || 1 : debate.user_position || participant?.position || 1;

  const clearTtsTimeout = useCallback(() => {
    if (ttsTimeoutRef.current) {
      clearTimeout(ttsTimeoutRef.current);
      ttsTimeoutRef.current = null;
    }
  }, []);

  const armTtsTimeout = useCallback(
    (speakerName) => {
      clearTtsTimeout();
      ttsTimeoutRef.current = setTimeout(() => {
        setTtsStatus(
          `${speakerName || "AI 辩手"} 语音仍在合成中：网络较慢时会稍久，辩论将继续进行。`,
        );
      }, health?.aliyun_tts_enabled === false ? 15000 : 38000);
    },
    [clearTtsTimeout, health?.aliyun_tts_enabled],
  );

  const {
    enqueue: enqueueAudio,
    playMessage: playMessageAudio,
    pause: pauseAudio,
    resume: resumeAudio,
    skipCurrent: skipCurrentAudio,
    clear: clearAudioQueue,
    setDisabled: setAudioDisabled,
    current: currentAudio,
    queueLength: audioQueueLength,
    isPaused: audioPaused,
    isDisabled: audioDisabled,
    subtitle: audioSubtitle,
  } = useAudioQueue();

  useEffect(() => {
    const enabled = debate.tts_enabled !== false;
    ttsEnabledRef.current = enabled;
    setAudioDisabled(!enabled);
    if (!enabled) {
      setTtsStatus("本场辩论已停止语音朗读与合成");
    }
  }, [debate.tts_enabled, setAudioDisabled]);

  useEffect(() => () => clearTtsTimeout(), [clearTtsTimeout]);

  const cleanupSpeechRecorder = useCallback(() => {
    const rec = speechRecorderRef.current;
    if (!rec) return null;
    speechRecorderRef.current = null;
    if (rec.timeout) clearTimeout(rec.timeout);
    rec.processor?.disconnect();
    rec.source?.disconnect();
    rec.gain?.disconnect();
    rec.stream?.getTracks().forEach((track) => track.stop());
    rec.audioContext?.close?.();
    setSpeechRecording(false);
    return rec;
  }, []);

  useEffect(() => () => cleanupSpeechRecorder(), [cleanupSpeechRecorder]);

  useEffect(() => {
    window.localStorage.setItem(SPEECH_FONT_STORAGE_KEY, String(speechFontPx));
  }, [speechFontPx]);

  const applyDebate = useCallback(
    (next, options = {}) => {
      const { clearStreaming = true } = options;
      const seen = new Set();
      let messages = (next.messages || []).filter((m) => {
        if (seen.has(m.id)) return false;
        seen.add(m.id);
        return true;
      });
      const streamSnap = clearStreaming ? streamingRef.current : null;
      if (streamSnap?.message_id && streamSnap.content) {
        messages = messages.map((m) => {
          if (m.id !== streamSnap.message_id) return m;
          const streamed = streamSnap.content || "";
          if (streamed.length > (m.content || "").length) {
            return { ...m, content: streamed };
          }
          return m;
        });
      }
      setDebate((prev) => {
        if (isDebateSnapshotStale(prev, next)) return prev;
        return {
          ...next,
          messages,
          argument_bank: mergeArgumentBank(prev?.argument_bank, next.argument_bank),
        };
      });
      if (clearStreaming) {
        setStreaming((prev) => {
          if (!prev) return null;
          const finalized = messages.some((m) => m.id === prev.message_id);
          return finalized ? null : prev;
        });
      }
      if (userInputEnabled && typeof next.user_draft === "string" && next.user_draft) {
        setDraft((current) => current || next.user_draft);
      }
      setAudioByMessage((current) => {
        const merged = { ...current };
        for (const message of next.messages || []) {
          if (message.audio_url) {
            merged[message.id] = {
              audio_url: message.audio_url,
              audio_urls: message.audio_urls || (message.audio_url ? [message.audio_url] : []),
              voice: message.tts_voice,
              instructions: message.tts_instructions,
            };
          }
        }
        return merged;
      });
    },
    [userInputEnabled],
  );

  const applyArgumentBankUpdate = useCallback((argumentBank) => {
    if (!argumentBank) return;
    setDebate((prev) => ({
      ...prev,
      argument_bank: mergeArgumentBank(prev.argument_bank, argumentBank),
      argument_bank_locked: true,
    }));
  }, []);

  const {
    connected: wsConnected,
    reconnecting: wsReconnecting,
    everConnected: wsEverConnected,
    connectionState: wsConnectionState,
    attempt: wsAttempt,
    lastError: wsLastError,
    sendWebRtcSignal,
    subscribeWebRtcSignal,
    sendViewerModeUpdate,
  } = useDebateRoomSocket({
    routeId,
    isLocal,
    debateRef,
    participant,
    visibility,
    applyDebate,
    applyArgumentBankUpdate,
    setStatus,
    setStreaming,
    setPipelineHint,
    setTtsStatus,
    setAudioByMessage,
    clearAudioQueue,
    clearTtsTimeout,
    armTtsTimeout,
    enqueueAudio,
    ttsEnabledRef,
    streamStaleRef,
    reportError,
  });

  const speechInputState = useMemo(
    () =>
      getSpeechInputState({
        debate,
        participant,
        mode,
        userInputEnabled,
        wsConnected: isLocal || wsConnected,
        wsReconnecting,
        wsEverConnected: isLocal || wsEverConnected,
        wsConnectionState: isLocal ? "open" : wsConnectionState,
        isLocal,
      }),
    [
      debate,
      participant,
      mode,
      userInputEnabled,
      wsConnected,
      wsReconnecting,
      wsEverConnected,
      wsConnectionState,
      isLocal,
    ],
  );
  const awaitingUser = speechInputState.isYourTurn;

  const turnSecondsLeft = useTurnTimer({
    enabled: timing === "limited",
    seconds: debate.segment_seconds || debate.turn_seconds || 90,
    running: debate.auto_running && !awaitingUser,
  });

  const activeAgent = useMemo(
    () => debate.agents?.find((a) => a.id === debate.active_speaker_id) || debate.agents?.[0] || null,
    [debate],
  );

  const visibleMessages = useMemo(
    () => debate.messages.filter((message) => isPublicStageMessage(message)),
    [debate.messages],
  );

  const teamDiscussions = useMemo(() => {
    const visibleInternal = debate.messages.filter((m) => isTeamDiscussion(m));
    return {
      affirmative: visibleInternal.filter((m) => teamDiscussionSide(m, debate.agents) === "affirmative"),
      negative: visibleInternal.filter((m) => teamDiscussionSide(m, debate.agents) === "negative"),
    };
  }, [debate.messages, debate.agents]);

  const aiStrategyNotes = useMemo(() => {
    if (visibility !== "context") return [];
    return debate.messages.filter((message) => message.private_thought || message.strategy);
  }, [debate.messages, visibility]);

  const processTimeline = useMemo(() => debate.messages, [debate.messages]);

  const speakingNow = useMemo(() => {
    if (streaming) {
      return {
        name: debaterPositionLabel(streaming.speaker_id, debate.agents) || (streaming.side === "judge" ? "裁判" : streaming.speaker_name),
        segment: streaming.segment_label || phaseName(streaming.phase),
        side: streaming.side,
      };
    }
    if (debate.auto_running && activeAgent) {
      return {
        name: debaterPositionLabel(activeAgent.id, debate.agents) || activeAgent.name,
        segment: debate.segment_label,
        side: activeAgent.side,
      };
    }
    return null;
  }, [streaming, debate.auto_running, debate.segment_label, activeAgent]);

  const showStreamingPublic =
    streaming &&
    isPublicStageMessage(streaming) &&
    !debate.messages.some((m) => m.id === streaming.message_id);

  useEffect(() => {
    if (!autoScroll) return;
    const el = messageListScrollRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }, [autoScroll, visibleMessages.length, streaming?.content, streaming?.message_id, showStreamingPublic]);

  const localStep = useCallback(async () => {
    if (localRunning.current) return;
    if (debate.phase === "finished") return;
    if (needsUserTurn(debate)) {
      setDebate((d) => ({ ...d, awaiting_user: true }));
      setStatus("轮到您发言（本地演示）。");
      return;
    }

    localRunning.current = true;
    const agent = debate.agents.find((a) => a.id === debate.active_speaker_id) || debate.agents[0];
    const messageId = crypto.randomUUID();
    const full = localDemoMarkdown(agent, debate);
    const chunks = full.match(/.{1,12}/g) || [full];

    setStreaming({
      message_id: messageId,
      speaker_id: agent.id,
      speaker_name: agent.name,
      side: agent.side,
      phase: debate.phase,
      segment_label: debate.segment_label,
      content: "",
    });

    let acc = "";
    for (const chunk of chunks) {
      acc += chunk;
      setStreaming((s) => (s ? { ...s, content: acc } : s));
      if (acc.length >= 40) {
        setPipelineHint({
          type: "pipeline_prep",
          speakerId: agent.id,
          speakerName: agent.name,
          side: agent.side,
          position: agent.position,
          nodeLabel: debate.segment_label,
          partialLength: acc.length,
          sourcesCount: 0,
          detail: `本地演示正在生成 ${debaterPositionLabel(agent.id, debate.agents) || agent.name} 的发言，已输出 ${acc.length} 字。`,
        });
      }
      await new Promise((r) => setTimeout(r, 80));
    }

    const next = structuredClone(debate);
    next.messages.push({
      id: messageId,
      speaker_id: agent.id,
      speaker_name: agent.name,
      side: agent.side,
      phase: next.phase,
      segment_label: next.segment_label,
      content: full,
      sources: [{ title: "本地演示", excerpt: "流式 Markdown 演示" }],
      score_delta: 1.5,
    });
    next.turn_index += 1;
    next.schedule_index = Math.min((next.schedule_index || 0) + 1, (next.schedule?.length || 1) - 1);
    if (next.schedule?.length) {
      next.schedule = next.schedule.map((item, index) => ({
        ...item,
        status: index < next.schedule_index ? "done" : index === next.schedule_index ? "current" : "pending",
      }));
      const segment = next.schedule[next.schedule_index];
      next.segment_label = segment?.label || next.segment_label;
      next.phase = segment?.phase || next.phase;
      next.segment_seconds = segment?.seconds || next.segment_seconds;
      next.active_speaker_id = segment?.speakerId || next.active_speaker_id;
    }
    if (agent.side === "affirmative" || agent.side === "negative") {
      next.score[agent.side] = (next.score[agent.side] || 0) + 1.5;
    }
    setStreaming(null);
    setDebate(next);
    localRunning.current = false;
    setStatus("本地演示：自动推进中…");
  }, [debate]);

  useEffect(() => {
    if (!isLocal) return undefined;
    if (awaitingUser || debate.phase === "finished") return undefined;
    localTimer.current = setInterval(localStep, 3500);
    return () => clearInterval(localTimer.current);
  }, [isLocal, awaitingUser, debate.phase, debate.turn_index, localStep]);

  useEffect(() => {
    if (!isLocal) return undefined;
    function injectDemoMessage(event) {
      const message = event.detail;
      if (!message?.id || !message.content) return;
      setDebate((current) => {
        if (current.messages?.some((item) => item.id === message.id)) return current;
        return {
          ...current,
          messages: [...(current.messages || []), message],
        };
      });
    }
    window.addEventListener("debate-demo-inject-message", injectDemoMessage);
    return () => window.removeEventListener("debate-demo-inject-message", injectDemoMessage);
  }, [isLocal]);

  useEffect(() => {
    if (!isLocal && routeId && routeId !== "demo") {
      sendViewerModeUpdate?.(visibility, userSide);
    }
  }, [isLocal, routeId, visibility, userSide, sendViewerModeUpdate]);

  useEffect(() => {
    if (isLocal || !routeId || routeId === "demo") return undefined;
    let cancelled = false;
    (async () => {
      try {
        const query = buildViewerQuery({
          viewerSide: userSide,
          participantId: participant?.id,
          viewerMode: visibility,
        });
        const remote = await debateRequest(`/api/debates/${routeId}${query}`);
        if (cancelled) return;
        applyDebate(remote);
        setHydrating(false);
        if (remote.phase === "finished") {
          setStatus("辩论已结束。");
          return;
        }
        if (remote.mode === "online_match") {
          if (needsUserTurn(remote, participant)) {
            setStatus("轮到您的联机席位发言，请在右侧输入后提交。");
          } else if (needsUserTurn(remote)) {
            setStatus("正在等待当前联机辩手发言。");
          } else if (!remote.auto_running) {
            setStatus("多人联机房间已就绪，等待辩手加入或手动继续。");
          } else {
            setStatus("AI/联机回合自动进行中…");
          }
          return;
        }
        if (remote.awaiting_user || needsUserTurn(remote)) {
          setStatus("轮到您发言，请在右侧输入后提交。");
          return;
        }
        if (!remote.auto_running) {
          await debateRequest(`/api/debates/${routeId}/resume`, { method: "POST" });
          if (!cancelled) setStatus("已启动自动推进…");
        } else {
          setStatus("AI 回合自动进行中…");
        }
      } catch (error) {
        if (!cancelled) {
          setHydrating(false);
          setStatus("无法连接后端，请确认服务已启动（默认 http://127.0.0.1:9000）。");
          reportError(errorDialogPayload(error, "连接后端失败", "DebateRoom.hydrate", "请确认服务已启动"));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isLocal, routeId, applyDebate, participant?.id, reportError, userSide, visibility]);

  useEffect(() => {
    if (isLocal || !routeId || routeId === "demo" || hydrating) return undefined;
    let cancelled = false;

    async function syncRemote() {
      try {
        const query = buildViewerQuery({
          viewerSide: userSide,
          participantId: participant?.id,
          viewerMode: visibility,
        });
        const remote = await debateRequest(`/api/debates/${routeId}${query}`);
        if (!cancelled) applyDebate(remote, { clearStreaming: false });
      } catch (error) {
        reportError(errorDialogPayload(error, "同步房间状态失败", "DebateRoom.poll", "正在重试同步房间状态"), {
          dedupeKey: `debate-room-poll:${routeId}`,
          throttleMs: 15000,
        });
      }
    }

    const timer = setInterval(syncRemote, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [isLocal, routeId, hydrating, applyDebate, reportError, userSide, participant?.id, visibility]);

  useEffect(() => {
    if (isLocal || mode === "online_match" || !userInputEnabled || !routeId || routeId === "demo") return undefined;
    const timer = setTimeout(() => {
      fetch(`${API_BASE}/api/debates/${routeId}/user-draft`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ draft }),
      }).catch(() => {});
    }, 600);
    return () => clearTimeout(timer);
  }, [draft, isLocal, mode, userInputEnabled, routeId]);

  const resumeDebate = useCallback(async () => {
    if (isLocal || !debate.id || debate.id === "demo-room") return;
    try {
      await debateRequest(`/api/debates/${debate.id}/resume`, { method: "POST" });
      setStatus("已请求继续自动推进…");
    } catch (err) {
      setStatus(`无法恢复推进：${err.message || "请检查后端"}`);
      reportError(errorDialogPayload(err, "恢复自动推进失败", "DebateRoom.resume", "请检查后端"));
    }
  }, [isLocal, debate.id, reportError]);

  const sendMessage = useCallback(async () => {
    if (!draft.trim() || !userInputEnabled || messageSending) return;
    if (!speechInputState.canSubmit) {
      setStatus(speechInputState.reason || "当前无法提交发言");
      return;
    }
    const side = userSide || "affirmative";
    const speakerId = mode === "online_match" ? onlineSpeakerId || "user" : userSpeakerId(debate) || "user";
    setMessageSending(true);
    setStatus("正在提交发言…");
    try {
      const query = buildViewerQuery({
        viewerSide: userSide,
        participantId: participant?.id,
        viewerMode: visibility,
      });
      const next = await debateRequest(`/api/debates/${debate.id}/message${query}`, {
        method: "POST",
        body: JSON.stringify({
          speaker_id: speakerId,
          speaker_name: participant?.name || "用户辩手",
          side,
          position: participant?.position || 1,
          participant_id: participant?.id,
          content: draft,
        }),
      });
      applyDebate(next);
      setDraft("");
      const lastUserMsg = [...(next.messages || [])]
        .reverse()
        .find((m) => m.speech_flag === "ok" || m.speech_flag === "inappropriate");
      if (lastUserMsg?.speech_flag === "inappropriate") {
        setStatus("发言已记录并扣分，请继续辩论。");
      } else {
        setStatus("发言已提交，AI 将继续自动推进。");
      }
    } catch (e) {
      if (!isLocal) {
        setStatus(`提交失败：${e.message || "请确认是否轮到您的席位发言"}`);
        reportError(errorDialogPayload(e, "提交发言失败", "DebateRoom.sendMessage", "请确认是否轮到您的席位发言"));
        return;
      }
      const next = structuredClone(debate);
      next.messages.push({
        id: crypto.randomUUID(),
        speaker_id: speakerId,
        speaker_name: participant?.name || "用户辩手",
        side,
        phase: next.phase,
        segment_label: next.segment_label,
        content: draft,
        sources: [],
      });
      next.awaiting_user = false;
      next.turn_index += 1;
      next.schedule_index = Math.min((next.schedule_index || 0) + 1, (next.schedule?.length || 1) - 1);
      if (next.schedule?.length) {
        const segment = next.schedule[next.schedule_index];
        next.active_speaker_id = segment?.speakerId || next.active_speaker_id;
        next.segment_label = segment?.label || next.segment_label;
        next.phase = segment?.phase || next.phase;
      }
      setDebate(next);
      setDraft("");
      setStatus("本地演示：已提交，自动继续…");
    } finally {
      setMessageSending(false);
    }
  }, [
    draft,
    userInputEnabled,
    messageSending,
    speechInputState,
    userSide,
    mode,
    onlineSpeakerId,
    debate,
    participant,
    isLocal,
    applyDebate,
    visibility,
  ]);

  const stopSpeechInput = useCallback(async () => {
    const rec = cleanupSpeechRecorder();
    if (!rec) return;
    if (!rec.chunks.length || Date.now() - rec.startedAt < 500) {
      setSpeechStatus("录音太短，请重新录入。");
      return;
    }
    setSpeechStatus("正在识别语音…");
    try {
      const audio = encodeChunksAsWav(rec.chunks, rec.audioContext.sampleRate, 16000);
      if (isLocal || !debate.id || debate.id === "demo-room") {
        setSpeechStatus("本地演示不连接阿里云识别，请在后端房间中使用。");
        return;
      }
      const form = new FormData();
      form.append("file", audio, "speech.wav");
      const response = await fetch(`${API_BASE}/api/debates/${debate.id}/speech-to-text`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) throw parseHttpErrorBody(await response.text(), response);
      const data = await response.json();
      const text = (data.text || "").trim();
      if (!text) throw new Error("未识别到文字");
      setDraft((current) => (current?.trim() ? `${current.trimEnd()}\n\n${text}` : text));
      setSpeechStatus(`已识别 ${text.length} 字，可继续修改后提交。`);
    } catch (e) {
      setSpeechStatus(`语音识别失败：${e.message || "请检查麦克风权限与阿里云配置"}`);
      reportError(errorDialogPayload(e, "语音识别失败", "DebateRoom.speechToText", "请检查麦克风权限与阿里云配置"));
    }
  }, [cleanupSpeechRecorder, debate.id, isLocal, reportError]);

  const startSpeechInput = useCallback(async () => {
    if (!awaitingUser || !userInputEnabled) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      setSpeechStatus("当前浏览器不支持麦克风录音。");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      const audioContext = new AudioContext();
      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      const gain = audioContext.createGain();
      gain.gain.value = 0;
      const chunks = [];
      processor.onaudioprocess = (event) => {
        chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
      };
      source.connect(processor);
      processor.connect(gain);
      gain.connect(audioContext.destination);
      speechRecorderRef.current = {
        stream,
        audioContext,
        source,
        processor,
        gain,
        chunks,
        startedAt: Date.now(),
        timeout: setTimeout(() => stopSpeechInput(), 45000),
      };
      setSpeechRecording(true);
      setSpeechStatus("正在录音，最多 45 秒。再次点击结束并识别。");
    } catch (e) {
      setSpeechStatus(`无法开启麦克风：${e.message || "请允许浏览器麦克风权限"}`);
    }
  }, [awaitingUser, userInputEnabled, stopSpeechInput]);

  const toggleSpeechInput = useCallback(() => {
    if (speechRecording) {
      stopSpeechInput();
      return;
    }
    startSpeechInput();
  }, [speechRecording, startSpeechInput, stopSpeechInput]);

  const exportFullHistory = useCallback(() => {
    if (!isLocal && debate.id && debate.id !== "demo-room") {
      const query = buildViewerQuery({
        viewerSide: userSide,
        participantId: participant?.id,
        viewerMode: visibility,
      });
      window.open(`${API_BASE}/api/debates/${debate.id}/export.md${query}`, "_blank", "noopener");
      return;
    }
    downloadTextFile(`debate-${debate.id || "local"}-history.md`, buildClientHistoryMarkdown(debate));
  }, [isLocal, debate, userSide, participant?.id, visibility]);

  const exportPdf = useCallback(() => {
    if (!isLocal && debate.id && debate.id !== "demo-room") {
      const query = buildViewerQuery({
        viewerSide: userSide,
        participantId: participant?.id,
        viewerMode: visibility,
      });
      window.open(`${API_BASE}/api/debates/${debate.id}/export.pdf${query}`, "_blank", "noopener");
    }
  }, [isLocal, debate.id, userSide, participant?.id, visibility]);

  const uploadMaterials = useCallback(
    async (replace = false) => {
      if (isLocal || !debate.id || debate.id === "demo-room" || !materialDraft.trim()) return;
      setMaterialStatus("正在写入向量库…");
      try {
        const data = await debateRequest(`/api/debates/${debate.id}/materials`, {
          method: "POST",
          body: JSON.stringify({ title: materialTitle, content: materialDraft, replace }),
        });
        setMaterialStatus(`已入库 ${data.chunks} 个片段，AI 检索将优先本场资料。`);
        setMaterialDraft("");
      } catch (e) {
        setMaterialStatus(`上传失败：${e.message}`);
        reportError(errorDialogPayload(e, "资料上传失败", "DebateRoom.uploadMaterials"));
      }
    },
    [isLocal, debate.id, materialDraft, materialTitle, reportError],
  );

  const onMaterialFile = useCallback(
    async (event) => {
      const file = event.target.files?.[0];
      if (!file || isLocal) return;
      const form = new FormData();
      form.append("file", file);
      form.append("title", file.name);
      form.append("replace", "false");
      setMaterialStatus("正在上传文件…");
      try {
        const response = await fetch(`${API_BASE}/api/debates/${debate.id}/materials/file`, {
          method: "POST",
          body: form,
        });
        if (!response.ok) throw parseHttpErrorBody(await response.text(), response);
        const data = await response.json();
        setMaterialStatus(`文件已入库：${data.chunks} 个片段`);
      } catch (e) {
        setMaterialStatus(`文件上传失败：${e.message}`);
        reportError(errorDialogPayload(e, "资料文件上传失败", "DebateRoom.uploadMaterialFile"));
      }
      event.target.value = "";
    },
    [isLocal, debate.id, reportError],
  );

  const askAssist = useCallback(async () => {
    if (!userInputEnabled) return;
    setAssistLoading(true);
    let fullText = "";
    try {
      await streamSseJson(`/api/debates/${debate.id}/assist/stream`, { side: userSide, position: userPosition, draft }, (event) => {
        if (event.type === "chunk") {
          fullText = event.full_text || `${fullText}${event.text || ""}`;
          setAssist((prev) => ({
            side: userSide,
            suggestion: fullText,
            counter_rebuttal: prev?.counter_rebuttal || "",
            possible_lines: prev?.possible_lines || [],
            sources: prev?.sources || [],
          }));
          return;
        }
        if (event.type === "done" && event.data) {
          setAssist(event.data);
          return;
        }
        if (event.type === "error") {
          setStatus(`建议流式生成失败：${event.message || "请检查后端"}`);
          reportError({
            title: "建议生成失败",
            message: event.message || "请检查后端",
            source: "DebateRoom.assist.stream",
          });
        }
      });
    } catch (e) {
      reportError(errorDialogPayload(e, "建议生成失败", "DebateRoom.assist", "请检查后端"));
      setAssist({
        suggestion: "用 Markdown 列出三点：承认对方最强点 → 指出证据缺口 → 回到本方标准。",
        possible_lines: ["**请问**对方的数据样本是否覆盖全体青少年？"],
        sources: [],
      });
    } finally {
      setAssistLoading(false);
    }
  }, [userInputEnabled, debate.id, userSide, userPosition, draft, reportError]);

  const askDraft = useCallback(async () => {
    if (!userInputEnabled || !awaitingUser) return;
    setDraftLoading(true);
    setShowDraftPreview(true);
    let fullText = "";
    try {
      await streamSseJson(`/api/debates/${debate.id}/assist/draft/stream`, { side: userSide, position: userPosition, draft }, (event) => {
        if (event.type === "chunk") {
          fullText = event.full_text || `${fullText}${event.text || ""}`;
          setDraft(fullText);
          return;
        }
        if (event.type === "done" && event.data?.draft) {
          setDraft(event.data.draft);
          setStatus("已流式生成代拟草稿，可继续修改后提交。");
          return;
        }
        if (event.type === "error") {
          setStatus(`代拟草稿流式生成失败：${event.message || "请检查后端"}`);
          reportError({
            title: "代拟草稿失败",
            message: event.message || "请检查后端",
            source: "DebateRoom.draft.stream",
          });
        }
      });
    } catch (e) {
      setStatus(`代拟草稿失败：${e.message}`);
      reportError(errorDialogPayload(e, "代拟草稿失败", "DebateRoom.draft", "请检查后端"));
    } finally {
      setDraftLoading(false);
    }
  }, [userInputEnabled, awaitingUser, debate.id, userSide, userPosition, draft, reportError]);

  const stopTtsSession = useCallback(async () => {
    ttsEnabledRef.current = false;
    clearAudioQueue();
    setAudioDisabled(true);
    clearTtsTimeout();
    setTtsStatus("本场辩论已停止语音朗读与合成");
    setDebate((prev) => ({ ...prev, tts_enabled: false }));
    if (!isLocal && debate.id && debate.id !== "demo-room") {
      try {
        await debateRequest(`/api/debates/${debate.id}/tts/stop`, { method: "POST" });
      } catch (e) {
        setTtsStatus(`停止语音失败：${e.message || "请稍后重试"}`);
        reportError(errorDialogPayload(e, "停止语音失败", "DebateRoom.stopTts", "请稍后重试"));
      }
    }
  }, [clearAudioQueue, clearTtsTimeout, debate.id, isLocal, reportError, setAudioDisabled]);

  useEffect(() => {
    function onKeyDown(event) {
      if (event.target.matches("textarea, input")) return;
      if (event.key === "Escape") {
        skipCurrentAudio();
        return;
      }
      if (event.code === "Space" && (currentAudio || audioPaused)) {
        event.preventDefault();
        if (audioPaused) resumeAudio();
        else pauseAudio();
      }
      if (event.altKey && event.key === "1") {
        messageBoardRef.current?.scrollIntoView({ behavior: "smooth" });
      }
      if (event.altKey && event.key === "e") {
        exportFullHistory();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [skipCurrentAudio, exportFullHistory, pauseAudio, resumeAudio, currentAudio, audioPaused]);

  return {
    mode,
    isLocal,
    initialCameraEnabled: init.cameraEnabled,
    debate,
    streaming,
    pipelineHint,
    pipelineHintText: formatPipelineHint(pipelineHint),
    draft,
    setDraft,
    participant,
    setParticipant,
    visibility,
    setVisibility,
    timing,
    setTiming,
    health,
    healthError,
    assist,
    assistLoading,
    status,
    materialDraft,
    setMaterialDraft,
    materialTitle,
    setMaterialTitle,
    materialStatus,
    audioByMessage,
    playMessageAudio,
    ttsStatus,
    speechStatus,
    speechRecording,
    messageBoardRef,
    messageListScrollRef,
    userInputEnabled,
    userSide,
    awaitingUser,
    speechInputState,
    turnSecondsLeft,
    activeAgent,
    visibleMessages,
    teamDiscussions,
    aiStrategyNotes,
    processTimeline,
    speakingNow,
    showStreamingPublic,
    hydrating,
    wsConnected,
    wsReconnecting,
    wsEverConnected,
    wsConnectionState,
    wsAttempt,
    wsLastError,
    sendWebRtcSignal,
    subscribeWebRtcSignal,
    sendViewerModeUpdate,
    currentAudio,
    audioQueueLength,
    audioSubtitle,
    audioPaused,
    audioDisabled,
    pauseAudio,
    resumeAudio,
    skipCurrentAudio,
    stopTtsSession,
    resumeDebate,
    sendMessage,
    messageSending,
    toggleSpeechInput,
    exportFullHistory,
    uploadMaterials,
    onMaterialFile,
    askAssist,
    askDraft,
    draftLoading,
    showDraftPreview,
    setShowDraftPreview,
    exportPdf,
    speechFontPx,
    setSpeechFontPx,
    autoScroll,
    setAutoScroll,
  };
}
