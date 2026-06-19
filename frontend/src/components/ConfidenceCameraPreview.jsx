import { useEffect, useRef, useState } from "react";
import { API_BASE } from "../utils/apiBase.js";

function normalizeMonitorError(message) {
  if (!message) return "";
  const text = String(message);
  if (text.includes("Traceback") || text.includes("File \"")) {
    return "训练进程异常，请重启训练后重试。";
  }
  const firstLine = text.split(/\r?\n/).find((line) => line.trim()) || text;
  return firstLine.length > 90 ? `${firstLine.slice(0, 90)}...` : firstLine;
}

/**
 * 自信度摄像头：未训练时用浏览器预览；训练开启后仅用后端帧，避免双摄像头争用闪烁。
 */
export default function ConfidenceCameraPreview({ enabled = true, className = "", compact = false }) {
  const videoRef = useRef(null);
  const imgRef = useRef(null);
  const streamRef = useRef(null);
  const [cameraError, setCameraError] = useState("");
  const [monitorStatus, setMonitorStatus] = useState(null);
  const [statusReady, setStatusReady] = useState(false);
  const running = Boolean(monitorStatus?.running);
  const useBackendPreview = enabled && statusReady && running && !monitorStatus?.last_error;

  useEffect(() => {
    if (!enabled || useBackendPreview) {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      return undefined;
    }
    let stopped = false;

    async function startCamera() {
      if (!navigator.mediaDevices?.getUserMedia) {
        const insecureHint =
          window.location.protocol !== "https:" &&
          !["localhost", "127.0.0.1"].includes(window.location.hostname);
        setCameraError(insecureHint ? "摄像头仅支持 HTTPS 或 localhost 访问" : "浏览器不支持摄像头");
        return;
      }
      try {
        let stream;
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
            audio: false,
          });
        } catch {
          stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        }
        if (stopped) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          try {
            await videoRef.current.play();
          } catch {
            /* autoplay policy */
          }
        }
        setCameraError("");
      } catch (err) {
        const message = err?.message || "无法打开摄像头，请检查浏览器权限";
        if (/video source|not found|notreadable|in use/i.test(message)) {
          setCameraError("摄像头被占用：请关闭其他占用页面，或仅使用后端自信度训练。");
        } else {
          setCameraError(message);
        }
      }
    }

    startCamera();
    return () => {
      stopped = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, [enabled, useBackendPreview]);

  useEffect(() => {
    if (!enabled) return undefined;
    let stopped = false;

    async function poll() {
      try {
        const res = await fetch(`${API_BASE}/api/confidence-monitor/status`);
        if (!res.ok) return;
        const data = await res.json();
        if (!stopped) {
          setMonitorStatus(data);
          setStatusReady(true);
        }
      } catch {
        /* 后端未启动 */
      }
    }

    poll();
    const timer = setInterval(poll, 1200);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [enabled]);

  useEffect(() => {
    if (!useBackendPreview) return undefined;
    let stopped = false;

    async function refreshFrame() {
      try {
        const res = await fetch(`${API_BASE}/api/confidence-monitor/preview.jpg`, { cache: "no-store" });
        if (!res.ok || stopped || !imgRef.current) return;
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const img = imgRef.current;
        const prev = img.dataset.blobUrl;
        img.src = url;
        img.dataset.blobUrl = url;
        if (prev) URL.revokeObjectURL(prev);
      } catch {
        /* ignore */
      }
    }

    refreshFrame();
    const timer = setInterval(refreshFrame, 450);
    return () => {
      stopped = true;
      clearInterval(timer);
      if (imgRef.current?.dataset.blobUrl) {
        URL.revokeObjectURL(imgRef.current.dataset.blobUrl);
      }
    };
  }, [useBackendPreview]);

  if (!enabled) return null;

  const sample = monitorStatus?.latest_sample;
  const faceDetected = Boolean(sample?.has_face);
  const confidence = Number(sample?.confidence || 0);
  const level = confidence >= 0.8 ? "A 优秀" : confidence >= 0.65 ? "B 良好" : confidence >= 0.45 ? "C 中等" : "D 待提升";
  const displayError = normalizeMonitorError(monitorStatus?.last_error);

  return (
    <section className={`confidence-camera ${className}`.trim()}>
      {!compact && (
        <div className="confidence-camera__header">
          <span>自信度摄像头</span>
          <span className={`confidence-camera__badge ${running ? "on" : "off"}`}>
            {running ? "分析中" : "未启动"}
          </span>
        </div>
      )}
      <div className="confidence-camera__viewport">
        <video
          ref={videoRef}
          className="confidence-camera__video"
          autoPlay
          playsInline
          muted
          style={{ display: useBackendPreview ? "none" : "block" }}
        />
        <img
          ref={imgRef}
          className="confidence-camera__backend-frame"
          alt="后端实时画面"
          style={{ display: useBackendPreview ? "block" : "none" }}
        />
        {cameraError && !useBackendPreview && <p className="confidence-camera__overlay error">{cameraError}</p>}
        {!cameraError && (
          <p className={`confidence-camera__overlay ${faceDetected ? "ok" : ""}`}>
            {displayError
              ? displayError
              : running
                ? "训练进行中"
                : faceDetected
                  ? "人脸/姿态: 已检测"
                  : "请在首页开启自信度训练"}
          </p>
        )}
      </div>
      {!compact && sample && (
        <div className="confidence-camera__scores">
          <span>自信度 {level}</span>
          <span>眼神 {Number(sample.eye || 0).toFixed(2)}</span>
          <span>手势 {Number(sample.gesture || 0).toFixed(2)}</span>
          <span>姿态 {Number(sample.posture || 0).toFixed(2)}</span>
        </div>
      )}
    </section>
  );
}
