import ReactMarkdown from "react-markdown";
import { normalizeMarkdownText } from "../utils/markdownText.js";

export default function MarkdownBody({ content, streaming }) {
  if (!content) return null;
  const normalized = normalizeMarkdownText(content);
  return (
    <div className={`md-body ${streaming ? "streaming" : ""}`}>
      <ReactMarkdown>{normalized}</ReactMarkdown>
      {streaming && <span className="stream-cursor" />}
    </div>
  );
}
