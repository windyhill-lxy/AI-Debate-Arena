import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const DEFAULT_ITEM_HEIGHT = 132;

/**
 * 轻量虚拟列表：固定估算行高，适合长辩论消息流。
 */
export default function VirtualMessageList({ items, renderItem, estimateHeight = DEFAULT_ITEM_HEIGHT, className = "" }) {
  const containerRef = useRef(null);
  const [viewport, setViewport] = useState({ height: 480, scrollTop: 0 });

  const onScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    setViewport({ height: el.clientHeight, scrollTop: el.scrollTop });
  }, []);

  useEffect(() => {
    onScroll();
    const el = containerRef.current;
    if (!el) return undefined;
    const observer = new ResizeObserver(onScroll);
    observer.observe(el);
    return () => observer.disconnect();
  }, [onScroll, items.length]);

  const { start, end, totalHeight, offsetY } = useMemo(() => {
    const count = items.length;
    const total = count * estimateHeight;
    const startIndex = Math.max(0, Math.floor(viewport.scrollTop / estimateHeight) - 3);
    const visibleCount = Math.ceil(viewport.height / estimateHeight) + 6;
    const endIndex = Math.min(count, startIndex + visibleCount);
    return {
      start: startIndex,
      end: endIndex,
      totalHeight: total,
      offsetY: startIndex * estimateHeight,
    };
  }, [items.length, estimateHeight, viewport.height, viewport.scrollTop]);

  const slice = items.slice(start, end);

  return (
    <div ref={containerRef} className={`virtual-list ${className}`} onScroll={onScroll}>
      <div className="virtual-list__spacer" style={{ height: totalHeight }}>
        <div className="virtual-list__window" style={{ transform: `translateY(${offsetY}px)` }}>
          {slice.map((item, index) => renderItem(item, start + index))}
        </div>
      </div>
    </div>
  );
}
