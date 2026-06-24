export class ApiError extends Error {
  constructor(message, meta = {}) {
    super(message);
    this.name = "ApiError";
    this.status = meta.status;
    this.code = meta.code;
    this.requestId = meta.requestId;
    this.details = meta.details;
    this.raw = meta.raw;
  }
}

export function parseHttpErrorBody(text, response, hints = {}) {
  const fallback = "请求失败，请稍后重试";
  const requestId = response?.headers?.get?.("x-request-id") || "";
  const status = response?.status;
  const trimmed = String(text || "").trim();
  if (!trimmed) return new ApiError(fallback, { status, requestId });

  try {
    const data = JSON.parse(trimmed);
    if (data?.error) {
      return new ApiError(data.error.message || fallback, {
        status: data.error.status || status,
        code: data.error.code,
        requestId: data.error.request_id || requestId,
        details: data.error.details,
        raw: data,
      });
    }
    const detail = data?.detail;
    if (typeof detail === "string") {
      return new ApiError(hints[detail] || detail, { status, requestId, raw: data });
    }
    if (Array.isArray(detail)) {
      return new ApiError(detail.map((item) => item?.msg || String(item)).join("；"), {
        status,
        requestId,
        details: detail,
        raw: data,
      });
    }
  } catch {
    // Plain text error body.
  }

  const message = trimmed.length > 200 ? `${trimmed.slice(0, 200)}…` : trimmed;
  return new ApiError(message || fallback, { status, requestId, raw: trimmed });
}

export async function throwHttpError(response, hints = {}) {
  throw parseHttpErrorBody(await response.text(), response, hints);
}

export function errorDialogPayload(error, title, source, fallback = "操作失败") {
  return {
    title,
    message: error?.message || fallback,
    code: error?.code || error?.status,
    requestId: error?.requestId,
    details: error?.details,
    source,
  };
}
