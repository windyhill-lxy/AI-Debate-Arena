import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { buildViewerQuery } from "../features/debate-room/visibilityModes.js";
import { API_BASE, toWebSocketBase } from "../utils/apiBase.js";

const DEBATE_EVENTS = new Set([
  "snapshot",
  "debate_created",
  "debate_stepped",
  "message_added",
  "participant_joined",
  "participant_left",
  "participant_kicked",
  "participant_presence_changed",
  "online_ready",
  "tts_stopped",
  "debate_audio_attached",
]);

function wsBase() {
  return toWebSocketBase(API_BASE);
}

async function fetchDebateSnapshot(debateId, options) {
  const response = await fetch(
    `${API_BASE}/api/debates/${debateId}${buildViewerQuery({
      viewerSide: options.viewerSide,
      participantId: options.participantId,
      viewerMode: options.viewerMode,
    })}`,
  );
  if (!response.ok) throw new Error("snapshot failed");
  return response.json();
}

function buildWsUrl(debateId, options) {
  return `${wsBase()}/api/debates/ws/${debateId}${buildViewerQuery({
    viewerSide: options.viewerSide,
    participantId: options.participantId,
    viewerMode: options.viewerMode,
  })}`;
}

export function useDebateSocket(debateId, handlers, options = {}) {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const [connectionState, setConnectionState] = useState("idle");
  const [reconnecting, setReconnecting] = useState(false);
  const [everConnected, setEverConnected] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [lastError, setLastError] = useState("");
  const [lastConnectedAt, setLastConnectedAt] = useState(null);

  const socketRef = useRef(null);
  const webrtcListenersRef = useRef(new Set());
  const snapshotSyncedAtRef = useRef(0);

  const connectionKey = useMemo(
    () =>
      [
        debateId || "",
        options.waitForParticipant ? options.participantId || "" : "any",
        options.viewerSide || "",
        options.viewerMode || "",
      ].join(":"),
    [
      debateId,
      options.waitForParticipant,
      options.participantId,
      options.viewerSide,
      options.viewerMode,
    ],
  );

  const connected = connectionState === "open";

  const sendWebRtcSignal = useCallback((payload) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({ type: "webrtc_signal", ...payload }));
  }, []);

  const subscribeWebRtcSignal = useCallback((listener) => {
    webrtcListenersRef.current.add(listener);
    return () => {
      webrtcListenersRef.current.delete(listener);
    };
  }, []);

  const sendViewerModeUpdate = useCallback((viewerMode, viewerSide) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(
      JSON.stringify({
        type: "update_viewer_mode",
        viewer_mode: viewerMode,
        viewer_side: viewerSide,
      }),
    );
  }, []);

  useEffect(() => {
    if (!debateId || debateId === "demo") return undefined;
    if (options.waitForParticipant && !options.participantId) return undefined;

    let socket = null;
    let disposed = false;
    let retryTimer = null;
    let pingTimer = null;
    let attempts = 0;

    const syncSnapshotThrottled = async () => {
      const now = Date.now();
      if (now - snapshotSyncedAtRef.current < 1500) return;
      snapshotSyncedAtRef.current = now;
      try {
        const debate = await fetchDebateSnapshot(debateId, optionsRef.current);
        handlersRef.current.onDebate?.(debate);
        handlersRef.current.onReconnected?.(debate);
      } catch (error) {
        handlersRef.current.onTransportError?.({
          title: "同步房间快照失败",
          message: error.message || "实时连接已恢复，但快照同步失败。",
          source: "useDebateSocket.snapshot",
          code: "snapshot_sync_failed",
        });
      }
    };

    const connect = () => {
      if (disposed) return;
      if (optionsRef.current.waitForParticipant && !optionsRef.current.participantId) return;

      setConnectionState((prev) => (prev === "open" ? "open" : "connecting"));
      setReconnecting(attempts > 0);
      setAttempt(attempts);

      const wsUrl = buildWsUrl(debateId, optionsRef.current);
      socket = new WebSocket(wsUrl);
      socketRef.current = socket;

      socket.onopen = () => {
        attempts = 0;
        setConnectionState("open");
        setReconnecting(false);
        setEverConnected(true);
        setLastError("");
        setLastConnectedAt(Date.now());
        setAttempt(0);
        syncSnapshotThrottled();
        if (pingTimer) clearInterval(pingTimer);
        pingTimer = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: "ping" }));
          }
        }, 25000);
      };

      socket.onerror = () => {
        if (!disposed) {
          setConnectionState("degraded");
          setReconnecting(true);
          setLastError("websocket_error");
          handlersRef.current.onTransportError?.({
            title: "WebSocket 连接异常",
            message: "实时连接异常，系统将尝试自动重连。",
            source: "useDebateSocket.onerror",
            code: "websocket_error",
          });
        }
      };

      socket.onclose = () => {
        if (pingTimer) {
          clearInterval(pingTimer);
          pingTimer = null;
        }
        if (socketRef.current === socket) socketRef.current = null;
        setConnectionState(disposed ? "closed" : "reconnecting");
        setReconnecting(!disposed);
        if (disposed) return;
        syncSnapshotThrottled();
        const delay = Math.min(8000, 500 * 2 ** attempts);
        attempts += 1;
        setAttempt(attempts);
        retryTimer = setTimeout(connect, delay);
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "pong") return;
          const h = handlersRef.current;
          const ev = data.event || data.type;
          if (ev === "debate_audio_attached" && data.debate) {
            h.onDebateMerge?.(data.debate);
          } else if (data.debate && DEBATE_EVENTS.has(ev)) {
            h.onDebate?.(data.debate);
          }
          if (!ev && data.content != null && (data.message_id || data.chunk != null)) {
            h.onSpeechChunk?.(data);
          }
          if (ev === "awaiting_user") h.onAwaitingUser?.(data.debate);
          if (ev === "debate_finished") h.onFinished?.(data.debate);
          if (ev === "speech_start") h.onSpeechStart?.(data);
          if (ev === "speech_chunk") h.onSpeechChunk?.(data);
          if (ev === "speech_end") h.onSpeechEnd?.(data);
          if (ev === "speech_audio_start") h.onSpeechAudioStart?.(data);
          if (ev === "speech_audio_progress") h.onSpeechAudioProgress?.(data);
          if (ev === "speech_audio") h.onSpeechAudio?.(data);
          if (ev === "speech_audio_error") h.onSpeechAudioError?.(data);
          if (ev === "error") h.onError?.(data);
          if (ev === "pipeline_prep") h.onPipelinePrep?.(data);
          if (ev === "workflow_progress") h.onWorkflowProgress?.(data);
          if (ev === "argument_bank_updated") h.onArgumentBankUpdated?.(data);
          if (ev === "argument_bank_seeded") h.onArgumentBankUpdated?.(data);
          if (ev === "reflection_done") h.onReflectionDone?.(data);
          if (data.type === "webrtc_signal" || ev === "webrtc_signal") {
            webrtcListenersRef.current.forEach((listener) => {
              try {
                Promise.resolve(listener(data)).catch((error) => {
                  h.onTransportError?.({
                    title: "视频连线信令处理失败",
                    message: error?.message || "视频连线收到过期或乱序信令，已自动跳过。",
                    source: "useDebateSocket.webrtc_listener",
                    code: "webrtc_listener_failed",
                  });
                });
              } catch (error) {
                h.onTransportError?.({
                  title: "视频连线信令处理失败",
                  message: error?.message || "视频连线收到过期或乱序信令，已自动跳过。",
                  source: "useDebateSocket.webrtc_listener",
                  code: "webrtc_listener_failed",
                });
              }
            });
            h.onWebRtcSignal?.(data);
          }
        } catch (error) {
          handlersRef.current.onTransportError?.({
            title: "实时消息解析失败",
            message: "收到无法解析的实时消息，已跳过本条。",
            details: error.message,
            source: "useDebateSocket.onmessage",
            code: "websocket_payload_parse",
          });
        }
      };
    };

    connect();

    return () => {
      disposed = true;
      if (retryTimer) clearTimeout(retryTimer);
      if (pingTimer) clearInterval(pingTimer);
      socket?.close();
      if (socketRef.current === socket) socketRef.current = null;
      setConnectionState("closed");
      setReconnecting(false);
    };
  }, [connectionKey, debateId]);

  return {
    connected,
    reconnecting,
    everConnected,
    connectionState,
    attempt,
    lastError,
    lastConnectedAt,
    sendWebRtcSignal,
    subscribeWebRtcSignal,
    sendViewerModeUpdate,
  };
}
