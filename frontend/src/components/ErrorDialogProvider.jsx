import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import AppErrorBoundary from "./AppErrorBoundary.jsx";

const ErrorDialogContext = createContext(null);

function normalizeError(input, fallback = "发生错误，请稍后重试") {
  if (!input) return { message: fallback };
  if (typeof input === "string") return { message: input };
  return {
    title: input.title || "操作失败",
    message: input.message || input.detail || fallback,
    details: input.details || input.stack || "",
    source: input.source || "",
    code: input.code || input.status || "",
    requestId: input.requestId || input.request_id || "",
  };
}

export function ErrorDialogProvider({ children }) {
  const [items, setItems] = useState([]);
  const recentRef = useRef(new Map());

  const reportError = useCallback((input, options = {}) => {
    const error = normalizeError(input, options.fallback);
    const key = options.dedupeKey || `${error.source}:${error.code}:${error.message}`;
    const now = Date.now();
    const throttleMs = options.throttleMs ?? 3000;
    const last = recentRef.current.get(key) || 0;
    if (now - last < throttleMs) return;
    recentRef.current.set(key, now);
    setItems((current) => [
      ...current,
      { ...error, id: `${now}-${Math.random().toString(16).slice(2)}` },
    ]);
  }, []);

  const dismiss = useCallback((id) => {
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  useEffect(() => {
    const onError = (event) => {
      reportError(
        {
          title: "页面运行错误",
          message: event.message || "页面脚本执行失败",
          details: event.error?.stack || "",
          source: "window.onerror",
        },
        { dedupeKey: `window:${event.message}` },
      );
    };
    const onUnhandledRejection = (event) => {
      const reason = event.reason;
      reportError(
        {
          title: "异步任务失败",
          message: reason?.message || String(reason || "未处理的异步错误"),
          details: reason?.stack || "",
          source: "unhandledrejection",
        },
        { dedupeKey: `promise:${reason?.message || reason}` },
      );
    };
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onUnhandledRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onUnhandledRejection);
    };
  }, [reportError]);

  const value = useMemo(() => ({ reportError }), [reportError]);
  const active = items[0];

  return (
    <ErrorDialogContext.Provider value={value}>
      <AppErrorBoundary reportError={reportError}>{children}</AppErrorBoundary>
      {active && (
        <div className="error-dialog-backdrop" role="presentation">
          <section className="error-dialog" role="alertdialog" aria-modal="true" aria-label={active.title || "错误提示"}>
            <header>
              <strong>{active.title || "操作失败"}</strong>
              <button type="button" onClick={() => dismiss(active.id)} aria-label="关闭错误提示">
                x
              </button>
            </header>
            <p>{active.message}</p>
            {(active.code || active.requestId || active.source) && (
              <small>
                {active.code ? `代码：${active.code} ` : ""}
                {active.requestId ? `请求ID：${active.requestId} ` : ""}
                {active.source ? `来源：${active.source}` : ""}
              </small>
            )}
            {active.details && (
              <pre>{typeof active.details === "string" ? active.details : JSON.stringify(active.details, null, 2)}</pre>
            )}
          </section>
        </div>
      )}
    </ErrorDialogContext.Provider>
  );
}

export function useErrorDialog() {
  return useContext(ErrorDialogContext) || { reportError: () => undefined };
}
