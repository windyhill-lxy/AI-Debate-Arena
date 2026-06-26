import { useEffect, useRef, useState } from "react";
import { API_BASE } from "../utils/apiBase.js";

const STATUS_REFRESH_MS = 2500;
const PREVIEW_REFRESH_MS = 1200;

function normalizeMonitorError(message) {
  if (!message) return "";
  const text = String(message);
  if (text.includes("Traceback") || text.includes('File "')) {
    return "识别进程异常，请重新开启后再试。";
  }
  const firstLine = text.split(/\r?\n/).find((line) => line.trim()) || text;
  return firstLine.length > 90 ? `${firstLine.slice(0, 90)}...` : firstLine;
}

function percent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

/**
 * 自信度识别预览只消费后端摄像头帧，避免浏览器和后端同时抢占摄像头。
 */
export default function ConfidenceCameraPreview({ enabled = true, className = "", compact = false }) {
  const imgRef = useRef(null);
  const [monitorStatus, setMonitorStatus] = useState(null);
  const [statusReady, setStatusReady] = useState(false);
  const [inlineError, setInlineError] = useState("");
  const running = Boolean(monitorStatus?.running);
  const useBackendPreview = enabled && statusReady && running && !monitorStatus?.last_error;

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
          setInlineError("");
        }
      } catch (error) {
        if (!stopped) {
          setInlineError(error?.message || "无法连接自信度识别服务");
          setStatusReady(true);
        }
      }
    }

    poll();
    const timer = setInterval(poll, STATUS_REFRESH_MS);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [enabled]);

  useEffect(() => {
    if (!useBackendPreview) return undefined;
    let stopped = false;

    async function refreshFrame() {
      if (document.hidden) return;
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
        /* preview may not be ready yet */
      }
    }

    refreshFrame();
    const timer = setInterval(refreshFrame, PREVIEW_REFRESH_MS);
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
  const summary = monitorStatus?.visual_summary || sample?.visual_summary || {};
  const faceDetected = Boolean(sample?.has_face);
  const confidence = Number(sample?.confidence || 0);
  const level = confidence >= 0.8 ? "A 优秀" : confidence >= 0.65 ? "B 良好" : confidence >= 0.45 ? "C 中等" : "D 待提升";
  const displayError = normalizeMonitorError(monitorStatus?.last_error || inlineError);
  const overlayText = displayError
    ? displayError
    : running
      ? summary?.summary || "识别进行中"
      : "识别未启动";

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
        <img
          ref={imgRef}
          className="confidence-camera__backend-frame"
          alt="后端实时画面"
          style={{ display: useBackendPreview ? "block" : "none" }}
        />
        {!useBackendPreview && (
          <div className="confidence-camera__placeholder">
            {displayError ? "摄像头不可用" : "等待后端摄像头画面"}
          </div>
        )}
        <p className={`confidence-camera__overlay ${displayError ? "error" : faceDetected ? "ok" : ""}`}>
          {overlayText}
        </p>
      </div>
      {!compact && (
        <div className="confidence-camera__scores">
          <span>自信度 {level}</span>
          <span>眼神 {percent(sample?.eye)}</span>
          <span>手势 {percent(sample?.gesture)}</span>
          <span>姿态 {percent(sample?.posture)}</span>
          <span>强度 {percent(sample?.arousal)}</span>
          <span>稳定 {percent(sample?.stability)}</span>
          {summary?.delivery && <span>状态 {summary.delivery}</span>}
          {summary?.emotion && <span>情绪 {summary.emotion}</span>}
        </div>
      )}
    </section>
  );
}
