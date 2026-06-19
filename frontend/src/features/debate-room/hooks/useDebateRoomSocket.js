import { useRef } from "react";
import { useDebateSocket } from "../../../hooks/useDebateSocket.js";
import { debateRequest } from "../api.js";
import { getOnlineStatusMessage, needsUserTurn } from "../utils.js";

export function useDebateRoomSocket({
  routeId,
  isLocal,
  debateRef,
  participant,
  visibility,
  applyDebate,
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
}) {
  const handlers = useRef({
    applyDebate,
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
    debateRef,
    participant,
    streamStaleRef,
  });

  handlers.current = {
    applyDebate,
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
    debateRef,
    participant,
    streamStaleRef,
  };

  const currentDebate = debateRef.current;
  const viewerSide =
    participant?.side && participant.side !== "spectator"
      ? participant.side
      : currentDebate?.user_side || null;

  const waitForParticipant =
    currentDebate?.mode === "online_match" || Boolean(participant?.id);

  return useDebateSocket(isLocal ? null : routeId, {
    onDebateMerge: (d) => {
      handlers.current.applyDebate(d, { clearStreaming: false });
    },
    onDebate: (d) => {
      handlers.current.applyDebate(d, { clearStreaming: true });
      if (d.phase === "finished") return;
      handlers.current.setStatus(getOnlineStatusMessage(d, handlers.current.participant));
    },
    onReconnected: () => handlers.current.setStatus("已重新连接并同步房间状态。"),
    onAwaitingUser: (d) => {
      handlers.current.applyDebate(d);
      handlers.current.setStatus(getOnlineStatusMessage(d, handlers.current.participant));
    },
    onFinished: (d) => {
      handlers.current.applyDebate(d);
      handlers.current.setStatus("辩论已结束。");
    },
    onSpeechStart: (data) => {
      const h = handlers.current;
      if (h.streamStaleRef.current) clearTimeout(h.streamStaleRef.current);
      h.setStreaming({
        message_id: data.message_id,
        speaker_id: data.speaker_id,
        speaker_name: data.speaker_name,
        side: data.side,
        phase: data.phase,
        segment_label: data.segment_label,
        content: "",
      });
      h.streamStaleRef.current = setTimeout(() => {
        h.setStreaming(null);
        h.setStatus("发言流中断，已等待服务器同步…");
      }, 120000);
    },
    onSpeechChunk: (data) => {
      const h = handlers.current;
      if (h.streamStaleRef.current) {
        clearTimeout(h.streamStaleRef.current);
        h.streamStaleRef.current = setTimeout(() => h.setStreaming(null), 120000);
      }
      h.setStreaming((prev) =>
        prev && prev.message_id === data.message_id
          ? {
              ...prev,
              speaker_id: data.speaker_id || prev.speaker_id,
              speaker_name: data.speaker_name || prev.speaker_name,
              side: data.side || prev.side,
              phase: data.phase || prev.phase,
              segment_label: data.segment_label || prev.segment_label,
              content: data.content,
            }
          : {
              message_id: data.message_id,
              speaker_id: data.speaker_id,
              speaker_name: data.speaker_name,
              side: data.side,
              phase: data.phase,
              segment_label: data.segment_label,
              content: data.content,
            },
      );
    },
    onSpeechEnd: (data) => {
      const h = handlers.current;
      if (h.streamStaleRef.current) {
        clearTimeout(h.streamStaleRef.current);
        h.streamStaleRef.current = null;
      }
      h.setStreaming((prev) => {
        if (!prev || data?.message_id !== prev.message_id) return prev;
        const finalText = data.content || "";
        const streamed = prev.content || "";
        // Backend must not shrink visible stream at speech_end; keep longer client buffer if needed.
        const content =
          finalText.length >= streamed.length ? finalText || streamed : streamed;
        return { ...prev, content };
      });
    },
    onSpeechAudioStart: (data) => {
      if (handlers.current.ttsEnabledRef?.current === false) return;
      const name = data.speaker_name || "AI 辩手";
      handlers.current.setTtsStatus(`${name} 正在合成语音（女声 · 快语速）…`);
      handlers.current.armTtsTimeout(name);
    },
    onSpeechAudioProgress: (data) => {
      if (handlers.current.ttsEnabledRef?.current === false) return;
      const name = data.speaker_name || "AI 辩手";
      handlers.current.setTtsStatus(`${name} 正在合成语音（第 ${data.chunk || 1}/${data.total || 1} 段）…`);
      handlers.current.armTtsTimeout(name);
    },
    onSpeechAudio: (data) => {
      const h = handlers.current;
      h.clearTtsTimeout();
      if (h.ttsEnabledRef?.current === false) return;
      const urls = data.audio_urls?.length ? data.audio_urls : [data.audio_url];
      h.setTtsStatus(
        `${data.speaker_name || "AI 辩手"} 开始朗读（${data.voice}）` +
          (urls.length > 1 ? `，共 ${urls.length} 段` : ""),
      );
      h.setAudioByMessage((current) => ({
        ...current,
        [data.message_id]: {
          audio_url: data.audio_url,
          audio_urls: urls,
          voice: data.voice,
          instructions: data.instructions,
        },
      }));
      const msg = h.debateRef.current.messages.find((m) => m.id === data.message_id);
      h.enqueueAudio(urls, {
        messageId: data.message_id,
        text: msg?.content || "",
        speakerName: data.speaker_name,
      });
    },
    onSpeechAudioError: (data) => {
      handlers.current.clearTtsTimeout();
      handlers.current.setTtsStatus(`语音合成失败：${data.message || "请检查 DashScope 配置"}`);
    },
    onError: (data) => {
      const h = handlers.current;
      h.clearTtsTimeout();
      const msg = data.message || "请查看后端日志";
      h.setStatus(`回合异常：${msg}（将尝试恢复自动推进）`);
      h.setTtsStatus((prev) => (prev.includes("正在合成语音") ? `回合异常：${msg}` : prev));
      const d = h.debateRef.current;
      if (d?.id && d.id !== "demo-room" && d.phase !== "finished" && !needsUserTurn(d)) {
        debateRequest(`/api/debates/${d.id}/resume`, { method: "POST" }).catch(() => {});
      }
    },
    onPipelinePrep: (data) => {
      handlers.current.setPipelineHint(
        `下一位 ${data.next_speaker_name} 已根据当前输出开始预热（${data.sources_count} 条资料）`,
      );
    },
    onReflectionDone: (data) => {
      const draftChars = data.draft_chars ?? data.draftChars;
      const polishedChars = data.polished_chars ?? data.polishedChars;
      if (draftChars != null && polishedChars != null) {
        handlers.current.setPipelineHint(`反思定稿完成（草稿 ${draftChars} 字 → 定稿 ${polishedChars} 字）`);
      }
    },
  }, {
    viewerSide,
    participantId: participant?.id || null,
    viewerMode: visibility || "context",
    waitForParticipant,
  });
}
