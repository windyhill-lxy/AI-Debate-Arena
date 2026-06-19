import { useCallback, useEffect, useRef, useState } from "react";

const CAMERA_ERROR_HINTS = {
  NotFoundError: "未检测到摄像头设备，可继续辩论",
  DevicesNotFoundError: "未检测到摄像头设备，可继续辩论",
  NotAllowedError: "摄像头权限被拒绝，请在浏览器设置中允许",
  PermissionDeniedError: "摄像头权限被拒绝，请在浏览器设置中允许",
  NotReadableError: "摄像头被占用或硬件资源不足，请关闭其他摄像头应用后重试",
  AbortError: "摄像头启动被中断，请稍后重试",
};

function mapCameraError(err) {
  const name = err?.name || "";
  const message = String(err?.message || "");
  if (/0xC00D3704|MFT|硬件资源|hardware/i.test(message)) {
    return "摄像头硬件资源不足或被占用，可关闭其他视频应用后继续辩论";
  }
  return CAMERA_ERROR_HINTS[name] || message || "无法打开摄像头";
}

export function useLocalCamera({ enabled = true } = {}) {
  const [stream, setStream] = useState(null);
  const [error, setError] = useState("");
  const [hasDevice, setHasDevice] = useState(true);
  const streamRef = useRef(null);

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setStream(null);
  }, []);

  const startStream = useCallback(async () => {
    if (!enabled) return null;
    if (streamRef.current) return streamRef.current;
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("当前环境不支持摄像头");
      setHasDevice(false);
      return null;
    }
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const videoInputs = devices.filter((d) => d.kind === "videoinput");
      if (!videoInputs.length) {
        setHasDevice(false);
        setError("未检测到摄像头设备，可继续辩论");
        return null;
      }
      setHasDevice(true);
      let media = null;
      try {
        media = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 640 }, height: { ideal: 480 } },
          audio: false,
        });
      } catch (primaryErr) {
        try {
          media = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        } catch {
          throw primaryErr;
        }
      }
      streamRef.current = media;
      setStream(media);
      setError("");
      return media;
    } catch (err) {
      setError(mapCameraError(err));
      return null;
    }
  }, [enabled]);

  useEffect(() => {
    if (!enabled) {
      stopStream();
      return undefined;
    }
    startStream();
    return () => stopStream();
  }, [enabled, startStream, stopStream]);

  return { stream, error, hasDevice, startStream, stopStream };
}
