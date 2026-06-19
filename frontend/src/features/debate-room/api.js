import { API_BASE } from "./constants.js";

const ERROR_HINTS = {
  "当前为队内讨论环节，无需用户发言": "队内讨论中，请等待轮到您在队内窗口发言",
  "当前为队内准备环节，无需用户发言": "准备环节中，请等待轮到您的发言回合",
  "当前环节不需要用户发言": "当前环节不需要您发言，请等待",
  "现在不是你的发言回合": "现在不是您的发言回合，请等待",
  "当前环节不是双方辩手发言": "当前环节不是辩手公开发言环节",
};

export function parseApiError(text) {
  if (!text) return "请求失败，请稍后重试";
  const trimmed = String(text).trim();
  try {
    const data = JSON.parse(trimmed);
    const detail = data?.detail;
    if (typeof detail === "string") {
      return ERROR_HINTS[detail] || detail;
    }
    if (Array.isArray(detail)) {
      return detail.map((item) => item?.msg || String(item)).join("；");
    }
  } catch {
    /* not JSON */
  }
  if (trimmed.length > 200) return `${trimmed.slice(0, 200)}…`;
  return trimmed;
}

export async function debateRequest(path, options = {}) {
  const { headers: extraHeaders, ...rest } = options;
  const response = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: { "Content-Type": "application/json", ...extraHeaders },
  });
  if (!response.ok) throw new Error(parseApiError(await response.text()));
  return response.json();
}
