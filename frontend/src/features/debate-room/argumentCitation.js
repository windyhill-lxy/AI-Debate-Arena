export function citationTokenForArgumentId(id = "") {
  const compact = String(id).trim().replace(/-/g, "");
  return compact ? `[${compact}]` : "";
}

export async function copyTextToClipboard(text) {
  if (!text) return "";
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return text;
  }
  if (typeof document !== "undefined") {
    const el = document.createElement("textarea");
    el.value = text;
    el.setAttribute("readonly", "");
    el.style.position = "fixed";
    el.style.left = "-9999px";
    document.body.appendChild(el);
    el.select();
    document.execCommand("copy");
    document.body.removeChild(el);
  }
  return text;
}
