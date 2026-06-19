import { useCallback, useEffect, useRef, useState } from "react";
import { useLocalCamera } from "./useLocalCamera.js";

const ICE_SERVERS = [{ urls: "stun:stun.l.google.com:19302" }];

export function useOnlinePeerCamera({
  debateId,
  participantId,
  enabled = true,
  sendSignal,
  subscribeWebRtcSignal,
}) {
  const [localOn, setLocalOn] = useState(true);
  const [remoteStreams, setRemoteStreams] = useState([]);
  const localCamera = useLocalCamera({ enabled: enabled && localOn });
  const peersRef = useRef(new Map());
  const selfIdRef = useRef(participantId || "");

  useEffect(() => {
    selfIdRef.current = participantId || "";
  }, [participantId]);

  const cleanupPeer = useCallback((remoteId) => {
    const pc = peersRef.current.get(remoteId);
    if (pc) {
      pc.close();
      peersRef.current.delete(remoteId);
    }
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
    return localCamera.startStream();
  }, [localCamera, localOn]);

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

  const handleSignal = useCallback(
    async (data) => {
      const remoteId = data.from_participant_id;
      if (!remoteId || remoteId === selfIdRef.current) return;
      const stream = await ensureLocalStream();
      let pc = peersRef.current.get(remoteId);
      if (!pc) {
        pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });
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
      }
      if (data.signal_type === "offer") {
        await pc.setRemoteDescription(new RTCSessionDescription(data.payload));
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        emitSignal({
          signal_type: "answer",
          to_participant_id: remoteId,
          payload: answer,
        });
      } else if (data.signal_type === "answer") {
        await pc.setRemoteDescription(new RTCSessionDescription(data.payload));
      } else if (data.signal_type === "ice" && data.payload) {
        try {
          await pc.addIceCandidate(new RTCIceCandidate(data.payload));
        } catch {
          /* ignore stale ice */
        }
      }
    },
    [addRemoteStream, cleanupPeer, emitSignal, ensureLocalStream],
  );

  useEffect(() => {
    if (!enabled || !subscribeWebRtcSignal) return undefined;
    return subscribeWebRtcSignal((data) => {
      if (data?.type === "webrtc_signal" || data?.signal_type) {
        handleSignal(data);
      }
    });
  }, [enabled, handleSignal, subscribeWebRtcSignal]);

  const syncPeers = useCallback(
    (participantIds) => {
      const ids = (participantIds || []).filter((id) => id && id !== selfIdRef.current);
      ids.forEach((id) => {
        createOffer(id);
      });
      for (const remoteId of peersRef.current.keys()) {
        if (!ids.includes(remoteId)) cleanupPeer(remoteId);
      }
    },
    [cleanupPeer, createOffer],
  );

  useEffect(() => {
    if (!localOn || localCamera.error) {
      if (!localOn) localCamera.stopStream();
      for (const remoteId of [...peersRef.current.keys()]) cleanupPeer(remoteId);
    }
  }, [cleanupPeer, localCamera, localCamera.error, localOn]);

  useEffect(
    () => () => {
      localCamera.stopStream();
      for (const remoteId of [...peersRef.current.keys()]) cleanupPeer(remoteId);
    },
    [cleanupPeer, localCamera],
  );

  const toggleLocal = useCallback(() => setLocalOn((on) => !on), []);

  return {
    localStream: localCamera.stream,
    localOn,
    toggleLocal,
    remoteStreams,
    error: localCamera.error,
    hasDevice: localCamera.hasDevice,
    syncPeers,
  };
}
