import { lazy, Suspense, useState } from "react";
import { createPortal } from "react-dom";
import { Maximize2, Workflow } from "lucide-react";

const DebateFlowViewerModal = lazy(() => import("./DebateFlowViewerModal.jsx"));

export default function DebateFlowViewer({ variant = "card" }) {
  const [open, setOpen] = useState(false);
  const isDock = variant === "dock";

  return (
    <>
      {isDock ? (
        <button type="button" className="dock-btn flow-viewer-dock-button" title="项目流程图" onClick={() => setOpen(true)}>
          <Workflow size={18} />
          <span>流程图</span>
        </button>
      ) : (
        <section className="panel flow-viewer-card">
          <div>
            <h3>项目流程图</h3>
            <p>按 docs/ai-debate-project-flow.mmd 生成 SVG。支持滚轮缩放、拖动和节点悬浮详情。</p>
          </div>
          <button type="button" className="flow-viewer-card__button" onClick={() => setOpen(true)}>
            <Maximize2 size={15} /> 查看流程图
          </button>
        </section>
      )}
      {open &&
        createPortal(
          <Suspense
            fallback={
              <div className="flow-viewer-modal" role="dialog" aria-modal="true" aria-label="项目流程图加载中">
                <div className="flow-viewer-modal__bar">
                  <div>
                    <strong>项目流程图</strong>
                    <span>正在生成 SVG 流程图…</span>
                  </div>
                </div>
                <div className="flow-viewer-modal__loading">加载流程图中…</div>
              </div>
            }
          >
            <DebateFlowViewerModal onClose={() => setOpen(false)} />
          </Suspense>,
          document.body,
        )}
    </>
  );
}
