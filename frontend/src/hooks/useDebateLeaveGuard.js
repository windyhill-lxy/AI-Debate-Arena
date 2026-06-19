import { useCallback, useEffect } from "react";

const DEFAULT_MESSAGE = "确定要离开辩论室吗？进行中的辩论/联机进度可能中断。";

function isDesktopApp() {
  return typeof window !== "undefined" && Boolean(window.debateDesktop?.isDesktop);
}

export function useDebateLeaveGuard(enabled, message = DEFAULT_MESSAGE) {
  useEffect(() => {
    if (!enabled || isDesktopApp()) return undefined;
    const onBeforeUnload = (event) => {
      event.preventDefault();
      event.returnValue = message;
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [enabled, message]);

  return useCallback(() => {
    if (!enabled) return true;
    return window.confirm(message);
  }, [enabled, message]);
}
