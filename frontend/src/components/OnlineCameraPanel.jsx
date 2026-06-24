import { useEffect, useRef, useState } from "react";
import { Camera, CameraOff } from "lucide-react";
import { useLocalCamera } from "../hooks/useLocalCamera.js";

function VideoTile({ stream, label, muted = false, mirror = false }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || !stream) return;
    el.srcObject = stream;
    el.play().catch(() => undefined);
  }, [stream]);
  if (!stream) return null;
  return (
    <div className="online-camera__tile">
      <video ref={ref} autoPlay playsInline muted={muted} className={mirror ? "is-mirror" : ""} />
      <span>{label}</span>
    </div>
  );
}

/** 加入页本地摄像头调试（仅预览，不推流） */
export function OnlineCameraDebug({ enabled = true, cameraEnabled = false, onCameraEnabledChange, onStream }) {
  const videoRef = useRef(null);
  const on = Boolean(cameraEnabled);
  const { stream, error } = useLocalCamera({ enabled: enabled && on, popupOnError: true });

  useEffect(() => {
    if (videoRef.current && stream) {
      videoRef.current.srcObject = stream;
    }
    onStream?.(stream);
  }, [onStream, stream]);

  return (
    <div className="online-camera online-camera--debug">
      <div className="online-camera__toolbar">
        <button type="button" className="online-simple__secondary" onClick={() => onCameraEnabledChange?.(!on)}>
          {on ? <CameraOff size={16} /> : <Camera size={16} />}
          {on ? "关闭我的摄像头" : "开启我的摄像头"}
        </button>
      </div>
      {error && <p className="online-simple__hint online-simple__hint--error">{error}</p>}
      {on && (
        <div className="online-camera__grid">
          <div className="online-camera__tile">
            <video ref={videoRef} autoPlay playsInline muted className="is-mirror" />
            <span>我的画面</span>
          </div>
        </div>
      )}
      <p className="online-simple__micro-hint">
        摄像头是可选项；不开启也可以继续辩论。进入辩论室后仍可随时开启或关闭。
      </p>
    </div>
  );
}

/** 辩论室联机摄像头：本地 + 远程 */
export default function OnlineCameraPanel({ camera }) {
  const { localStream, localOn, toggleLocal, remoteStreams, error, syncPeers, participantIds } = camera;

  useEffect(() => {
    syncPeers?.(participantIds);
  }, [participantIds, syncPeers]);

  return (
    <div className="online-camera">
      <div className="online-camera__toolbar">
        <button type="button" className="online-simple__secondary compact" onClick={toggleLocal}>
          {localOn ? <CameraOff size={16} /> : <Camera size={16} />}
          {localOn ? "关闭我的摄像头" : "开启我的摄像头"}
        </button>
      </div>
      {error && <p className="online-simple__micro-hint">{error}</p>}
      <div className="online-camera__grid">
        {localOn && <VideoTile stream={localStream} label="我的画面" muted mirror />}
        {remoteStreams.map((item) => (
          <VideoTile key={item.id} stream={item.stream} label="对方辩手" />
        ))}
        {localOn && remoteStreams.length === 0 && (
          <p className="online-simple__micro-hint">等待对方开启摄像头…</p>
        )}
      </div>
    </div>
  );
}
