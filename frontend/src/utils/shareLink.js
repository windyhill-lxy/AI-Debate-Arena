/** 只读回放分享链接（/share/:id，无写权限入口） */
export function buildShareUrl(debateId, origin) {
  const base = (origin || (typeof window !== "undefined" ? window.location.origin : "")).replace(/\/$/, "");
  return `${base}/share/${debateId}`;
}

export function buildJoinUrl(debateId, origin) {
  const base = (origin || (typeof window !== "undefined" ? window.location.origin : "")).replace(/\/$/, "");
  return `${base}/join/${debateId}`;
}

async function copyUrl(url) {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(url);
    return url;
  }
  if (typeof document !== "undefined") {
    const el = document.createElement("textarea");
    el.value = url;
    el.setAttribute("readonly", "");
    el.style.position = "fixed";
    el.style.left = "-9999px";
    document.body.appendChild(el);
    el.select();
    document.execCommand("copy");
    document.body.removeChild(el);
    return url;
  }
  return url;
}

export async function copyShareUrl(debateId, origin) {
  return copyUrl(buildShareUrl(debateId, origin));
}

export async function copyJoinUrl(debateId, origin) {
  return copyUrl(buildJoinUrl(debateId, origin));
}
