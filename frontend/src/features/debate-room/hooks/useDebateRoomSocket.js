import { useRef } from "react";
import { useDebateSocket } from "../../../hooks/useDebateSocket.js";
import { debaterPositionLabel } from "../../../utils/debateDisplay.js";
import { debateRequest } from "../api.js";
import { getOnlineStatusMessage, needsUserTurn } from "../utils.js";

function speakerSeatLabel(debate, speakerId, fallback, side) {
  return debaterPositionLabel(speakerId, debate?.agents || []) || (side === "judge" ? "裁判" : fallback || "系统");
}

export function useDebateRoomSocket({
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
}) {
  const handlers = useRef({
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
    debateRef,
    participant,
    streamStaleRef,
    reportError,
  });

  handlers.current = {
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
    debateRef,
    participant,
    streamStaleRef,
    reportError,
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
      const agent = h.debateRef.current?.agents?.find((item) => item.id === data.speaker_id);
      h.setPipelineHint({
        type: "workflow_progress",
        nodeLabel: data.segment_label || "辩手发言生成",
        speakerId: data.speaker_id,
        speakerName: speakerSeatLabel(h.debateRef.current, data.speaker_id, data.speaker_name, data.side),
        side: data.side,
        position: agent?.position || 0,
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
      const name = speakerSeatLabel(handlers.current.debateRef.current, data.speaker_id, data.speaker_name, data.side);
      handlers.current.setTtsStatus(`${name} 正在合成语音（女声 · 快语速）…`);
      handlers.current.armTtsTimeout(name);
    },
    onSpeechAudioProgress: (data) => {
      if (handlers.current.ttsEnabledRef?.current === false) return;
      const name = speakerSeatLabel(handlers.current.debateRef.current, data.speaker_id, data.speaker_name, data.side);
      handlers.current.setTtsStatus(`${name} 正在合成语音（第 ${data.chunk || 1}/${data.total || 1} 段）…`);
      handlers.current.armTtsTimeout(name);
    },
    onSpeechAudio: (data) => {
      const h = handlers.current;
      h.clearTtsTimeout();
      if (h.ttsEnabledRef?.current === false) return;
      const urls = data.audio_urls?.length ? data.audio_urls : [data.audio_url];
      h.setTtsStatus(
        `${speakerSeatLabel(h.debateRef.current, data.speaker_id, data.speaker_name, data.side)} 开始朗读（${data.voice}）` +
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
        speakerName: speakerSeatLabel(h.debateRef.current, data.speaker_id, data.speaker_name, data.side),
      });
    },
    onSpeechAudioError: (data) => {
      handlers.current.clearTtsTimeout();
      handlers.current.setTtsStatus(`语音合成失败：${data.message || "请检查 DashScope 配置"}`);
      handlers.current.reportError?.({
        title: "语音合成失败",
        message: data.message || "请检查 DashScope 配置",
        code: data.code,
        requestId: data.request_id,
        source: "DebateRoom.socket.speechAudioError",
      });
    },
    onError: (data) => {
      const h = handlers.current;
      h.clearTtsTimeout();
      const msg = data.message || "请查看后端日志";
      h.setStatus(`回合异常：${msg}（将尝试恢复自动推进）`);
      h.setTtsStatus((prev) => (prev.includes("正在合成语音") ? `回合异常：${msg}` : prev));
      h.reportError?.({
        title: "辩论回合异常",
        message: msg,
        code: data.code || "debate_turn_error",
        requestId: data.request_id,
        source: "DebateRoom.socket.error",
      });
      const d = h.debateRef.current;
      if (d?.id && d.id !== "demo-room" && d.phase !== "finished" && !needsUserTurn(d)) {
        debateRequest(`/api/debates/${d.id}/resume`, { method: "POST" }).catch(() => {});
      }
    },
    onTransportError: (error) => {
      handlers.current.reportError?.(error, {
        dedupeKey: `${error.source}:${routeId}`,
        throttleMs: 10000,
      });
    },
    onPipelinePrep: (data) => {
      handlers.current.setPipelineHint({
        type: "pipeline_prep",
        speakerId: data.next_speaker_id,
        speakerName: speakerSeatLabel(handlers.current.debateRef.current, data.next_speaker_id, data.next_speaker_name, data.side),
        nodeLabel: data.segment_label,
        partialLength: data.partial_length,
        sourcesCount: data.sources_count,
        detail: `${speakerSeatLabel(handlers.current.debateRef.current, data.next_speaker_id, data.next_speaker_name, data.side)} 已读取当前输出，预热 ${data.sources_count || 0} 条资料。`,
      });
    },
    onWorkflowProgress: (data) => {
      if (["publish_message", "judge_score", "turn_router"].includes(data.node_id)) return;
      handlers.current.setPipelineHint({
        type: "workflow_progress",
        nodeId: data.node_id,
        nodeLabel: data.node_label || data.segment_label,
        nodeDetail: data.node_detail,
        speakerId: data.speaker_id,
        speakerName: speakerSeatLabel(handlers.current.debateRef.current, data.speaker_id, data.speaker_name, data.side),
        side: data.side,
        position: data.position,
        scheduleIndex: data.schedule_index,
        scheduleTotal: data.schedule_total,
      });
    },
    onArgumentBankUpdated: (data) => {
      handlers.current.applyArgumentBankUpdate?.(data.argument_bank);
      const sideLabel = data.side === "negative" ? "反方" : data.side === "affirmative" ? "正方" : "双方";
      handlers.current.setPipelineHint({
        type: "argument_bank_updated",
        nodeLabel: data.segment_label || "AI 检索真实论据入库",
        speakerName: speakerSeatLabel(handlers.current.debateRef.current, data.speaker_id, data.speaker_name || "裁判调度", data.side),
        side: data.side,
        added: data.added,
        affirmativeCount: data.affirmative_count,
        negativeCount: data.negative_count,
        targetPerSide: data.target_per_side,
        detail: `${sideLabel}论据已入库：正方 ${data.affirmative_count || 0} 条，反方 ${data.negative_count || 0} 条。`,
      });
    },
    onReflectionDone: (data) => {
      const draftChars = data.draft_chars ?? data.draftChars;
      const polishedChars = data.polished_chars ?? data.polishedChars;
      if (draftChars != null && polishedChars != null) {
        handlers.current.setPipelineHint({
          type: "reflection_done",
          nodeLabel: "反思:草稿→定稿",
          speakerName: speakerSeatLabel(handlers.current.debateRef.current, data.speaker_id, data.speaker_name || "当前 AI", data.side),
          draftChars,
          polishedChars,
          detail: `反思定稿完成：草稿 ${draftChars} 字，定稿 ${polishedChars} 字。`,
        });
      }
    },
  }, {
    viewerSide,
    participantId: participant?.id || null,
    viewerMode: visibility || "context",
    waitForParticipant,
  });
}
