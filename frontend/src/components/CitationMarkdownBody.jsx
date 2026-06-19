import ReactMarkdown from "react-markdown";
import { renderTextWithCitations } from "../utils/citationMap.jsx";
import { normalizeMarkdownText } from "../utils/markdownText.js";

function withCitations(children, sourceMap, onCitationSelect) {
  if (!onCitationSelect || !sourceMap?.size) return children;
  if (typeof children === "string") {
    return renderTextWithCitations(children, sourceMap, onCitationSelect);
  }
  if (Array.isArray(children)) {
    return children.map((child, i) => (
      <span key={i}>{withCitations(child, sourceMap, onCitationSelect)}</span>
    ));
  }
  return children;
}

const CITATION_COMPONENTS = (sourceMap, onCitationSelect) => ({
  p: ({ children }) => <p>{withCitations(children, sourceMap, onCitationSelect)}</p>,
  li: ({ children }) => <li>{withCitations(children, sourceMap, onCitationSelect)}</li>,
  strong: ({ children }) => <strong>{withCitations(children, sourceMap, onCitationSelect)}</strong>,
  em: ({ children }) => <em>{withCitations(children, sourceMap, onCitationSelect)}</em>,
});

export default function CitationMarkdownBody({ content, streaming, sourceMap, onCitationSelect }) {
  if (!content) return null;
  const normalized = normalizeMarkdownText(content);
  const components =
    sourceMap?.size && onCitationSelect
      ? CITATION_COMPONENTS(sourceMap, onCitationSelect)
      : undefined;
  return (
    <div className={`md-body ${streaming ? "streaming" : ""}`}>
      <ReactMarkdown components={components}>{normalized}</ReactMarkdown>
      {streaming && <span className="stream-cursor" />}
    </div>
  );
}
