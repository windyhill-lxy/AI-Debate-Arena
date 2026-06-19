/** 从辩论状态聚合资料编号/标题 -> 摘要，供主舞台引用点击使用 */

const CITATION_RE = /(?:\[([^\]]+)\]|【([^】]+)】)/g;

const CITATION_ALIASES = {
  "kb-topic-x": "kb-topic",
  "topic-x": "kb-topic",
};

function resolveCitationKey(key, sourceMap) {
  const raw = (key || "").trim();
  if (!raw) return null;
  const aliased = CITATION_ALIASES[raw] || raw;
  if (sourceMap.has(aliased)) return sourceMap.get(aliased);
  if (sourceMap.has(raw)) return sourceMap.get(raw);
  for (const source of sourceMap.values()) {
    if (source.title === raw || source.title === aliased) return source;
  }
  return null;
}

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
    if (source.title) map.set(source.title, map.get(source.id));
  };
  for (const message of debate?.messages || []) {
    for (const s of message.sources || []) add(s);
  }
  for (const side of ["affirmative", "negative"]) {
    for (const item of debate?.argument_bank?.[side] || []) {
      add({
        id: item.id,
        title: item.title || item.id,
        excerpt: item.claim || "",
        reliability: 0.8,
      });
    }
  }
  for (const s of extraSources || []) add(s);
  return map;
}

export function findCitationIdsInText(text) {
  if (!text) return [];
  const ids = new Set();
  let match = CITATION_RE.exec(text);
  while (match) {
    ids.add(match[1] || match[2]);
    match = CITATION_RE.exec(text);
  }
  CITATION_RE.lastIndex = 0;
  return [...ids];
}

export function renderTextWithCitations(text, sourceMap, onSelect) {
  if (!text || typeof text !== "string") return text;
  const parts = text.split(/(\[[^\]]+\]|【[^】]+】)/g);
  return parts.map((part, index) => {
    const bracket = part.match(/^\[([^\]]+)\]$/);
    const book = part.match(/^【([^】]+)】$/);
    const key = bracket?.[1] || book?.[1];
    if (!key) return part;
    const source = resolveCitationKey(key, sourceMap);
    const label = source?.title || key;
    return (
      <button
        key={`cite-${index}-${key}`}
        type="button"
        className={`citation-ref ${source ? "citation-ref--known" : "citation-ref--unknown"}`}
        onClick={() =>
          onSelect?.(
            source || {
              id: key,
              title: key,
              excerpt: "未找到该资料，可能未入库或已被校验移除。",
            },
          )
        }
        title={source ? "查看资料摘要" : "资料未入库"}
      >
        【{label}】
      </button>
    );
  });
}
