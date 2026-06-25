import { useCallback, useEffect, useRef, useState } from "react";

/**
 * 垂直可拖拽分割面板：上方与下方区域均可独立滚动。
 * 双击拖拽条可重置到默认比例。
 */
export default function ResizableSplitPane({
  top,
  bottom,
  defaultRatio = 0.62,
  minTopPx = 80,
  minBottomPx = 80,
  className = "",
}) {
  const rootRef = useRef(null);
  const [ratio, setRatio] = useState(defaultRatio);
  const dragging = useRef(false);

  const onPointerDown = useCallback((event) => {
    dragging.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
  }, []);

  const onPointerMove = useCallback((event) => {
    if (!dragging.current || !rootRef.current) return;
    const rect = rootRef.current.getBoundingClientRect();
    const next = (event.clientY - rect.top) / rect.height;
    const minTop = minTopPx / rect.height;
    const minBottom = minBottomPx / rect.height;
    setRatio(Math.min(1 - minBottom, Math.max(minTop, next)));
  }, [minBottomPx, minTopPx]);

  const onPointerUp = useCallback((event) => {
    dragging.current = false;
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      /* ignore */
    }
  }, []);

  const onDoubleClick = useCallback(() => {
    setRatio(defaultRatio);
  }, [defaultRatio]);

  useEffect(() => {
    const onResize = () => {
      if (!rootRef.current) return;
      setRatio((prev) => prev);
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return (
    <div ref={rootRef} className={`resizable-split ${className}`.trim()}>
      <div className="resizable-split__top" style={{ flexBasis: `${ratio * 100}%` }}>
        {top}
      </div>
      <div
        className="resizable-split__handle"
        role="separator"
        aria-orientation="horizontal"
        aria-label="调整上下区域大小（双击重置）"
        title="拖动调整大小；双击重置"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onDoubleClick={onDoubleClick}
        style={{ minHeight: 8, cursor: "row-resize" }}
      />
      <div className="resizable-split__bottom" style={{ flexBasis: `${(1 - ratio) * 100}%` }}>
        {bottom}
      </div>
    </div>
  );
}
