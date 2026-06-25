import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Camera, Minimize2, X } from "lucide-react";
import OnlineCameraPanel from "./OnlineCameraPanel.jsx";

const POS_KEY = "online-camera-pos";
const VISIBLE_KEY = "online-camera-visible";

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

export default function FloatingOnlineCamera({ camera, enabled = true }) {
  const [visible, setVisible] = useState(() => {
    if (typeof window === "undefined") return true;
    return window.localStorage.getItem(VISIBLE_KEY) !== "0";
  });
  const [collapsed, setCollapsed] = useState(false);
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
    return { width: 300, height: 280 };
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

  const hidePanel = useCallback((event) => {
    event.preventDefault();
    event.stopPropagation();
    setVisible(false);
  }, []);

  if (!enabled) return null;

  const { width, height } = floatSize();

  const content = !visible ? (
    <button
      ref={boxRef}
      type="button"
      className="floating-online-camera__fab"
      style={{ left: pos.x, top: pos.y }}
      onPointerDown={onDragStart}
      onPointerMove={onDragMove}
      onPointerUp={onReopenPointerUp}
      onPointerCancel={onDragEnd}
      title="显示联机摄像头（可拖动）"
      aria-label="显示联机摄像头"
    >
      <Camera size={18} />
    </button>
  ) : (
    <div
      ref={boxRef}
      className={`floating-online-camera ${collapsed ? "is-collapsed" : ""}`}
      style={{ left: pos.x, top: pos.y, width, height }}
    >
      <header
        className="floating-online-camera__head"
        onPointerDown={onDragStart}
        onPointerMove={onDragMove}
        onPointerUp={onDragEnd}
        onPointerCancel={onDragEnd}
      >
        <span className="floating-online-camera__drag-handle">
          <Camera size={14} /> 联机摄像头
        </span>
        <div
          className="floating-online-camera__actions"
          onPointerDown={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            onClick={() => setCollapsed((value) => !value)}
            title={collapsed ? "展开" : "收起"}
            aria-label={collapsed ? "展开" : "收起"}
          >
            <Minimize2 size={14} />
          </button>
          <button type="button" onClick={hidePanel} title="隐藏" aria-label="隐藏摄像头">
            <X size={14} />
          </button>
        </div>
      </header>
      {!collapsed && <OnlineCameraPanel camera={camera} />}
    </div>
  );

  if (typeof document === "undefined") return content;
  return createPortal(content, document.body);
}
