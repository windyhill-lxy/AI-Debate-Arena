export function normalizeMarkdownText(content = "") {
  return String(content)
    .replace(/[—–]/g, "，")
    .replace(/\*\*([^\n*]{1,30})\*\*/g, "$1")
    .replace(/__([^\n_]{1,30})__/g, "$1")
    .replace(/[ \t]+\n/g, "\n")
    .trim();
}
