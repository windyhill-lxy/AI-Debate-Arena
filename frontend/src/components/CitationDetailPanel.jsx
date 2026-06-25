import { BookOpen, X } from "lucide-react";

export default function CitationDetailPanel({ citation, onClose }) {
  if (!citation) return null;
  return (
    <aside className="citation-detail-panel" aria-live="polite">
      <div className="citation-detail-panel__head">
        <BookOpen size={16} />
        <strong>资料</strong>
        <button type="button" className="citation-detail-panel__close" onClick={onClose} aria-label="关闭">
          <X size={16} />
        </button>
      </div>
      <h4>{citation.title || citation.id}</h4>
      <p className="citation-detail-panel__excerpt">{citation.excerpt || "（无摘要）"}</p>
      {citation.reliability != null && (
        <p className="citation-detail-panel__meta">可信度 {Math.round(citation.reliability * 100)}%</p>
      )}
    </aside>
  );
}
