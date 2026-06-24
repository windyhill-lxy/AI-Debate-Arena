import { useCallback, useEffect, useRef, useState } from "react";
import { useLocalCamera } from "./useLocalCamera.js";

const ICE_SERVERS = [{ urls: "stun:stun.l.google.com:19302" }];

function shouldAcceptOfferCollision(selfId, remoteId) {
  return String(selfId || "") > String(remoteId || "");
}

export function useOnlinePeerCamera({
  debateId,
  participantId,
  enabled = true,
  initialLocalOn = true,
  sendSignal,
  subscribeWebRtcSignal,
}) {
  const [localOn, setLocalOn] = useState(() => Boolean(initialLocalOn));
  const [remoteStreams, setRemoteStreams] = useState([]);
  const {
    stream: localStream,
    error: localError,
    hasDevice,
    startStream,
    stopStream,
  } = useLocalCamera({ enabled: enabled && localOn, popupOnError: true });
  const peersRef = useRef(new Map());
  const signalQueuesRef = useRef(new Map());
  const selfIdRef = useRef(participantId || "");

  useEffect(() => {
    selfIdRef.current = participantId || "";
  }, [participantId]);

  useEffect(() => {
    if (enabled && !initialLocalOn) setLocalOn(false);
  }, [enabled, initialLocalOn]);

  const cleanupPeer = useCallback((remoteId) => {
    const pc = peersRef.current.get(remoteId);
    if (pc) {
      pc.close();
      peersRef.current.delete(remoteId);
    }
    signalQueuesRef.current.delete(remoteId);
    setRemoteStreams((prev) => prev.filter((item) => item.id !== remoteId));
  }, []);

  const addRemoteStream = useCallback((remoteId, stream) => {
    setRemoteStreams((prev) => {
      const others = prev.filter((item) => item.id !== remoteId);
      return [...others, { id: remoteId, stream }];
    });
  }, []);

  const emitSignal = useCallback(
    (payload) => {
      if (!sendSignal || !selfIdRef.current) return;
      sendSignal({
        from_participant_id: selfIdRef.current,
        ...payload,
      });
    },
    [sendSignal],
  );

  const ensureLocalStream = useCallback(async () => {
    if (!localOn) return null;
    return startStream();
  }, [localOn, startStream]);

  const createOffer = useCallback(
    async (remoteId) => {
      if (!enabled || !debateId || !selfIdRef.current || remoteId === selfIdRef.current) return;
      if (peersRef.current.has(remoteId)) return;
      const stream = await ensureLocalStream();
      const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });
      peersRef.current.set(remoteId, pc);
      stream?.getTracks().forEach((track) => pc.addTrack(track, stream));
      pc.onicecandidate = (event) => {
        if (event.candidate) {
          emitSignal({
            signal_type: "ice",
            to_participant_id: remoteId,
            payload: event.candidate,
          });
        }
      };
      pc.ontrack = (event) => {
        const [remote] = event.streams;
        if (remote) addRemoteStream(remoteId, remote);
      };
      pc.onconnectionstatechange = () => {
        if (pc.connectionState === "failed" || pc.connectionState === "closed") {
          cleanupPeer(remoteId);
        }
      };
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      emitSignal({
        signal_type: "offer",
        to_participant_id: remoteId,
        payload: offer,
      });
    },
    [addRemoteStream, cleanupPeer, debateId, enabled, emitSignal, ensureLocalStream],
  );

  const createPeer = useCallback(
    (remoteId, stream) => {
      const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });
      peersRef.current.set(remoteId, pc);
      stream?.getTracks().forEach((track) => pc.addTrack(track, stream));
      pc.onicecandidate = (event) => {
        if (event.candidate) {
          emitSignal({
            signal_type: "ice",
            to_participant_id: remoteId,
            payload: event.candidate,
          });
        }
      };
      pc.ontrack = (event) => {
        const [remote] = event.streams;
        if (remote) addRemoteStream(remoteId, remote);
      };
      pc.onconnectionstatechange = () => {
        if (pc.connectionState === "failed" || pc.connectionState === "closed") {
          cleanupPeer(remoteId);
        }
      };
      return pc;
    },
    [addRemoteStream, cleanupPeer, emitSignal],
  );

  const handleSignal = useCallback(
    async (data) => {
      const remoteId = data.from_participant_id;
      if (!remoteId || remoteId === selfIdRef.current) return;
      const stream = await ensureLocalStream();
      const pc = peersRef.current.get(remoteId) || createPeer(remoteId, stream);
      if (data.signal_type === "offer") {
        if (data.payload?.type !== "offer") return;
        if (pc.signalingState !== "stable") {
          if (pc.signalingState !== "have-local-offer" || !shouldAcceptOfferCollision(selfIdRef.current, remoteId)) return;
          await pc.setLocalDescription({ type: "rollback" });
        }
        await pc.setRemoteDescription(new RTCSessionDescription(data.payload));
        if (pc.signalingState !== "have-remote-offer") return;
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        emitSignal({
          signal_type: "answer",
          to_participant_id: remoteId,
          payload: answer,
        });
      } else if (data.signal_type === "answer") {
        if (data.payload?.type !== "answer") return;
        if (pc.signalingState !== "have-local-offer") return;
        await pc.setRemoteDescription(new RTCSessionDescription(data.payload));
      } else if (data.signal_type === "ice" && data.payload) {
        try {
          await pc.addIceCandidate(new RTCIceCandidate(data.payload));
        } catch {
          /* ignore stale ice */
        }
      }
    },
    [createPeer, emitSignal, ensureLocalStream],
  );

  const enqueueSignal = useCallback(
    (data) => {
      const remoteId = data?.from_participant_id;
      if (!remoteId || remoteId === selfIdRef.current) return;

      const current = signalQueuesRef.current.get(remoteId) || Promise.resolve();
      const next = current
        .catch(() => {})
        .then(() => handleSignal(data))
        .catch(() => {
          /* ignore stale or out-of-order WebRTC signals */
        });
      signalQueuesRef.current.set(remoteId, next);
    },
    [handleSignal],
  );

  useEffect(() => {
    if (!enabled || !subscribeWebRtcSignal) return undefined;
    return subscribeWebRtcSignal((data) => {
      if (data?.type === "webrtc_signal" || data?.signal_type) {
        enqueueSignal(data);
      }
    });
  }, [enabled, enqueueSignal, subscribeWebRtcSignal]);

  const syncPeers = useCallback(
    (participantIds) => {
      const ids = (participantIds || []).filter((id) => id && id !== selfIdRef.current);
      ids.forEach((id) => {
        createOffer(id).catch(() => {
          /* ignore transient WebRTC setup failures */
        });
      });
      for (const remoteId of peersRef.current.keys()) {
        if (!ids.includes(remoteId)) cleanupPeer(remoteId);
      }
    },
    [cleanupPeer, createOffer],
  );

  useEffect(() => {
    if (!localOn || localError) {
      if (!localOn) stopStream();
      for (const remoteId of [...peersRef.current.keys()]) cleanupPeer(remoteId);
    }
  }, [cleanupPeer, localError, localOn, stopStream]);

  useEffect(
    () => () => {
      stopStream();
      for (const remoteId of [...peersRef.current.keys()]) cleanupPeer(remoteId);
    },
    [cleanupPeer, stopStream],
  );

  const toggleLocal = useCallback(() => setLocalOn((on) => !on), []);

  return {
    localStream,
    localOn,
    toggleLocal,
    remoteStreams,
    error: localError,
    hasDevice,
    syncPeers,
  };
}
