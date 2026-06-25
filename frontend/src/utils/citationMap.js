/** 从辩论状态聚合资料编号 -> 摘要，供主舞台引用点击使用 */

const CITATION_RE = /\[([a-z]+-[\w-]+)\]/gi;

export function collectCitationSources(debate, extraSources = []) {
  const map = new Map();
  const add = (source) => {
    if (!source?.id) return;
    map.set(source.id, {
      id: source.id,
      title: source.title || source.id,
      excerpt: source.excerpt || "",
      reliability: source.reliability,
    });
  };
  for (const message of debate?.messages || []) {
    for (const s of message.sources || []) add(s);
  }
  for (const s of extraSources || []) add(s);
  return map;
}

export function findCitationIdsInText(text) {
  if (!text) return [];
  const ids = new Set();
  let match = CITATION_RE.exec(text);
  while (match) {
    ids.add(match[1]);
    match = CITATION_RE.exec(text);
  }
  CITATION_RE.lastIndex = 0;
  return [...ids];
}

export function renderTextWithCitations(text, sourceMap, onSelect) {
  if (!text || typeof text !== "string") return text;
  const parts = text.split(/(\[[a-z]+-[\w-]+\])/gi);
  return parts.map((part, index) => {
    const m = part.match(/^\[([a-z]+-[\w-]+)\]$/i);
    if (!m) return part;
    const id = m[1];
    const known = sourceMap.has(id);
    return (
      <button
        key={`cite-${index}-${id}`}
        type="button"
        className={`citation-ref ${known ? "citation-ref--known" : "citation-ref--unknown"}`}
        onClick={() => onSelect?.({ id, ...(sourceMap.get(id) || { title: id, excerpt: "未找到该资料编号，可能未入库或已被校验移除。" }) })}
        title={known ? "查看资料摘要" : "资料未入库"}
      >
        {part}
      </button>
    );
  });
}
