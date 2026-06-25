import { isTunnelHost } from "./apiBase.js";

export function isLoopbackHost(host) {
  if (!host) return true;
  const h = host.toLowerCase();
  return h === "localhost" || h === "127.0.0.1" || h === "[::1]";
}

export function isHostDesktop() {
  if (typeof window === "undefined") return false;
  if (window.debateDesktop?.isDesktop) return true;
  return isLoopbackHost(window.location.hostname);
}

export function isGuestWeb(pathname = "") {
  if (typeof window === "undefined") return false;
  const path = pathname || window.location.pathname || "";
  if (path.startsWith("/join/")) return true;
  if (isTunnelHost(window.location.hostname) && !path.startsWith("/room/")) return true;
  return false;
}

export function isGuestRoute(pathname = "") {
  const path = pathname || (typeof window !== "undefined" ? window.location.pathname : "");
  return path.startsWith("/join/");
}

export function shouldHideBrowserNav(pathname = "") {
  const path = pathname || (typeof window !== "undefined" ? window.location.pathname : "");
  if (path.startsWith("/room/")) return true;
  return isGuestRoute(path);
}

export function isCompactViewport() {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(max-width: 900px)").matches;
}

export function isMobilePortrait() {
  return isCompactViewport();
}

export function useGuestShellClass() {
  if (typeof document === "undefined") return "";
  const classes = ["guest-shell"];
  if (isMobilePortrait()) classes.push("guest-shell--mobile");
  return classes.join(" ");
}
