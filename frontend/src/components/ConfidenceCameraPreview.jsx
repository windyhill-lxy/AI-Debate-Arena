import { useEffect, useRef, useState } from "react";
import { API_BASE } from "../utils/apiBase.js";

const STATUS_REFRESH_MS = 3500;
const PREVIEW_REFRESH_MS = 100;

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

function scoreText(value) {
  const n = Number(value || 0);
  if (!n) return "+0.00";
  return `${n > 0 ? "+" : ""}${n.toFixed(2)}`;
}

function gestureText(counts = {}) {
  const names = {
    shrug: "摊手",
    pointing: "指人",
    chop: "切分手势",
    fast_wave: "快速挥手",
    open_palm: "开放手势",
    raised_hand: "举手",
  };
  const rows = Object.entries(counts || {}).filter(([, count]) => Number(count) > 0);
  if (!rows.length) return "未检测到明显动作";
  return rows.map(([key, count]) => `${names[key] || key}x${count}`).join("、");
}

/**
 * 自信度识别预览只消费后端摄像头帧，避免浏览器和后端同时抢占摄像头。
 */
export default function ConfidenceCameraPreview({
  enabled = true,
  className = "",
  compact = false,
  onStart = null,
  onStop = null,
  busy = false,
  externalStatus = null,
}) {
  const imgRef = useRef(null);
  const [monitorStatus, setMonitorStatus] = useState(null);
  const [statusReady, setStatusReady] = useState(false);
  const [inlineError, setInlineError] = useState("");
  const running = Boolean(monitorStatus?.running);
  const useBackendPreview = enabled && statusReady && running && !monitorStatus?.last_error;

  useEffect(() => {
    if (!externalStatus) return;
    setMonitorStatus(externalStatus);
    setStatusReady(true);
  }, [externalStatus]);

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
  const dimensions = summary?.dimensions || {};
  const faceDetected = Boolean(sample?.has_face);
  const confidence = Number(sample?.confidence || 0);
  const level = confidence >= 0.8 ? "A 优秀" : confidence >= 0.65 ? "B 良好" : confidence >= 0.45 ? "C 中等" : "D 待提升";
  const reliabilityLabel = {
    high: "高",
    medium: "中",
    low: "低",
    none: "无",
  }[monitorStatus?.confidence_reliability || summary?.reliability] || "低";
  const expression = `${summary?.confidence_label || "未知"} / ${summary?.emotion || sample?.emotion || "未知"}`;
  const motion = gestureText(summary?.gesture_counts);
  const advice = monitorStatus?.fixed_realtime_hint || summary?.score_reason || monitorStatus?.confidence_reliability_hint || "";
  const scoreEstimate = scoreText(summary?.score_delta);
  const sampleCount = Number(summary?.sample_count || 0);
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
          <div className="confidence-camera__header-actions">
            <span className={`confidence-camera__badge ${running ? "on" : "off"}`}>
              {busy ? "启动中" : running ? "分析中" : "未启动"}
            </span>
            {onStart && !running && (
              <button type="button" className="confidence-camera__action" onClick={onStart} disabled={busy}>
                启动摄像头
              </button>
            )}
            {onStart && running && (
              <button type="button" className="confidence-camera__action" onClick={onStart} disabled={busy}>
                重启
              </button>
            )}
            {onStop && running && (
              <button type="button" className="confidence-camera__action muted" onClick={onStop} disabled={busy}>
                停止
              </button>
            )}
          </div>
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
        <div className="confidence-camera__readout">
          <div className="confidence-camera__realtime-grid" aria-label="摄像头实时多维数据">
            <span>
              <strong>神态</strong>
              {expression}
            </span>
            <span>
              <strong>动作</strong>
              {motion}
            </span>
            <span>
              <strong>姿态</strong>
              {percent(dimensions.posture ?? sample?.posture)}
            </span>
            <span>
              <strong>眼神</strong>
              {percent(dimensions.eye ?? sample?.eye)}
            </span>
            <span>
              <strong>强度</strong>
              {percent(dimensions.arousal ?? sample?.arousal)}
            </span>
            <span>
              <strong>稳定</strong>
              {percent(dimensions.stability ?? sample?.stability)}
            </span>
            <span>
              <strong>可信度</strong>
              {reliabilityLabel} · {sampleCount} 帧
            </span>
            <span>
              <strong>计分预估</strong>
              {scoreEstimate}
            </span>
          </div>
          <p className="confidence-camera__advice">
            {advice || "正在累积神态、动作、姿态和情绪数据。发言结束后计入本轮分数。"}
          </p>
          <p className="confidence-camera__score-note">发言结束后计入本轮分数，并影响对手下一轮策略提示。</p>
          <div className="confidence-camera__scores">
            <span>自信度 {level}</span>
            <span>综合 {percent(sample?.confidence)}</span>
            {summary?.delivery && <span>状态 {summary.delivery}</span>}
          </div>
        </div>
      )}
    </section>
  );
}
