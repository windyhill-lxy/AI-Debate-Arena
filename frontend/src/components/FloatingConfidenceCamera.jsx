import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, Maximize2, Minimize2, Power, X } from "lucide-react";
import ConfidenceCameraPreview from "./ConfidenceCameraPreview.jsx";
import { API_BASE } from "../utils/apiBase.js";

const POS_KEY = "confidence-camera-pos";
const VISIBLE_KEY = "confidence-camera-visible";

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

export default function FloatingConfidenceCamera({ enabledByMode = true }) {
  const [visible, setVisible] = useState(() => {
    if (typeof window === "undefined") return true;
    return window.localStorage.getItem(VISIBLE_KEY) !== "0";
  });
  const [collapsed, setCollapsed] = useState(false);
  const [monitorOn, setMonitorOn] = useState(true);
  const [pos, setPos] = useState({ x: 24, y: 88 });
  const boxRef = useRef(null);
  const dragging = useRef(false);
  const pointerIdRef = useRef(null);
  const offset = useRef({ x: 0, y: 0 });
  const didDrag = useRef(false);
  const dragStartPos = useRef({ x: 0, y: 0 });

  const floatSize = useCallback(() => {
    if (!visible) return { width: 44, height: 44 };
    if (collapsed) return { width: 160, height: 44 };
    return { width: 280, height: 260 };
  }, [visible, collapsed]);

  useEffect(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem(POS_KEY) || "null");
      if (saved?.x != null && saved?.y != null) setPos(saved);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(VISIBLE_KEY, visible ? "1" : "0");
  }, [visible]);

  useEffect(() => {
    if (!enabledByMode) return undefined;
    let stopped = false;

    async function syncStatus() {
      try {
        const res = await fetch(`${API_BASE}/api/confidence-monitor/status`);
        if (!res.ok || stopped) return;
        const data = await res.json();
        setMonitorOn(Boolean(data.running));
      } catch {
        /* backend offline */
      }
    }

    syncStatus();
    const timer = setInterval(syncStatus, 2500);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [enabledByMode]);

  const persistPos = useCallback((next) => {
    setPos(next);
    window.localStorage.setItem(POS_KEY, JSON.stringify(next));
  }, []);

  const onDragStart = useCallback((event) => {
    if (event.button !== 0) return;
    const target = event.currentTarget;
    const rect = boxRef.current?.getBoundingClientRect();
    if (!rect) return;
    dragging.current = true;
    didDrag.current = false;
    dragStartPos.current = { x: event.clientX, y: event.clientY };
    pointerIdRef.current = event.pointerId;
    offset.current = { x: event.clientX - rect.left, y: event.clientY - rect.top };
    target.setPointerCapture(event.pointerId);
  }, []);

  const onDragMove = useCallback(
    (event) => {
      if (!dragging.current || pointerIdRef.current !== event.pointerId) return;
      const dx = event.clientX - dragStartPos.current.x;
      const dy = event.clientY - dragStartPos.current.y;
      if (Math.hypot(dx, dy) > 4) didDrag.current = true;
      const { width, height } = floatSize();
      persistPos({
        x: clamp(event.clientX - offset.current.x, 8, window.innerWidth - width - 8),
        y: clamp(event.clientY - offset.current.y, 8, window.innerHeight - height - 8),
      });
    },
    [floatSize, persistPos],
  );

  const onDragEnd = useCallback((event) => {
    if (pointerIdRef.current !== event.pointerId) return;
    dragging.current = false;
    pointerIdRef.current = null;
    event.currentTarget.releasePointerCapture(event.pointerId);
  }, []);

  const onReopenPointerUp = useCallback(
    (event) => {
      onDragEnd(event);
      if (!didDrag.current) setVisible(true);
    },
    [onDragEnd],
  );

  const toggleMonitor = useCallback(async () => {
    const next = !monitorOn;
    try {
      const res = await fetch(`${API_BASE}/api/confidence-monitor/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: next, low_performance: true }),
      });
      if (!res.ok) return;
      setMonitorOn(next);
    } catch {
      /* ignore */
    }
  }, [monitorOn]);

  if (!enabledByMode) return null;

  if (!visible) {
    return (
      <button
        ref={boxRef}
        type="button"
        className="confidence-float-reopen"
        style={{ left: pos.x, top: pos.y }}
        onPointerDown={onDragStart}
        onPointerMove={onDragMove}
        onPointerUp={onReopenPointerUp}
        onPointerCancel={onDragEnd}
        title="显示自信度摄像头（可拖动）"
        aria-label="显示自信度摄像头"
      >
        <Camera size={18} />
      </button>
    );
  }

  return (
    <div
      ref={boxRef}
      className={`confidence-float ${collapsed ? "confidence-float--collapsed" : ""}`}
      style={{ left: pos.x, top: pos.y }}
    >
      <div className="confidence-float__chrome">
        <span
          className="confidence-float__title"
          onPointerDown={onDragStart}
          onPointerMove={onDragMove}
          onPointerUp={onDragEnd}
          onPointerCancel={onDragEnd}
        >
          <Camera size={14} /> 自信度摄像头
        </span>
        <div className="confidence-float__actions">
          <button
            type="button"
            className={monitorOn ? "on" : ""}
            onClick={toggleMonitor}
            title={monitorOn ? "关闭分析" : "开启分析"}
            aria-label={monitorOn ? "关闭分析" : "开启分析"}
          >
            <Power size={14} />
          </button>
          <button
            type="button"
            onClick={() => setCollapsed((v) => !v)}
            title={collapsed ? "展开" : "收起"}
            aria-label={collapsed ? "展开" : "收起"}
          >
            {collapsed ? <Maximize2 size={14} /> : <Minimize2 size={14} />}
          </button>
          <button type="button" onClick={() => setVisible(false)} title="隐藏" aria-label="隐藏摄像头">
            <X size={14} />
          </button>
        </div>
      </div>
      {!collapsed && <ConfidenceCameraPreview enabled={monitorOn} className="confidence-float__body" compact />}
    </div>
  );
}
